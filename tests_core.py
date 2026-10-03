from app.core.professional import AlarmManager, PhaseDetector

def test_phase_detector():
    p=PhaseDetector()
    assert p.phase=='PRELAUNCH'
    p.update({'alt_m':0,'vspeed':4,'az_g':2})
    assert p.phase=='LAUNCH'
    p.update({'alt_m':12,'vspeed':8,'az_g':2})
    assert p.phase=='POWERED ASCENT'

def test_alarms():
    a=AlarmManager({'battery_low_v':10.5,'battery_critical_v':9.8,'temperature_high_c':50,'g_high':4.5,'g_critical':6,'crc_rate_warn_pct':2,'gps_min_sats':5})
    new=a.evaluate({'battery_v':9.5,'temp_c':20,'az_g':1,'sats':8},{'crc_pct':0},True)
    assert any(x.key=='BAT_CRIT' for x in new)

if __name__=='__main__':
    test_phase_detector(); test_alarms(); print('core tests OK')
