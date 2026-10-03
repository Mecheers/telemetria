# Revisión de estabilidad de botones

Se centralizó el estado de la interfaz en `MainWindow._sync_controls()` para que la apariencia y la habilitación de cada botón dependan del estado real de la conexión serial, simulación, banco manual, replay y grabación.

## Cambios principales

- Los botones de simulación ya no conservan el fondo verde/rojo cuando están deshabilitados.
- `CONECTAR` muestra `CONECTARING…` mientras el puerto todavía no se abrió.
- La conexión solo se marca activa después de que `SerialWorker` confirma la apertura real del puerto.
- Los errores y cierres del puerto actualizan automáticamente todos los controles.
- `REPRODUCIR` cambia a `STOP REPRODUCIR` mientras se reproduce un archivo y permite detenerlo.
- Al finalizar un replay, la interfaz vuelve automáticamente a modo EN VIVO.
- Al terminar o fallar una simulación, el modo y los botones vuelven a un estado coherente.
- El banco manual bloquea las otras fuentes de telemetría mientras está abierto y libera los controles al cerrarse.
- Los botones de navegación quedaron agrupados de forma exclusiva; solo una pestaña puede aparecer activa.
- REC/STOP reflejan directamente el estado real del logger.

## Verificación realizada

- Compilación sintáctica de todos los módulos Python.
- Ejecución satisfactoria de `tests_core.py`.
- No se pudo ejecutar la interfaz gráfica en este entorno porque PyQt6 no está instalado en el contenedor de revisión.
