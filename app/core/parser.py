from app.core.constants import SYNC1, SYNC2, VER, MAX_LN
from app.core.crc import crc16_ccitt


class FrameParser:
    """
    Parser robusto:
    - Busca SYNC AA55
    - Lee VER/TYPE/LEN
    - Lee payload + CRC16
    - MAX_LN por seguridad
    - Reporta ok con CRC + VER
    """

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)
        out = []

        while True:
            i = self.buf.find(bytes([SYNC1, SYNC2]))
            if i < 0:
                self.buf = self.buf[-1:]
                break
            if i > 0:
                del self.buf[:i]

            if len(self.buf) < 5:
                break

            _, _, ver, typ, ln = self.buf[:5]

            if ln > MAX_LN:
                # LEN corrupto -> descartar SYNC y reescanear
                del self.buf[:2]
                continue

            need = 5 + ln + 2
            if len(self.buf) < need:
                break

            payload = bytes(self.buf[5 : 5 + ln])
            crc_rx = self.buf[5 + ln] | (self.buf[5 + ln + 1] << 8)
            crc_calc = crc16_ccitt(bytes([ver, typ, ln]) + payload)

            ok = (ver == VER) and (crc_rx == crc_calc)
            out.append((typ, payload, ok, ln, int(crc_rx), int(crc_calc), int(ver)))
            del self.buf[:need]

        return out
