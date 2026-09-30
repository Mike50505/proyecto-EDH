# Mapeo de migración

| Origen | Destino | Regla |
| --- | --- | --- |
| Archivo cifrado | `SourceBook.filename`, `sha256`, `classification` | Hash del archivo original; los cuatro son un mismo cliente Daikin. |
| `Datos!G2` | `Client.name` | Texto conservado; no se interpreta como planta. |
| `Familias!A` | `Part.part_type` | Conserva FP/RM/PP/BR o vacío; vacío exige revisión. |
| `Familias!B:C` | `Part.bom_revision`, `drawing_revision` | Texto. |
| `Familias!D:G` | `Part.code`, `description`, `drawing_number`; `BOMItem.quantity_per` | Código como texto. Cantidad por unidad pertenece a la relación padre-componente. |
| `Familias!H:J` | `Part.od_raw`, `wall_raw`, `development_raw` | Se conserva texto y calificadores; sin conversión automática de unidades. |
| Fórmula en `Familias!J` | `Part.development_formula` y `development_raw` | Se guarda fórmula y resultado cacheado; no se recalcula. |
| `Familias!K:L` | `Part.comments`, `phase` | Texto original. |
| Bloque FP de Headers | `BOMItem.parent`, `component`, `position` | El siguiente FP cierra el bloque. También se conserva `Part.source_row`. |
| `Ruta!A` | `Route.code`, `source_code`, `source_row` | Se limpia clave de búsqueda; valor original y fila no se pierden. Cada fila con código crea una ruta de origen. |
| Encabezados de Ruta, fila 1 | `Operation.name`, `source_group` | Grupos de cuatro columnas de cada libro; DOBLEZ 1/2 no se fusionan. |
| Cada grupo de Ruta | `Operation.source_sequence`, `tooling`, `inspection`, `machine` | Orden por secuencia numérica y grupo original; las repeticiones se reportan, no se sobrescriben. |
| `Datos!A:I` | `Schedule` y `ScheduleLine` al capturar programación nueva | El origen no se importó como producción ejecutada o entregada. Semana y orden son texto. |
| Captura web por emisión | `Schedule.issue_date`, `ship_date`, `responsible` | Fecha de emisión prellenada con el día actual; embarque opcional hasta que se conozca. No se inventan fechas del Excel. |
| Copias elegidas por el usuario | `Schedule.copies`, `IssuedDocument.snapshot.copies` | Se repiten páginas del documento; no se multiplica la cantidad programada ni la BOM. |
| `PartList`, `Etiqueta`, `Etiqueta1` | Ningún catálogo nuevo | Son salidas heredadas. Sirven para validación visual, no para crear piezas maestras. |

`Part.source_values` guarda la fila A:L como evidencia adicional. `Route.source`, `source_sheet` y `source_row` permiten volver al origen. `ImportRun` e `ImportIssue` conservan simulaciones, conflictos e incidencias. No se fusionan variantes por código.
