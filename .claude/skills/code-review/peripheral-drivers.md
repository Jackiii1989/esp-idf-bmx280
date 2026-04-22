# Peripheral Driver Reference: PCNT, I2C Master, NVS, esp_timer

This reference covers driver-specific patterns and known pitfalls for the peripherals used in this project.

## esp_timer (High Resolution Timer)

### Dispatch Modes

| Mode | Callback runs in | Can block? | Can call FreeRTOS? | Yield mechanism |
|------|-----------------|------------|-------------------|----------------|
| `ESP_TIMER_TASK` (default) | `esp_timer` task (high-priority) | No — delays other timers | Yes, non-blocking variants only | `xSemaphoreGive`, `xQueueSend` |
| `ESP_TIMER_ISR` | Hardware timer ISR | No | Only `*FromISR` variants | `esp_timer_isr_dispatch_need_yield()` |

### Correct TASK-dispatch pattern
```c
static void rpm_timer_cb(void *arg)
{
    // Short: update counters, signal task
    s_window_count++;
    if (s_window_count >= 4) {
        s_rpm_800ms = compute_rpm();
        s_rpm_ready_800ms = true;
        s_window_count = 0;
    }
    // If task signaling needed:
    // xSemaphoreGiveFromISR is NOT needed here — we're in a task context.
    // xSemaphoreGive(s_ready_sem) is correct.
}
```

### Correct ISR-dispatch pattern
```c
static void IRAM_ATTR fast_timer_cb(void *arg)
{
    // Only *FromISR calls, no portYIELD_FROM_ISR!
    BaseType_t woken = pdFALSE;
    xSemaphoreGiveFromISR(s_sem, &woken);
    if (woken) {
        esp_timer_isr_dispatch_need_yield();  // NOT portYIELD_FROM_ISR
    }
}
```

### Lifecycle
```c
esp_timer_handle_t timer;
esp_timer_create_args_t args = {
    .callback = my_cb,
    .dispatch_method = ESP_TIMER_TASK,
    .name = "my_timer",
};
ESP_ERROR_CHECK(esp_timer_create(&args, &timer));
ESP_ERROR_CHECK(esp_timer_start_periodic(timer, 200000));  // 200 ms in µs

// On teardown:
esp_timer_stop(timer);
esp_timer_delete(timer);  // Must delete, not just stop
```

---

## PCNT (Pulse Counter) — New Driver API (ESP-IDF ≥ 5.0)

### Unit Lifecycle
```
esp_err_t pcnt_new_unit()       → pcnt_unit_handle_t
esp_err_t pcnt_unit_set_glitch_filter()   ← must be BEFORE enable
esp_err_t pcnt_unit_add_watch_point()
esp_err_t pcnt_unit_register_event_callbacks()
esp_err_t pcnt_unit_enable()    ← acquires APB_FREQ_MAX PM lock
esp_err_t pcnt_unit_clear_count()
esp_err_t pcnt_unit_start()
    ... running ...
esp_err_t pcnt_unit_stop()
esp_err_t pcnt_unit_disable()   ← releases PM lock
esp_err_t pcnt_del_unit()
```

### Glitch Filter Setup (must be before enable)
```c
pcnt_glitch_filter_config_t filter = {
    .max_glitch_ns = 1000,  // pulses shorter than 1 µs are noise
};
// Call BEFORE pcnt_unit_enable()
ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(unit, &filter));
```

### Event Callback — ISR Context Rules
```c
static bool IRAM_ATTR pcnt_on_reach(pcnt_unit_handle_t unit,
                                     const pcnt_watch_event_data_t *edata,
                                     void *user_ctx)
{
    BaseType_t woken = pdFALSE;
    // Use FromISR variants only
    xQueueSendFromISR(s_queue, &edata->watch_point_val, &woken);
    return (woken == pdTRUE);  // Return true to request context switch
}

pcnt_event_callbacks_t cbs = { .on_reach = pcnt_on_reach };
ESP_ERROR_CHECK(pcnt_unit_register_event_callbacks(unit, &cbs, NULL));
```

### Reading Count
```c
int pulse_count = 0;
ESP_ERROR_CHECK(pcnt_unit_get_count(unit, &pulse_count));
```

### Overflow Compensation
```c
// Use large watch limits to minimize interrupt frequency
pcnt_unit_config_t unit_config = {
    .low_limit  = -32767,
    .high_limit =  32767,  // Use max range for overflow compensation
};
```

