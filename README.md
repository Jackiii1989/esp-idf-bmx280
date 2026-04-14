
## Overview

ESP32-S3 firmware that reads a BME280 environmental sensor and a Hall-effect RPM sensor, then streams CSV data over UART for live plotting.

## How to use example

### Hardware Required

An ESP32-S3 development board with:
- A BME280 (or BMP280) environmental sensor connected via I2C
- A Hall-effect RPM sensor connected to GPIO42

#### Pin Assignment

| Signal       | GPIO |
| ------------ | ---- |
| I2C SDA      | 12   |
| I2C SCL      | 14   |
| Hall sensor  | 42   |

Internal pull-ups are enabled on SDA/SCL — no external resistors needed.

### Build and Flash

```bash
idf.py build
idf.py -p COM<N> flash monitor   # flash and open serial monitor
idf.py menuconfig                 # configure SDK/component options
```

(To exit the serial monitor, type `Ctrl-]`.)

### Key menuconfig Options

- `BMX280 Options → I2C driver setting` — set to **I2C Master Driver** (required for ESP-IDF ≥ 5.3)
- `BMX280 Options → I2C Clock Speed` — default 100 kHz
- `BMX280 Options → Installed Sensor Model` — auto-detect by default
- `BMX280 Options → I2C Slave Address` — auto-detect by default (0x76 or 0x77)

## Example Output

```
Sensor started:
0.00,1013.25,24.50
12.34,1013.18,24.52
```

Serial format (115200 baud): `rpm,pressure_hpa,temperature_c`

## Live Plot

A Python PyQt6 GUI for live plotting is in `live-plot/`. Package manager: `uv`.

```bash
cd live-plot
uv run python main.py --port COM<N>               # receive and plot
uv run python main.py --port COM<N> --csv         # also log to auto-named CSV
uv run python main.py --port COM<N> --csv out.csv # also log to named CSV
uv run python sender.py --port COM<N>             # inject synthetic test data
```

## Troubleshooting

(For any technical queries, please open an [issue](https://github.com/espressif/esp-idf/issues) on GitHub. We will get back to you as soon as possible.)
