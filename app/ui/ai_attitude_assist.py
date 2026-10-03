from __future__ import annotations

from typing import Any, Dict
from PyQt6 import QtCore, QtWidgets


class AIAttitudeAssistWidget(QtWidgets.QFrame):
    """Panel compacto de asistencia IA para la página ATTITUDE.

    Presenta inferencias locales y determinísticas. No ejecuta comandos ni
    sustituye las alarmas principales de la estación terrestre.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aiAttitudeAssist")
        self.setMinimumHeight(170)
        self._build()

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 8)
        root.setSpacing(5)

        top = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("ASISTENCIA IA DE VUELO")
        title.setObjectName("aiAssistTitle")
        self.badge = QtWidgets.QLabel("MODELO LOCAL")
        self.badge.setObjectName("aiAssistBadge")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.badge)
        root.addLayout(top)

        metrics = QtWidgets.QGridLayout()
        metrics.setHorizontalSpacing(8)
        metrics.setVerticalSpacing(3)
        self.stability = self._metric(metrics, 0, "ESTABILIDAD", "---")
        self.risk = self._metric(metrics, 1, "RIESGO", "---")
        self.confidence = self._metric(metrics, 2, "CONFIANZA", "---")
        self.phase = self._metric(metrics, 3, "FASE", "---")
        root.addLayout(metrics)

        self.stability_bar = QtWidgets.QProgressBar()
        self.stability_bar.setObjectName("aiStabilityBar")
        self.stability_bar.setRange(0, 100)
        self.stability_bar.setValue(0)
        self.stability_bar.setFormat("ESTABILIDAD  %p%")
        root.addWidget(self.stability_bar)

        self.trend = QtWidgets.QLabel("TENDENCIA: esperando telemetría")
        self.trend.setObjectName("aiAssistTrend")
        self.trend.setWordWrap(True)
        root.addWidget(self.trend)

        self.recommendation = QtWidgets.QLabel("RECOMENDACIÓN: inicie telemetría o simulación")
        self.recommendation.setObjectName("aiAssistAdvice")
        self.recommendation.setWordWrap(True)
        root.addWidget(self.recommendation, 1)

        note = QtWidgets.QLabel("SOLO ASESORAMIENTO • SIN ÓRDENES DE CONTROL DE VUELO")
        note.setObjectName("aiAssistNote")
        root.addWidget(note)

    def _metric(self, layout, column: int, label: str, value: str):
        box = QtWidgets.QFrame()
        box.setObjectName("aiMetricBox")
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(5, 3, 5, 3)
        lay.setSpacing(0)
        lab = QtWidgets.QLabel(label)
        lab.setObjectName("aiMetricLabel")
        val = QtWidgets.QLabel(value)
        val.setObjectName("aiMetricValue")
        val.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lab)
        lay.addWidget(val)
        layout.addWidget(box, 0, column)
        return val

    @staticmethod
    def _set_state(widget: QtWidgets.QWidget, state: str):
        widget.setProperty("state", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def update_assistance(self, data: Dict[str, Any]):
        if not data or data.get("status") != "OK":
            self.stability.setText("---")
            self.risk.setText("NO DATA")
            self.confidence.setText("0%")
            self.phase.setText("STANDBY")
            self.stability_bar.setValue(0)
            self.trend.setText("TENDENCIA: esperando telemetría")
            self.recommendation.setText("RECOMENDACIÓN: inicie telemetría o simulación")
            self._set_state(self.risk, "neutral")
            return

        score = int(round(float(data.get("stability_score", 0))))
        risk = str(data.get("risk_level", "UNKNOWN"))
        confidence = int(round(float(data.get("confidence_pct", 0))))
        phase = str(data.get("phase", "UNKNOWN"))
        self.stability.setText(f"{score}%")
        self.risk.setText({"LOW":"BAJO","MEDIUM":"MEDIO","HIGH":"ALTO"}.get(risk, risk))
        self.confidence.setText(f"{confidence}%")
        self.phase.setText(phase)
        self.stability_bar.setValue(max(0, min(100, score)))
        self.trend.setText(f"TENDENCIA: {data.get('trend', 'datos insuficientes')}")
        self.recommendation.setText(f"RECOMENDACIÓN: {data.get('recommendation', 'continuar supervisando')}")

        state = "safe" if risk == "LOW" else "warn" if risk == "MEDIUM" else "critical"
        self._set_state(self.risk, state)
        self._set_state(self.recommendation, state)
        self._set_state(self.stability_bar, state)
