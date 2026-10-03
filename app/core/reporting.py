import json
from datetime import datetime

def generate_html_report(path, mission_name, telemetry, stats, config, alarms, phase):
    rows = ''.join(
        '<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            datetime.fromtimestamp(a.timestamp).strftime('%H:%M:%S'), a.severity, a.message
        ) for a in alarms
    ) or '<tr><td colspan="3">Sin alarmas</td></tr>'
    cards = [
        ('Fase', phase), ('Altitud máxima', f"{stats['max_alt']:.1f} m"),
        ('Tramas válidas', str(stats['frames'])), ('Errores CRC', str(stats['crc'])),
        ('G máxima', f"{stats['max_g']:.2f} g"), ('Pérdidas de secuencia', str(stats['loss'])),
        ('GPS', f"{telemetry['lat']:.6f}, {telemetry['lon']:.6f}"), ('Batería', f"{telemetry['battery_v']:.2f} V")
    ]
    card_html=''.join(f'<div class="card">{k}<br><b>{v}</b></div>' for k,v in cards)
    html=f'''<!doctype html><html><head><meta charset="utf-8"><title>Mission report</title><style>
body{{font-family:Segoe UI,Arial;background:#071017;color:#dceef4;padding:30px}} h1,h2{{color:#65d9ff}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}} .card{{background:#0b1922;border:1px solid #285064;padding:15px}}
table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #285064;padding:8px}}pre{{background:#03090d;padding:15px;overflow:auto}}
</style></head><body><h1>ESTACIÓN TERRESTRE — INFORME DE MISIÓN</h1><p>{mission_name} · {datetime.now().isoformat(timespec='seconds')}</p>
<div class="grid">{card_html}</div><h2>Historial de alarmas</h2><table><tr><th>Hora</th><th>Severidad</th><th>Mensaje</th></tr>{rows}</table>
<h2>Configuración registrada</h2><pre>{json.dumps(config,indent=2,ensure_ascii=False)}</pre></body></html>'''
    path.write_text(html,encoding='utf-8')
    return path
