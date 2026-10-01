# Decisiones y pendientes

## Decisiones implementadas

- Django y PostgreSQL en un monolito; Excel solo se lee durante importación.
- Identificadores y medidas originales se conservan como texto. No se convierte la semana a ISO ni se sustituyen rutas entre variantes.
- Cada fila de Ruta con código crea una ruta con procedencia. Conflictos y duplicados quedan visibles; no se sobrescriben datos de la web en reimportación.
- Los PDFs emitidos desde una programación guardan instantánea y archivo original privado. La descarga se registra separada de la generación.
- La tabla de **Seleccionar órdenes** y su plantilla Excel solo preparan un PDF temporal en memoria. No crean programación ni documento emitido. Las rutas por revisar salen marcadas **NO APROBADA**; para duplicados en el mismo libro la vista previa usa la primera coincidencia de la macro e indica la fila. La emisión persistente sigue bloqueada hasta resolver incidencias.
- La captura `Captura de pantalla 2026-09-29 113422` guía la composición: dos etiquetas de componentes RM por hoja carta horizontal, con logo MESA y 15 filas para operaciones y escritura manual. El BR de ese ejemplo no genera etiqueta.
- El diseño web usa componentes y paleta inspirados en Apple: fondo gris claro, superficies blancas, texto grafito, azul de acción, radios discretos, tipografía de sistema y retroalimentación breve al presionar. La navegación y formularios no dependen de animaciones.

## Pendientes para aceptación completa

1. Obtener muestras aprobadas de las demás salidas y validar papel, márgenes, cortes y escala física en una impresión al 100 %.
2. Confirmar la etiqueta `1 DE 3` del padre y la regla general para PP/BR; la captura solo muestra `2 DE 3` y `3 DE 3` de dos RM.
3. Resolver conflictos entre variantes, FP sin Ruta local, secuencias repetidas y tipos vacíos con responsables operativos.
4. Confirmar la cantidad por etiqueta/número de etiquetas; el número de copias del PDF ya se captura separado de la cantidad de piezas. La pantalla de incidencias ya muestra registros y operaciones de coincidencias lado a lado, con selección de variante y resolución documentada.
5. Medir la red/impresora con uso real. `audit_print_sources --large-batch` generó y verificó un PDF temporal por cada una de las siete variantes y un lote de 200 etiquetas (100 páginas, 1,034,055 bytes, 15.14 s); la plantilla Excel acepta 200 filas y rechaza 201. `benchmark_catalog --requests 40 --workers 4` midió la vista con las 2,468 rutas importadas. Faltan pruebas de concurrencia HTTP desde otros dispositivos y aprobación física de cada plantilla.
6. Completar respaldo/restauración conjunta de PostgreSQL y PDFs en el servidor definitivo. `tools/verify_backup.ps1` copia ambos volúmenes, restaura la base en un nombre temporal y compara conteos; también comprueba existencia y SHA-256 de PDFs emitidos cuando los haya. La ejecución del 1 de octubre restauró 2,468 rutas y 4,171 piezas, pero había 0 documentos emitidos y 0 archivos, por lo que aún falta verificar un vínculo documento-PDF real. Para uso en producción se debe pausar la escritura de documentos durante la copia para obtener una instantánea coherente.

La importación de datos no equivale a aprobación de rutas o impresión. Los estados **Por revisar** bloquean su emisión; las restantes rutas aún generan un formato marcado provisional.

## Avance del cierre (1 de octubre de 2026)

Estimación global: **65 %**. La comparación de incidencias está implementada, las siete variantes producen un PDF temporal verificable y se midieron 40 lecturas concurrentes del catálogo (mediana 39 ms, p95 55 ms, 4 trabajadores). La plantilla acepta 200 órdenes; un PDF temporal de 200 etiquetas produjo 100 páginas en 15.14 s. La base y el volumen de medios se respaldaron y se restauró la base temporalmente con los conteos esperados. El porcentaje mide avance de tareas, no aprobación del formato para producción. Siguen pendientes las muestras físicas y las reglas de padre/PP/BR, las decisiones operativas sobre incidencias, la prueba de uso desde red e impresora reales y la restauración conjunta con un PDF emitido. En esta base todavía hay **0 documentos emitidos**.
