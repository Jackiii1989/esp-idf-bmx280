# Testing & Observability — Topic 8 Reference

Reference material for grilling on testing strategies and observability. Use during Topic 8 of an architecture review.

---

## Grilling anchors

**Core tension:** hardware-coupled firmware is hard to test without a device. Probe whether the user has considered the separation between logic and I/O.

Questions to probe (one at a time):
- "How do you verify `bmx280_readoutFloat()` returns correct values — without a sensor attached?"
- "How do you test the RPM calculation logic without spinning a motor?"
- "What's your plan if a CI machine has no ESP32?"
- "How would you catch a regression in the CSV output format before it breaks the live-plot consumer?"

---

## Testing strategies

### On-device: Unity test framework
- ESP-IDF ships Unity (`components/unity`). Tests run on the target and report via UART.
- Use for integration tests that require real peripherals: I2C bus, PCNT edge counting.
- Run with `idf.py -T <test_dir> flash monitor`.
- Limitation: requires hardware. Not suitable for CI without a connected device.

### Host-side: CMock / CMock + Unity
- Pure-C logic (RPM formula, CSV formatting, timeout logic) can be extracted and tested on the host.
- CMock generates mocks from headers — mock `esp_timer_get_time`, `pcnt_unit_get_count`, etc.
- Allows CI without hardware. Requires isolating logic from ESP-IDF HAL calls.
- Limitation: mocks are only as good as the model — bus timing, electrical noise not captured.

### Loopback / synthetic injection: sender.py
- `sender.py` is a synthetic data injector for the live-plot GUI (in `live-plot/`). **Not yet implemented.**
- Planned: emit CSV lines over a virtual COM port at a configurable rate to test the PyQt6 consumer without real firmware.
- Useful for: testing plot scaling, CSV parsing edge cases, column-order regressions.

---

## Observability mechanisms

### Logging
- `ESP_LOGI` / `ESP_LOGW` / `ESP_LOGE` — component-tagged, level-filtered.
- Set log level per component: `esp_log_level_set("rpm_unit", ESP_LOG_DEBUG)`.
- Key gap in this project: `isSampling()` loop has no `ESP_LOGW` on timeout exit.

### ESP-IDF system state
- `esp_get_free_heap_size()` — heap headroom at runtime.
- `uxTaskGetStackHighWaterMark(NULL)` — stack headroom of current task.
- `esp_timer_dump(stdout)` — lists all active timers with periods and drift.
- `vTaskList()` — task list with state and stack usage (requires `CONFIG_FREERTOS_USE_TRACE_FACILITY`).

### Watchdog as a canary
- Task Watchdog (TWDT): fires if a task doesn't yield within the configured timeout.
- In this project: if `isSampling()` hangs indefinitely, TWDT fires before the user sees any other symptom. Treat TWDT as an observability signal, not just a safety net.

### CSV as an integration observable
- The CSV output is the end-to-end integration test of the full data path (I2C read → compute → format → UART).
- A stuck value, NaN, or field swap in the CSV is a detectable regression.
- Field order: `rpm, pressure_hpa, temperature_c` (no humidity — BMP280 has no humidity sensor).

---

## Recommended answer (Topic 8)

A complete answer names all three layers:
1. **On-device Unity tests** for peripheral integration (I2C, PCNT)
2. **Host-side unit tests** (CMock) for logic isolated from HAL
3. **`sender.py`** (or equivalent) for end-to-end consumer testing without firmware

A partial answer that names only hardware testing misses the host-testable layer. A partial answer that names only mocks misses that electrical timing can only be verified on real hardware.
