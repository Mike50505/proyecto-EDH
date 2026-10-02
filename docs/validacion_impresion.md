# Validación de impresión

## Referencia recibida

La captura `Captura de pantalla 2026-09-29 113422` muestra dos etiquetas apiladas en una hoja horizontal para el padre `4P503730-1`: los componentes RM `3P500707-1` (2 DE 3) y `4PA17856-6` (3 DE 3). Incluye logo MESA Ramos Arizpe, título EDH, identificación, tabla de 15 filas, instrucciones especiales, certificado, notas de calidad y plan de reacción. El BR del BOM no aparece como etiqueta en esta captura.

## Implementación y comprobación

El PDF usa hoja carta horizontal con dos etiquetas por página. Cada RM del padre produce una etiqueta con su ruta de la misma fuente y cantidad programada multiplicada por cantidad por unidad. La opción Original conserva el contador `2 DE 3` y `3 DE 3` de la captura; la opción Solo componentes los numera `1 DE 2` y `2 DE 2`; la opción Incluir padre agrega primero una etiqueta del ensamble sin dimensiones de componente y usa `1 DE 3`, `2 DE 3`, `3 DE 3`. Una ruta sin RM produce una etiqueta. Las copias repiten las hojas sin multiplicar piezas. Las operaciones que exceden diez se continúan en otra etiqueta con contexto y un total de 15 filas para escritura manual.

La muestra `output/pdf/ejemplo_provisional_daikin.pdf` usa los datos reales de las rutas de la captura y una orden `PRUEBA-NO-PRODUCCION`. Se renderizó a PNG y se inspeccionó: una página, dos etiquetas completas, sin cortes visibles. Las pruebas Django cubren cantidad, numeración, exclusión de BR, páginas por copia, instantánea histórica y bloqueo de rutas de componente ambiguas o sin aprobar.

La captura no aporta medidas físicas ni configuración de impresora. Por eso la escala de impresión, márgenes y zonas de corte siguen pendientes de cotejo con una hoja impresa al 100 %. También faltan muestras aprobadas de las demás variantes y la aprobación física de la etiqueta 1 DE 3 del padre. El PDF lleva aviso de composición provisional para evitar confundir la muestra con un formato aprobado de producción.

## Correspondencia de campos

| Campo | Fuente del PDF |
| --- | --- |
| Padre, componente, descripción, OD, pared y desarrollo | `Familias` |
| Ruta, máquina, inspección y herramental | `Ruta` del componente, preservando la variante |
| Semana, orden, cantidad, fechas y responsables | Programación web |
| Logo | Recurso extraído del libro Headers proporcionado |

Los textos de medidas se conservan sin conversión de unidades. Los encabezados Inspección y Herramental expresan el contenido real de esos campos, aunque los encabezados heredados de Excel sean inconsistentes.

## Validación a escala real pendiente

1. Imprimir el PDF de muestra al 100 % en la impresora del taller y medir papel, márgenes, bloques y corte.
2. Confirmar si se emite la etiqueta 1 DE 3 del padre y qué regla aplica a PP/BR.
3. Repetir comparación para Headers, Individuales y ambas variantes SLP con una muestra aprobada de cada una.
4. Registrar aprobación de producción/calidad antes de retirar el aviso provisional.
