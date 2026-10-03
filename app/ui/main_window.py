import os
import csv
import time
import struct
import json
from datetime import datetime
from collections import deque
from typing import Optional

import numpy as np
import pyqtgraph as pg
import serial.tools.list_ports
from PyQt6 import QtWidgets, QtCore, QtGui

from app.core.constants import VER, TYPE_FAST, TYPE_SLOW, ATT_ALPHA, LOG_MAGIC, LOG_VER
from app.core.decoder import decode_fast, decode_slow
from app.core.logger import FlightLogger
from app.workers.serial_worker import SerialWorker
from app.workers.replay_worker import ReplayWorker
from app.workers.simulation_worker import SimulationWorker
from app.ui.rocket_3d import Rocket3DWidget
from app.ui.status_panel import StatusPanel
from app.ui.esc_filter import EscFilter
from app.ui.instruments import PanelFrame, ValueTile, AttitudeIndicator, CircularGauge, HeadingGauge, BodyRatesWidget
from app.core.professional import ConfigManager, AlarmManager, PhaseDetector, MissionSession, AppDiagnostics
from app.core.reporting import generate_html_report
from app.ui.professional_dialogs import SettingsDialog, ManualSimulationDialog
from app.core.ai_telemetry import TelemetryAIAnalyzer
from app.ui.ai_attitude_assist import AIAttitudeAssistWidget
from app.ui.ai_panel import AITelemetryPage


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QtCore.QSettings("TelemetriaSpace", "GroundStationTelemetry")
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.config_manager = ConfigManager(self.base_dir)
        self.config = self.config_manager.data
        self.alarm_manager = AlarmManager(self.config["limits"])
        self.phase_detector = PhaseDetector()
        self.mission_session = MissionSession(self.base_dir)
        self.application_log = AppDiagnostics.install(self.base_dir)
        self.ai_analyzer = TelemetryAIAnalyzer()

        self.setWindowTitle("Estación Terrestre – Telemetría + Asistencia IA de Actitud v2.2")
        self.resize(1366, 768)
        self.setMinimumSize(1200, 700)

        central = QtWidgets.QWidget()
        central.setObjectName("consoleRoot")
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(5)

        # MISSION HEADER
        header = QtWidgets.QFrame()
        header.setObjectName("missionHeader")
        h = QtWidgets.QHBoxLayout(header)
        h.setContentsMargins(10, 5, 10, 5)
        h.setSpacing(8)
        brand = QtWidgets.QLabel("◢  ESTACIÓN TERRESTRE")
        brand.setObjectName("brandLabel")
        h.addWidget(brand)
        self.navButtons = []
        self.navGroup = QtWidgets.QButtonGroup(self)
        self.navGroup.setExclusive(True)
        for text in ("MISIÓN", "PANEL GENERAL", "ACTITUD", "GPS", "AMBIENTE", "SERIE", "REGISTRO / REPRODUCCIÓN", "ANALISTA IA"):
            b = QtWidgets.QPushButton(text)
            b.setObjectName("navButtonActive" if text == "ACTITUD" else "navButton")
            b.setFlat(True)
            b.setCheckable(True)
            b.setChecked(text == "ACTITUD")
            self.navButtons.append(b)
            self.navGroup.addButton(b)
            h.addWidget(b)
        h.addStretch()
        self.lblMode = QtWidgets.QLabel("● EN VIVO")
        self.lblMode.setObjectName("liveBadge")
        self.lblClock = QtWidgets.QLabel("00:00:00")
        self.lblClock.setObjectName("clockLabel")
        h.addWidget(self.lblMode)
        h.addWidget(self.lblClock)
        self.btnCloseApp = QtWidgets.QPushButton("✕ CERRAR")
        self.btnCloseApp.setObjectName("closeAppButton")
        self.btnCloseApp.setToolTip("Cerrar Ground Station de forma segura")
        h.addWidget(self.btnCloseApp)
        root.addWidget(header)

        # OPERATIONS BAR
        ops = QtWidgets.QFrame(); ops.setObjectName("operationsBar")
        top = QtWidgets.QHBoxLayout(ops); top.setContentsMargins(8,4,8,4); top.setSpacing(6)
        self.cmbPorts = QtWidgets.QComboBox(); self.cmbPorts.setMinimumWidth(105)
        self.btnPorts = QtWidgets.QPushButton("BUSCAR")
        self._refresh_ports()
        self.btnConn = QtWidgets.QPushButton("CONECTAR")
        self.btnDisc = QtWidgets.QPushButton("DESCONECTAR"); self.btnDisc.setEnabled(False)
        self.btnReset = QtWidgets.QPushButton("REINICIAR"); self.btnReset.setEnabled(False)
        self.btnRec = QtWidgets.QPushButton("● GRABAR")
        self.btnStopRec = QtWidgets.QPushButton("DETENER"); self.btnStopRec.setEnabled(False)
        self.btnReplay = QtWidgets.QPushButton("REPRODUCIR")
        self.cmbSim = QtWidgets.QComboBox()
        self.cmbSim.addItems(["Vuelo completo", "Ascenso continuo", "Banco de instrumentos"])
        self.cmbSim.setMinimumWidth(145)
        self.btnSim = QtWidgets.QPushButton("▶ SIMULAR")
        self.btnStopSim = QtWidgets.QPushButton("■ DETENER SIM.")
        self.btnStopSim.setEnabled(False)
        self.btnExportCSV = QtWidgets.QPushButton("EXPORTAR CSV")
        self.btnSettings = QtWidgets.QPushButton("CONFIGURACIÓN")
        self.btnReport = QtWidgets.QPushButton("INFORME DE MISIÓN")
        self.btnManualSim = QtWidgets.QPushButton("BANCO MANUAL")
        self.chkFreeze = QtWidgets.QCheckBox("CONGELAR")
        self.chkAutofit = QtWidgets.QCheckBox("AJUSTE AUTOMÁTICO"); self.chkAutofit.setChecked(True)
        self.chkChase = QtWidgets.QCheckBox("CÁMARA DE SEGUIMIENTO"); self.chkChase.setChecked(True)
        self.btnResetTrail = QtWidgets.QPushButton("BORRAR TRAYECTORIA")
        self.lblReplaySpeed = QtWidgets.QLabel("1.0×")
        self.sldReplay = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal); self.sldReplay.setRange(5,30); self.sldReplay.setValue(10); self.sldReplay.setFixedWidth(105)
        self.chkFastestReplay = QtWidgets.QCheckBox("MAX")
        for w in (QtWidgets.QLabel("PUERTO"), self.cmbPorts, self.btnPorts, self.btnConn, self.btnDisc, self.btnReset, self.btnRec, self.btnStopRec, self.btnReplay, self.btnExportCSV):
            top.addWidget(w)
        top.addStretch()
        for w in (self.chkFreeze, self.chkAutofit, self.chkChase, self.btnResetTrail, self.lblReplaySpeed, self.sldReplay, self.chkFastestReplay):
            top.addWidget(w)
        root.addWidget(ops)

        # SIMULATOR BAR: always visible and deliberately separated from the crowded serial toolbar.
        simbar = QtWidgets.QFrame(); simbar.setObjectName("simulatorBar")
        simlay = QtWidgets.QHBoxLayout(simbar); simlay.setContentsMargins(8,5,8,5); simlay.setSpacing(8)
        simtitle = QtWidgets.QLabel("SIMULADOR EN PC"); simtitle.setObjectName("simulatorTitle")
        self.btnSim.setObjectName("simStartButton")
        self.btnStopSim.setObjectName("simStopButton")
        self.btnSim.setMinimumWidth(150); self.btnStopSim.setMinimumWidth(135)
        self.btnSim.setMinimumHeight(30); self.btnStopSim.setMinimumHeight(30)
        simlay.addWidget(simtitle)
        simlay.addWidget(QtWidgets.QLabel("ESCENARIO"))
        simlay.addWidget(self.cmbSim)
        simlay.addWidget(self.btnSim)
        simlay.addWidget(self.btnStopSim)
        simlay.addWidget(self.btnManualSim)
        simlay.addWidget(self.btnSettings)
        simlay.addWidget(self.btnReport)
        simlay.addStretch()
        self.lblSimDiag = QtWidgets.QLabel("LISTO — pulse SIMULAR")
        self.lblSimDiag.setObjectName("simDiagnostic")
        simlay.addWidget(self.lblSimDiag)
        root.addWidget(simbar)

        self.lblStatus = QtWidgets.QLabel("SISTEMA EN ESPERA — SIN ENLACE DE TELEMETRÍA")
        self.lblStatus.setObjectName("systemStatus")
        self.lblCounters = QtWidgets.QLabel("BYTES 0   |   TRAMAS CORRECTAS 0   |   CRC ERRÓNEOS 0   |   ÚLTIMA —")
        self.lblCounters.setObjectName("counterStrip")
        status_row = QtWidgets.QHBoxLayout(); status_row.addWidget(self.lblStatus,1); status_row.addWidget(self.lblCounters,2)
        root.addLayout(status_row)

        # FUNCTIONAL PAGE STACK
        self.pageStack = QtWidgets.QStackedWidget()
        self.pageStack.setObjectName("pageStack")
        root.addWidget(self.pageStack, 1)

        attitude_page = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(attitude_page); grid.setContentsMargins(0,0,0,0); grid.setSpacing(5)

        self.attitude = AttitudeIndicator()
        p_att = PanelFrame("Pantalla primaria de vuelo", "PPV"); p_att.addWidget(self.attitude)
        tiles = QtWidgets.QHBoxLayout()
        self.tileAlt = ValueTile("ALTITUD", "m"); self.tileAz = ValueTile("CARGA", "g"); self.tileGps = ValueTile("GPS", "posición/sat.")
        tiles.addWidget(self.tileAlt); tiles.addWidget(self.tileAz); tiles.addWidget(self.tileGps)
        p_att.addLayout(tiles)

        self.rocket3d = Rocket3DWidget()
        p_3d = PanelFrame("Visualización 3D de actitud", "3D • EN VIVO")

        # Selector explícito del comportamiento del modelo 3D.
        # AUTO: usa la actitud recibida por telemetría.
        # MANUAL: congela la entrada automática y permite imponer roll/pitch/yaw.
        mode3d_row = QtWidgets.QHBoxLayout()
        mode3d_row.setSpacing(5)
        mode3d_row.addWidget(QtWidgets.QLabel("MODO 3D"))
        self.cmb3DMode = QtWidgets.QComboBox()
        self.cmb3DMode.addItem("AUTOMÁTICO", "AUTO")
        self.cmb3DMode.addItem("MANUAL", "MANUAL")
        self.cmb3DMode.setMinimumWidth(105)
        mode3d_row.addWidget(self.cmb3DMode)

        self.spn3DRoll = QtWidgets.QDoubleSpinBox()
        self.spn3DPitch = QtWidgets.QDoubleSpinBox()
        self.spn3DYaw = QtWidgets.QDoubleSpinBox()
        for label, spin in (("R", self.spn3DRoll), ("P", self.spn3DPitch), ("Y", self.spn3DYaw)):
            spin.setRange(-180.0, 180.0)
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setSuffix("°")
            spin.setMaximumWidth(82)
            mode3d_row.addWidget(QtWidgets.QLabel(label))
            mode3d_row.addWidget(spin)
        self.btn3DZero = QtWidgets.QPushButton("CERO")
        self.btn3DZero.setToolTip("Poner roll, pitch y yaw manuales en cero")
        mode3d_row.addWidget(self.btn3DZero)
        mode3d_row.addStretch()
        p_3d.addLayout(mode3d_row)
        p_3d.addWidget(self.rocket3d)

        self.turnGauge = CircularGauge("TURN / SLIP", "deg", -90, 90)
        self.bodyRates = BodyRatesWidget()
        p_turn = PanelFrame("Giro, derrape y velocidades angulares", "GD"); p_turn.addWidget(self.turnGauge); p_turn.addWidget(self.bodyRates)

        self.headingGauge = HeadingGauge()
        p_hdg = PanelFrame("Rumbo — giróscopo direccional", "RUMBO"); p_hdg.addWidget(self.headingGauge)

        self.vspeedGauge = CircularGauge("VERTICAL SPEED", "m/s", -20, 20)
        self.gGauge = CircularGauge("G-METER", "g", -1, 6)
        gauge_row = QtWidgets.QHBoxLayout(); gauge_row.addWidget(self.vspeedGauge); gauge_row.addWidget(self.gGauge)
        p_gauges = PanelFrame("Rendimiento de vuelo", "DIN"); p_gauges.addLayout(gauge_row,1)

        self.statusPanel = StatusPanel()
        p_health = PanelFrame("Estado de la telemetría", "SIS"); p_health.addWidget(self.statusPanel)

        self.aiAttitudeAssist = AIAttitudeAssistWidget()
        p_ai_attitude = PanelFrame("Asistencia IA de vuelo", "IA • LOCAL")
        p_ai_attitude.addWidget(self.aiAttitudeAssist)

        grid.addWidget(p_att,0,0); grid.addWidget(p_3d,0,1); grid.addWidget(p_turn,0,2)
        grid.addWidget(p_hdg,1,0); grid.addWidget(p_gauges,1,1); grid.addWidget(p_health,1,2)
        grid.addWidget(p_ai_attitude,2,0,1,3)
        grid.setColumnStretch(0,31); grid.setColumnStretch(1,38); grid.setColumnStretch(2,31)
        grid.setRowStretch(0,49); grid.setRowStretch(1,34); grid.setRowStretch(2,17)

        self._build_functional_pages(attitude_page)
        for index, button in enumerate(self.navButtons):
            button.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
        self._switch_page(2)

        # Hidden/compact plots retained for live plotting and CSV workflow
        self.plotAlt = pg.PlotWidget(title="ALTITUDE HISTORY")
        self.plotAz = pg.PlotWidget(title="ACCELERATION Z HISTORY")
        self.plotAlt.setVisible(False); self.plotAz.setVisible(False)
        self.curAlt = self.plotAlt.plot(); self.curAz = self.plotAz.plot(); self.apogee_line = None

        self.lblAltTop = QtWidgets.QLabel("Alt: --- m")
        self.lblAzTop = QtWidgets.QLabel("Az: --- g")

        # BUFFERS
        self.alt_t = deque(maxlen=5000)
        self.alt_v = deque(maxlen=5000)
        self.az_t = deque(maxlen=10000)
        self.az_v = deque(maxlen=10000)
        self.gps_x = deque(maxlen=3000)
        self.gps_y = deque(maxlen=3000)

        # Estado unificado: LIVE, REPLAY y SIM escriben aquí y todas las pestañas leen lo mismo.
        self.telemetry = {
            "alt_m": 0.0, "az_g": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "vspeed": 0.0, "fix": 0, "sats": 0,
            "lat": -31.3880, "lon": -57.9601,
            "temp_c": 22.0, "pressure_hpa": 1013.25, "humidity": 55.0, "battery_v": 12.2,
            "t_ms": 0, "seq": 0,
        }
        self._last_dashboard_event_t = 0.0

        # STATS
        self.bytes_in = 0
        self.ok_frames = 0
        self.bad_crc_frames = 0
        self.ver_mismatch = 0
        self.last_info = "-"

        self.fast_rate = 0.0
        self.slow_rate = 0.0
        self._fast_cnt = 0
        self._slow_cnt = 0
        self._rate_t0 = time.time()

        self._bw_bytes = 0
        self._bw_Bps = 0.0
        self._bw_t0 = time.time()

        self.seq_prev = None
        self.seq_lost = 0

        # WORKERS/MODES
        self.worker = None
        self.logger = FlightLogger()
        self.replay = None
        self.simulation = None
        self.mode = "LIVE"
        self.serial_connecting = False
        self._serial_user_disconnect = False

        # link watchdog + reconexión
        self.last_rx_time = 0.0
        self._reconnect_next_t = 0.0
        self._reconnect_backoff = 1.0

        # estado vuelo
        self.roll_f = self.pitch_f = self.yaw_f = 0.0
        self.yaw_prev = None

        self.alt_m_max = None
        self.apogee_announced = False

        self.x = self.y = self.z = 0.0
        self.last_t_s: Optional[float] = None

        # TIMER UI
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_ui)
        self.timer.start(50)

        # SIGNALS
        self.btnPorts.clicked.connect(self._refresh_ports)
        self.btnConn.clicked.connect(self.connect_serial)
        self.btnDisc.clicked.connect(self.disconnect_serial)
        self.btnReset.clicked.connect(self.reset_session)

        self.btnRec.clicked.connect(self.start_record)
        self.btnStopRec.clicked.connect(self.stop_record)
        self.btnReplay.clicked.connect(self.toggle_replay)
        self.btnSim.clicked.connect(self.start_simulation)
        self.btnStopSim.clicked.connect(self.stop_simulation)
        self.btnExportCSV.clicked.connect(self.export_csv)
        self.btnSettings.clicked.connect(self.open_settings)
        self.btnReport.clicked.connect(self.generate_mission_report)
        self.btnManualSim.clicked.connect(self.open_manual_simulator)
        self.btnCloseApp.clicked.connect(self.close)

        self.cmb3DMode.currentIndexChanged.connect(self._on_3d_mode_changed)
        self.spn3DRoll.valueChanged.connect(self._on_manual_3d_attitude_changed)
        self.spn3DPitch.valueChanged.connect(self._on_manual_3d_attitude_changed)
        self.spn3DYaw.valueChanged.connect(self._on_manual_3d_attitude_changed)
        self.btn3DZero.clicked.connect(self._zero_manual_3d)

        self.chkAutofit.toggled.connect(self.rocket3d.set_autofit)
        self.chkChase.toggled.connect(self.rocket3d.set_chase_cam)
        self.btnResetTrail.clicked.connect(self.rocket3d.reset_trail_only)

        self.sldReplay.valueChanged.connect(self._on_replay_speed_changed)
        self.chkFastestReplay.toggled.connect(self._on_replay_fastest_changed)

        # ESC global
        self._esc_filter = EscFilter(self)
        QtWidgets.QApplication.instance().installEventFilter(self._esc_filter)

        self._on_3d_mode_changed()
        self._apply_theme()
        self._load_settings()
        self._sync_controls()

    def _on_3d_mode_changed(self, _index=None):
        manual = self.cmb3DMode.currentData() == "MANUAL"
        self.rocket3d.set_control_mode("MANUAL" if manual else "AUTO")
        for widget in (self.spn3DRoll, self.spn3DPitch, self.spn3DYaw, self.btn3DZero):
            widget.setEnabled(manual)
        # En modo manual la cámara queda bajo control del mouse; se evita que
        # AUTO FIT o CHASE CAM vuelvan a moverla en cada frame.
        self.chkAutofit.setEnabled(not manual)
        self.chkChase.setEnabled(not manual)
        if manual:
            self.rocket3d.set_manual_attitude(
                self.spn3DRoll.value(), self.spn3DPitch.value(), self.spn3DYaw.value()
            )

    def _on_manual_3d_attitude_changed(self, _value=None):
        if self.cmb3DMode.currentData() != "MANUAL":
            return
        self.rocket3d.set_manual_attitude(
            self.spn3DRoll.value(), self.spn3DPitch.value(), self.spn3DYaw.value()
        )

    def _zero_manual_3d(self):
        blockers = [QtCore.QSignalBlocker(w) for w in (self.spn3DRoll, self.spn3DPitch, self.spn3DYaw)]
        self.spn3DRoll.setValue(0.0)
        self.spn3DPitch.setValue(0.0)
        self.spn3DYaw.setValue(0.0)
        del blockers
        self._on_manual_3d_attitude_changed()

    def _set_dynamic_property(self, widget, name: str, value):
        if widget.property(name) == value:
            return
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _sync_controls(self):
        """Deriva el estado visual de los botones del estado real de los procesos."""
        serial_active = self.worker is not None
        sim_active = bool(self.simulation and self.simulation.isRunning())
        replay_active = self.replay is not None
        manual_active = bool(getattr(self, "manual_dialog", None) and self.manual_dialog.isVisible() and self.mode == "SIM")
        recording = self.logger.is_recording()
        source_busy = serial_active or sim_active or replay_active or manual_active

        has_port = bool(self.cmbPorts.currentText().strip())
        self.btnConn.setEnabled(has_port and not source_busy)
        self.btnDisc.setEnabled(serial_active)
        self.btnPorts.setEnabled(not serial_active)
        self.cmbPorts.setEnabled(not serial_active)

        self.btnSim.setEnabled(not source_busy)
        self.btnStopSim.setEnabled(sim_active or manual_active)
        self.cmbSim.setEnabled(not source_busy)
        self.btnReplay.setEnabled(not serial_active and not sim_active and not manual_active)

        self.btnRec.setEnabled(not recording)
        self.btnStopRec.setEnabled(recording)
        self.btnReset.setEnabled(source_busy or self.ok_frames > 0 or self.bad_crc_frames > 0)

        self._set_dynamic_property(self.btnConn, "active", serial_active and not self.serial_connecting)
        self._set_dynamic_property(self.btnDisc, "active", serial_active)
        self._set_dynamic_property(self.btnSim, "active", sim_active)
        self._set_dynamic_property(self.btnStopSim, "active", sim_active or manual_active)
        self._set_dynamic_property(self.btnReplay, "active", replay_active)
        self._set_dynamic_property(self.btnRec, "active", recording)
        self._set_dynamic_property(self.btnStopRec, "active", recording)

        self.btnConn.setText("CONECTANDO…" if self.serial_connecting else "CONECTAR")
        self.btnReplay.setText("DETENER REPRODUCCIÓN" if replay_active else "REPRODUCIR")

    def _make_readout(self, title, value="---", unit=""):
        box = QtWidgets.QFrame(); box.setObjectName("dataCard")
        lay = QtWidgets.QVBoxLayout(box); lay.setContentsMargins(10,8,10,8); lay.setSpacing(2)
        lab = QtWidgets.QLabel(title.upper()); lab.setObjectName("dataCardTitle")
        val = QtWidgets.QLabel(value); val.setObjectName("dataCardValue")
        uni = QtWidgets.QLabel(unit); uni.setObjectName("dataCardUnit")
        lay.addWidget(lab); lay.addStretch(); lay.addWidget(val); lay.addWidget(uni)
        return box, val

    def _build_functional_pages(self, attitude_page):
        self.pageStack.addWidget(self._build_mission_page())
        self.pageStack.addWidget(self._build_dashboard_page())
        self.pageStack.addWidget(attitude_page)
        self.pageStack.addWidget(self._build_gps_page())
        self.pageStack.addWidget(self._build_environment_page())
        self.pageStack.addWidget(self._build_serial_page())
        self.pageStack.addWidget(self._build_log_page())
        self.aiPage = AITelemetryPage(self.ai_analyzer, self)
        self.pageStack.addWidget(self.aiPage)

    def _switch_page(self, index):
        self.pageStack.setCurrentIndex(index)
        for i, button in enumerate(self.navButtons):
            active = i == index
            button.setChecked(active)
            button.setObjectName("navButtonActive" if active else "navButton")
            button.style().unpolish(button); button.style().polish(button)

    def _build_mission_page(self):
        page = QtWidgets.QWidget(); main = QtWidgets.QVBoxLayout(page); main.setContentsMargins(0,0,0,0); main.setSpacing(5)
        top = QtWidgets.QHBoxLayout()
        self.missionName = QtWidgets.QLineEdit("MISIÓN DEMO-01")
        self.missionName.setObjectName("missionInput")
        self.btnMissionStart = QtWidgets.QPushButton("INICIAR CRONÓMETRO DE MISIÓN")
        self.btnMissionStart.clicked.connect(self._toggle_mission_timer)
        self.lblMissionElapsed = QtWidgets.QLabel("T+ 00:00:00.0"); self.lblMissionElapsed.setObjectName("missionTimer")
        top.addWidget(QtWidgets.QLabel("ID DE MISIÓN")); top.addWidget(self.missionName,1); top.addWidget(self.btnMissionStart); top.addWidget(self.lblMissionElapsed)
        main.addLayout(top)
        cards=QtWidgets.QHBoxLayout()
        c,self.missionAlt= self._make_readout("Altitud actual","0.0","m"); cards.addWidget(c)
        c,self.missionMaxAlt= self._make_readout("Altitud máxima","0.0","m"); cards.addWidget(c)
        c,self.missionFrames= self._make_readout("Tramas válidas","0","frames"); cards.addWidget(c)
        c,self.missionLoss= self._make_readout("Pérdidas de secuencia","0","frames"); cards.addWidget(c)
        main.addLayout(cards)
        lower=QtWidgets.QHBoxLayout()
        checklist=PanelFrame("Lista de verificación de misión","OPS")
        self.missionChecks=[]
        for text in ("Estación terrestre energizada", "Enlace de telemetría verificado", "Posición GPS adquirida", "Grabación habilitada", "Área de seguridad despejada", "Misión autorizada"):
            cb=QtWidgets.QCheckBox(text); checklist.addWidget(cb); self.missionChecks.append(cb)
        lower.addWidget(checklist,1)
        events=PanelFrame("Cronología de eventos de misión","EVENTOS")
        self.missionEvents=QtWidgets.QPlainTextEdit(); self.missionEvents.setReadOnly(True); self.missionEvents.setPlaceholderText("Los eventos de la misión aparecerán aquí...")
        events.addWidget(self.missionEvents); lower.addWidget(events,2)
        main.addLayout(lower,1)
        professional=QtWidgets.QHBoxLayout()
        phaseBox=PanelFrame("Fase automática de vuelo","FASE")
        self.lblFlightPhase=QtWidgets.QLabel("PRELAUNCH"); self.lblFlightPhase.setObjectName("phaseValue"); self.lblFlightPhase.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        phaseBox.addWidget(self.lblFlightPhase); professional.addWidget(phaseBox,1)
        alarmBox=PanelFrame("Gestión de alarmas activas","ALARMA")
        self.alarmTable=QtWidgets.QTableWidget(0,4); self.alarmTable.setHorizontalHeaderLabels(["HORA","SEVERIDAD","ALARMA","RECONOCIDA"]); self.alarmTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch); self.alarmTable.setMaximumHeight(150)
        alarmBox.addWidget(self.alarmTable)
        self.btnAckAlarms=QtWidgets.QPushButton("RECONOCER TODAS"); self.btnAckAlarms.clicked.connect(self.acknowledge_alarms); alarmBox.addWidget(self.btnAckAlarms)
        professional.addWidget(alarmBox,3); main.addLayout(professional)
        self.mission_start_time=None
        return page

    def _toggle_mission_timer(self):
        if self.mission_start_time is None:
            self.ensure_mission_session(); self.mission_start_time=time.time(); self.btnMissionStart.setText("DETENER CRONÓMETRO DE MISIÓN")
            self._add_mission_event("Cronómetro de misión iniciado")
        else:
            self._add_mission_event("Cronómetro de misión detenido")
            self.mission_start_time=None; self.btnMissionStart.setText("INICIAR CRONÓMETRO DE MISIÓN")

    def _add_mission_event(self, text):
        if hasattr(self,"missionEvents"):
            self.missionEvents.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {text}")

    def _build_dashboard_page(self):
        page=QtWidgets.QWidget(); g=QtWidgets.QGridLayout(page); g.setContentsMargins(0,0,0,0); g.setSpacing(5)
        cards=QtWidgets.QHBoxLayout()
        c,self.dashAlt=self._make_readout("Altitud","0.0","m"); cards.addWidget(c)
        c,self.dashVSpeed=self._make_readout("Velocidad vertical","0.0","m/s"); cards.addWidget(c)
        c,self.dashG=self._make_readout("Carga axial","0.00","g"); cards.addWidget(c)
        c,self.dashHeading=self._make_readout("Rumbo","000","deg"); cards.addWidget(c)
        c,self.dashLink=self._make_readout("Enlace","EN ESPERA",""); cards.addWidget(c)
        holder=QtWidgets.QWidget(); holder.setLayout(cards); g.addWidget(holder,0,0,1,2)
        self.dashboardAltPlot=pg.PlotWidget(title="ALTITUD / PERFIL VERTICAL"); self.dashboardAltPlot.setBackground('#03080c'); self.dashboardAltPlot.showGrid(x=True,y=True,alpha=.18)
        self.dashboardAltCurve=self.dashboardAltPlot.plot(pen=pg.mkPen(width=2))
        self.dashboardAzPlot=pg.PlotWidget(title="ACELERACIÓN AXIAL"); self.dashboardAzPlot.setBackground('#03080c'); self.dashboardAzPlot.showGrid(x=True,y=True,alpha=.18)
        self.dashboardAzCurve=self.dashboardAzPlot.plot(pen=pg.mkPen(width=2))
        g.addWidget(self.dashboardAltPlot,1,0); g.addWidget(self.dashboardAzPlot,1,1)
        self.dashboardTable=QtWidgets.QTableWidget(0,4); self.dashboardTable.setHorizontalHeaderLabels(["HORA","EVENTO","VALOR","ESTADO"]); self.dashboardTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        g.addWidget(self.dashboardTable,2,0,1,2); g.setRowStretch(1,3); g.setRowStretch(2,2)
        return page

    def _build_gps_page(self):
        page=QtWidgets.QWidget(); g=QtWidgets.QGridLayout(page); g.setContentsMargins(0,0,0,0); g.setSpacing(5)
        cards=QtWidgets.QHBoxLayout()
        c,self.gpsFix=self._make_readout("Calidad de posición","NO FIX",""); cards.addWidget(c)
        c,self.gpsSats=self._make_readout("Satélites","0","sats"); cards.addWidget(c)
        c,self.gpsLat=self._make_readout("Latitud","-31.3833","deg"); cards.addWidget(c)
        c,self.gpsLon=self._make_readout("Longitud","-57.9667","deg"); cards.addWidget(c)
        c,self.gpsSpeed=self._make_readout("Velocidad sobre el terreno","0.0","m/s"); cards.addWidget(c)
        holder=QtWidgets.QWidget(); holder.setLayout(cards); g.addWidget(holder,0,0,1,2)
        self.gpsPlot=pg.PlotWidget(title="TRAYECTORIA GPS — COORDENADAS LOCALES SIMULADAS"); self.gpsPlot.setBackground('#03080c'); self.gpsPlot.showGrid(x=True,y=True,alpha=.18); self.gpsPlot.setAspectLocked(True)
        self.gpsCurve=self.gpsPlot.plot(pen=pg.mkPen(width=2), symbol='o', symbolSize=4)
        g.addWidget(self.gpsPlot,1,0)
        info=PanelFrame("Solución de navegación","NAV")
        self.gpsInfo=QtWidgets.QLabel("Esperando telemetría GPS..."); self.gpsInfo.setWordWrap(True); self.gpsInfo.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        info.addWidget(self.gpsInfo); g.addWidget(info,1,1); g.setColumnStretch(0,3); g.setColumnStretch(1,1)
        return page

    def _build_environment_page(self):
        page=QtWidgets.QWidget(); g=QtWidgets.QGridLayout(page); g.setContentsMargins(0,0,0,0); g.setSpacing(5)
        self.envTemp=CircularGauge("TEMPERATURA DEL AIRE","°C",-20,60)
        self.envPressure=CircularGauge("PRESIÓN","hPa",800,1100)
        self.envHumidity=CircularGauge("HUMEDAD","%",0,100)
        self.envBattery=CircularGauge("BATERÍA","V",9,13)
        for i,(title,w) in enumerate((("Térmico",self.envTemp),("Atmosférico",self.envPressure),("Humedad",self.envHumidity),("Alimentación",self.envBattery))):
            p=PanelFrame(title,"ENV"); p.addWidget(w); g.addWidget(p,0,i)
        self.envPlot=pg.PlotWidget(title="TENDENCIA AMBIENTAL (SIMULADA SIN DATOS DE SENSORES)"); self.envPlot.setBackground('#03080c'); self.envPlot.showGrid(x=True,y=True,alpha=.18)
        self.envTempCurve=self.envPlot.plot(pen=pg.mkPen(width=2), name='Temp')
        g.addWidget(self.envPlot,1,0,1,4); g.setRowStretch(1,2)
        self.env_t=deque(maxlen=1000); self.env_temp=deque(maxlen=1000)
        return page

    def _build_serial_page(self):
        page=QtWidgets.QWidget(); v=QtWidgets.QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(5)
        cards=QtWidgets.QHBoxLayout()
        c,self.serialPortVal=self._make_readout("Puerto","---",""); cards.addWidget(c)
        c,self.serialBaudVal=self._make_readout("Velocidad en baudios","9600","bps"); cards.addWidget(c)
        c,self.serialRateVal=self._make_readout("Frecuencia de tramas","0.0","Hz"); cards.addWidget(c)
        c,self.serialBwVal=self._make_readout("Ancho de banda","0","B/s"); cards.addWidget(c)
        c,self.serialCrcVal=self._make_readout("Errores CRC","0","frames"); cards.addWidget(c)
        v.addLayout(cards)
        bar=QtWidgets.QHBoxLayout(); self.chkSerialAuto=QtWidgets.QCheckBox("DESPLAZAMIENTO AUTOMÁTICO"); self.chkSerialAuto.setChecked(True); self.btnSerialClear=QtWidgets.QPushButton("LIMPIAR CONSOLA"); self.btnSerialClear.clicked.connect(lambda:self.serialConsole.clear()); bar.addWidget(self.chkSerialAuto); bar.addStretch(); bar.addWidget(self.btnSerialClear); v.addLayout(bar)
        self.serialConsole=QtWidgets.QPlainTextEdit(); self.serialConsole.setReadOnly(True); self.serialConsole.setMaximumBlockCount(1500); self.serialConsole.setObjectName("serialConsole"); v.addWidget(self.serialConsole,1)
        return page

    def _build_log_page(self):
        page=QtWidgets.QWidget(); g=QtWidgets.QGridLayout(page); g.setContentsMargins(0,0,0,0); g.setSpacing(5)
        controls=PanelFrame("Control de grabación y reproducción","REG")
        self.logPath=QtWidgets.QLabel("No hay archivo de registro activo"); self.logPath.setWordWrap(True)
        controls.addWidget(self.logPath)
        row=QtWidgets.QHBoxLayout(); b1=QtWidgets.QPushButton("INICIAR GRABACIÓN"); b1.clicked.connect(self.start_record); b2=QtWidgets.QPushButton("DETENER GRABACIÓN"); b2.clicked.connect(self.stop_record); b3=QtWidgets.QPushButton("ABRIR REPRODUCCIÓN"); b3.clicked.connect(self.start_replay); b4=QtWidgets.QPushButton("EXPORT CSV"); b4.clicked.connect(self.export_csv)
        for b in (b1,b2,b3,b4): row.addWidget(b)
        controls.addLayout(row)
        g.addWidget(controls,0,0,1,2)
        self.logTable=QtWidgets.QTableWidget(0,6); self.logTable.setHorizontalHeaderLabels(["HORA","TIPO","LONG.","CRC","VERSIÓN","DETALLE"]); self.logTable.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch); self.logTable.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        g.addWidget(self.logTable,1,0)
        stats=PanelFrame("Estadísticas de la sesión","EST")
        self.logStats=QtWidgets.QLabel("Tramas: 0\nErrores CRC: 0\nBytes: 0\nPérdidas: 0\nModo: EN VIVO"); self.logStats.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop); stats.addWidget(self.logStats)
        g.addWidget(stats,1,1); g.setColumnStretch(0,4); g.setColumnStretch(1,1)
        return page

    def _append_serial_line(self, text):
        if not hasattr(self,"serialConsole"): return
        self.serialConsole.appendPlainText(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]}  {text}")
        if self.chkSerialAuto.isChecked():
            self.serialConsole.verticalScrollBar().setValue(self.serialConsole.verticalScrollBar().maximum())

    def _append_log_row(self, typ, ln, ok, ver_rx, detail):
        if not hasattr(self,"logTable"): return
        r=self.logTable.rowCount(); self.logTable.insertRow(r)
        vals=[time.strftime('%H:%M:%S'),str(typ),str(ln),'OK' if ok else 'BAD',str(ver_rx),detail]
        for c,v in enumerate(vals): self.logTable.setItem(r,c,QtWidgets.QTableWidgetItem(v))
        if self.logTable.rowCount()>300: self.logTable.removeRow(0)

    def _apply_theme(self):
        pg.setConfigOptions(antialias=True)
        self.setStyleSheet("""
            QWidget#consoleRoot { background:#03080c; color:#d8e8ee; }
            QWidget { font-family: 'Segoe UI'; font-size: 12px; }
            QFrame#missionHeader { background:#070d12; border:1px solid #182b35; border-radius:3px; }
            QLabel#brandLabel { color:#f0f6f8; font-weight:800; letter-spacing:1px; font-size:15px; padding-right:10px; }
            QPushButton#navButton, QPushButton#navButtonActive { border:none; padding:6px 8px; color:#718b97; font:700 12px 'Consolas'; }
            QPushButton#navButton:hover { color:#d7f4ff; background:#0b1720; }
            QPushButton#navButtonActive { color:#8be8ff; background:#102433; border-bottom:2px solid #55d4ff; }
            QLabel#liveBadge { color:#74f6c5; font:700 11px 'Consolas'; padding:5px 9px; border:1px solid #1b604d; background:#071a16; }
            QPushButton#closeAppButton { color:#ffb7b7; background:#261012; border:1px solid #7a3035; font:700 10px 'Consolas'; padding:7px 11px; }
            QPushButton#closeAppButton:hover { color:#ffffff; background:#8b2028; border-color:#ff6872; }
            QPushButton#closeAppButton:pressed { background:#5d151b; }
            QLabel#clockLabel { color:#9bb1bb; font:700 12px 'Consolas'; min-width:78px; }
            QFrame#operationsBar, QFrame#simulatorBar { background:#050b10; border:1px solid #132630; }
            QLabel#simulatorTitle { color:#72ddff; font:700 11px 'Consolas'; padding-right:10px; }
            QLabel#simDiagnostic { color:#7fa5b3; font:700 12px 'Consolas'; }
            QPushButton#simStartButton { background:#0b392e; border:1px solid #27d99a; color:#baffdf; font:700 12px 'Consolas'; }
            QPushButton#simStartButton:hover { background:#105340; }
            QPushButton#simStartButton:disabled { background:#08130f; border-color:#173229; color:#3f6155; }
            QPushButton#simStopButton { background:#3b161a; border:1px solid #ff6470; color:#ffd2d5; font:700 12px 'Consolas'; }
            QPushButton#simStopButton:disabled { background:#140b0d; border-color:#32191d; color:#654247; }
            QPushButton[active="true"] { border-color:#65dcff; color:#ffffff; }
            QPushButton#simStartButton[active="true"] { background:#126047; border-color:#46f0b2; }
            QPushButton#simStopButton[active="true"] { background:#641f27; border-color:#ff7b85; }
            QPushButton { background:#09131a; border:1px solid #24414d; color:#b9d5df; padding:5px 8px; border-radius:2px; font:700 12px 'Consolas'; }
            QPushButton:hover { background:#102631; border-color:#5bd7ff; color:#ffffff; }
            QPushButton:disabled { color:#40545d; border-color:#15242b; }
            QComboBox { background:#061017; border:1px solid #24414d; color:#d8eef5; padding:6px 9px; font:700 11px 'Consolas'; min-height:20px; }
            QCheckBox { color:#78949f; font:700 10px 'Consolas'; spacing:7px; }
            QSlider::groove:horizontal { height:3px; background:#18303a; }
            QSlider::handle:horizontal { width:10px; margin:-4px 0; background:#65d9ff; border-radius:5px; }
            QLabel#systemStatus { color:#77e5ff; background:#06131a; border:1px solid #17313c; padding:6px 10px; font:700 11px 'Consolas'; }
            QLabel#counterStrip { color:#7c949e; background:#050c11; border:1px solid #13242c; padding:4px 8px; font:700 12px 'Consolas'; }
            QFrame#panelFrame { background:#050b10; border:1px solid #17313d; border-radius:2px; }
            QLabel#panelTitle { color:#c8dce3; font:700 10px 'Consolas'; letter-spacing:1px; }
            QLabel#panelCode { color:#466672; font:700 12px 'Consolas'; }
            QFrame#valueTile { background:#071219; border:1px solid #18333e; }
            QLabel#tileLabel { color:#63808b; font:700 11px 'Consolas'; }
            QLabel#tileValue { color:#dff9ff; font:700 20px 'Consolas'; }
            QLabel#tileUnit { color:#57cdec; font:700 11px 'Consolas'; }
            QGroupBox { background:transparent; border:none; margin:0; padding:0; color:#91aab4; font:700 12px 'Consolas'; }
            QGroupBox::title { color:#91aab4; }
            QLabel { color:#c9dce3; }
            QStackedWidget#pageStack { background:#03080c; border:none; }
            QFrame#dataCard { background:#061017; border:1px solid #183541; border-radius:3px; min-height:68px; }
            QLabel#dataCardTitle { color:#64818c; font:700 12px 'Consolas'; }
            QLabel#dataCardValue { color:#e6fbff; font:700 22px 'Consolas'; }
            QLabel#dataCardUnit { color:#54c8e8; font:700 12px 'Consolas'; }
            QLabel#missionTimer { color:#70e6ff; font:700 20px 'Consolas'; padding:4px 10px; }
            QLabel#phaseValue { color:#84f8c8; font:900 26px 'Consolas'; padding:14px; background:#071a16; border:1px solid #1b604d; }
            QLineEdit#missionInput { background:#061017; border:1px solid #24414d; color:#d8eef5; padding:5px; font:700 12px 'Consolas'; }
            QPlainTextEdit#serialConsole, QPlainTextEdit { background:#020609; color:#8de7b5; border:1px solid #183541; font:11px 'Consolas'; }
            QTableWidget { background:#03090d; alternate-background-color:#071118; color:#c7e0e8; gridline-color:#16303a; border:1px solid #183541; font:11px 'Consolas'; }
            QHeaderView::section { background:#0a1720; color:#73cfe9; border:1px solid #183541; padding:5px; font:700 12px 'Consolas'; }
            QLabel#aiStatus { color:#72ddff; background:#06131a; border:1px solid #1f5263; padding:6px 10px; font:700 11px 'Consolas'; }
            QLabel#aiStatus[online="true"] { color:#84f8c8; background:#071a16; border-color:#1b604d; }
            QPlainTextEdit#aiOutput { background:#020609; color:#bcefff; border:1px solid #1c4657; font:12px 'Consolas'; selection-background-color:#17465a; }
            QFrame#aiAttitudeAssist { background:#03090d; border:1px solid #1c4657; border-radius:2px; }
            QLabel#aiAssistTitle { color:#8be8ff; font:800 11px 'Consolas'; letter-spacing:1px; }
            QLabel#aiAssistBadge { color:#84f8c8; background:#071a16; border:1px solid #1b604d; padding:2px 6px; font:700 11px 'Consolas'; }
            QFrame#aiMetricBox { background:#061017; border:1px solid #183541; }
            QLabel#aiMetricLabel { color:#63808b; font:700 11px 'Consolas'; }
            QLabel#aiMetricValue { color:#e6fbff; font:800 14px 'Consolas'; }
            QLabel#aiMetricValue[state="safe"] { color:#84f8c8; }
            QLabel#aiMetricValue[state="warn"] { color:#ffd56a; }
            QLabel#aiMetricValue[state="critical"] { color:#ff7782; }
            QLabel#aiAssistTrend { color:#9bc3d0; font:700 12px 'Consolas'; }
            QLabel#aiAssistAdvice { color:#bcefff; background:#06131a; border-left:3px solid #55d4ff; padding:4px 7px; font:700 12px 'Consolas'; }
            QLabel#aiAssistAdvice[state="safe"] { border-left-color:#46f0b2; color:#baffdf; }
            QLabel#aiAssistAdvice[state="warn"] { border-left-color:#ffd56a; color:#ffe8a6; }
            QLabel#aiAssistAdvice[state="critical"] { border-left-color:#ff6470; color:#ffd2d5; }
            QLabel#aiAssistNote { color:#466672; font:700 11px 'Consolas'; }
            QProgressBar#aiStabilityBar { background:#061017; border:1px solid #183541; color:#c7eefa; text-align:center; height:13px; font:700 11px 'Consolas'; }
            QProgressBar#aiStabilityBar::chunk { background:#35c79a; }
            QProgressBar#aiStabilityBar[state="warn"]::chunk { background:#d6a832; }
            QProgressBar#aiStabilityBar[state="critical"]::chunk { background:#d74f5b; }
        """)
        for p in (self.plotAlt, self.plotAz):
            p.setBackground("#03080c"); p.showGrid(x=True,y=True,alpha=.15)

    def _load_settings(self):
        try:
            geom = self.settings.value("geometry")
            if geom:
                self.restoreGeometry(geom)

            last_port = self.settings.value("port", "")
            if last_port:
                idx = self.cmbPorts.findText(last_port)
                if idx >= 0:
                    self.cmbPorts.setCurrentIndex(idx)

            self.chkAutofit.setChecked(self.settings.value("autofit", True, bool))
            self.chkChase.setChecked(self.settings.value("chase", True, bool))
            self.chkFreeze.setChecked(self.settings.value("freeze", False, bool))

            sp = self.settings.value("replaySpeed", 1.0, float)
            sp = max(0.5, min(3.0, sp))
            self.sldReplay.setValue(int(round(sp * 10)))
            self.chkFastestReplay.setChecked(self.settings.value("replayFastest", False, bool))
            self._update_replay_label()

            self.rocket3d.set_autofit(self.chkAutofit.isChecked())
            self.rocket3d.set_chase_cam(self.chkChase.isChecked())
        except Exception:
            pass

    def _save_settings(self):
        try:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("port", self.cmbPorts.currentText())
            self.settings.setValue("autofit", self.chkAutofit.isChecked())
            self.settings.setValue("chase", self.chkChase.isChecked())
            self.settings.setValue("freeze", self.chkFreeze.isChecked())
            self.settings.setValue("replaySpeed", self._replay_speed())
            self.settings.setValue("replayFastest", self.chkFastestReplay.isChecked())
        except Exception:
            pass

    def _refresh_ports(self):
        cur = self.cmbPorts.currentText()
        self.cmbPorts.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["COM13"]
        self.cmbPorts.addItems(ports)
        if cur:
            idx = self.cmbPorts.findText(cur)
            if idx >= 0:
                self.cmbPorts.setCurrentIndex(idx)

    def _replay_speed(self) -> float:
        return self.sldReplay.value() / 10.0

    def _update_replay_label(self):
        self.lblReplaySpeed.setText(f"Replay: {self._replay_speed():.1f}x")

    def _on_replay_speed_changed(self):
        self._update_replay_label()
        if self.replay:
            self.replay.set_speed(self._replay_speed())

    def _on_replay_fastest_changed(self, checked: bool):
        if self.replay:
            self.replay.set_fastest(checked)

    def start_record(self):
        mission_path=self.ensure_mission_session()
        default=str(mission_path / "telemetry.tlog")
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar vuelo", default, "Telemetry log (*.tlog)")
        if not fn: return
        if not fn.lower().endswith(".tlog"): fn += ".tlog"

        self.logger.start(fn)
        if hasattr(self, "logPath"): self.logPath.setText(fn)
        self._add_mission_event(f"Recording started: {os.path.basename(fn)}")
        self.statusPanel.set_event("GRABANDO (REC)", warn=False)
        self._sync_controls()

    def stop_record(self):
        self.logger.stop()
        self._add_mission_event("Recording stopped")
        self.statusPanel.set_event("LOG DETENIDO", warn=False)
        self._sync_controls()

    def toggle_replay(self):
        if self.replay is not None:
            self.stop_replay()
        else:
            self.start_replay()

    def stop_replay(self):
        replay = self.replay
        self.replay = None
        if replay is not None:
            try:
                replay.stop()
                replay.wait(700)
            except Exception as exc:
                self.on_status(f"error al detener replay: {exc}")
        if self.mode == "REPLAY":
            self.mode = "LIVE"
            self.statusPanel.set_link(False)
            self.statusPanel.set_event("REPRODUCCIÓN DETENIDA", warn=False)
            self.on_status("replay detenido")
        self._sync_controls()

    def start_replay(self):
        self.stop_simulation()
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Reproducir vuelo", "", "Telemetry log (*.tlog)")
        if not fn:
            return

        if self.worker:
            self.disconnect_serial()

        if self.replay:
            self.replay.stop()
            self.replay.wait(500)
            self.replay = None

        if self.logger.is_recording():
            self.stop_record()

        self.reset_session()
        self.mode = "REPLAY"
        self.statusPanel.set_event("REPRODUCCIÓN", warn=False)

        self.replay = ReplayWorker(fn, speed=self._replay_speed(), fastest=self.chkFastestReplay.isChecked())
        self.replay.frame.connect(self.on_frame)
        self.replay.status.connect(self.on_status)
        self.replay.finished.connect(self._replay_finished)
        self.replay.start()
        self._sync_controls()

    def _replay_finished(self):
        self.replay = None
        if self.mode == "REPLAY":
            self.mode = "LIVE"
            self.statusPanel.set_link(False)
            self.statusPanel.set_event("REPRODUCCIÓN FINALIZADA", warn=False)
        self._sync_controls()

    def export_csv(self):
        tlog, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir LOG (.tlog)", "", "Telemetry log (*.tlog)")
        if not tlog:
            return

        csv_out, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar CSV", "", "CSV (*.csv)")
        if not csv_out:
            return
        if not csv_out.lower().endswith(".csv"):
            csv_out += ".csv"

        try:
            with open(tlog, "rb") as f:
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

                with open(csv_out, "w", newline="", encoding="utf-8") as fc:
                    w = csv.writer(fc)
                    w.writerow(["t_pc","typ","ok","ln","t_ms","az_g","roll_deg","pitch_deg","yaw_deg","seq","alt_m","fix","sats"])

                    while True:
                        if is_v2:
                            hdr = f.read(20)
                            if not hdr or len(hdr) < 20:
                                break
                            t_pc, typ, ok, ln, crc_rx, crc_calc, t_ms = struct.unpack("<dBBHHHI", hdr)
                            payload = f.read(ln)
                            if len(payload) < ln:
                                break
                        else:
                            hdr = f.read(8 + 1 + 1 + 2)
                            if not hdr or len(hdr) < (8 + 1 + 1 + 2):
                                break
                            t_pc, typ, ok, ln = struct.unpack("<dBBH", hdr)
                            payload = f.read(ln)
                            if len(payload) < ln:
                                break
                            t_ms = struct.unpack_from("<I", payload, 0)[0] if len(payload) >= 4 else 0xFFFFFFFF

                        az_g = roll = pitch = yaw = seq = ""
                        alt_m = fix = sats = ""

                        if int(ok):
                            if int(typ) == TYPE_FAST:
                                ff = decode_fast(payload)
                                if ff:
                                    az_g = f"{ff.az_g:.6f}"
                                    roll = f"{ff.roll_deg:.6f}"
                                    pitch = f"{ff.pitch_deg:.6f}"
                                    yaw = f"{ff.yaw_deg:.6f}"
                                    seq = int(ff.seq)
                            elif int(typ) == TYPE_SLOW:
                                sf = decode_slow(payload)
                                if sf:
                                    alt_m = f"{sf.alt_m:.6f}"
                                    fix = int(sf.fix)
                                    sats = int(sf.sats)

                        w.writerow([t_pc, int(typ), int(ok), int(ln), int(t_ms), az_g, roll, pitch, yaw, seq, alt_m, fix, sats])

            self.statusPanel.set_event(f"CSV exportado: {os.path.basename(csv_out)}", warn=False)
        except Exception as e:
            self.statusPanel.set_event(f"CSV error: {e!r}", warn=True)

    def start_simulation(self):
        if self.worker:
            self.disconnect_serial()
        if self.replay:
            self.replay.stop()
            self.replay.wait(500)
            self.replay = None
        self.stop_simulation(reset_mode=False)
        self.reset_session()
        self.mode = "SIM"
        self.simulation = SimulationWorker(self.cmbSim.currentText(), self, profile=self.config["simulation"])
        self.simulation.frame.connect(self.on_frame)
        self.simulation.status.connect(self.on_status)
        self.simulation.error.connect(self._simulation_error)
        self.simulation.finished.connect(self._simulation_finished)
        self.lblSimDiag.setText(f"STARTING — {self.cmbSim.currentText()}")
        self.simulation.start()
        self.on_status(f"iniciando simulación: {self.cmbSim.currentText()}")
        self.lblMode.setText("● SIMULATION")
        self._sync_controls()
        self.statusPanel.set_link(True)
        self.statusPanel.set_event("SIMULATION", warn=False)
        self.last_rx_time = time.time()
        if self.mission_start_time is None:
            self.mission_start_time = time.time()
            self.btnMissionStart.setText("DETENER CRONÓMETRO DE MISIÓN")
        self._add_mission_event(f"Simulation started: {self.cmbSim.currentText()}")

    def stop_simulation(self, reset_mode=True):
        manual = getattr(self, "manual_dialog", None)
        if manual is not None and manual.isVisible():
            manual.close()
        if self.simulation:
            sim = self.simulation
            self.simulation = None
            try:
                sim.stop()
                sim.wait(1000)
            except Exception as exc:
                self.on_status(f"error al detener simulación: {exc}")
        self._sync_controls()
        if reset_mode and self.mode == "SIM":
            self.mode = "LIVE"
            self.on_status("simulación detenida")
            self.statusPanel.set_link(False)
            self.statusPanel.set_event("SIM STOPPED", warn=False)
            self.lblSimDiag.setText("DETENIDA — pulse SIMULAR para reiniciar")

    def _simulation_error(self, message: str):
        self.lblSimDiag.setText(message)
        self.on_status(message)
        self.statusPanel.set_event("SIM ERROR", warn=True)
        QtWidgets.QMessageBox.critical(self, "Error de simulación", message)

    def _simulation_finished(self):
        self.simulation = None
        if self.mode == "SIM":
            self.mode = "LIVE"
            self.statusPanel.set_link(False)
            self.lblSimDiag.setText("FINALIZADA — pulse SIMULAR para reiniciar")
        self._sync_controls()

    def connect_serial(self):
        self.stop_simulation()
        if self.replay:
            self.replay.stop()
            self.replay.wait(500)
            self.replay = None

        self.mode = "LIVE"
        port = self.cmbPorts.currentText().strip()
        if not port:
            self.on_status("Puerto vacío")
            return

        self.worker = SerialWorker(port, int(self.config["serial"]["baud"]))
        self.worker.frame.connect(self.on_frame)
        self.worker.status.connect(self.on_status)
        self.worker.connected.connect(self._serial_connected)
        self.worker.disconnected.connect(self._serial_disconnected)
        self.worker.error.connect(self._serial_error)
        self.serial_connecting = True
        self._serial_user_disconnect = False
        self.worker.start()
        self.statusPanel.set_link(False)
        self._sync_controls()

        self._reconnect_backoff = 1.0
        self._reconnect_next_t = 0.0

    def _serial_connected(self, port: str, baud: int):
        self.serial_connecting = False
        self.last_rx_time = time.time()
        self.statusPanel.set_link(True)
        self.on_status(f"conectado a {port} @ {baud}")
        self._sync_controls()

    def _serial_error(self, message: str):
        self.serial_connecting = False
        self.statusPanel.set_link(False)
        self.statusPanel.set_event("ERROR DE PUERTO SERIE", warn=True)
        self._sync_controls()

    def _serial_disconnected(self):
        self.serial_connecting = False
        # La señal puede llegar durante disconnect_serial(); no vuelve a activar un estado antiguo.
        if self.sender() is self.worker:
            self.worker = None
        self.statusPanel.set_link(False)
        self._sync_controls()

    def disconnect_serial(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(1000)
            self.worker = None

        self.serial_connecting = False
        self.on_status("desconectado")
        self.statusPanel.set_link(False)
        self.statusPanel.set_crc(None)
        self.statusPanel.set_event("---", warn=False)

        self.lblAltTop.setText("Alt: --- m")
        self.lblAzTop.setText("Az: --- g")
        self.statusPanel.lbl_alt.setText("---")
        self.statusPanel.lbl_az.setText("---")
        self.statusPanel.lbl_gps.setText("---")
        self.statusPanel.lbl_last.setText("-")
        self.statusPanel.lbl_rate.setText("0.0 / 0.0 Hz")
        self.statusPanel.lbl_bw.setText("0 B/s")
        self._sync_controls()

    def on_status(self, msg: str):
        self.lblStatus.setText(f"Estado: {msg}")
        if hasattr(self, "lblSimDiag") and ("SIM" in msg.upper() or "simul" in msg.lower()):
            self.lblSimDiag.setText(msg)
        self._append_serial_line(f"STATUS  {msg}")

    def reset_session(self):
        self.alt_t.clear(); self.alt_v.clear()
        self.az_t.clear(); self.az_v.clear()
        self.gps_x.clear(); self.gps_y.clear()
        self.curAlt.setData([], [])
        self.curAz.setData([], [])

        if self.apogee_line is not None:
            try:
                self.plotAlt.removeItem(self.apogee_line)
            except Exception:
                pass
            self.apogee_line = None

        self.bytes_in = 0
        self.ok_frames = 0
        self.bad_crc_frames = 0
        self.ver_mismatch = 0
        self.last_info = "-"

        self._fast_cnt = 0
        self._slow_cnt = 0
        self._rate_t0 = time.time()

        self._bw_bytes = 0
        self._bw_Bps = 0.0
        self._bw_t0 = time.time()

        self.seq_prev = None
        self.seq_lost = 0

        self.lblCounters.setText("Bytes: 0 | OK: 0 | CRC bad: 0 | Last: -")
        self.lblAltTop.setText("Alt: --- m")
        self.lblAzTop.setText("Az: --- g")

        self.roll_f = self.pitch_f = self.yaw_f = 0.0
        self.yaw_prev = None

        self.alt_m_max = None
        self.apogee_announced = False

        self.x = self.y = self.z = 0.0
        self.last_t_s = None

        self.rocket3d.reset_scene()
        self.phase_detector.reset()
        self.alarm_manager = AlarmManager(self.config["limits"])
        if hasattr(self,"alarmTable"): self.alarmTable.setRowCount(0)
        if hasattr(self,"lblFlightPhase"): self.lblFlightPhase.setText("PRELAUNCH")
        self.statusPanel.set_event("REINICIO", warn=False)

        if self.worker:
            self.worker.send(b"R")

    def _update_apogee_logic(self, alt_m: float, t_s: Optional[float]):
        if self.alt_m_max is None or alt_m > self.alt_m_max:
            self.alt_m_max = alt_m

        if (self.alt_m_max is not None) and (not self.apogee_announced):
            if alt_m < (self.alt_m_max - 2.0):
                self.apogee_announced = True
                self.statusPanel.set_event(f"APOGEO ~ {self.alt_m_max:.1f} m", warn=False)
                if t_s is not None:
                    try:
                        self.apogee_line = pg.InfiniteLine(pos=t_s, angle=90, movable=False)
                        self.plotAlt.addItem(self.apogee_line)
                    except Exception:
                        pass

    def _unwrap_deg(self, prev, cur):
        if prev is None:
            return cur
        d = cur - prev
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        return prev + d

    def _decimate(self, xs, ys, max_points=2000):
        n = len(xs)
        if n <= max_points:
            return xs, ys
        step = max(1, n // max_points)
        return xs[::step], ys[::step]

    def _update_rates_bw(self):
        now = time.time()

        dt = now - self._rate_t0
        if dt >= 1.0:
            self.fast_rate = self._fast_cnt / dt
            self.slow_rate = self._slow_cnt / dt
            self._fast_cnt = 0
            self._slow_cnt = 0
            self._rate_t0 = now

        dtb = now - self._bw_t0
        if dtb >= 1.0:
            self._bw_Bps = self._bw_bytes / dtb
            self._bw_bytes = 0
            self._bw_t0 = now

        self.statusPanel.lbl_rate.setText(f"{self.fast_rate:.1f} / {self.slow_rate:.1f} Hz")
        self.statusPanel.lbl_loss.setText(f"{self.seq_lost}")
        self.statusPanel.lbl_bw.setText(f"{self._bw_Bps:.0f} B/s")

    def on_frame(self, typ: int, payload: bytes, ok: bool, ln: int, crc_rx: int, crc_calc: int, ver_rx: int):
        if self.mode in ("LIVE", "SIM"):
            self.logger.log_frame(typ, payload, ok, crc_rx, crc_calc)

        self.last_rx_time = time.time()
        self.statusPanel.set_link(True)
        self.statusPanel.set_crc(ok)

        ver_ok = (ver_rx == VER)
        self.statusPanel.set_ver(ver_ok, ver_rx)
        if not ver_ok:
            self.ver_mismatch += 1

        frame_size = (5 + ln + 2)
        self.bytes_in += frame_size
        self._bw_bytes += frame_size

        if ok:
            self.ok_frames += 1
        else:
            self.bad_crc_frames += 1

        self.last_info = f"TYPE={typ} LEN={ln} CRC={'OK' if ok else 'BAD'}"
        self.statusPanel.lbl_last.setText(self.last_info)
        self._append_serial_line(f"RX TYPE={typ:02d} LEN={ln:03d} VER={ver_rx} CRC={'OK' if ok else 'BAD'}")
        self._append_log_row(typ, ln, ok, ver_rx, self.last_info)

        if not ok:
            self._professional_state_update()
            self.lblCounters.setText(f"Bytes: {self.bytes_in} | OK: {self.ok_frames} | CRC bad: {self.bad_crc_frames} | Last: {self.last_info}")
            return

        if typ == TYPE_FAST:
            self._fast_cnt += 1
            ff = decode_fast(payload)
            if ff:
                if self.seq_prev is not None:
                    expected = (self.seq_prev + 1) & 0xFFFF
                    if ff.seq != expected:
                        diff = (ff.seq - expected) & 0xFFFF
                        if diff > 2000:
                            self.statusPanel.set_event("SEQ RESET / RESYNC", warn=False)
                        else:
                            self.seq_lost += diff
                self.seq_prev = ff.seq

                self.lblAzTop.setText(f"Az: {ff.az_g:.2f} g")
                self.statusPanel.lbl_az.setText(f"{ff.az_g:.2f} g")
                self.az_t.append(ff.t_ms / 1000.0)
                self.az_v.append(ff.az_g)

                roll = ff.roll_deg
                pitch = ff.pitch_deg
                yaw = self._unwrap_deg(self.yaw_prev, ff.yaw_deg)
                self.yaw_prev = yaw

                a = ATT_ALPHA
                self.roll_f = (1 - a) * self.roll_f + a * roll
                self.pitch_f = (1 - a) * self.pitch_f + a * pitch
                self.yaw_f = (1 - a) * self.yaw_f + a * yaw

                t_s = ff.t_ms / 1000.0
                if self.last_t_s is None:
                    self.last_t_s = t_s
                dt = max(0.0, min(0.2, t_s - self.last_t_s))
                self.last_t_s = t_s

                v = 0.15
                rad = np.deg2rad(self.yaw_f)
                self.x += v * dt * np.cos(rad)
                self.y += v * dt * np.sin(rad)

                self.rocket3d.set_flame(ff.az_g > 1.5)
                self.rocket3d.set_position_estimated(self.x, self.y, self.z, yaw_deg=self.yaw_f)
                self.rocket3d.set_attitude(self.roll_f, self.pitch_f, self.yaw_f)
                self.attitude.set_attitude(self.roll_f, self.pitch_f, self.yaw_f)
                self.headingGauge.setValue(self.yaw_f)
                self.turnGauge.setValue(self.roll_f)
                self.bodyRates.set_rates(self.roll_f, self.pitch_f, self.yaw_f)
                self.gGauge.setValue(ff.az_g)
                self.tileAz.setValue(ff.az_g, 2)
                self.telemetry.update({
                    "az_g": float(ff.az_g), "roll": float(self.roll_f),
                    "pitch": float(self.pitch_f), "yaw": float(self.yaw_f),
                    "t_ms": int(ff.t_ms), "seq": int(ff.seq),
                })
                self._update_all_pages_from_state()

        elif typ == TYPE_SLOW:
            self._slow_cnt += 1
            sf = decode_slow(payload)
            if sf:
                self.lblAltTop.setText(f"Alt: {sf.alt_m:.2f} m")
                self.statusPanel.lbl_alt.setText(f"{sf.alt_m:.2f} m")
                self.alt_t.append(sf.t_ms / 1000.0)
                self.alt_v.append(sf.alt_m)

                self.statusPanel.lbl_gps.setText(f"fix={sf.fix} sats={sf.sats}")
                self.tileAlt.setValue(sf.alt_m, 1)
                self.tileGps.setValue(f"{sf.fix}/{sf.sats}")
                vs = self.telemetry.get("vspeed", 0.0)
                if len(self.alt_t) >= 2:
                    dt_alt = self.alt_t[-1] - self.alt_t[-2]
                    if dt_alt > 0:
                        vs=(self.alt_v[-1] - self.alt_v[-2]) / dt_alt
                        self.vspeedGauge.setValue(vs)

                # El frame lento contiene ambiente y GPS; se decodifica completo para todas las pestañas.
                temp_c = self.telemetry.get("temp_c", 22.0)
                pressure_hpa = self.telemetry.get("pressure_hpa", 1013.25)
                lat = self.telemetry.get("lat", -31.3880)
                lon = self.telemetry.get("lon", -57.9601)
                try:
                    _, _, temp_cC, press_Pa, lat_e7, lon_e7, _, _, _ = struct.unpack("<IihIiiiBB", payload)
                    temp_c = temp_cC / 100.0
                    pressure_hpa = press_Pa / 100.0
                    lat = lat_e7 / 1e7
                    lon = lon_e7 / 1e7
                except Exception:
                    pass
                self.telemetry.update({
                    "alt_m": float(sf.alt_m), "vspeed": float(vs),
                    "fix": int(sf.fix), "sats": int(sf.sats),
                    "lat": float(lat), "lon": float(lon),
                    "temp_c": float(temp_c), "pressure_hpa": float(pressure_hpa),
                    "humidity": 55.0 + 8.0*np.sin(sf.t_ms/30000.0),
                    "battery_v": 12.2 - 0.25*((sf.t_ms/1000.0)%300.0)/300.0,
                    "t_ms": int(sf.t_ms),
                })
                self._update_apogee_logic(sf.alt_m, t_s=(sf.t_ms / 1000.0))

                self.z = sf.alt_m / 10.0
                self.rocket3d.set_position_estimated(self.x, self.y, self.z, yaw_deg=self.yaw_f)
                self.rocket3d.set_attitude(self.roll_f, self.pitch_f, self.yaw_f)
                self.gps_x.append(self.x); self.gps_y.append(self.y)
                self._update_all_pages_from_state()

        self._professional_state_update()
        self.lblCounters.setText(f"Bytes: {self.bytes_in} | OK: {self.ok_frames} | CRC bad: {self.bad_crc_frames} | Last: {self.last_info}")

    @staticmethod
    def _mode_es(mode):
        """Devuelve una etiqueta en español para el modo interno de operación."""
        mapping = {
            "LIVE": "EN VIVO",
            "SIM": "SIMULACIÓN",
            "REPLAY": "REPRODUCCIÓN",
        }
        key = str(mode).upper()
        return mapping.get(key, str(mode))

    @staticmethod
    def _phase_es(phase):
        """Devuelve una etiqueta en español para la fase interna de vuelo."""
        mapping = {
            "PRELAUNCH": "PRELANZAMIENTO",
            "LAUNCH": "LANZAMIENTO",
            "POWERED ASCENT": "ASCENSO PROPULSADO",
            "COAST": "ASCENSO POR INERCIA",
            "APOGEE": "APOGEO",
            "DESCENT": "DESCENSO",
            "LANDED": "ATERRIZADO",
        }
        key = str(phase).upper()
        return mapping.get(key, str(phase))

    def _update_all_pages_from_state(self):
        """Actualiza todas las pestañas con el último estado, sin importar su visibilidad."""
        t = self.telemetry
        self.ai_analyzer.add_sample(t, self.mode)
        if hasattr(self, "aiAttitudeAssist"):
            self.aiAttitudeAssist.update_assistance(self.ai_analyzer.attitude_assistance())
        alt = float(t["alt_m"]); az = float(t["az_g"]); vs = float(t["vspeed"])
        yaw = float(t["yaw"]) % 360.0

        # Mission / Dashboard
        self.missionAlt.setText(f"{alt:.1f}")
        self.missionMaxAlt.setText(f"{max(self.alt_v) if self.alt_v else alt:.1f}")
        self.missionFrames.setText(str(self.ok_frames))
        self.missionLoss.setText(str(self.seq_lost))
        self.dashAlt.setText(f"{alt:.1f}")
        self.dashVSpeed.setText(f"{vs:.1f}")
        self.dashG.setText(f"{az:.2f}")
        self.dashHeading.setText(f"{yaw:03.0f}")
        self.dashLink.setText("SIMULACIÓN" if self.mode == "SIM" else "EN LÍNEA")

        # GPS
        self.gpsFix.setText({0:"NO FIX",1:"GPS",2:"DGPS",3:"3D FIX"}.get(int(t["fix"]), f"FIX {t['fix']}"))
        self.gpsSats.setText(str(int(t["sats"])))
        self.gpsLat.setText(f"{float(t['lat']):.6f}")
        self.gpsLon.setText(f"{float(t['lon']):.6f}")
        ground_speed = max(0.0, (0.15 if self.mode == "SIM" else 0.0))
        self.gpsSpeed.setText(f"{ground_speed:.2f}")
        self.gpsInfo.setText(
            f"MODE: {self.mode}\nLOCAL X: {self.x:.2f} m\nLOCAL Y: {self.y:.2f} m\n"
            f"ALTITUDE: {alt:.2f} m\nVERTICAL SPEED: {vs:.2f} m/s\n"
            f"HEADING: {yaw:.1f}°\nFIX/SATS: {int(t['fix'])}/{int(t['sats'])}"
        )
        if self.gps_x:
            self.gpsCurve.setData(list(self.gps_x), list(self.gps_y))

        # Environment
        self.envTemp.setValue(float(t["temp_c"]))
        self.envPressure.setValue(float(t["pressure_hpa"]))
        self.envHumidity.setValue(float(t["humidity"]))
        self.envBattery.setValue(float(t["battery_v"]))
        now = time.time()
        if not self.env_t or now - self.env_t[-1] >= 0.2:
            self.env_t.append(now); self.env_temp.append(float(t["temp_c"]))
            self.envTempCurve.setData(list(self.env_t), list(self.env_temp))

        # Serial / Log
        self.serialPortVal.setText("SIMULACIÓN VIRTUAL" if self.mode == "SIM" else self.cmbPorts.currentText())
        self.serialBaudVal.setText("VIRTUAL" if self.mode == "SIM" else str(self.config.get("serial", {}).get("baud", 9600)))
        self.serialRateVal.setText(f"{self.fast_rate+self.slow_rate:.1f}")
        self.serialBwVal.setText(f"{self._bw_Bps:.0f}")
        self.serialCrcVal.setText(str(self.bad_crc_frames))
        self.logStats.setText(
            f"Tramas: {self.ok_frames}\nErrores CRC: {self.bad_crc_frames}\nBytes: {self.bytes_in}\n"
            f"Pérdidas: {self.seq_lost}\nModo: {self._mode_es(self.mode)}\nEscenario: {self.cmbSim.currentText()}"
        )

        # Dashboard event table (limitado para no saturar).
        if time.time() - self._last_dashboard_event_t >= 1.0:
            self._last_dashboard_event_t = time.time()
            r = self.dashboardTable.rowCount(); self.dashboardTable.insertRow(r)
            values = [time.strftime("%H:%M:%S"), self.mode, f"ALT {alt:.1f} m | G {az:.2f}", "OK"]
            for c, value in enumerate(values):
                self.dashboardTable.setItem(r, c, QtWidgets.QTableWidgetItem(value))
            if self.dashboardTable.rowCount() > 120:
                self.dashboardTable.removeRow(0)
            self.dashboardTable.scrollToBottom()

    def refresh_ui(self):
        self.lblClock.setText(time.strftime("%H:%M:%S"))
        self._sync_controls()
        if self.mission_start_time is not None:
            e=time.time()-self.mission_start_time; h=int(e//3600); m=int((e%3600)//60); sec=e%60
            self.lblMissionElapsed.setText(f"T+ {h:02d}:{m:02d}:{sec:04.1f}")
        if hasattr(self,"missionFrames"): self.missionFrames.setText(str(self.ok_frames))
        if hasattr(self,"missionLoss"): self.missionLoss.setText(str(self.seq_lost))
        if hasattr(self,"dashLink"): self.dashLink.setText("EN LÍNEA" if self.last_rx_time and time.time()-self.last_rx_time<2 else "FUERA DE LÍNEA")
        if hasattr(self,"dashboardAltCurve") and self.alt_t:
            self.dashboardAltCurve.setData(list(self.alt_t),list(self.alt_v))
        if hasattr(self,"dashboardAzCurve") and self.az_t:
            self.dashboardAzCurve.setData(list(self.az_t),list(self.az_v))
        self._update_all_pages_from_state()
        if self.mode == "REPLAY":
            self.lblMode.setText("● REPRODUCCIÓN")
        elif self.mode == "SIM":
            self.lblMode.setText("● SIMULATION")
        else:
            self.lblMode.setText("● LIVE")
        if not self.chkFreeze.isChecked():
            if self.alt_t:
                xs = list(self.alt_t); ys = list(self.alt_v)
                xs, ys = self._decimate(xs, ys, max_points=2000)
                self.curAlt.setData(xs, ys)

            if self.az_t:
                xs = list(self.az_t); ys = list(self.az_v)
                xs, ys = self._decimate(xs, ys, max_points=2000)
                self.curAz.setData(xs, ys)

        self._update_rates_bw()

        if self.worker and self.mode == "LIVE":
            dt = time.time() - self.last_rx_time
            if dt > 0.7:
                self.statusPanel.set_link(False)
                self.statusPanel.set_event("LINK LOST", warn=True)

            if dt > 2.5:
                now = time.time()
                if now >= self._reconnect_next_t:
                    self.statusPanel.set_event("RECONECTANDO...", warn=True)
                    self.disconnect_serial()
                    QtCore.QTimer.singleShot(250, self.connect_serial)

                    self._reconnect_next_t = now + self._reconnect_backoff
                    self._reconnect_backoff = min(10.0, self._reconnect_backoff * 1.7)


    def open_settings(self):
        dlg=SettingsDialog(self.config,self)
        if dlg.exec()==QtWidgets.QDialog.DialogCode.Accepted:
            self.config=dlg.values(); self.config_manager.data=self.config; self.config_manager.save()
            self.alarm_manager.limits=self.config["limits"]
            self.on_status("configuration saved")
            self._add_mission_event("Configuration updated")

    def open_manual_simulator(self):
        if getattr(self, "manual_dialog", None) and self.manual_dialog.isVisible():
            self.manual_dialog.raise_()
            self.manual_dialog.activateWindow()
            return
        if self.worker:
            self.disconnect_serial()
        if self.replay:
            self.stop_replay()
        self.stop_simulation()
        self.mode = "SIM"
        self.manual_dialog = ManualSimulationDialog(self)
        self.manual_dialog.changed.connect(self._apply_manual_state)
        self.manual_dialog.finished.connect(self._manual_sim_closed)
        self.manual_dialog.show()
        self.statusPanel.set_link(True)
        self.statusPanel.set_event("SIMULACIÓN MANUAL", warn=False)
        self.lblSimDiag.setText("BANCO MANUAL ACTIVO")
        self._sync_controls()

    def _manual_sim_closed(self, _result=0):
        self.manual_dialog = None
        if self.mode == "SIM" and self.simulation is None:
            self.mode = "LIVE"
            self.statusPanel.set_link(False)
            self.statusPanel.set_event("SIMULACIÓN MANUAL DETENIDA", warn=False)
            self.lblSimDiag.setText("LISTO — pulse SIMULAR")
        self._sync_controls()

    def _apply_manual_state(self,d):
        if self.mode!="SIM":
            self.stop_simulation(reset_mode=False); self.mode="SIM"; self.statusPanel.set_link(True); self.lblMode.setText("● SIMULACIÓN MANUAL")
        previous_alt=float(self.telemetry.get("alt_m",0)); self.telemetry.update(d)
        self.telemetry["vspeed"]=(float(d.get("alt_m",previous_alt))-previous_alt)/0.1
        self.roll_f=float(self.telemetry["roll"]); self.pitch_f=float(self.telemetry["pitch"]); self.yaw_f=float(self.telemetry["yaw"])
        self.attitude.set_attitude(self.roll_f,self.pitch_f,self.yaw_f); self.headingGauge.setValue(self.yaw_f); self.turnGauge.setValue(self.roll_f); self.gGauge.setValue(float(self.telemetry["az_g"])); self.vspeedGauge.setValue(float(self.telemetry["vspeed"]))
        self.rocket3d.set_attitude(self.roll_f,self.pitch_f,self.yaw_f); self.tileAlt.setValue(float(self.telemetry["alt_m"]),1); self.tileAz.setValue(float(self.telemetry["az_g"]),2)
        self._update_all_pages_from_state(); self._professional_state_update()

    def acknowledge_alarms(self):
        self.alarm_manager.acknowledge_all(); self._refresh_alarm_table(); self._add_mission_event("Todas las alarmas fueron reconocidas")

    def _refresh_alarm_table(self):
        if not hasattr(self,"alarmTable"): return
        active=self.alarm_manager.active(); self.alarmTable.setRowCount(len(active))
        for r,a in enumerate(active):
            vals=[datetime.fromtimestamp(a.timestamp).strftime("%H:%M:%S"),a.severity,a.message,"YES" if a.acknowledged else "NO"]
            for c,v in enumerate(vals): self.alarmTable.setItem(r,c,QtWidgets.QTableWidgetItem(v))

    def _professional_state_update(self):
        phase=self.phase_detector.update(self.telemetry)
        if phase:
            self.lblFlightPhase.setText(self._phase_es(phase)); self._add_mission_event(f"Fase de vuelo: {self._phase_es(phase)}"); self.mission_session.add_event("PHASE",self._phase_es(phase))
        total=max(1,self.ok_frames+self.bad_crc_frames); stats={"crc_pct":100.0*self.bad_crc_frames/total}
        link_ok=(self.mode=="SIM") or bool(self.last_rx_time and time.time()-self.last_rx_time<float(self.config["serial"]["link_timeout_s"]))
        new=self.alarm_manager.evaluate(self.telemetry,stats,link_ok)
        for a in new:
            self._add_mission_event(f"{a.severity}: {a.message}"); self.mission_session.add_event("ALARM",f"{a.severity} {a.message}"); self.statusPanel.set_event(a.message,warn=True)
        if new or int(time.time()*2)%4==0: self._refresh_alarm_table()

    def ensure_mission_session(self):
        if not self.mission_session.path:
            path=self.mission_session.start(self.missionName.text().strip() or self.config["general"]["mission_prefix"],self.config)
            self._add_mission_event(f"Mission folder: {path.name}")
        return self.mission_session.path

    def generate_mission_report(self):
        path=self.ensure_mission_session(); report=path/"mission_report.html"; t=self.telemetry
        stats={"max_alt":max(self.alt_v) if self.alt_v else float(t["alt_m"]),"frames":self.ok_frames,"crc":self.bad_crc_frames,"max_g":max(map(abs,self.az_v)) if self.az_v else abs(float(t["az_g"])),"loss":self.seq_lost}
        generate_html_report(report,self.missionName.text(),t,stats,self.config,self.alarm_manager.history,self.phase_detector.phase)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(report))); self.on_status(f"report generated: {report.name}")

    def closeEvent(self, event):
        try:
            self.stop_simulation()
        except Exception:
            pass

        try:
            if self.replay:
                self.replay.stop()
                self.replay.wait(500)
                self.replay = None
        except Exception:
            pass

        try:
            self.logger.stop()
        except Exception:
            pass

        self.disconnect_serial()
        self._save_settings()
        event.accept()

    def keyPressEvent(self, event):
        k = event.key()
        if k == QtCore.Qt.Key.Key_Escape:
            self.exit_fullscreen()
            return
        if k == QtCore.Qt.Key.Key_R:
            self.reset_session()
            return
        if k == QtCore.Qt.Key.Key_F:
            if self.isFullScreen():
                self.showNormal()
                self.showMaximized()
            else:
                self.showFullScreen()
            return
        if k == QtCore.Qt.Key.Key_Space:
            self.chkFreeze.setChecked(not self.chkFreeze.isChecked())
            return

        super().keyPressEvent(event)

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.showMaximized()
            self.activateWindow()
            self.raise_()
