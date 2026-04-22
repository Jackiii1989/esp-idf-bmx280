# ESP-IDF Debug Patterns

Common failure signatures and their root causes.

---

## Crashes

**Guru Meditation / Illegal instruction / LoadProhibited**
Log: `Guru Meditation Error: Core 0 panic'ed (LoadProhibited)`
Cause: NULL or unaligned pointer dereference. Check the backtrace PC address.

**Stack overflow**
Log: `***ERROR*** A stack overflow in task <name> has been detected`
Cause: task stack too small, or large local arrays/recursion. Increase stack size in `xTaskCreate` or move buffers to heap/static.

**Heap corruption / malloc failure**
Log: `CORRUPT HEAP` or `assert failed: block is corrupted` or `malloc returned NULL`
Cause: write past allocation, double-free, or heap exhausted. Enable `CONFIG_HEAP_CORRUPTION_DETECTION` in menuconfig.

**Abort / ESP_ERROR_CHECK failure**
Log: `abort() was called at PC ... in function ...` or `ESP_ERROR_CHECK failed: esp_err_t 0x...`
Cause: `ESP_ERROR_CHECK` on a failed return. The preceding log line usually names the failing call.

**Watchdog trigger (TWDT)**
Log: `Task watchdog got triggered. The following tasks/users did not reset the watchdog in time: ... IDLE`
Cause: a task is blocking the CPU without yielding — tight loop, blocking I2C/SPI call, or infinite wait.

**Watchdog trigger (IWDT)**
Log: `Interrupt watchdog timeout on CPU0`
Cause: ISR or critical section running too long (> ~10 ms). Move work out of the ISR.

---

## Hangs (no crash output)

**Silent hang, watchdog never fires**
Cause: `vTaskDelay(portMAX_DELAY)` or blocking call with no timeout. Check `isSampling()` loops, semaphore takes, and queue receives for missing timeouts.

**Boot loop (resets repeatedly)**
Log: repeated boot banner with no progress
Cause: crash in `app_main` before logging starts, or `ESP_ERROR_CHECK` on a peripheral that fails init. Add `ESP_LOGI` at the top of `app_main` to narrow down where it resets.

---

## I2C errors

**NACK on address**
Log: `i2c: i2c_master_cmd_begin(xxx): i2c device not ack`
Cause: wrong I2C address, device not powered, SDA/SCL swapped, or missing pull-ups.

**Timeout**
Log: `I2C timeout` or `ESP_ERR_TIMEOUT`
Cause: bus stuck low (previous transaction not completed), missing pull-ups, or clock too fast for the device.

**Arbitration lost**
Log: `i2c: i2c arbitration lost`
Cause: multiple masters on the bus, or electrical noise.

---

## PCNT / RPM issues

**Always zero RPM**
Cause: wrong GPIO, signal level incompatible with PCNT thresholds, or `pcnt_unit_start()` not called.

**RPM doubles unexpectedly**
Cause: `hall_rpm_init()` called twice → two timers accumulating counts separately.

**RPM wildly fluctuating**
Cause: `PULSES_PER_REV` wrong, or debounce filter not set, or electrical noise on the Hall sensor line.

---

## Wrong output / data issues

**CSV fields misaligned or NaN**
Cause: `bmx280_readoutFloat()` failed silently (check return value), or `printf` format string mismatch.

**Pressure/temperature values stuck**
Cause: sensor in forced mode not re-triggered, or `isSampling()` timeout hit and read skipped.

**RPM always 0.00 after first reading**
Cause: `s_rpm_ready_800ms` flag not cleared after read, or window counter not resetting.
