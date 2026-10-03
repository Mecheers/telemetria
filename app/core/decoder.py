import struct
from typing import Optional

from app.core.constants import ANGLE_SCALE
from app.core.frames import FastFrame, SlowFrame


def decode_fast(payload: bytes) -> Optional[FastFrame]:
    ln = len(payload)
    try:
        if ln == 22:
            t_ms, ax, ay, az, gx, gy, gz, roll, pitch, seq = struct.unpack("<IhhhhhhhhH", payload)
            yaw = 0
        elif ln == 24:
            t_ms, ax, ay, az, gx, gy, gz, roll, pitch, yaw, seq = struct.unpack("<IhhhhhhhhhH", payload)
        else:
            return None

        az_g = az / 1000.0
        roll_deg = float(roll) / ANGLE_SCALE
        pitch_deg = float(pitch) / ANGLE_SCALE
        yaw_deg = float(yaw) / ANGLE_SCALE
        return FastFrame(t_ms=t_ms, az_g=az_g, roll_deg=roll_deg, pitch_deg=pitch_deg, yaw_deg=yaw_deg, seq=seq)
    except Exception:
        return None


def decode_slow(payload: bytes) -> Optional[SlowFrame]:
    if len(payload) != 28:
        return None
    try:
        t_ms, alt_cm, temp_cC, press_Pa, lat_e7, lon_e7, gps_alt_cm, sats, fix = struct.unpack("<IihIiiiBB", payload)
        alt_m = alt_cm / 100.0
        return SlowFrame(t_ms=t_ms, alt_m=alt_m, sats=int(sats), fix=int(fix))
    except Exception:
        return None
