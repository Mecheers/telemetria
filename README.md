# Estación Terrestre – Telemetría (PyQt6 + PyQtGraph + OpenGL)

## Ejecutar
```bash
pip install -r requirements.txt
python run.py
```

Si al iniciar ves pantalla negra:
- Probá actualizar drivers de GPU
- Probá desactivar fullscreen (ver app/main.py: w.showMaximized())

## Consola Flight Dynamics (edición visual)

Esta edición incorpora una interfaz inspirada en consolas de misión aeroespacial:

- Horizonte artificial con roll, pitch y rumbo.
- Teatro 3D central del vehículo.
- Indicadores circulares de giro, velocidad vertical y carga G.
- Brújula / directional gyro.
- Panel de body rates y estado de telemetría.
- Barra de misión, operaciones y estados EN VIVO/REPRODUCIR.

La lógica serial, CRC, registro TLOG, replay y exportación CSV se conserva.

## Modo simulación sin hardware

1. Ejecutar `python run.py`.
2. Elegir un escenario en **SCENARIO**.
3. Pulsar **▶ SIMULAR**.
4. La aplicación genera telemetría local a 20 Hz/4 Hz, incluyendo altitud, aceleración, roll, pitch, yaw, GPS y una secuencia completa con apogeo.
5. Pulsar **■ DETENER SIM.** para detenerla.

La simulación también puede grabarse con **REC** y reproducirse luego con **REPRODUCIR**.

## Pestañas funcionales

- **MISIÓN:** identificación, cronómetro, checklist, métricas y eventos.
- **PANEL GENERAL:** tarjetas de vuelo, gráficas en vivo y resumen de eventos.
- **ACTITUD:** instrumentos primarios, cohete 3D y dinámica de vuelo.
- **GPS:** fix, satélites, coordenadas y recorrido local simulado.
- **AMBIENTE:** temperatura, presión, humedad, batería y tendencia.
- **SERIE:** puerto, tasa, ancho de banda, errores CRC y consola RX.
- **REGISTRO / REPRODUCCIÓN:** control de grabación, reproducción, exportación y tabla de frames.

Todas las pestañas funcionan también con el modo SIMULATION, sin hardware externo.

## Revisión profunda del simulador
- Los controles del simulador están en una barra propia, siempre visible debajo de la barra serial.
- `SIMULAR` y `DETENER SIM.` ya no compiten por espacio con los controles de puerto.
- Se corrigió un error de pintura Qt en el indicador de rumbo que podía interrumpir la interfaz.
- El estado del simulador se muestra en un diagnóstico visible junto a los botones.
- Prueba realizada: generación local FAST 20 Hz + SBAJO 4 Hz, actualización de frames y parada correcta.

## Professional Operations Suite

This version adds a complete operational layer while preserving the working telemetry and simulator engine:

- Persistent `config.json` with serial, alarm, display and simulation parameters.
- Automatic mission folders under `missions/`.
- Automatic flight-phase detection: PRELAUNCH, LAUNCH, POWERED ASCENT, COAST, APOGEE, DESCENT and LANDED.
- Configurable alarms for telemetry link, battery, temperature, acceleration load, GPS and CRC rate.
- Alarm acknowledgment and event timeline.
- Manual instrument bench for direct control of altitude, attitude, G load, environment and GPS.
- Simulation fault injection: frame loss, CRC errors and GPS dropout.
- Mission report generation in portable HTML.
- Application diagnostics in `logs/application.log`.
- Configuration snapshot and `events.csv` stored with each mission.

### Recommended workflow

1. Open **CONFIGURACIÓN** and define serial speed, limits and simulation fault percentages.
2. Open **MISIÓN**, enter a mission ID and start the mission timer.
3. Start **SIMULAR** or connect the real serial device.
4. Use **REC** to save a TLOG inside the mission folder.
5. Review automatic phases and acknowledge alarms.
6. Press **MISIÓN REPORT** to create and open the final report.

### Manual bench

Press **BANCO MANUAL** to move every major instrument from the computer without hardware. Values are injected directly into the unified telemetry state and update every page.

## AI Analyst integrado

La pestaña **ANALISTA IA** incorpora análisis determinístico local y análisis consultivo mediante API:

- Diagnóstico local sin Internet.
- Ventanas de análisis de 30 y 60 segundos.
- Consulta libre sobre la telemetría.
- Explicación de alarmas.
- Informe postvuelo.
- Guardado de respuestas en TXT.
- La clave API se toma de `OPENAI_API_KEY` o se pega temporalmente en la pestaña; no se guarda en el proyecto.
- La IA no controla ignición, actuadores, sistemas pirotécnicos ni despliegues críticos.

En PowerShell puede definir la clave para la sesión:

```powershell
$env:OPENAI_API_KEY="su_clave"
$env:OPENAI_MODEL="gpt-5-mini"
python run.py
```

Para probar sin API, inicie **SIMULAR**, abra **ANALISTA IA** y pulse **DIAGNÓSTICO LOCAL**.


## Versión 02 — asistencia IA en Actitud

La pestaña **ACTITUD** incorpora un panel `ASISTENCIA IA DE VUELO` que se actualiza con la telemetría y muestra:

- estabilidad estimada de 0 a 100 %;
- nivel de riesgo BAJO, MEDIO o ALTO;
- confianza del análisis según disponibilidad y calidad de datos;
- fase estimada del vuelo;
- tendencia reciente de roll y pitch;
- recomendación de observación para el operador.

Este panel funciona localmente, no requiere API y no transmite órdenes al cohete. La pestaña **ANALISTA IA** sigue disponible para análisis explicativos mediante API.

# Versión 03 en español

Toda la interfaz visible fue adaptada al español sin modificar la arquitectura ni las funciones del programa.
