from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from statistics import mean
from typing import Any, Deque, Dict, List, Optional


@dataclass
class LocalAlert:
    timestamp: str
    severity: str
    code: str
    message: str
    value: Optional[float] = None
    limit: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TelemetryAIAnalyzer:
    """Historial y análisis determinístico para el asistente IA.

    No controla hardware. Funciona sin conexión a Internet y evita duplicar
    muestras cuando la UI se actualiza varias veces con el mismo t_ms/seq.
    """

    def __init__(self, max_samples: int = 18000):
        self.samples: Deque[Dict[str, Any]] = deque(maxlen=max_samples)
        self.alerts: Deque[LocalAlert] = deque(maxlen=1000)
        self._last_signature: Optional[tuple] = None
        self._last_alert_at: Dict[str, float] = {}
        self.received_packets = 0
        self.expected_packets = 0
        self._previous_seq: Optional[int] = None

    @staticmethod
    def _num(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(data.get(key, default))
        except (TypeError, ValueError):
            return default

    def add_sample(self, telemetry: Dict[str, Any], mode: str = "LIVE") -> List[LocalAlert]:
        sample = dict(telemetry)
        sample["mode"] = mode
        sample["captured_at"] = datetime.now().isoformat(timespec="milliseconds")

        signature = (sample.get("t_ms"), sample.get("seq"), mode)
        if signature == self._last_signature:
            return []
        self._last_signature = signature

        seq = int(self._num(sample, "seq", 0)) & 0xFFFF
        if self._previous_seq is None:
            self.expected_packets += 1
        else:
            delta = (seq - self._previous_seq) & 0xFFFF
            self.expected_packets += max(1, min(delta, 2000))
        self.received_packets += 1
        self._previous_seq = seq

        if self.expected_packets:
            sample["packet_loss_pct"] = max(
                0.0,
                100.0 * (self.expected_packets - self.received_packets) / self.expected_packets,
            )
        else:
            sample["packet_loss_pct"] = 0.0

        self.samples.append(sample)
        return self._evaluate(sample)

    def _emit(
        self,
        code: str,
        severity: str,
        message: str,
        value: float,
        limit: float,
        cooldown_s: float = 8.0,
    ) -> Optional[LocalAlert]:
        import time

        now = time.time()
        if now - self._last_alert_at.get(code, 0.0) < cooldown_s:
            return None
        self._last_alert_at[code] = now
        alert = LocalAlert(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            severity=severity,
            code=code,
            message=message,
            value=value,
            limit=limit,
        )
        self.alerts.append(alert)
        return alert

    def _evaluate(self, sample: Dict[str, Any]) -> List[LocalAlert]:
        found: List[LocalAlert] = []
        checks = [
            ("BATTERY_LOW", "HIGH", "Batería por debajo del límite", self._num(sample, "battery_v"), 10.5, lambda v, l: v < l),
            ("TEMP_HIGH", "HIGH", "Temperatura elevada", self._num(sample, "temp_c"), 60.0, lambda v, l: v > l),
            ("DESCENT_FAST", "CRITICAL", "Velocidad de descenso excesiva", self._num(sample, "vspeed"), -25.0, lambda v, l: v < l),
            ("G_HIGH", "HIGH", "Carga axial elevada", abs(self._num(sample, "az_g")), 6.0, lambda v, l: v > l),
            ("PACKET_LOSS", "HIGH", "Pérdida de paquetes elevada", self._num(sample, "packet_loss_pct"), 20.0, lambda v, l: v > l),
        ]
        for code, severity, message, value, limit, condition in checks:
            if condition(value, limit):
                alert = self._emit(code, severity, message, value, limit)
                if alert:
                    found.append(alert)
        return found

    def window(self, seconds: Optional[float]) -> List[Dict[str, Any]]:
        data = list(self.samples)
        if seconds is None or not data:
            return data
        latest = self._num(data[-1], "t_ms") / 1000.0
        selected: List[Dict[str, Any]] = []
        for item in reversed(data):
            t = self._num(item, "t_ms") / 1000.0
            if latest - t <= seconds:
                selected.append(item)
            else:
                break
        return list(reversed(selected))

    def summary(self, seconds: Optional[float] = None) -> Dict[str, Any]:
        data = self.window(seconds)
        if not data:
            return {"status": "NO_DATA", "samples": 0}

        keys = ("alt_m", "vspeed", "az_g", "roll", "pitch", "yaw", "temp_c", "pressure_hpa", "humidity", "battery_v", "sats", "packet_loss_pct")
        stats: Dict[str, Dict[str, float]] = {}
        for key in keys:
            values = [self._num(item, key) for item in data if item.get(key) is not None]
            if values:
                stats[key] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": mean(values),
                    "last": values[-1],
                }

        return {
            "status": "OK",
            "samples": len(data),
            "window_seconds": seconds,
            "latest_sample": data[-1],
            "statistics": stats,
            "link": {
                "received_packets": self.received_packets,
                "expected_packets": self.expected_packets,
                "packet_loss_pct": stats.get("packet_loss_pct", {}).get("last", 0.0),
            },
            "recent_local_alerts": [item.as_dict() for item in list(self.alerts)[-25:]],
        }


    def attitude_assistance(self) -> Dict[str, Any]:
        """Genera una ayuda compacta para la pantalla de actitud.

        Se basa en la ventana reciente y en reglas locales explicables. El
        resultado es consultivo y nunca acciona hardware.
        """
        data = self.window(8.0)
        if len(data) < 3:
            return {"status": "NO_DATA"}

        latest = data[-1]
        roll = abs(self._num(latest, "roll"))
        pitch = abs(self._num(latest, "pitch"))
        vspeed = self._num(latest, "vspeed")
        g_load = abs(self._num(latest, "az_g"))
        packet_loss = self._num(latest, "packet_loss_pct")
        sats = self._num(latest, "sats")
        altitude = self._num(latest, "alt_m")

        # Variación reciente: una actitud que cambia rápidamente reduce estabilidad.
        rolls = [self._num(item, "roll") for item in data]
        pitches = [self._num(item, "pitch") for item in data]
        roll_span = max(rolls) - min(rolls)
        pitch_span = max(pitches) - min(pitches)

        penalty = 0.0
        penalty += min(28.0, roll * 0.55)
        penalty += min(28.0, pitch * 0.55)
        penalty += min(18.0, roll_span * 0.45 + pitch_span * 0.45)
        penalty += min(14.0, max(0.0, g_load - 1.0) * 3.0)
        penalty += min(12.0, packet_loss * 0.45)
        stability = max(0.0, 100.0 - penalty)

        if altitude < 5.0 and abs(vspeed) < 1.5:
            phase = "GROUND"
        elif vspeed > 5.0 and g_load > 1.3:
            phase = "BOOST"
        elif vspeed > 2.0:
            phase = "ASCENT"
        elif abs(vspeed) <= 2.0 and altitude > 10.0:
            phase = "APOGEE"
        elif vspeed < -2.0:
            phase = "DESCENT"
        else:
            phase = "FLIGHT"

        critical = (
            roll > 55.0 or pitch > 55.0 or g_load > 6.0 or
            vspeed < -25.0 or packet_loss > 20.0
        )
        warning = (
            roll > 30.0 or pitch > 30.0 or g_load > 3.5 or
            vspeed < -15.0 or packet_loss > 8.0 or sats < 4.0
        )
        risk = "HIGH" if critical else "MEDIUM" if warning else "LOW"

        if roll_span + pitch_span > 35.0:
            trend = "se detectó una variación rápida de actitud"
        elif roll > 25.0 or pitch > 25.0:
            trend = "inclinación sostenida fuera de la zona nominal"
        elif packet_loss > 8.0:
            trend = "actitud estable; la calidad del enlace de telemetría se está degradando"
        elif g_load > 3.5:
            trend = "actitud coherente; se observa carga axial elevada"
        else:
            trend = "la actitud y el movimiento reciente permanecen dentro del rango esperado"

        if risk == "HIGH":
            recommendation = "priorice las alarmas locales y verifique la actitud, la velocidad de descenso y la integridad del enlace"
        elif risk == "MEDIUM":
            recommendation = "aumente la frecuencia de supervisión y compare la actitud con la velocidad vertical y la carga G"
        elif phase == "APOGEE":
            recommendation = "confirme la transición al descenso y vigile cambios bruscos de actitud"
        elif phase == "DESCENT":
            recommendation = "supervise la velocidad de descenso, la oscilación de actitud y la posición de aterrizaje"
        elif phase in ("BOOST", "ASCENT"):
            recommendation = "continúe supervisando la estabilidad de actitud, la carga axial y la calidad de las comunicaciones"
        else:
            recommendation = "los parámetros de vuelo son coherentes; continúe la supervisión normal"

        completeness = sum(1 for key in ("roll", "pitch", "yaw", "vspeed", "az_g", "alt_m", "sats") if latest.get(key) is not None)
        confidence = min(98.0, 45.0 + len(data) * 1.8 + completeness * 4.0)
        if packet_loss > 10.0:
            confidence = max(25.0, confidence - packet_loss * 0.8)

        return {
            "status": "OK",
            "stability_score": stability,
            "risk_level": risk,
            "confidence_pct": confidence,
            "phase": phase,
            "trend": trend,
            "recommendation": recommendation,
            "roll_abs_deg": roll,
            "pitch_abs_deg": pitch,
            "g_load": g_load,
            "vertical_speed_m_s": vspeed,
            "packet_loss_pct": packet_loss,
        }

    def local_text_report(self, seconds: Optional[float] = None) -> str:
        summary = self.summary(seconds)
        if summary.get("status") != "OK":
            return "NO DATA — Inicie una simulación, replay o enlace serial antes de analizar."
        st = summary["statistics"]
        latest = summary["latest_sample"]

        def stat(key: str, field: str = "last", digits: int = 2) -> str:
            value = st.get(key, {}).get(field)
            return "—" if value is None else f"{value:.{digits}f}"

        lines = [
            "ANÁLISIS LOCAL DEL VUELO",
            "=" * 56,
            f"Muestras analizadas : {summary['samples']}",
            f"Modo de operación   : {latest.get('mode', '—')}",
            f"Altitud actual      : {stat('alt_m')} m",
            f"Altitud máxima      : {stat('alt_m', 'max')} m",
            f"Velocidad vertical  : {stat('vspeed')} m/s",
            f"Máximo |G|          : {max(abs(st.get('az_g', {}).get('min', 0.0)), abs(st.get('az_g', {}).get('max', 0.0))):.2f} g",
            f"Temperatura         : {stat('temp_c')} °C",
            f"Batería             : {stat('battery_v')} V",
            f"Satélites           : {stat('sats', digits=0)}",
            f"Pérdida de paquetes : {summary['link']['packet_loss_pct']:.2f} %",
            "",
            "ALERTAS LOCALES",
        ]
        alerts = summary["recent_local_alerts"]
        if alerts:
            lines.extend(f"[{a['severity']}] {a['message']} ({a['value']:.2f})" for a in alerts)
        else:
            lines.append("No se detectaron alarmas locales por umbral.")
        lines.extend([
            "",
            "NOTA",
            "El módulo de IA es únicamente consultivo. Las alarmas determinísticas locales siguen siendo prioritarias.",
        ])
        return "\n".join(lines)
