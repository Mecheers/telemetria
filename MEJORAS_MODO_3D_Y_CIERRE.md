# Mejoras: modo 3D y cierre del programa

## Selector del gráfico 3D

Se agregó un selector **3D MODE** dentro del panel del cohete:

- **AUTOMÁTICO**: el modelo adopta roll, pitch y yaw recibidos por telemetría o simulación. AJUSTE AUTOMÁTICO y CÁMARA DE SEGUIMIENTO permanecen disponibles.
- **MANUAL**: la actitud automática queda ignorada para el modelo 3D. Se habilitan controles independientes de **R**, **P** y **Y** entre -180° y +180°.
- El botón **ZERO** lleva los tres ángulos manuales a 0°.
- En modo manual AJUSTE AUTOMÁTICO y CÁMARA DE SEGUIMIENTO se deshabilitan, permitiendo orbitar y ampliar la cámara con el mouse sin que vuelva a moverse automáticamente.
- Al volver a automático, el cohete recupera inmediatamente la última actitud válida de telemetría.

## Botón de cierre

Se agregó el botón **✕ CERRAR** en el extremo superior derecho.

El botón utiliza el cierre normal de la ventana, por lo que ejecuta la limpieza ya existente:

- detiene simulación;
- detiene replay;
- detiene grabación;
- desconecta el puerto serie;
- guarda la configuración antes de salir.

## Verificación

- Compilación sintáctica correcta de `main_window.py` y `rocket_3d.py`.
- `tests_core.py`: OK.
