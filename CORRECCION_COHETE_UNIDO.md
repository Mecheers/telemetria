# Corrección del modelo 3D del cohete

Se corrigieron dos causas que hacían que el cohete se viera desarmado o inestable:

1. La ogiva estaba generada al revés: comenzaba en punta sobre el fuselaje y terminaba ancha en la parte superior. Ahora comienza con el radio del fuselaje y termina en radio cero.
2. Las rotaciones propias de las aletas se aplicaban como transformaciones temporales. `resetTransform()` las eliminaba en cada actualización. Ahora las orientaciones se incorporan directamente a los vértices del modelo.

Todas las piezas mantienen coordenadas locales comunes y reciben la misma transformación de actitud y posición.
