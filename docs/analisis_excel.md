# Análisis de las fuentes Excel

## Alcance de esta verificación

El 29-09-2026 se abrieron las cuatro fuentes cifradas en memoria, en modo de lectura, sin ejecutar VBA ni modificar los originales. Se leyeron `Familias`, `Ruta`, `Datos`, la lista de hojas y metadatos XML de impresión. La inspección previa de VBA, dibujos y plantillas descrita en el prompt se conserva como antecedente; **no se reextrajo aquí todo el proyecto VBA ni se realizó impresión física**.

Una fila de Ruta cuenta si A contiene un código tras quitar espacios exteriores, incluido espacio no separable. Las operaciones se cuentan por grupo con algún dato, ordenadas por el número de secuencia original sin renumerarlo.

| Variante | SHA-256 del archivo cifrado | Familias | Ruta | Ruta con operaciones | Operaciones importadas | Grupos |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Headers | `cd5c5b633b13e6c4ac01e77d7a5083bcdc06e72a749420bce1b92fd4a6032ae9` | 82 | 65 | 42 | 272 | 32 |
| Individuales | `b612af099b0b92601d42e4f258cfe2039327bc7fb763722e47ebd1b2959a02c2` | 69 | 64 | 64 | 369 | 30 |
| SLP Headers | `8fb603b3045e1b80494cc9b6b22772259bf2d341ae1b0d097f9dff190432d6ec` | 96 | 75 | 47 | 317 | 33 |
| SLP Individuales | `f22b4ee95f42de1904062deaeb33774c3b67ecd45f8a9f6405c66ea528e32ab1` | 79 | 75 | 75 | 437 | 33 |

Total: **326 filas de Familias, 279 filas de Ruta, 1,395 grupos de operación con datos**. PostgreSQL contiene 4 procedencias, 326 piezas de origen, 279 rutas de origen y 124 relaciones BOM. No son 279 rutas únicas. Hubo 103 incidencias de importación iniciales; la auditoría añadió 152 diferencias entre libros y 15 FP sin Ruta local: **270 incidencias** en total. Quedaron 206 rutas por revisar y 73 activas.

## Estructura y reglas observadas

- Todos los libros tienen `DAIKIN` en `Datos!G2`. Headers y SLP Headers tienen `PartList`, `Ruta`, `Familias`, `Etiqueta1`, `Datos`, `Etiqueta`. Los Individuales también contienen `Hoja1`.
- `Familias!A:L` contiene tipo, revisiones, parte, descripción, dibujo, cantidad, OD, pared, desarrollo, comentario y fase. En Headers, una fila FP inicia el bloque de ensamble; la posición original se conserva en la BOM.
- `Ruta!A` contiene el código. Desde B, grupos de cuatro columnas contienen secuencia, herramental, inspección y máquina; el nombre del proceso se toma de la fila 1. El orden se toma del número de secuencia, preservando el grupo original y números repetidos.
- `Datos!A:I` corresponde a shop order, padre, cantidad, semana, RE, secuencia, línea/cliente, planner y responsable. `PartList` y `Etiqueta` son salidas, no nuevos catálogos.
- `Familias!J8` y `J12` en los dos Individuales conservaron `=124-1`/`123` y `=180-2`/`178`, respectivamente. La biblioteca lee el resultado guardado; no recalcula fórmulas.
- `Familias!A45` de ambos Headers está vacío para `4P669357-1`; se conservó sin tipo y requiere clasificación.
- `4PA17856-6` aparece en filas 4 y 57 de cada Headers; `4P663164-1` aparece en filas 6 y 34 de los Individuales después de limpiar espacios. Se conservaron como rutas separadas, en revisión. También se preservan secuencias repetidas.

## Ajustes de impresión almacenados

El XML de las cuatro `Etiqueta1` muestra orientación horizontal y escala 73%, 72%, 73%, 73% respectivamente. En Headers se encontraron 45 saltos de fila declarados. Los márgenes XML de `Etiqueta1` aparecen en pulgadas: izquierda 0.3, derecha ~0.1181, arriba 0.17, abajo ~0.1575. El área de impresión guardada es inconsistente: por ejemplo, en Headers no figura `Etiqueta1`, mientras en Individuales sí figura `Etiqueta1!$A$1:$CS$2647`. Estos metadatos no determinan por sí solos el papel físico ni cuántas etiquetas salen por página; hay configuración binaria de impresora y se requiere una referencia real.

## Conciliaciones pendientes

- Verificar significado operativo de Headers, Individuales y SLP. Se guardan como clasificaciones de origen, no como clientes o plantas.
- Confirmar cuáles componentes RM, PP y BR necesitan ruta y etiqueta separada. La BOM conserva todos.
- Comparar versiones y duplicados entre libros, seleccionar rutas autorizadas y resolver FP sin Ruta local. `reconcile_sources` reporta esas diferencias sin fusionarlas.
- Confirmar numeración `N DE M`, impresión del padre, caso SOLDADURA NIPLES y si se usa `Etiqueta` además de `Etiqueta1`.
- Confirmar unidades por campo y resolver textos como `7mm`, `3/8`, `223*` sin conversión supuesta.
- Comparar PDF contra una muestra aprobada y una impresión a escala real. Ver `validacion_impresion.md`.

No se midió Excel ejecutando macros. Los posibles costos por estilos, dibujos, búsquedas lineales y rangos enormes siguen siendo hipótesis del análisis estático previo.

## Medición de desarrollo

Con Docker Desktop sobre este equipo Windows, 279 rutas, 326 piezas, 1,395 operaciones y un solo usuario, una ejecución de `tools/benchmark.py` midió búsqueda paginada (30 resultados) en 0.0147 s, carga ORM de detalle en 0.0031 s, PDF de una partida en 0.129 s y PDF de diez partidas en 0.479 s. Son tiempos de una ejecución, sin concurrencia ni impresión física; no representan un compromiso para mayor volumen.
