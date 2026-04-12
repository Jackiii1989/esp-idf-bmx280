from __future__ import annotations

import argparse
import math
import time

import serial
import serial.tools.list_ports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send fake BME280 CSV frames to a Windows COM port."
    )
    parser.add_argument("--port", required=True, help="Serial port, e.g. COM12")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")
    parser.add_argument(
        "--interval-ms",
        type=float,
        default=5.0,
        help="Delay between samples in milliseconds (5.0 ms = 200 Hz)",
    )
    return parser


def open_port_or_exit(port: str, baudrate: int) -> serial.SerialBase:
    try:
        return serial.serial_for_url(port, baudrate=baudrate, timeout=0, write_timeout=0)
    except serial.SerialException as e:
        print(f"Could not open serial port {port}: {e}")
        print("Available ports:")
        for info in sorted(serial.tools.list_ports.comports()):
            print(f"  - {info.device}: {info.description}")
        raise SystemExit(1)


def main() -> int:
    args = build_parser().parse_args()
    ser = open_port_or_exit(args.port, args.baudrate)
    t0 = time.perf_counter()

    try:
        while True:
            t = time.perf_counter() - t0

            pressure_hpa = 1008.0 + 0.8 * math.sin(2.0 * math.pi * 0.03 * t)
            temperature_c = (
                24.0
                + 1.8 * math.sin(2.0 * math.pi * 0.07 * t)
                + 0.15 * math.sin(2.0 * math.pi * 1.3 * t)
            )
            humidity_percent = 45.0 + 4.0 * math.sin(2.0 * math.pi * 0.05 * t + 1.2)

            line = f"{pressure_hpa:.3f},{temperature_c:.3f},{humidity_percent:.3f}\n".encode("ascii")
            ser.write(line)
            time.sleep(args.interval_ms / 1000.0)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
