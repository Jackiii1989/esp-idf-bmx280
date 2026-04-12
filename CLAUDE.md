# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ESP32-S3 firmware that reads a BME280 environmental sensor and a Hall-effect RPM sensor, then streams CSV data over UART for live plotting.

**Toolchain:** ESP-IDF v6.0.0 at `C:\esp\v6.0\esp-idf`

```bash
idf.py build
idf.py -p COM<N> flash monitor   # flash + open serial monitor
idf.py menuconfig                 # configure SDK/component options
```

---

## Firmware Architecture

**`main/main.cpp`** — entry point. Initializes the I2C bus, BMX280 driver, and RPM unit, then spins in a 20 ms loop. Once per second, when `s_rpm_ready_1s` is set by the RPM timer callback, it reads BMX280 and prints one log line.

**`components/bme280/`** — BMX280 driver (supports BME280 and BMP280). The driver has two I2C backend modes selectable via `menuconfig → BMX280 Options → I2C driver setting`:
- **Legacy** (`driver/i2c.h`) — for ESP-IDF < 5.3
- **Master** (`driver/i2c_master.h`) — used in this project (ESP-IDF ≥ 5.3)

The `CONFIG_USE_I2C_MASTER_DRIVER` Kconfig flag controls which path compiles. `bmx280_dev_init()` is the entry point used by main; it wraps `bmx280_create_master()`, `bmx280_init()`, and default `bmx280_configure()`.

**`components/rpm_unit/`** — Hall-effect RPM counter using ESP32's PCNT peripheral on GPIO42. A 200 ms `esp_timer` fires 5 times, accumulating pulse counts, then computes RPM = `(total_pulses * 60) / PULSES_PER_REV` and sets the `s_rpm_ready_1s` flag. The flag and `s_rpm_1s` are `volatile` globals shared with `main.cpp` via `extern`.

**Pin assignments:**
- I2C SDA: GPIO12, SCL: GPIO14 (internal pull-ups enabled)
- Hall sensor: GPIO42

**Serial output format** (115200 baud):
```
I (timestamp) MAIN: RPM=X.X, temp=XX.XX C, pres=XX.XX Pa
```
> Note: humidity is read but not printed. The `live-plot` subproject expects CSV (`pressure_hpa,temperature_c,humidity_percent`) — the firmware would need to be updated to emit that format.

---

## live-plot

Python PyQt6 GUI that plots live serial data. Located in `live-plot/`. Package manager: `uv`.

```bash
cd live-plot
uv run python main.py --port COM<N>            # receive from ESP32 (default role)
uv run python main.py receiver --port COM<N>   # explicit receiver mode
uv run python main.py sender --port COM<N>     # inject synthetic sine-wave data
```

`--port` is always required. The sender injects synthetic data through a real COM port (use a virtual COM pair for loopback testing).

**Architecture:** Everything is in `main.py`. `SerialReaderThread` reads bytes from the serial port in a background thread and pushes parsed `(time, pressure, temperature, humidity)` tuples into a `SimpleQueue`. `PlotWindow` (QMainWindow) drains the queue via a `QTimer` and updates three linked `pyqtgraph` plots (pressure/temperature/humidity) sharing the same x-axis.

---

## Key Configuration (menuconfig)

- `BMX280 Options → I2C driver setting` — must be set to **I2C Master Driver** for this project
- `BMX280 Options → I2C Clock Speed` — default 100 kHz
- `BMX280 Options → Installed Sensor Model` — auto-detect by default
- `BMX280 Options → I2C Slave Address` — auto-detect by default (0x76 or 0x77)
- Oversampling and IIR filter settings are under `BMX280 Options → Default Configuration`
