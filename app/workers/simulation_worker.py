import math
import random
import struct
import time

from PyQt6 import QtCore

from app.core.constants import VER, TYPE_FAST, TYPE_SLOW


class SimulationWorker(QtCore.QObject):
    """Simulador local basado en QTimer.

    Se ejecuta en el mismo hilo de la interfaz para evitar problemas de QThread,
    señales perdidas o cierres silenciosos en Windows.
    Mantiene la misma API usada por MainWindow: start(), stop() y wait().
    """

    frame = QtCore.pyqtSignal(int, bytes, bool, int, int, int, int)
    status = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()

    def __init__(self, scenario: str = "Vuelo completo", parent=None, profile=None):
        super().__init__(parent)
        self.scenario = scenario
        self.profile = profile or {}
        self.packet_loss_pct = float(self.profile.get("packet_loss_pct", 0.0))
        self.crc_error_pct = float(self.profile.get("crc_error_pct", 0.0))
        self.gps_dropout_pct = float(self.profile.get("gps_dropout_pct", 0.0))
        self.noise = float(self.profile.get("noise", 0.015))
        self._running = False
        self._seq = 0
        self._t0 = 0.0
        self._next_fast = 0.0
        self._next_slow = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._tick)

    def start(self):
        if self._running:
            return
        self._running = True
        self._seq = 0
        self._t0 = time.perf_counter()
        self._next_fast = 0.0
        self._next_slow = 0.0
        self.status.emit(f"SIMULACIÓN ACTIVA — {self.scenario}")
        # Emitir inmediatamente un ciclo para que el usuario vea respuesta al pulsar.
        self._tick()
        self._timer.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self.status.emit("SIMULACIÓN DETENIDA")
        self.finished.emit()

    def wait(self, _milliseconds: int = 0):
        """Compatibilidad con la API anterior basada en QThread."""
        return True

    def isRunning(self):
        return self._running

    def _flight_state(self, t: float):
        if self.scenario == "Banco de instrumentos":
            alt = 120.0 + 25.0 * math.sin(t * 0.22)
            az = 1.0 + 0.35 * math.sin(t * 1.7)
            roll = 35.0 * math.sin(t * 0.48)
            pitch = 18.0 * math.sin(t * 0.34 + 0.8)
            yaw = (t * 13.0) % 360.0
            return alt, az, roll, pitch, yaw

        if self.scenario == "Ascenso continuo":
            alt = min(1200.0, 3.0 * t + 0.12 * t * t)
            az = 1.35 + 0.20 * math.sin(t * 2.0)
            roll = 5.0 * math.sin(t * 0.8)
            pitch = 8.0 + 3.0 * math.sin(t * 0.4)
            yaw = (25.0 + t * 2.0) % 360.0
            return alt, az, roll, pitch, yaw

        cycle = t % 70.0
        if cycle < 5.0:
            alt, az, pitch, roll = 0.0, 1.0, 0.0, 0.0
        elif cycle < 13.0:
            u = cycle - 5.0
            alt = 4.0 * u * u
            az = 2.7 - 0.08 * u + 0.12 * math.sin(u * 4.0)
            pitch = 3.0 + 0.7 * u
            roll = 2.0 * math.sin(u * 1.8)
        elif cycle < 35.0:
            u = cycle - 13.0
            alt = 256.0 + 26.0 * u - 0.56 * u * u
            az = 0.15 + 0.08 * math.sin(u * 1.3)
            pitch = max(-3.0, 8.6 - 0.55 * u)
            roll = 6.0 * math.sin(u * 0.45)
        else:
            u = cycle - 35.0
            alt = max(0.0, 524.0 - 6.0 * u - 0.18 * u * u)
            az = 0.92 + 0.10 * math.sin(u * 1.1)
            pitch = -8.0 + 3.0 * math.sin(u * 0.28)
            roll = 12.0 * math.sin(u * 0.35)
        yaw = (42.0 + cycle * 2.2 + 8.0 * math.sin(cycle * 0.2)) % 360.0
        return alt, az, roll, pitch, yaw

    def _emit_fast(self, t: float, az: float, roll: float, pitch: float, yaw: float):
        t_ms = int(t * 1000.0) & 0xFFFFFFFF
        ax = int(80 * math.sin(t * 1.4))
        ay = int(60 * math.sin(t * 1.1 + 0.7))
        az_raw = int((az + random.uniform(-self.noise, self.noise)) * 1000)
        gx = int(roll * 10)
        gy = int(pitch * 10)
        yaw_signed = ((yaw + 180.0) % 360.0) - 180.0
        gz = int(yaw_signed * 2)
        roll_raw = int(max(-327.67, min(327.67, roll)) * 100)
        pitch_raw = int(max(-327.67, min(327.67, pitch)) * 100)
        yaw_raw = int(max(-327.67, min(327.67, yaw_signed)) * 100)
        payload = struct.pack(
            "<IhhhhhhhhhH",
            t_ms, ax, ay, az_raw, gx, gy, gz,
            roll_raw, pitch_raw, yaw_raw, self._seq,
        )
        if random.random()*100.0 < self.packet_loss_pct:
            return
        good = random.random()*100.0 >= self.crc_error_pct
        self.frame.emit(TYPE_FAST, payload, good, len(payload), 0 if good else 1, 0, VER)
        self._seq = (self._seq + 1) & 0xFFFF

    def _emit_slow(self, t: float, alt: float):
        t_ms = int(t * 1000.0) & 0xFFFFFFFF
        alt_cm = int((alt + random.uniform(-0.08, 0.08)) * 100)
        temp_cC = int((22.0 + 1.5 * math.sin(t * 0.05)) * 100)
        press_pa = int(101325 * math.exp(-max(0.0, alt) / 8434.5))
        lat = -31.3880 + 0.00015 * math.sin(t * 0.025)
        lon = -57.9601 + 0.00015 * math.cos(t * 0.025)
        fix, sats = (0, 0) if random.random()*100.0 < self.gps_dropout_pct else (3, 11)
        payload = struct.pack(
            "<IihIiiiBB",
            t_ms,
            alt_cm,
            temp_cC,
            press_pa,
            int(lat * 1e7),
            int(lon * 1e7),
            alt_cm,
            sats,
            fix,
        )
        if random.random()*100.0 < self.packet_loss_pct:
            return
        good = random.random()*100.0 >= self.crc_error_pct
        self.frame.emit(TYPE_SLOW, payload, good, len(payload), 0 if good else 1, 0, VER)

    @QtCore.pyqtSlot()
    def _tick(self):
        if not self._running:
            return
        try:
            t = time.perf_counter() - self._t0
            alt, az, roll, pitch, yaw = self._flight_state(t)

            # Recuperación por atraso: no genera una ráfaga infinita de frames.
            if t >= self._next_fast:
                self._emit_fast(t, az, roll, pitch, yaw)
                self._next_fast = t + 0.05

            if t >= self._next_slow:
                self._emit_slow(t, alt)
                self._next_slow = t + 0.25
        except Exception as exc:
            self._timer.stop()
            self._running = False
            self.error.emit(f"ERROR SIMULADOR: {type(exc).__name__}: {exc}")
            self.finished.emit()
