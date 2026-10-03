import os
import struct
import time
from PyQt6 import QtCore

from app.core.constants import LOG_MAGIC, LOG_VER, VER


class ReplayWorker(QtCore.QThread):
    frame = QtCore.pyqtSignal(int, bytes, bool, int, int, int, int)  # typ, payload, ok, ln, crc_rx, crc_calc, ver
    status = QtCore.pyqtSignal(str)

    def __init__(self, filename: str, speed: float = 1.0, fastest: bool = False):
        super().__init__()
        self.filename = filename
        self.running = True
        self.speed = max(0.05, float(speed))
        self.fastest = bool(fastest)

    def set_speed(self, speed: float):
        self.speed = max(0.05, float(speed))

    def set_fastest(self, fastest: bool):
        self.fastest = bool(fastest)

    def run(self):
        try:
            with open(self.filename, "rb") as f:
                start = f.read(5)
                is_v2 = False
                if len(start) == 5:
                    magic, ver = struct.unpack("<4sB", start)
                    if magic == LOG_MAGIC and ver == LOG_VER:
                        is_v2 = True
                    else:
                        f.seek(0)
                else:
                    f.seek(0)

                prev_t_pc = None
                self.status.emit(f"REPRODUCCIÓN: {os.path.basename(self.filename)} ({'v2' if is_v2 else 'v1'})")

                while self.running:
                    if is_v2:
                        hdr = f.read(20)
                        if not hdr or len(hdr) < 20:
                            break
                        t_pc, typ, ok, ln, crc_rx, crc_calc, t_ms = struct.unpack("<dBBHHHI", hdr)
                        payload = f.read(ln)
                        if len(payload) < ln:
                            break

                        if prev_t_pc is not None and not self.fastest:
                            dt = (t_pc - prev_t_pc) / self.speed
                            if dt > 0:
                                time.sleep(min(dt, 0.2))
                        prev_t_pc = t_pc

                        self.frame.emit(int(typ), payload, bool(ok), int(ln), int(crc_rx), int(crc_calc), VER)
                    else:
                        hdr = f.read(8 + 1 + 1 + 2)
                        if not hdr or len(hdr) < (8 + 1 + 1 + 2):
                            break
                        t_pc, typ, ok, ln = struct.unpack("<dBBH", hdr)
                        payload = f.read(ln)
                        if len(payload) < ln:
                            break

                        if prev_t_pc is not None and not self.fastest:
                            dt = (t_pc - prev_t_pc) / self.speed
                            if dt > 0:
                                time.sleep(min(dt, 0.2))
                        prev_t_pc = t_pc

                        self.frame.emit(int(typ), payload, bool(ok), int(ln), 0, 0, VER)

                self.status.emit("REPRODUCCIÓN: fin")
        except Exception as e:
            self.status.emit(f"ERROR DE REPRODUCCIÓN: {e!r}")

    def stop(self):
        self.running = False
