from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6 import QtCore, QtWidgets

from app.core.ai_telemetry import TelemetryAIAnalyzer
from app.ui.instruments import PanelFrame


SYSTEM_INSTRUCTIONS = """
You are the advisory telemetry analyst for an educational rocket Ground Station.
Respond in clear professional Spanish. Use only the supplied telemetry data.
Never invent measurements. Distinguish observations, hypotheses, and checks.
The deterministic local alarms are primary. You must not issue or execute
commands for ignition, actuators, pyrotechnics, parachute deployment, or other
flight-critical systems.
""".strip()


class AIWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(bool, str, str)

    def __init__(self, api_key: str, model: str, summary: Dict[str, Any], question: str):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.summary = summary
        self.question = question

    @QtCore.pyqtSlot()
    def run(self):
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            payload = json.dumps(self.summary, ensure_ascii=False, indent=2, default=str)
            response = client.responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=f"Solicitud del operador:\n{self.question}\n\nDatos de telemetría:\n{payload}",
            )
            text = getattr(response, "output_text", "") or "The API returned no text."
            self.finished.emit(True, text, "")
        except Exception as exc:
            self.finished.emit(False, "La API de IA no está disponible. El análisis local continúa operativo.", f"{type(exc).__name__}: {exc}")


class AITelemetryPage(QtWidgets.QWidget):
    def __init__(self, analyzer: TelemetryAIAnalyzer, parent=None):
        super().__init__(parent)
        self.analyzer = analyzer
        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[AIWorker] = None
        self._build_ui()
        self._update_status()

    def _build_ui(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(5)

        header = PanelFrame("Analista de telemetría con inteligencia artificial", "IA • ASESORAMIENTO")
        header_row = QtWidgets.QHBoxLayout()
        self.lblStatus = QtWidgets.QLabel("ANÁLISIS LOCAL LISTO")
        self.lblStatus.setObjectName("aiStatus")
        self.txtModel = QtWidgets.QLineEdit(os.getenv("OPENAI_MODEL", "gpt-5-mini"))
        self.txtModel.setMaximumWidth(150)
        self.txtModel.setPlaceholderText("API model")
        self.txtKey = QtWidgets.QLineEdit()
        self.txtKey.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.txtKey.setPlaceholderText("OPENAI_API_KEY (temporal)")
        self.txtKey.setText(os.getenv("OPENAI_API_KEY", ""))
        self.txtKey.setMinimumWidth(250)
        self.chkShowKey = QtWidgets.QCheckBox("SHOW KEY")
        self.chkShowKey.toggled.connect(
            lambda checked: self.txtKey.setEchoMode(
                QtWidgets.QLineEdit.EchoMode.Normal if checked else QtWidgets.QLineEdit.EchoMode.Password
            )
        )
        header_row.addWidget(self.lblStatus)
        header_row.addStretch()
        header_row.addWidget(QtWidgets.QLabel("MODEL"))
        header_row.addWidget(self.txtModel)
        header_row.addWidget(QtWidgets.QLabel("API KEY"))
        header_row.addWidget(self.txtKey)
        header_row.addWidget(self.chkShowKey)
        header.addLayout(header_row)
        main.addWidget(header)

        actions = PanelFrame("Analysis actions", "TOOLS")
        row = QtWidgets.QHBoxLayout()
        self.btnLocal = QtWidgets.QPushButton("DIAGNÓSTICO LOCAL")
        self.btn30 = QtWidgets.QPushButton("IA — ÚLTIMOS 30 S")
        self.btn60 = QtWidgets.QPushButton("IA — ÚLTIMOS 60 S")
        self.btnAlarms = QtWidgets.QPushButton("EXPLICAR ALARMAS")
        self.btnReport = QtWidgets.QPushButton("INFORME POSVUELO")
        self.btnSave = QtWidgets.QPushButton("GUARDAR ANÁLISIS")
        for button in (self.btnLocal, self.btn30, self.btn60, self.btnAlarms, self.btnReport, self.btnSave):
            row.addWidget(button)
        row.addStretch()
        actions.addLayout(row)
        main.addWidget(actions)

        query = PanelFrame("Operator query", "QUERY")
        qrow = QtWidgets.QHBoxLayout()
        self.txtQuestion = QtWidgets.QLineEdit("¿Cuál fue la altura máxima y qué anomalías se detectaron?")
        self.btnAsk = QtWidgets.QPushButton("ASK AI")
        qrow.addWidget(self.txtQuestion, 1)
        qrow.addWidget(self.btnAsk)
        query.addLayout(qrow)
        main.addWidget(query)

        lower = QtWidgets.QHBoxLayout()
        output_frame = PanelFrame("Analysis output", "RESULT")
        self.output = QtWidgets.QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setObjectName("aiOutput")
        self.output.setPlainText(
            "ANALISTA IA LISTO\n\n"
            "Inicie SIMULACIÓN, REPRODUCCIÓN o telemetría EN VIVO.\n"
            "El DIAGNÓSTICO LOCAL funciona sin Internet ni clave de API."
        )
        output_frame.addWidget(self.output)
        lower.addWidget(output_frame, 3)

        safety = PanelFrame("Operational boundary", "SAFETY")
        self.lblSafety = QtWidgets.QLabel(
            "SOLO ASESORAMIENTO\n\n"
            "• No ignition control\n"
            "• No actuator commands\n"
            "• No pyrotechnic commands\n"
            "• No parachute deployment\n\n"
            "Local rules and alarms remain primary."
        )
        self.lblSafety.setWordWrap(True)
        self.lblSafety.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        safety.addWidget(self.lblSafety)
        lower.addWidget(safety, 1)
        main.addLayout(lower, 1)

        self.btnLocal.clicked.connect(self.show_local)
        self.btn30.clicked.connect(lambda: self.ask_ai("Analizá los últimos 30 segundos: estado, tendencias, anomalías y verificaciones recomendadas.", 30.0))
        self.btn60.clicked.connect(lambda: self.ask_ai("Analizá el último minuto de telemetría.", 60.0))
        self.btnAlarms.clicked.connect(lambda: self.ask_ai("Explicá las alarmas recientes, posibles causas y verificaciones, sin inventar datos.", None))
        self.btnReport.clicked.connect(self.post_flight_report)
        self.btnSave.clicked.connect(self.save_output)
        self.btnAsk.clicked.connect(lambda: self.ask_ai(self.txtQuestion.text().strip(), None))
        self.txtQuestion.returnPressed.connect(lambda: self.ask_ai(self.txtQuestion.text().strip(), None))

    def _update_status(self):
        if self.txtKey.text().strip() or os.getenv("OPENAI_API_KEY"):
            self.lblStatus.setText("● API CONFIGURADA — LOCAL + NUBE")
            self.lblStatus.setProperty("online", True)
        else:
            self.lblStatus.setText("● SISTEMA LOCAL LISTO — CLAVE API NO CONFIGURADA")
            self.lblStatus.setProperty("online", False)
        self.lblStatus.style().unpolish(self.lblStatus)
        self.lblStatus.style().polish(self.lblStatus)

    def show_local(self):
        self.output.setPlainText(self.analyzer.local_text_report())
        self.lblStatus.setText("● ANÁLISIS LOCAL COMPLETADO")

    def ask_ai(self, question: str, seconds: Optional[float]):
        if not question:
            return
        api_key = self.txtKey.text().strip() or os.getenv("OPENAI_API_KEY", "")
        self._update_status()
        if not api_key:
            self.output.setPlainText(
                self.analyzer.local_text_report(seconds)
                + "\n\nAPI NOT CONFIGURED\nSet OPENAI_API_KEY or paste a temporary key in this panel."
            )
            return
        summary = self.analyzer.summary(seconds)
        if summary.get("status") != "OK":
            self.output.setPlainText("SIN DATOS — Inicie una fuente de telemetría antes de usar el análisis de IA.")
            return
        self._start_worker(api_key, self.txtModel.text().strip() or "gpt-5-mini", summary, question)

    def post_flight_report(self):
        question = (
            "Generá un informe postvuelo profesional con resumen ejecutivo, fases, máximos y mínimos, "
            "calidad del enlace, alarmas, hipótesis claramente marcadas, verificaciones recomendadas y conclusión."
        )
        self.ask_ai(question, None)

    def _start_worker(self, api_key: str, model: str, summary: Dict[str, Any], question: str):
        if self._thread and self._thread.isRunning():
            return
        self._set_busy(True)
        self.output.setPlainText("CONECTANDO CON LA API DE IA…")
        self._thread = QtCore.QThread(self)
        self._worker = AIWorker(api_key, model, summary, question)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @QtCore.pyqtSlot(bool, str, str)
    def _on_finished(self, ok: bool, text: str, error: str):
        self._set_busy(False)
        self.output.setPlainText(text + (f"\n\nDETALLE TÉCNICO\n{error}" if error else ""))
        self.lblStatus.setText("● RESPUESTA DE IA RECIBIDA" if ok else "● IA NO DISPONIBLE — ANÁLISIS LOCAL ACTIVO")
        self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool):
        for button in (self.btn30, self.btn60, self.btnAlarms, self.btnReport, self.btnAsk):
            button.setEnabled(not busy)

    def save_output(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Guardar análisis de IA", "telemetry_ai_analysis.txt", "Archivo de texto (*.txt);;Todos los archivos (*.*)"
        )
        if path:
            Path(path).write_text(self.output.toPlainText(), encoding="utf-8")
