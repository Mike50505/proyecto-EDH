# Fuentes DAIKIN, LENNOX y RHEEM

Estado de la base de desarrollo tras la importación del 30 de septiembre de 2026. Los libros cifrados permanecen fuera de Git. La contraseña se introduce durante la importación y no se guarda.

| Cliente | Variante | Familias | Rutas | Grupos de operaciones | Estado de impresión |
| --- | --- | ---: | ---: | ---: | --- |
| DAIKIN | Headers, Individuales, SLP Headers, SLP Individuales | 326 | 279 | 1,395 | Formatos existentes conservados; 73 rutas activas y 206 en revisión |
| LENNOX | General | 1,807 | 282 | 1,044 | 282 en revisión; formato pendiente de aprobación |
| RHEEM | Headers | 1,017 | 919 | 4,003 | 919 en revisión; formato pendiente de aprobación |
| RHEEM | Individuales | 1,021 | 988 | 5,092 | 988 en revisión; formato pendiente de aprobación |
| **Total** | **Siete libros** | **4,171** | **2,468** | **11,534** | |

Se hicieron simulaciones de los tres libros nuevos antes de importarlos. Sus recuentos de filas coincidieron con los de la importación. La reconciliación posterior añadió dos discrepancias entre libros y 327 piezas FP sin una ruta equivalente en el mismo libro; al repetirla añadió cero, por lo que es idempotente. No se fusionaron filas entre variantes ni clientes.

El cliente y la variante se seleccionan explícitamente al importar. En el libro RHEEM Headers, `Datos!G2` dice `RHEMM`; se conserva como incidencia `cliente_distinto` y las rutas se asignan a RHEEM por la selección explícita. La pantalla de incidencias muestra solo ejecuciones confirmadas; los informes de simulación siguen disponibles por separado.

El catálogo conserva filtros de consulta por cliente y variante. La tabla temporal de impresión busca ITEM PADRE en todos los clientes y orígenes y permite mezclarlos en un PDF. Cuando un código tiene varias rutas, cada fila exige elegir el cliente y origen correctos. Pegar filas de Excel sigue disponible. Los valores comunes LINEA, PLANNER y RESPONSABLE son opcionales y se recuerdan por usuario en el navegador.

## Puerta de aprobación

Las tres fuentes nuevas tienen `print_approved=False`. Sus rutas pueden generar una **vista previa NO APROBADA**, pero no un documento emitido. Para aprobar un formato, cotejar el PDF con la etiqueta real del cliente, confirmar dimensiones y contenido con una impresión física y registrar la decisión en el administrador del libro de origen. Después se resuelven las incidencias aplicables y se activa cada ruta revisada. Resolver incidencias o aprobar el formato, por separado, no activa rutas automáticamente.

El respaldo anterior a esta importación se conserva localmente en `tmp/edh-before-multiclient.dump`; ese archivo está excluido de Git.

## Procesos registrados en el padre

En una ruta importada, si el padre tiene operaciones y ninguno de sus materiales RM tiene una ruta en el mismo libro, la impresi?n utiliza una sola etiqueta del padre con sus operaciones. Los materiales se muestran por separado en el detalle. Ejemplo: `626794-01` contiene cuatro operaciones; `626794-01A` es un material de Familias sin ruta propia. No se crean operaciones para ese material. Si existen rutas de componentes parciales o archivadas, se conserva la validaci?n; tampoco se omiten las comprobaciones de revisi?n y aprobaci?n para emitir documentos.
