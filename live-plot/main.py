from __future__ import annotations  # Lets us use modern type hints cleanly.

import argparse  # Reads command-line arguments like sender/receiver and --port.
import math  # Used to generate fake BME280-like demo values in sender mode.
import sys  # Gives access to command-line args and clean exit handling.
import threading  # Lets serial reading run in a background thread.
import time  # Used for timing, delays, and x-axis timestamps.
from collections import deque  # Efficient rolling buffers for live plotting.
from queue import Empty, SimpleQueue  # Thread-safe queue between reader thread and GUI.

import pyqtgraph as pg  # Fast live plotting library.
import serial  # pySerial for COM-port communication on Windows.
from PyQt6 import QtCore, QtWidgets  # Qt GUI classes used by pyqtgraph.

import serial.tools.list_ports


# This queue transports parsed samples from the serial-reader thread
# to the GUI thread safely.
#
# Each item is:
#   (receive_time_seconds, pressure_hpa, temperature_c, humidity_percent)
sample_queue: SimpleQueue[tuple[float, float, float, float]] = SimpleQueue()


# This event is used to stop the background reader thread cleanly.
stop_event = threading.Event()




# --------------------------------------------------------------------------------------------------------------
# init globals
# --------------------------------------------------------------------------------------------------------------

class SerialReaderThread(threading.Thread):
    # This thread continuously reads serial bytes, splits them into lines,
    # parses each line as:
    #   pressure,temperature,humidity
    # and pushes the parsed data into sample_queue.
    def __init__(self, ser: serial.SerialBase) -> None:
        super().__init__(daemon=True)  # Daemon thread won't block Python shutdown.
        self.ser = ser  # Save the already-open serial port object.
        self.t0 = time.perf_counter()  # Reference start time for receiver-local x-axis.

    def run(self) -> None:
        # This byte buffer stores raw incoming bytes until a full line arrives.
        buffer = bytearray()

        # Keep looping until the main program asks the thread to stop.
        while not stop_event.is_set():
            # Number of bytes currently waiting in the serial buffer.
            waiting = self.ser.in_waiting

            # Read all currently waiting bytes.
            # If there are no bytes waiting yet, read 1 byte to keep progress moving.
            chunk = self.ser.read(waiting or 1)

            # If nothing came in, sleep briefly so we do not burn CPU in a tight loop.
            if not chunk:
                time.sleep(0.001)
                continue

            # Append the newly received bytes to the local buffer.
            buffer.extend(chunk)

            # Process every complete line currently inside the buffer.
            while True:
                # Find newline byte, which marks the end of one message.
                newline_index = buffer.find(b"\n")

                # If no newline exists yet, we do not have a full message.
                if newline_index == -1:
                    break

                # Extract one raw line without the newline.
                line = buffer[:newline_index]

                # Remove the processed line and the newline from the buffer.
                del buffer[: newline_index + 1]

                try:
                    # Decode the raw bytes into ASCII text and strip spaces.
                    # Example:
                    #   b"1008.52,24.31,47.92" -> "1008.52,24.31,47.92"
                    text = line.decode("ascii").strip()

                    # Split the line into the three expected fields.
                    pressure_text, temperature_text, humidity_text = text.split(",", maxsplit=2)

                    # Convert all fields from text to float.
                    pressure_hpa = float(pressure_text)
                    temperature_c = float(temperature_text)
                    humidity_percent = float(humidity_text)

                    # Use receiver-local elapsed time for the x-axis.
                    receive_time_s = time.perf_counter() - self.t0

                    # Push the parsed sample into the queue for the GUI thread.
                    sample_queue.put(
                        (receive_time_s, pressure_hpa, temperature_c, humidity_percent)
                    )

                except Exception:
                    # If any malformed line arrives, ignore it and keep going.
                    # This prevents one bad frame from crashing the whole program.
                    continue


