from dataclasses import dataclass


@dataclass
class FastFrame:
    t_ms: int
    az_g: float
    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    seq: int


@dataclass
class SlowFrame:
    t_ms: int
    alt_m: float
    sats: int
    fix: int
