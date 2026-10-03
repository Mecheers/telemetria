from PyQt6 import QtWidgets, QtCore

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent); self.config=config; self.setWindowTitle('Ground Station Configuration'); self.resize(620,520)
        v=QtWidgets.QVBoxLayout(self); tabs=QtWidgets.QTabWidget(); v.addWidget(tabs)
        self.fields={}
        sections=[('GENERAL','general'),('PUERTO SERIE','serial'),('LÍMITES / ALARMAS','limits'),('SIMULACIÓN','simulation'),('VISUALIZACIÓN','display')]
        for title,key in sections:
            page=QtWidgets.QWidget(); form=QtWidgets.QFormLayout(page)
            for name,value in config[key].items():
                if isinstance(value,bool): w=QtWidgets.QCheckBox(); w.setChecked(value)
                elif isinstance(value,int): w=QtWidgets.QSpinBox(); w.setRange(-1000000,1000000); w.setValue(value)
                elif isinstance(value,float): w=QtWidgets.QDoubleSpinBox(); w.setDecimals(3); w.setRange(-1000000,1000000); w.setValue(value)
                else: w=QtWidgets.QLineEdit(str(value))
                self.fields[(key,name)]=w; form.addRow(name.replace('_',' ').upper(),w)
            tabs.addTab(page,title)
        box=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); v.addWidget(box)
    def values(self):
        out={k:dict(v) for k,v in self.config.items()}
        for (sec,name),w in self.fields.items():
            if isinstance(w,QtWidgets.QCheckBox): val=w.isChecked()
            elif isinstance(w,(QtWidgets.QSpinBox,QtWidgets.QDoubleSpinBox)): val=w.value()
            else: val=w.text()
            out[sec][name]=val
        return out

class ManualSimulationDialog(QtWidgets.QDialog):
    changed=QtCore.pyqtSignal(dict)
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('Manual Instrument Bench'); self.resize(430,520)
        f=QtWidgets.QFormLayout(self); self.sliders={}
        specs={'alt_m':(0,2000,0),'az_g':(-100,800,100),'roll':(-180,180,0),'pitch':(-90,90,0),'yaw':(0,359,0),'temp_c':(-20,80,22),'battery_v':(80,140,122),'sats':(0,20,11)}
        for key,(lo,hi,val) in specs.items():
            row=QtWidgets.QHBoxLayout(); s=QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal); s.setRange(lo,hi); s.setValue(val); lab=QtWidgets.QLabel(str(val)); s.valueChanged.connect(lambda x,l=lab,k=key:(l.setText(str(x)),self._emit())); row.addWidget(s); row.addWidget(lab); f.addRow(key.upper(),row); self.sliders[key]=s
        b=QtWidgets.QPushButton('CERRAR'); b.clicked.connect(self.close); f.addRow(b)
    def _emit(self):
        d={k:s.value() for k,s in self.sliders.items()}; d['az_g']/=100; d['battery_v']/=10; self.changed.emit(d)