---

## I2C Master Driver (driver/i2c_master.h — ESP-IDF ≥ 5.3)

### Handle Hierarchy
```
i2c_master_bus_handle_t   (one per physical I2C bus)
    └── i2c_master_dev_handle_t  (one per device on that bus)
```

### Initialization
```c
// 1. Create bus (once per I2C port)
i2c_master_bus_config_t bus_cfg = {
    .i2c_port    = I2C_NUM_0,
    .sda_io_num  = GPIO_NUM_12,
    .scl_io_num  = GPIO_NUM_14,
    .clk_source  = I2C_CLK_SRC_DEFAULT,
    .glitch_ignore_cnt = 7,
    .flags.enable_internal_pullup = true,
};
i2c_master_bus_handle_t bus;
ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));

// 2. Add device (once per slave address)
i2c_device_config_t dev_cfg = {
    .dev_addr_length = I2C_ADDR_BIT_LEN_7,
    .device_address  = 0x76,
    .scl_speed_hz    = 100000,
    .scl_wait_us     = 5000,  // 5 ms for BME280 clock stretching
};
i2c_master_dev_handle_t dev;
ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &dev_cfg, &dev));
```

### Write then Read (register access)
```c
uint8_t reg_addr = 0xF3;
uint8_t data[2];
// transmit_receive sends reg_addr, issues REPEATED START, then reads
ESP_ERROR_CHECK(i2c_master_transmit_receive(dev, &reg_addr, 1, data, 2, -1));
```

### Known Bug: ESP_OK on NACK
Some ESP-IDF versions return `ESP_OK` when the slave NAKs the address byte. Validate data plausibility if the sensor can be absent:
```c
esp_err_t err = i2c_master_transmit_receive(dev, &reg, 1, buf, len, -1);
if (err == ESP_OK) {
    // Sanity-check: BME280 chip ID register should be 0x60 or 0x58
    if (buf[0] != 0x60 && buf[0] != 0x58) {
        ESP_LOGW(TAG, "Unexpected chip ID 0x%02x — device may be absent", buf[0]);
    }
}
```

### Teardown (must delete in order)
```c
i2c_master_bus_rm_device(dev);   // Remove device first
i2c_del_master_bus(bus);         // Then delete bus
```

### Do NOT Mix Old and New APIs
```c
// WRONG — old and new drivers conflict on same I2C port
i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0);
i2c_new_master_bus(&bus_cfg, &bus);  // Crashes — double-init
```

---

## NVS (Non-Volatile Storage)

### Initialization Pattern
```c
esp_err_t err = nvs_flash_init();
if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    // Partition is corrupt or version mismatch — erase and reinit
    ESP_ERROR_CHECK(nvs_flash_erase());
    err = nvs_flash_init();
}
ESP_ERROR_CHECK(err);
```

### Write + Commit Pattern
```c
nvs_handle_t handle;
ESP_ERROR_CHECK(nvs_open("storage", NVS_READWRITE, &handle));

ESP_ERROR_CHECK(nvs_set_u32(handle, "rpm_cal", calibration_value));
ESP_ERROR_CHECK(nvs_commit(handle));  // REQUIRED — data not persisted without this

nvs_close(handle);
```

### Read Pattern
```c
nvs_handle_t handle;
ESP_ERROR_CHECK(nvs_open("storage", NVS_READONLY, &handle));

uint32_t value = 0;
esp_err_t err = nvs_get_u32(handle, "rpm_cal", &value);
if (err == ESP_ERR_NVS_NOT_FOUND) {
    value = DEFAULT_CAL;  // Key not yet written — use default
} else {
    ESP_ERROR_CHECK(err);
}

nvs_close(handle);
```

### Constraints
| Item | Limit |
|------|-------|
| Namespace length | 15 characters max (silently truncated) |
| Key length | 15 characters max (silently truncated) |
| Value types | u8, u16, u32, u64, i8, i16, i32, i64, str, blob |
| Max blob size | 508000 bytes |
| Concurrent open handles | limited (driver-internal pool) |

### Key/Namespace Collision from Truncation
```c
// BAD — both truncate to "sensor_calibrat" — they share the same NVS slot!
nvs_set_u32(h, "sensor_calibration_v1", 100);
nvs_set_u32(h, "sensor_calibration_v2", 200);

// GOOD — keep names under 15 chars
nvs_set_u32(h, "cal_v1", 100);
nvs_set_u32(h, "cal_v2", 200);
```