class PlotWindow(QtWidgets.QMainWindow):
    # This is the GUI window in receiver mode.
    #
    # It creates 3 stacked live plots:
    #   1) pressure
    #   2) temperature
    #   3) humidity
    #
    # The GUI updates on a timer and redraws in batches for speed.
    def __init__(self, history: int, refresh_ms: int) -> None:
        super().__init__()  # Initialize the QMainWindow base class.

        # Set the title shown in the window frame.
        self.setWindowTitle("Live Jet Engine Graph")

        # Create a normal central widget for the main window.
        central_widget = QtWidgets.QWidget()

        # Put that widget into the main window.
        self.setCentralWidget(central_widget)

        # Create a vertical layout so the 3 plots are stacked top-to-bottom.
        layout = QtWidgets.QVBoxLayout(central_widget)

        # Reduce margins slightly so the plots use more space.
        layout.setContentsMargins(6, 6, 6, 6)

        # Add a little spacing between plots.
        layout.setSpacing(6)

        # -----------------------------
        # Pressure plot
        # -----------------------------
        self.pressure_plot = pg.PlotWidget()
        self.pressure_plot.setLabel("left", "Pressure", units="hPa")
        self.pressure_plot.showGrid(x=True, y=True)
        layout.addWidget(self.pressure_plot)

        # Create the pressure curve.
        self.pressure_curve = self.pressure_plot.plot(
            [],
            [],
            antialias=False,      # Turn off smoothing for speed.
            autoDownsample=True,  # Reduce displayed density when needed.
            clipToView=True,      # Only draw visible part of the curve.
            skipFiniteCheck=True, # Faster if your data is always valid floats.
        )

        # -----------------------------
        # Temperature plot
        # -----------------------------
        self.temperature_plot = pg.PlotWidget()
        self.temperature_plot.setLabel("left", "Temperature", units="°C")
        self.temperature_plot.showGrid(x=True, y=True)
        layout.addWidget(self.temperature_plot)

        # Link the x-axis to the pressure plot so zoom/pan stays aligned.
        self.temperature_plot.setXLink(self.pressure_plot)

        # Create the temperature curve.
        self.temperature_curve = self.temperature_plot.plot(
            [],
            [],
            antialias=False,
            autoDownsample=True,
            clipToView=True,
            skipFiniteCheck=True,
        )

        # -----------------------------
        # Humidity plot
        # -----------------------------
        self.humidity_plot = pg.PlotWidget()
        self.humidity_plot.setLabel("left", "Humidity", units="%")
        self.humidity_plot.setLabel("bottom", "Receive time", units="s")
        self.humidity_plot.showGrid(x=True, y=True)
        layout.addWidget(self.humidity_plot)

        # Link the x-axis to the pressure plot here too.
        self.humidity_plot.setXLink(self.pressure_plot)

        # Create the humidity curve.
        self.humidity_curve = self.humidity_plot.plot(
            [],
            [],
            antialias=False,
            autoDownsample=True,
            clipToView=True,
            skipFiniteCheck=True,
        )

        # Rolling x-axis buffer.
        self.x_data = deque(maxlen=history)

        # Rolling pressure buffer.
        self.pressure_data = deque(maxlen=history)

        # Rolling temperature buffer.
        self.temperature_data = deque(maxlen=history)

        # Rolling humidity buffer.
        self.humidity_data = deque(maxlen=history)

        # Create a timer that periodically updates the GUI.
        self.timer = QtCore.QTimer(self)

        # When the timer fires, call our redraw method.
        self.timer.timeout.connect(self.drain_queue_and_redraw)

        # Start the timer.
        # Example:
        #   20 ms -> about 50 redraws per second.
        self.timer.start(refresh_ms)

    def drain_queue_and_redraw(self) -> None:
        # This flag tells us whether any new data arrived.
        changed = False

        # Drain all currently queued samples without blocking.
        while True:
            try:
                receive_time_s, pressure_hpa, temperature_c, humidity_percent = (
                    sample_queue.get_nowait()
                )
            except Empty:
                # Stop once the queue is empty.
                break

            # Append the newest values to each rolling buffer.
            self.x_data.append(receive_time_s)
            self.pressure_data.append(pressure_hpa)
            self.temperature_data.append(temperature_c)
            self.humidity_data.append(humidity_percent)

            # Mark that something changed.
            changed = True

        # Only redraw when new data actually arrived.
        if changed:
            # Update all 3 curves using the same time axis.
            self.pressure_curve.setData(list(self.x_data), list(self.pressure_data))
            self.temperature_curve.setData(list(self.x_data), list(self.temperature_data))
            self.humidity_curve.setData(list(self.x_data), list(self.humidity_data))

    def closeEvent(self, event) -> None:
        # Ask the background thread to stop when the window closes.
        stop_event.set()

        # Continue with normal Qt close handling.
        super().closeEvent(event)


