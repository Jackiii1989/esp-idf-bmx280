from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from collections import deque
from queue import Empty, SimpleQueue
# [CHANGED] Added NamedTuple — used by the Sample class below.
from typing import NamedTuple

import pyqtgraph as pg
import serial
import serial.tools.list_ports
from PyQt6 import QtCore, QtWidgets


# ---------------------------------------------------------------------------
# [CHANGED] Replaced the raw 4-tuple with a NamedTuple called Sample.
#
# Before: SimpleQueue[tuple[float, float, float, float]]
#         Fields were accessed by position, making it easy to mix up the order.
#
# After:  SimpleQueue[Sample]
#         Each field has a name (sample.pressure_hpa, sample.time_s, …),
#         so every call site is self-documenting and positional mistakes
#         are caught immediately.
# ---------------------------------------------------------------------------

class Sample(NamedTuple):
    time_s: float
    pressure_hpa: float
    temperature_c: float
    humidity_percent: float


# ---------------------------------------------------------------------------
# [CHANGED] Removed the two module-level globals (sample_queue, stop_event).
#
# Before: Both were global variables shared implicitly by SerialReaderThread
#         and PlotWindow, creating hidden coupling that makes the code hard
#         to follow and impossible to unit-test.
#
# After:  Both are created in main() and passed explicitly to each class
#         that needs them. The dependency is now visible at the call site.
# ---------------------------------------------------------------------------


class SerialReaderThread(threading.Thread):
    """Background daemon thread that owns all serial I/O.

    Reads raw bytes from the COM port, assembles them into complete lines,
    parses each line as comma-separated pressure,temperature,humidity values,
    and pushes the result into the queue for the GUI thread to consume.
    """

    # [CHANGED] Constructor now receives queue and stop as arguments
    #           instead of reading the module-level globals.
    def __init__(
        self,
        ser: serial.SerialBase,
        queue: SimpleQueue[Sample],
        stop: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self.ser = ser
        self.queue = queue
        self.stop = stop
        self.t0 = time.perf_counter()

    # [CHANGED] Extracted CSV parsing into its own method _parse_line().
    #
    # Before: The try/except block sat directly inside the byte-reading loop
    #         in run(), mixing three concerns (I/O, line assembly, parsing)
    #         in one long method.
    #
    # After:  run() stays focused on I/O and line assembly; all parsing
    #         logic lives here. If the format ever changes, only this
    #         method needs updating.
    def _parse_line(self, line: bytearray) -> Sample | None:
        """Parse one raw line into a Sample, or return None if malformed."""
        try:
            text = line.decode("ascii").strip()
            p, t, h = text.split(",", maxsplit=2)
            return Sample(
                time_s=time.perf_counter() - self.t0,
                pressure_hpa=float(p),
                temperature_c=float(t),
                humidity_percent=float(h),
            )
        except Exception:
            # Malformed or partial frames are silently dropped so one bad
            # frame does not crash the display.
            return None

    def run(self) -> None:
        buffer = bytearray()
        synced = False  # True once the "Sensor started:" banner has been seen

        while not self.stop.is_set():
            waiting = self.ser.in_waiting
            chunk = self.ser.read(waiting or 1)

            if not chunk:
                time.sleep(0.001)
                continue

            buffer.extend(chunk)

            while True:
                newline_index = buffer.find(b"\n")
                if newline_index == -1:
                    break

                line = buffer[:newline_index]
                del buffer[:newline_index + 1]

                # [CHANGED] Improved debug print.
                #
                # Before: print(line)  → printed raw bytearray repr, hard to read.
                #
                # After:  decoded to a readable string with a [raw] prefix so it
                #         is easy to identify in the terminal. errors='replace'
                #         prevents a crash if any non-ASCII byte arrives.
                print(f"[raw] {line.decode('ascii', errors='replace').strip()}")

                # Skip all lines until the firmware's "Sensor started:" banner.
                if not synced:
                    if b"Sensor started:" in line:
                        synced = True
                    continue

                # [CHANGED] Replaced inline try/except with _parse_line() call.
                sample = self._parse_line(line)
                if sample is not None:
                    self.queue.put(sample)


class PlotWindow(QtWidgets.QMainWindow):
    """Main Qt window with three vertically stacked live plots.

    A QTimer fires on the GUI thread at `refresh_ms` intervals, drains
    the queue, and redraws all three curves in one batch.
    """

    # [CHANGED] Constructor now receives queue as an argument
    #           instead of reading the module-level global.
    def __init__(
        self,
        queue: SimpleQueue[Sample],
        history: int,
        refresh_ms: int,
    ) -> None:
        super().__init__()
        self.queue = queue
        self.setWindowTitle("Live BME280 COM Plot")

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # [CHANGED] Replaced three copy-pasted plot setup blocks with
        #           calls to _make_plot().
        #
        # Before: each plot repeated the same six lines of configuration,
        #         meaning any styling tweak had to be made three times.
        #
        # After:  _make_plot() owns all shared configuration; the three
        #         calls below only specify what differs between them.
        self.pressure_plot, self.pressure_curve = self._make_plot("Pressure", "hPa")
        self.temperature_plot, self.temperature_curve = self._make_plot(
            "Temperature", "°C", link_to=self.pressure_plot
        )
        self.humidity_plot, self.humidity_curve = self._make_plot(
            "Humidity", "%", link_to=self.pressure_plot, x_label="Receive time"
        )

        for plot in (self.pressure_plot, self.temperature_plot, self.humidity_plot):
            layout.addWidget(plot)

        self.x_data = deque(maxlen=history)
        self.pressure_data = deque(maxlen=history)
        self.temperature_data = deque(maxlen=history)
        self.humidity_data = deque(maxlen=history)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.drain_queue_and_redraw)
        self.timer.start(refresh_ms)

    # [CHANGED] Added _make_plot() helper to remove the three-way repetition
    #           that was in __init__ before.
    def _make_plot(
        self,
        label: str,
        units: str,
        link_to: pg.PlotWidget | None = None,
        x_label: str | None = None,
    ) -> tuple[pg.PlotWidget, pg.PlotDataItem]:
        """Create a configured PlotWidget + curve pair.

        Shared options (grid, performance flags) are set here once.
        Callers only pass what differs: axis label, units, and optional x-link.
        """
        plot = pg.PlotWidget()
        plot.setLabel("left", label, units=units)
        plot.showGrid(x=True, y=True)
        if link_to is not None:
            # Linking the x-axis means zoom/pan on any plot applies to all three.
            plot.setXLink(link_to)
        if x_label is not None:
            plot.setLabel("bottom", x_label, units="s")
        # Performance flags: no antialiasing, auto-thin dense data,
        # skip drawing outside the visible range, trust all values are finite.
        curve = plot.plot(
            [], [],
            antialias=False,
            autoDownsample=True,
            clipToView=True,
            skipFiniteCheck=True,
        )
        return plot, curve

    def drain_queue_and_redraw(self) -> None:
        changed = False

        while True:
            try:
                # [CHANGED] Destructuring now uses named fields from Sample
                #           instead of positional unpacking.
                sample = self.queue.get_nowait()
            except Empty:
                break

            self.x_data.append(sample.time_s)
            self.pressure_data.append(sample.pressure_hpa)
            self.temperature_data.append(sample.temperature_c)
            self.humidity_data.append(sample.humidity_percent)
            changed = True

        if changed:
            x = list(self.x_data)
            self.pressure_curve.setData(x, list(self.pressure_data))
            self.temperature_curve.setData(x, list(self.temperature_data))
            self.humidity_curve.setData(x, list(self.humidity_data))

    def closeEvent(self, event) -> None:
        # stop is set by the finally block in main(), so PlotWindow does not
        # need to hold a reference to it.
        super().closeEvent(event)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Receive BME280 CSV frames from a Windows COM port and plot them live."
    )
    parser.add_argument("--port", required=True, help="Serial port, e.g. COM13")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate")
    parser.add_argument("--history", type=int, default=4000, help="Number of points to keep")
    parser.add_argument("--refresh-ms", type=int, default=20, help="GUI redraw interval in milliseconds")
    return parser


