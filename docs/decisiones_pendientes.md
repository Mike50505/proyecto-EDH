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
4. Ampliar la pantalla de incidencias con comparación lado a lado y confirmar la cantidad por etiqueta/número de etiquetas; el número de copias del PDF ya se captura separado de la cantidad de piezas. La resolución con nota y selección múltiple ya están disponibles.
5. Añadir pruebas de plantilla por cada variante, cargas largas y mediciones de rendimiento con volumen/concurrencia reales.
6. Ejecutar y documentar respaldo/restauración conjunta de PostgreSQL y PDFs en el servidor definitivo. La restauración de PostgreSQL se comprobó en una base temporal con conteos idénticos.

La importación de datos no equivale a aprobación de rutas o impresión. Los estados **Por revisar** bloquean su emisión; las restantes rutas aún generan un formato marcado provisional.
