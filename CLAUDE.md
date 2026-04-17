# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ESP32-S3 firmware that reads a BME280 environmental sensor and a Hall-effect RPM sensor, then streams CSV data over UART for live plotting.

**Toolchain:** ESP-IDF v6.0.0 at `C:\esp\v6.0\esp-idf`

Before any `idf.py` command, activate the ESP-IDF environment in the terminal:
```powershell
# PowerShell
. C:\esp\v6.0\esp-idf\export.ps1
```
```cmd
:: CMD
C:\esp\v6.0\esp-idf\export.bat
```

```bash
idf.py build
idf.py -p COM<N> flash monitor   # flash + open serial monitor
idf.py menuconfig                 # configure SDK/component options
```

---

## Firmware Architecture

**`main/main.cpp`** — entry point. Initializes the I2C bus, BMX280 driver, and RPM unit, then spins in a 20 ms loop. Prints the `"Sensor started:"` banner once, then once per ~800 ms (when `s_rpm_ready_800ms` is set by the RPM timer callback) reads BMX280 and prints one CSV line.

**`components/bme280/`** — BMX280 driver (supports BME280 and BMP280). The driver has two I2C backend modes selectable via `menuconfig → BMX280 Options → I2C driver setting`:
- **Legacy** (`driver/i2c.h`) — for ESP-IDF < 5.3
- **Master** (`driver/i2c_master.h`) — used in this project (ESP-IDF ≥ 5.3)

The `CONFIG_USE_I2C_MASTER_DRIVER` Kconfig flag controls which path compiles. `bmx280_dev_init()` is the entry point used by main; it wraps `bmx280_create_master()`, `bmx280_init()`, and default `bmx280_configure()`.

**`components/rpm_unit/`** — Hall-effect RPM counter using ESP32's PCNT peripheral on GPIO42. A 200 ms `esp_timer` fires; after **4 windows** (800 ms total) it computes RPM = `(total_pulses * 75.0) / PULSES_PER_REV` and sets `s_rpm_ready_800ms`. The flag and `s_rpm_800ms` are `volatile` globals shared with `main.cpp` via `extern`.

**Cross-component globals design:** `s_rpm_ready_800ms` and `s_rpm_800ms` are *defined* in `main.cpp` and *declared `extern`* in `rpm_unit.c`. The component writes into main's variables rather than owning its own state. This is intentional but non-standard — if refactoring, consider moving ownership to `rpm_unit` and exposing a getter.

**Humidity field:** `bmx280_readoutFloat()` populates a `hum` variable but it is not printed. BMP280 (the sensor variant used here) has no humidity sensor; the field is read to satisfy the API signature and silently discarded. The CSV is always 3 fields: `rpm, pressure_hpa, temperature_c`.

**Pin assignments:**
- I2C SDA: GPIO12, SCL: GPIO14 (internal pull-ups enabled)
- Hall sensor: GPIO42

**Serial output format** (115200 baud):
```
Sensor started:
<rpm>,<pressure_hpa>,<temperature_c>\r\n
```
Example: `0.00,1013.25,24.50`

---

## live-plot

Python PyQt6 GUI that plots live serial data. Located in `live-plot/`. Package manager: `uv`. See `live-plot/CLAUDE.md` for full architecture details.

```bash
cd live-plot
uv run python main.py --port COM<N>               # receive and plot (from ESP32 or virtual COM)
uv run python main.py --port COM<N> --csv         # also log to an auto-named CSV file
uv run python main.py --port COM<N> --csv out.csv # also log to a named CSV file
```

`--port` is always required. `main.py` also accepts `--baudrate` (default 115200), `--history` (default 4000 points), and `--refresh-ms` (default 20). CSV columns: `timestamp, time_s, rpm, pressure_hpa, temperature_c`.

Note: `sender.py` (a synthetic data injector for loopback testing) is referenced in `live-plot/CLAUDE.md` but has not been implemented yet.

---

## Key Configuration (menuconfig)

- `BMX280 Options → I2C driver setting` — must be set to **I2C Master Driver** for this project
- `BMX280 Options → I2C Clock Speed` — default 100 kHz
- `BMX280 Options → Installed Sensor Model` — auto-detect by default
- `BMX280 Options → I2C Slave Address` — auto-detect by default (0x76 or 0x77)
- Oversampling and IIR filter settings are under `BMX280 Options → Default Configuration`
