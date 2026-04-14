# live-plot

Live serial plotter for the ESP32 BME280 + RPM sensor firmware. Displays RPM, pressure, and temperature in real time using a PyQt6 GUI.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

## Usage

### Plot live data from the ESP32

```bash
uv run python main.py --port COM<N>
```

### Save data to a CSV file while plotting

```bash
# Auto-generate a timestamped filename (e.g. bme280_2026-04-14_10-32-05.csv)
uv run python main.py --port COM<N> --csv

# Or specify a filename
uv run python main.py --port COM<N> --csv my_run.csv
```

The CSV contains columns: `timestamp, time_s, rpm, pressure_hpa, temperature_c`.

### Test the plotter without hardware (synthetic data)

Use a virtual COM pair (e.g. [com0com](https://com0com.sourceforge.net/) on Windows) and run the sender on one port while the plotter listens on the other:

```bash
uv run python main.py --port COM<M>     # terminal 2 — plots it
```

## Options

### `main.py`

| Flag | Default | Description |
|---|---|---|
| `--port` | *(required)* | Serial port, e.g. `COM13` |
| `--baudrate` | `115200` | Serial baud rate |
| `--history` | `4000` | Number of data points kept on screen |
| `--refresh-ms` | `20` | GUI redraw interval in milliseconds |
| `--csv [FILE]` | off | Save to CSV; omit `FILE` for an auto-named file |
