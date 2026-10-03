from __future__ import annotations
import json, logging, math, os, shutil, sys, time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_CONFIG = {
    "general": {"mission_prefix":"MISSION", "operator":"", "vehicle":"Cohete experimental", "units":"metric", "sound_alarms":False},
    "serial": {"baud":9600, "expected_fast_hz":20.0, "expected_slow_hz":1.0, "link_timeout_s":2.5},
    "limits": {"battery_low_v":10.5, "battery_critical_v":9.8, "temperature_high_c":50.0, "g_high":4.5, "g_critical":6.0, "crc_rate_warn_pct":2.0, "gps_min_sats":5},
    "simulation": {"max_altitude_m":525.0, "cycle_s":70.0, "noise":0.015, "packet_loss_pct":0.0, "crc_error_pct":0.0, "gps_dropout_pct":0.0, "battery_start_v":12.4, "battery_end_v":10.8},
    "display": {"max_plot_points":5000, "autofit":True, "chase_camera":True}
}

class ConfigManager:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "config.json"
        self.data = json.loads(json.dumps(DEFAULT_CONFIG))
        self.load()
    def load(self):
        if self.path.exists():
            try:
                user = json.loads(self.path.read_text(encoding="utf-8"))
                self._merge(self.data, user)
            except Exception:
                pass
        self.save()
        return self.data
    def _merge(self, dst, src):
        for k,v in src.items():
            if isinstance(v,dict) and isinstance(dst.get(k),dict): self._merge(dst[k],v)
            else: dst[k]=v
    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

@dataclass
class Alarm:
    key: str; severity: str; message: str; timestamp: float = field(default_factory=time.time); active: bool = True; acknowledged: bool = False

class AlarmManager:
    def __init__(self, limits: Dict): self.limits=limits; self.alarms: Dict[str,Alarm]={}; self.history: List[Alarm]=[]
    def _set(self,key,severity,msg,condition):
        a=self.alarms.get(key)
        if condition:
            if not a or not a.active:
                a=Alarm(key,severity,msg); self.alarms[key]=a; self.history.append(a); return a
            a.message=msg; a.severity=severity
        elif a and a.active: a.active=False
        return None
    def evaluate(self,t:Dict,stats:Dict,link_ok:bool):
        new=[]; L=self.limits
        checks=[
            ("LINK","CRITICAL","Enlace de telemetría perdido",not link_ok),
            ("BAT_CRIT","CRITICAL",f"Batería crítica: {t.get('battery_v',0):.2f} V",t.get('battery_v',99)<=L['battery_critical_v']),
            ("BAT_LOW","WARNING",f"Batería baja: {t.get('battery_v',0):.2f} V",L['battery_critical_v']<t.get('battery_v',99)<=L['battery_low_v']),
            ("TEMP","WARNING",f"Temperatura elevada: {t.get('temp_c',0):.1f} °C",t.get('temp_c',0)>=L['temperature_high_c']),
            ("G_CRIT","CRITICAL",f"Carga crítica: {t.get('az_g',0):.2f} g",abs(t.get('az_g',0))>=L['g_critical']),
            ("G_HIGH","WARNING",f"Carga elevada: {t.get('az_g',0):.2f} g",L['g_high']<=abs(t.get('az_g',0))<L['g_critical']),
            ("GPS","WARNING",f"GPS degradado: {int(t.get('sats',0))} sats",int(t.get('sats',0))<L['gps_min_sats']),
            ("CRC","WARNING",f"Tasa de errores CRC: {stats.get('crc_pct',0):.1f}%",stats.get('crc_pct',0)>=L['crc_rate_warn_pct']),
        ]
        for c in checks:
            a=self._set(*c)
            if a:new.append(a)
        return new
    def active(self): return [a for a in self.alarms.values() if a.active]
    def acknowledge_all(self):
        for a in self.active(): a.acknowledged=True

class PhaseDetector:
    PHASES=("PRELAUNCH","LAUNCH","POWERED ASCENT","COAST","APOGEE","DESCENT","LANDED")
    def __init__(self): self.phase="PRELAUNCH"; self.last_change=time.time(); self.events=[]; self.max_alt=0.0; self.stable_since=None
    def reset(self): self.__init__()
    def update(self,t:Dict):
        alt=float(t.get('alt_m',0)); vs=float(t.get('vspeed',0)); g=float(t.get('az_g',1)); self.max_alt=max(self.max_alt,alt); p=self.phase
        if p=="PRELAUNCH" and (g>1.35 or vs>2): p="LAUNCH"
        elif p=="LAUNCH" and alt>8 and vs>4: p="POWERED ASCENT"
        elif p=="POWERED ASCENT" and g<0.6 and vs>1: p="COAST"
        elif p in ("POWERED ASCENT","COAST") and self.max_alt-alt>2 and vs<0: p="APOGEE"
        elif p=="APOGEE" and vs<-1: p="DESCENT"
        elif p=="DESCENT":
            if alt<3 and abs(vs)<1.2:
                self.stable_since=self.stable_since or time.time()
                if time.time()-self.stable_since>2: p="LANDED"
            else:self.stable_since=None
        if p!=self.phase:
            self.phase=p; self.last_change=time.time(); self.events.append((self.last_change,p,alt)); return p
        return None

class MissionSession:
    def __init__(self, base_dir:str):
        self.root=Path(base_dir)/"missions"; self.root.mkdir(exist_ok=True); self.path:Optional[Path]=None; self.started=None; self.events=[]
    def start(self,name:str,config:Dict):
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); safe=''.join(c if c.isalnum() or c in '-_' else '_' for c in name)[:60] or 'MISSION'
        self.path=self.root/f"{safe}_{stamp}"; self.path.mkdir(parents=True,exist_ok=True); self.started=time.time(); self.events=[]
        (self.path/'configuration.json').write_text(json.dumps(config,indent=2,ensure_ascii=False),encoding='utf-8')
        self.add_event('INICIO_MISION','Sesión de misión creada')
        return self.path
    def add_event(self,event,detail):
        item={"time_iso":datetime.now().isoformat(timespec='milliseconds'),"elapsed_s":0 if not self.started else time.time()-self.started,"event":event,"detail":detail}; self.events.append(item)
        if self.path:
            import csv
            fp=self.path/'events.csv'; exists=fp.exists()
            with fp.open('a',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=item.keys());
                if not exists:w.writeheader()
                w.writerow(item)
    def default_log_path(self): return str(self.path/'telemetry.tlog') if self.path else ''

class AppDiagnostics:
    @staticmethod
    def install(base_dir:str):
        logs=Path(base_dir)/'logs'; logs.mkdir(exist_ok=True)
        log=logs/'application.log'
        logging.basicConfig(filename=log, level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        def hook(tp,val,tb): logging.exception('Unhandled exception',exc_info=(tp,val,tb)); sys.__excepthook__(tp,val,tb)
        sys.excepthook=hook
        return log
