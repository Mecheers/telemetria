import struct
import time
from typing import Optional

from app.core.constants import LOG_MAGIC, LOG_VER


class FlightLogger:
    """
    v2:
      Header: [4s 'TLOG'][B ver]
      Frame : [double t_pc][B typ][B ok][H ln][H crc_rx][H crc_calc][I t_ms][payload...]
    """

    def __init__(self):
        self.f = None
        self.filename: Optional[str] = None

    def start(self, filename: str):
        self.stop()
        self.filename = filename
        self.f = open(filename, "wb")
        self.f.write(struct.pack("<4sB", LOG_MAGIC, LOG_VER))

    def stop(self):
        if self.f:
            try:
                self.f.close()
            except Exception:
                pass
        self.f = None
        self.filename = None

    def is_recording(self) -> bool:
        return self.f is not None

    def _extract_t_ms(self, payload: bytes) -> int:
        if not payload or len(payload) < 4:
            return 0xFFFFFFFF
        return struct.unpack_from("<I", payload, 0)[0]

    def log_frame(self, typ: int, payload: bytes, ok: bool, crc_rx: int, crc_calc: int):
        if not self.f:
            return
        t_pc = time.time()
        t_ms = self._extract_t_ms(payload)
        ln = len(payload)
        self.f.write(struct.pack("<dBBHHHI", t_pc, typ, int(ok), ln, crc_rx & 0xFFFF, crc_calc & 0xFFFF, t_ms))
        self.f.write(payload)