def open_port_or_exit(port: str, baudrate: int) -> serial.SerialBase:
    try:
        return serial.serial_for_url(port, baudrate=baudrate, timeout=0)
    except serial.SerialException as e:
        print(f"Could not open serial port {port}: {e}")
        print("Available ports:")
        for info in sorted(serial.tools.list_ports.comports()):
            print(f"  - {info.device}: {info.description}")
        raise SystemExit(1)


def main() -> int:
    args = build_parser().parse_args()

    # [CHANGED] queue and stop are now created here and injected into both
    #           SerialReaderThread and PlotWindow, replacing the module-level
    #           globals. Each class receives only what it needs.
    queue: SimpleQueue[Sample] = SimpleQueue()
    stop = threading.Event()

    ser = open_port_or_exit(args.port, args.baudrate)
    reader = SerialReaderThread(ser, queue=queue, stop=stop)
    reader.start()

    app = QtWidgets.QApplication(sys.argv)

    # Ctrl+C support: PyQt6's C++ event loop never yields to Python on its
    # own, so SIGINT would be silently ignored. The no-op QTimer forces a
    # re-entry into Python every 200 ms, giving the signal handler a window
    # to fire.
    def _handle_sigint(*_):
        stop.set()
        app.quit()

    signal.signal(signal.SIGINT, _handle_sigint)

    sigint_guard = QtCore.QTimer()
    sigint_guard.start(200)
    sigint_guard.timeout.connect(lambda: None)

    window = PlotWindow(queue=queue, history=args.history, refresh_ms=args.refresh_ms)
    window.resize(1100, 800)
    window.show()

    try:
        return app.exec()
    finally:
        stop.set()
        ser.close()


if __name__ == "__main__":
    raise SystemExit(main())