def build_parser() -> argparse.ArgumentParser:
    # Create the top-level argument parser.
    parser = argparse.ArgumentParser(
        description="Windows COM-port sender/receiver demo for BME280-like data."
    )

    # Make role optional.
    #
    # If the user does not provide it, default to "receiver".
    #
    # Valid examples:
    #   python script.py --port COM13
    #   python script.py receiver --port COM13
    #   python script.py sender --port COM12
    parser.add_argument(
        "role",
        nargs="?",                    # Optional positional argument.
        choices=("receiver", "sender"),
        default="receiver",           # Default mode when omitted.
        help="Role to run. Defaults to receiver."
    )

    # Require the serial port explicitly.
    parser.add_argument(
        "--port",
        required=True,
        help="Serial port name, for example COM12 or COM13."
    )

    # Allow baudrate override.
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Serial baudrate."
    )

    # Sender-only setting:
    # how often the fake sender produces a new sample.
    parser.add_argument(
        "--interval-ms",
        type=float,
        default=5.0,
        help="Sender sample interval in milliseconds. 5.0 ms = 200 Hz."
    )

    # Receiver-only setting:
    # number of points kept in the rolling history.
    parser.add_argument(
        "--history",
        type=int,
        default=4000,
        help="Receiver graph history length in points."
    )

    # Receiver-only setting:
    # how often the GUI redraws.
    parser.add_argument(
        "--refresh-ms",
        type=int,
        default=20,
        help="Receiver redraw period in milliseconds. 20 ms ~= 50 FPS."
    )

    # Return the configured parser.
    return parser


def run_sender(args: argparse.Namespace) -> int:
    # Open the requested serial port.
    #
    # serial_for_url also supports pySerial URL handlers,
    # but on Windows you will normally pass a real COM name like COM12.
    ser = serial.serial_for_url(
        args.port,
        baudrate=args.baudrate,
        timeout=0,
        write_timeout=0,
    )

    # Reference time used to create slowly changing fake sensor values.
    t0 = time.perf_counter()

    try:
        # Run until the user stops the program with Ctrl+C.
        while True:
            # Elapsed time in seconds.
            t = time.perf_counter() - t0

            # Generate fake but realistic BME280-like values.
            #
            # Pressure around 1008 hPa with a very small slow variation.
            pressure_hpa = 1008.0 + 0.8 * math.sin(2.0 * math.pi * 0.03 * t)

            # Temperature around 24 °C with slow and small fast ripple.
            temperature_c = (
                24.0
                + 1.8 * math.sin(2.0 * math.pi * 0.07 * t)
                + 0.15 * math.sin(2.0 * math.pi * 1.3 * t)
            )

            # Humidity around 45 % with its own slower variation.
            humidity_percent = 45.0 + 4.0 * math.sin(2.0 * math.pi * 0.05 * t + 1.2)

            # Build one CSV line containing exactly:
            #   pressure,temperature,humidity\n
            #
            # Example:
            #   1008.123,24.532,46.221\n
            line = (
                f"{pressure_hpa:.3f},{temperature_c:.3f},{humidity_percent:.3f}\n"
            ).encode("ascii")

            # Send the line to the COM port.
            ser.write(line)

            # Sleep until the next sample time.
            time.sleep(args.interval_ms / 1000.0)

    except KeyboardInterrupt:
        # Allow graceful exit with Ctrl+C.
        pass
    finally:
        # Always close the serial port before leaving.
        ser.close()

    # Return success exit code.
    return 0


def run_receiver(args: argparse.Namespace) -> int:
    # Clear any old stop request.
    stop_event.clear()

    # Open the serial port for reading.
    try:
        ser = serial.serial_for_url(
            args.port,
            baudrate=args.baudrate,
            timeout=0,
        )
    except serial.SerialException as e:
        print(f"Could not open serial port {args.port}: {e}")
        print("Available ports:")
        for port_info in serial.tools.list_ports.comports():
            print(f"  - {port_info.device} : {port_info.description}")
        return 1

    # Start the background serial reader thread.
    reader = SerialReaderThread(ser)
    reader.start()

    # Create the Qt application object.
    app = QtWidgets.QApplication(sys.argv)

    # Create the live plotting window.
    window = PlotWindow(history=args.history, refresh_ms=args.refresh_ms)

    # Give the window an initial size.
    window.resize(1100, 800)

    # Show the window.
    window.show()

    try:
        # Enter the Qt event loop.
        return app.exec()
    finally:
        # Ask the reader thread to stop.
        stop_event.set()

        # Close the serial port.
        ser.close()


def main() -> int:
    # Build the command-line parser.
    parser = build_parser()

    # Parse the user arguments.
    args = parser.parse_args()

    # If role is sender, run sender mode.
    if args.role == "sender":
        return run_sender(args)

    # Otherwise run receiver mode.
    #
    # Because receiver is the default, this also handles the case where
    # the user omitted the role completely.
    return run_receiver(args)


if __name__ == "__main__":
    # Run main() and exit the process with its return code.
    raise SystemExit(main())