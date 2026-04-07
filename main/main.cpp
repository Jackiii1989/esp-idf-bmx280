
/* i2c - Simple Example
*/
#include <stdio.h>
#include "esp_log.h"
#include "bmx280.h"
#include "driver/i2c_types.h"
#include "rpm_unit.h"

static const char *TAG = "MAIN";

#define I2C_PORT_AUTO -1
#define BMX280_SDA_NUM GPIO_NUM_12
//#define BMX280_SDA_NUM GPIO_NUM_13
#define BMX280_SCL_NUM GPIO_NUM_14




// Flag set by the timer callback when a fresh 1-second RPM value is ready.
volatile bool s_rpm_ready_1s = false;
// Final RPM value computed once per second.
volatile float s_rpm_1s = 0.0f;

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


extern "C" void app_main(void)
{

    i2c_master_bus_handle_t bus_handle = i2c_bus_init(BMX280_SDA_NUM, BMX280_SCL_NUM);
    bmx280_t* bmx280 = NULL;
    ESP_ERROR_CHECK(bmx280_dev_init(&bmx280,bus_handle));
    ESP_ERROR_CHECK(bmx280_setMode(bmx280, BMX280_MODE_CYCLE));

    hall_rpm_init();

    float temp = 0.0f, pres = 0.0f, hum = 0.0f;
     // Main application loop.
    while (true)
    {
        // Only do the expensive/logging work once a fresh 1-second RPM value is ready.
        if (s_rpm_ready_1s) {

            // Clear the flag immediately so we don't print the same sample twice.
            s_rpm_ready_1s = false;

            // Wait until the BMX280 finishes any current conversion cycle.
            do {
                vTaskDelay(pdMS_TO_TICKS(1));
            } while(bmx280_isSampling(bmx280));

            ESP_ERROR_CHECK(bmx280_readoutFloat(bmx280, &temp, &pres, &hum));
            // Print one combined line once per second:
            //   RPM + temperature + pressure + humidity
            ESP_LOGI(TAG,
                     "RPM=%.1f, temp=%.2f C, pres=%.2f Pa",
                     s_rpm_1s, temp, pres);
        
        }
        // Small sleep so the loop does not busy-spin and waste CPU.
        vTaskDelay(pdMS_TO_TICKS(20));    
    }


    ESP_LOGI(TAG, "I2C de-initialized successfully");
    bmx280_close(bmx280);
    i2c_del_master_bus(bus_handle);
    //ESP_LOGI(TAG, "Restarting now.");
    //esp_restart();
}
