/*
 * SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Unlicense OR CC0-1.0
 */
/* i2c - Simple Example

   Simple I2C example that shows how to initialize I2C
   as well as reading and writing from and to registers for a sensor connected over I2C.

   The sensor used in this example is a MPU9250 inertial measurement unit.
*/
#include <stdio.h>
#include "esp_log.h"
#include "bmx280.h"
#include "driver/i2c_types.h"

static const char *TAG = "MAIN";

#define I2C_PORT_AUTO -1
#define BMX280_SDA_NUM GPIO_NUM_13
#define BMX280_SCL_NUM GPIO_NUM_14

i2c_master_bus_handle_t i2c_bus_init(gpio_num_t sda_io, gpio_num_t scl_io)
{
    i2c_master_bus_config_t cfg{};  // zero-initialize all fields
    cfg.i2c_port = I2C_PORT_AUTO;
    cfg.sda_io_num = sda_io;
    cfg.scl_io_num = scl_io;
    cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    cfg.glitch_ignore_cnt = 7;
    cfg.intr_priority = 0;
    cfg.trans_queue_depth = 0;
    cfg.flags.enable_internal_pullup = true;
    cfg.flags.allow_pd = false;

    i2c_master_bus_handle_t bus_handle = nullptr;
    ESP_ERROR_CHECK(i2c_new_master_bus(&cfg, &bus_handle));
    ESP_LOGI(TAG,"I2C master bus created");
    return bus_handle;
}

esp_err_t bmx280_dev_init(bmx280_t** bmx280,i2c_master_bus_handle_t bus_handle)
{
    *bmx280 = bmx280_create_master(bus_handle);
    if (!*bmx280) { 
        ESP_LOGE("test", "Could not create bmx280 driver.");
        return ESP_FAIL;
    }
    
    ESP_ERROR_CHECK(bmx280_init(*bmx280));
    bmx280_config_t bmx_cfg = BMX280_DEFAULT_CONFIG;
    ESP_ERROR_CHECK(bmx280_configure(*bmx280, &bmx_cfg));
    return ESP_OK;
}


extern "C" void app_main(void)
{

    ESP_LOGI(TAG, "I2C initialized successfully");
    i2c_master_bus_handle_t bus_handle = i2c_bus_init(BMX280_SDA_NUM, BMX280_SCL_NUM);
    bmx280_t* bmx280 = NULL;
    ESP_ERROR_CHECK(bmx280_dev_init(&bmx280,bus_handle));

        ESP_ERROR_CHECK(bmx280_setMode(bmx280, BMX280_MODE_CYCLE));
    float temp = 0, pres = 0, hum = 0;
    for(int i = 0; i < 30; i++)
    {
        do {
            vTaskDelay(pdMS_TO_TICKS(1));
        } while(bmx280_isSampling(bmx280));

        ESP_ERROR_CHECK(bmx280_readoutFloat(bmx280, &temp, &pres, &hum));
        ESP_LOGI(TAG, "temp = %f C, pres = %f Pa, hum = %f RH", temp, pres, hum);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }


    ESP_LOGI(TAG, "I2C de-initialized successfully");
    bmx280_close(bmx280);
    i2c_del_master_bus(bus_handle);
    ESP_LOGI(TAG, "Restarting now.");
    //esp_restart();
}
