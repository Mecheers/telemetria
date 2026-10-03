from PyQt6 import QtWidgets, QtGui


class StatusPanel(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("Estado / Eventos")

        grid = QtWidgets.QGridLayout(self)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        row = 0

        def mk(title: str):
            nonlocal row
            lbl1 = QtWidgets.QLabel(title)
            lbl1.setStyleSheet("color:#bdbdbd;")
            lbl2 = QtWidgets.QLabel("---")
            mono = QtGui.QFont("Consolas", 10)
            lbl2.setFont(mono)
            grid.addWidget(lbl1, row, 0)
            grid.addWidget(lbl2, row, 1)
            row += 1
            return lbl2

        self.lbl_link = mk("LINK")
        self.lbl_crc = mk("CRC")
        self.lbl_ver = mk("VER")
        self.lbl_last = mk("Última trama")
        self.lbl_alt = mk("Altitud")
        self.lbl_az = mk("Az")
        self.lbl_gps = mk("GPS (fix/sats)")
        self.lbl_rate = mk("Frecuencia (RÁPIDA/LENTA)")
        self.lbl_loss = mk("PÉRDIDAS (sec.)")
        self.lbl_bw = mk("BW (B/s)")
        self.lbl_event = mk("EVENTO")

        self.set_link(False)
        self.set_crc(None)

    def set_link(self, ok: bool):
        if ok:
            self.lbl_link.setText("OK")
            self.lbl_link.setStyleSheet("color: #00aa00; font-weight: bold;")
        else:
            self.lbl_link.setText("DESCONECTADO")
            self.lbl_link.setStyleSheet("color: #aa0000; font-weight: bold;")

    def set_crc(self, ok):
        if ok is None:
            self.lbl_crc.setText("---")
            self.lbl_crc.setStyleSheet("")
        elif ok:
            self.lbl_crc.setText("OK")
            self.lbl_crc.setStyleSheet("color: #00aa00; font-weight: bold;")
        else:
            self.lbl_crc.setText("ERRÓNEO")
            self.lbl_crc.setStyleSheet("color: #aa0000; font-weight: bold;")

    def set_ver(self, ver_ok: bool, ver_val: int):
        if ver_ok:
            self.lbl_ver.setText(f"{ver_val} (OK)")
            self.lbl_ver.setStyleSheet("color: #00aa00; font-weight: bold;")
        else:
            self.lbl_ver.setText(f"{ver_val} (NO COINCIDE)")
            self.lbl_ver.setStyleSheet("color: #aa0000; font-weight: bold;")

    def set_event(self, txt: str, warn=False):
        self.lbl_event.setText(txt)
        if warn:
            self.lbl_event.setStyleSheet("color: #aa0000; font-weight: bold;")
        else:
            self.lbl_event.setStyleSheet("color: #4aa3ff; font-weight: bold;")
