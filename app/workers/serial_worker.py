import serial
from PyQt6 import QtCore

from app.core.parser import FrameParser


class SerialWorker(QtCore.QThread):
    frame = QtCore.pyqtSignal(int, bytes, bool, int, int, int, int)  # typ, payload, ok, ln, crc_rx, crc_calc, ver
    status = QtCore.pyqtSignal(str)
    connected = QtCore.pyqtSignal(str, int)
    disconnected = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, port: str, baud: int = 9600):
        super().__init__()
        self.port = port
        self.baud = baud
        self.running = True
        self.parser = FrameParser()
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.05)
            self.connected.emit(self.port, self.baud)
            self.status.emit(f"Conectado a {self.port} @ {self.baud}")
            while self.running:
                data = self.ser.read(2048)
                if data:
                    for typ, payload, ok, ln, crc_rx, crc_calc, ver in self.parser.feed(data):
                        self.frame.emit(typ, payload, ok, ln, crc_rx, crc_calc, ver)
        except Exception as e:
            message = f"Serial error: {e!r}"
            self.error.emit(message)
            self.status.emit(message)
        finally:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.disconnected.emit()

    def stop(self):
        self.running = False
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass

    def send(self, b: bytes):
        try:
            if self.ser and self.ser.is_open:
                self.ser.write(b)
        except Exception:
            pass
