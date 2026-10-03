import math
from PyQt6 import QtCore, QtGui, QtWidgets


class PanelFrame(QtWidgets.QFrame):
    def __init__(self, title: str, code: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("panelFrame")
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 8)
        self._layout.setSpacing(4)
        head = QtWidgets.QHBoxLayout()
        title_lbl = QtWidgets.QLabel(title.upper())
        title_lbl.setObjectName("panelTitle")
        head.addWidget(title_lbl)
        head.addStretch()
        if code:
            code_lbl = QtWidgets.QLabel(code.upper())
            code_lbl.setObjectName("panelCode")
            head.addWidget(code_lbl)
        self._layout.addLayout(head)

    def addWidget(self, widget, stretch=1):
        self._layout.addWidget(widget, stretch)

    def addLayout(self, layout, stretch=0):
        self._layout.addLayout(layout, stretch)


class ValueTile(QtWidgets.QFrame):
    def __init__(self, label: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("valueTile")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(0)
        self.label = QtWidgets.QLabel(label.upper())
        self.label.setObjectName("tileLabel")
        self.value = QtWidgets.QLabel("---")
        self.value.setObjectName("tileValue")
        self.value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.unit = QtWidgets.QLabel(unit)
        self.unit.setObjectName("tileUnit")
        self.unit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        lay.addWidget(self.value, 1)
        lay.addWidget(self.unit)

    def setValue(self, value, precision=1):
        if value is None:
            self.value.setText("---")
        elif isinstance(value, str):
            self.value.setText(value)
        else:
            self.value.setText(f"{float(value):.{precision}f}")


class AttitudeIndicator(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.setMinimumSize(280, 240)

    def set_attitude(self, roll, pitch, yaw):
        self.roll, self.pitch, self.yaw = float(roll), float(pitch), float(yaw)
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(8, 8, -8, -8)
        side = min(r.width(), r.height())
        cx, cy = r.center().x(), r.center().y()
        radius = side * 0.46
        clip = QtGui.QPainterPath(); clip.addEllipse(QtCore.QPointF(cx, cy), radius, radius)
        p.save(); p.setClipPath(clip)
        p.translate(cx, cy); p.rotate(-self.roll)
        pitch_px = max(-radius, min(radius, self.pitch * radius / 45.0))
        sky = QtCore.QRectF(-radius*1.5, -radius*1.5 + pitch_px, radius*3, radius*1.5)
        ground = QtCore.QRectF(-radius*1.5, pitch_px, radius*3, radius*1.5)
        p.fillRect(sky, QtGui.QColor("#164769")); p.fillRect(ground, QtGui.QColor("#68431e"))
        p.setPen(QtGui.QPen(QtGui.QColor("#d8f5ff"), 2)); p.drawLine(QtCore.QPointF(-radius*1.4,pitch_px), QtCore.QPointF(radius*1.4,pitch_px))
        p.setFont(QtGui.QFont("Consolas", 8))
        for deg in range(-30, 31, 10):
            if deg == 0: continue
            y = pitch_px - deg * radius / 45.0
            w = radius * (0.38 if deg % 20 == 0 else 0.25)
            p.drawLine(QtCore.QPointF(-w,y), QtCore.QPointF(w,y)); p.drawText(QtCore.QPointF(w+4,y+3), str(deg))
        p.restore()
        p.setPen(QtGui.QPen(QtGui.QColor("#6dd9ff"), 2)); p.setBrush(QtCore.Qt.BrushStyle.NoBrush); p.drawEllipse(QtCore.QPointF(cx,cy),radius,radius)
        p.setPen(QtGui.QPen(QtGui.QColor("#f5f8fa"), 2));
        p.drawLine(QtCore.QPointF(cx-radius*.38,cy), QtCore.QPointF(cx-radius*.09,cy))
        p.drawLine(QtCore.QPointF(cx+radius*.09,cy), QtCore.QPointF(cx+radius*.38,cy))
        p.drawLine(QtCore.QPointF(cx-radius*.09,cy), QtCore.QPointF(cx,cy+radius*.08)); p.drawLine(QtCore.QPointF(cx,cy+radius*.08), QtCore.QPointF(cx+radius*.09,cy))
        p.setPen(QtGui.QColor("#8fe8ff")); p.setFont(QtGui.QFont("Consolas", 10, 700));
        p.drawText(r.adjusted(0,0,0,-6), QtCore.Qt.AlignmentFlag.AlignBottom|QtCore.Qt.AlignmentFlag.AlignHCenter, f"HDG {self.yaw%360:05.1f}°")


class CircularGauge(QtWidgets.QWidget):
    """Instrumento circular con escala, zonas, valor, tendencia y pico."""
    def __init__(self, title="GAUGE", unit="", minimum=-1, maximum=1, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        self.value = 0.0
        self.peak_value = 0.0
        self.setMinimumSize(230, 210)

    def setValue(self, value):
        value = float(value)
        self.value = max(self.minimum, min(self.maximum, value))
        if abs(self.value) > abs(self.peak_value):
            self.peak_value = self.value
        self.update()

    def reset_peak(self):
        self.peak_value = self.value
        self.update()

    def _frac(self, value):
        if self.maximum == self.minimum:
            return 0.0
        return max(0.0, min(1.0, (value - self.minimum) / (self.maximum - self.minimum)))

    def _angle(self, value):
        return math.radians(225.0 - 270.0 * self._frac(value))

    def _status_text(self):
        title = self.title.upper()
        v = self.value
        if "VERTICAL" in title:
            if v > 0.5:
                return "ASCENSO"
            if v < -0.5:
                return "DESCENT"
            return "NIVEL"
        if "MEDIDOR G" in title or self.unit.lower() == "g":
            if v >= 4.0:
                return "G ALTA"
            if v >= 1.5:
                return "CARGA"
            if v < 0.0:
                return "G NEGATIVA"
            return "NOMINAL"
        if "GIRO" in title:
            if v > 3.0:
                return "DERECHA"
            if v < -3.0:
                return "IZQUIERDA"
            return "CENTRO"
        return "ACTIVE"

    def _zone_color(self, frac):
        title = self.title.upper()
        if "MEDIDOR G" in title:
            if frac >= self._frac(4.0):
                return QtGui.QColor("#ff6262")
            if frac >= self._frac(2.5):
                return QtGui.QColor("#ffca5c")
            return QtGui.QColor("#60e5a8")
        if "VERTICAL" in title:
            return QtGui.QColor("#68d9ff")
        return QtGui.QColor("#68d9ff")

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(8, 5, -8, -5)
        side = min(rect.width(), rect.height())
        c = QtCore.QPointF(rect.center().x(), rect.center().y() + side * 0.02)
        rad = side * 0.39
        arc_rect = QtCore.QRectF(c.x()-rad, c.y()-rad, 2*rad, 2*rad)

        # Título y rango superior
        p.setPen(QtGui.QColor("#91aab4"))
        p.setFont(QtGui.QFont("Consolas", 8, 700))
        p.drawText(rect, QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignHCenter, self.title.upper())
        p.setFont(QtGui.QFont("Consolas", 7, 700))
        p.setPen(QtGui.QColor("#4e7482"))
        p.drawText(rect.adjusted(8, 17, -8, 0), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft, f"MIN {self.minimum:g}")
        p.drawText(rect.adjusted(8, 17, -8, 0), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight, f"MAX {self.maximum:g}")

        # Arco base y zonas operativas
        p.setPen(QtGui.QPen(QtGui.QColor("#193440"), 13, cap=QtCore.Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, 225*16, -270*16)

        title = self.title.upper()
        if "MEDIDOR G" in title:
            zones = [
                (self.minimum, 2.5, "#4acb91"),
                (2.5, 4.0, "#f2bd4f"),
                (4.0, self.maximum, "#ef5e5e"),
            ]
            for z0, z1, color in zones:
                z0 = max(self.minimum, z0); z1 = min(self.maximum, z1)
                if z1 <= z0: continue
                start = 225 - 270*self._frac(z0)
                span = -270*(self._frac(z1)-self._frac(z0))
                p.setPen(QtGui.QPen(QtGui.QColor(color), 5, cap=QtCore.Qt.PenCapStyle.FlatCap))
                p.drawArc(arc_rect, int(start*16), int(span*16))
        else:
            p.setPen(QtGui.QPen(QtGui.QColor("#315868"), 4, cap=QtCore.Qt.PenCapStyle.FlatCap))
            p.drawArc(arc_rect, 225*16, -270*16)

        # Progreso actual
        frac = self._frac(self.value)
        p.setPen(QtGui.QPen(self._zone_color(frac), 5, cap=QtCore.Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, 225*16, int(-270*frac*16))

        # Marcas y números de escala
        major_count = 10
        p.setFont(QtGui.QFont("Consolas", 7, 700))
        for i in range(major_count + 1):
            value = self.minimum + (self.maximum-self.minimum)*i/major_count
            a = math.radians(225 - 270*i/major_count)
            outer = QtCore.QPointF(c.x()+rad*math.cos(a), c.y()-rad*math.sin(a))
            inner = QtCore.QPointF(c.x()+rad*.80*math.cos(a), c.y()-rad*.80*math.sin(a))
            p.setPen(QtGui.QPen(QtGui.QColor("#a7c3ce"), 1.2))
            p.drawLine(inner, outer)

            label_r = rad * .64
            lp = QtCore.QPointF(c.x()+label_r*math.cos(a), c.y()-label_r*math.sin(a))
            if abs(value) >= 10 or float(value).is_integer():
                txt = f"{value:.0f}"
            else:
                txt = f"{value:.1f}"
            p.setPen(QtGui.QColor("#b8d3dc"))
            p.drawText(QtCore.QRectF(lp.x()-17, lp.y()-8, 34, 16), QtCore.Qt.AlignmentFlag.AlignCenter, txt)

            if i < major_count:
                for j in range(1, 5):
                    sf = (i + j/5) / major_count
                    sa = math.radians(225 - 270*sf)
                    sout = QtCore.QPointF(c.x()+rad*math.cos(sa), c.y()-rad*math.sin(sa))
                    sinr = QtCore.QPointF(c.x()+rad*.90*math.cos(sa), c.y()-rad*.90*math.sin(sa))
                    p.setPen(QtGui.QPen(QtGui.QColor("#587987"), .8))
                    p.drawLine(sinr, sout)

        # Marcador de pico
        pa = self._angle(self.peak_value)
        p1 = QtCore.QPointF(c.x()+rad*.98*math.cos(pa), c.y()-rad*.98*math.sin(pa))
        p2 = QtCore.QPointF(c.x()+rad*.84*math.cos(pa), c.y()-rad*.84*math.sin(pa))
        p.setPen(QtGui.QPen(QtGui.QColor("#ffca5c"), 3))
        p.drawLine(p1, p2)

        # Aguja
        ang = self._angle(self.value)
        end = QtCore.QPointF(c.x()+rad*.70*math.cos(ang), c.y()-rad*.70*math.sin(ang))
        p.setPen(QtGui.QPen(QtGui.QColor("#eefaff"), 3.2, cap=QtCore.Qt.PenCapStyle.RoundCap))
        p.drawLine(c, end)
        p.setBrush(QtGui.QColor("#65d8ff"))
        p.setPen(QtGui.QPen(QtGui.QColor("#dffaff"), 1))
        p.drawEllipse(c, 7, 7)

        # Display digital central
        box_w, box_h = rad*1.02, 38
        box = QtCore.QRectF(c.x()-box_w/2, c.y()-22, box_w, box_h)
        p.setBrush(QtGui.QColor("#02070a"))
        p.setPen(QtGui.QPen(QtGui.QColor("#315766"), 1.2))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QtGui.QColor("#effcff"))
        p.setFont(QtGui.QFont("Consolas", 17, 700))
        precision = 2 if abs(self.maximum-self.minimum) <= 10 else 1
        p.drawText(box.adjusted(0, -2, 0, -7), QtCore.Qt.AlignmentFlag.AlignCenter, f"{self.value:.{precision}f}")
        p.setPen(QtGui.QColor("#66d9ff"))
        p.setFont(QtGui.QFont("Consolas", 7, 700))
        p.drawText(box.adjusted(0, 20, 0, 0), QtCore.Qt.AlignmentFlag.AlignCenter, self.unit)

        # Pie: estado y pico
        footer = rect.adjusted(8, 0, -8, -1)
        p.setFont(QtGui.QFont("Consolas", 7, 700))
        p.setPen(QtGui.QColor("#63e6b5"))
        p.drawText(footer, QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignLeft, self._status_text())
        p.setPen(QtGui.QColor("#f3c55d"))
        p.drawText(footer, QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignRight, f"PEAK {self.peak_value:+.1f}")


class HeadingGauge(QtWidgets.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.heading=0.0; self.setMinimumSize(230,200)
    def setValue(self,v): self.heading=float(v)%360; self.update()
    def paintEvent(self,event):
        p=QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing); r=self.rect().adjusted(8,8,-8,-8); c=QtCore.QPointF(r.center()); rad=min(r.width(),r.height())*.43
        p.setPen(QtGui.QPen(QtGui.QColor("#315766"),2)); p.drawEllipse(c,rad,rad)
        p.setFont(QtGui.QFont("Consolas",9,700))
        for deg in range(0,360,15):
            a=math.radians(deg-90-self.heading); out=QtCore.QPointF(c.x()+rad*math.cos(a),c.y()+rad*math.sin(a)); inn=QtCore.QPointF(c.x()+rad*(.84 if deg%45==0 else .91)*math.cos(a),c.y()+rad*(.84 if deg%45==0 else .91)*math.sin(a)); p.setPen(QtGui.QColor("#9fc2cf")); p.drawLine(inn,out)
            if deg%45==0:
                labels={0:'N',90:'E',180:'S',270:'W'}; txt=labels.get(deg,str(deg)); pos=QtCore.QPointF(c.x()+rad*.68*math.cos(a),c.y()+rad*.68*math.sin(a)); p.drawText(QtCore.QRectF(pos.x()-15,pos.y()-8,30,16),QtCore.Qt.AlignmentFlag.AlignCenter,txt)
        p.setPen(QtGui.QPen(QtGui.QColor("#77e4ff"),3)); p.drawLine(QtCore.QPointF(c.x(),c.y()-rad),QtCore.QPointF(c.x(),c.y()-rad*.78))
        p.setPen(QtGui.QColor("#eafcff")); p.setFont(QtGui.QFont("Consolas",17,700)); p.drawText(r,QtCore.Qt.AlignmentFlag.AlignCenter,f"{self.heading:03.0f}°")
        p.setPen(QtGui.QColor("#76e2ff")); p.setFont(QtGui.QFont("Consolas",8,700)); p.drawText(r,QtCore.Qt.AlignmentFlag.AlignBottom|QtCore.Qt.AlignmentFlag.AlignHCenter,"RUMBO / GIRÓSCOPO DIRECCIONAL")


class BodyRatesWidget(QtWidgets.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.values=[0.,0.,0.]; self.setMinimumSize(230,180)
    def set_rates(self,roll,pitch,yaw): self.values=[float(roll),float(pitch),float(yaw)]; self.update()
    def paintEvent(self,event):
        p=QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing); r=self.rect().adjusted(10,8,-10,-8)
        labels=['ALABEO','CABECEO','GUIÑADA']; cols=['#65d9ff','#62e3c2','#c7a9ff']
        for i,(lab,val,col) in enumerate(zip(labels,self.values,cols)):
            y=r.top()+28+i*(r.height()-35)/3; p.setPen(QtGui.QColor('#8fa7b0')); p.setFont(QtGui.QFont('Consolas',8,700)); p.drawText(r.left(),int(y-8),55,16,QtCore.Qt.AlignmentFlag.AlignLeft,lab)
            x1=r.left()+60; x2=r.right()-45; mid=(x1+x2)/2; p.setPen(QtGui.QPen(QtGui.QColor('#294552'),2)); p.drawLine(QtCore.QPointF(x1,y),QtCore.QPointF(x2,y)); pos=mid+max(-1,min(1,val/90.0))*(x2-x1)/2; p.setBrush(QtGui.QColor(col)); p.setPen(QtCore.Qt.PenStyle.NoPen); p.drawEllipse(QtCore.QPointF(pos,y),7,7); p.setPen(QtGui.QColor('#dff8ff')); p.setFont(QtGui.QFont('Consolas',9,700)); p.drawText(x2+5,int(y-8),42,16,QtCore.Qt.AlignmentFlag.AlignRight,f'{val:+.0f}')
