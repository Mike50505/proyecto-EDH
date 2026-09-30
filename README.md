# EDH · Rutas de proceso

Aplicación interna en español para consultar rutas, conservar procedencias de cuatro libros Daikin, editar operaciones, programar partidas y generar PDF. La interfaz usa superficies, tipografía de sistema, color y patrones de interacción inspirados en las interfaces de Apple. El PDF reproduce la composición de la captura de referencia recibida y sigue **provisional** hasta cotejarlo a escala real con una impresión aprobada.

## Requisitos

- Docker Desktop / Docker Engine con Compose.
- Los cuatro `.xlsm` originales disponibles localmente. No se incluyen en la imagen ni en Git.
- Puerto 8000 libre en el equipo servidor.

Se fijan Django 5.2.17 LTS, PostgreSQL 16.15, Python 3.13 y las demás versiones en `requirements.txt`. Las dependencias y parches deben revisarse periódicamente.

## Arranque

1. Copia `.env.example` a `.env`. Genera valores aleatorios propios para `DJANGO_SECRET_KEY` y `POSTGRES_PASSWORD`. Configura `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS` para el nombre o IP de la red interna.
2. Ejecuta `docker compose up -d --build`.
3. Crea el administrador con `docker compose exec web python manage.py createsuperuser`.
4. Crea los roles con `docker compose exec web python manage.py bootstrap_roles`. Asigna usuarios a los grupos desde `/admin/`.
5. Abre `http://localhost:8000/` o la dirección interna configurada.

La aplicación no publica PDFs ni archivos importados como medios estáticos; cada descarga pasa por permisos de Django. Los volúmenes `postgres_data` y `media_data` guardan los datos. `docker compose down` no los borra. No uses `down -v` para una instalación con datos que deban conservarse.

## Importación

Desde **Importar Excel**, selecciona cada archivo `.xlsm`, introduce la contraseña de apertura y ejecuta primero **Solo simular**. La contraseña no se almacena ni se registra. Revisa el CSV de incidencias y repite sin esa casilla para confirmar. También se puede usar el comando:

```text
docker compose exec web python manage.py import_workbooks /ruta/libro.xlsm
docker compose exec web python manage.py import_workbooks /ruta/libro.xlsm --commit
docker compose exec web python manage.py reconcile_sources
```

El comando solicita la contraseña por entrada sin eco. Para usarlo en Docker, monta los libros cifrados como volumen de solo lectura o cópialos temporalmente al contenedor. La importación usa `Familias`, `Ruta` y `Datos`; no ejecuta macros y no toma `PartList` o `Etiqueta` como catálogo. El hash evita duplicar el mismo libro, y cada fila de Ruta mantiene su propio registro. Las rutas ambiguas quedan **Por revisar** y no se pueden emitir. La pantalla de importación muestra incidencias y permite descargar un CSV; la resolución detallada aún se hace con edición/admin y el informe.

El comando `reconcile_sources` compara contenidos entre variantes y reporta FP sin Ruta en el mismo libro. No fusiona variantes ni traslada procesos de un archivo a otro. En **Incidencias**, el administrador documenta la decisión para cada registro; esa acción no activa automáticamente la ruta. Se revisa el detalle y se activa mediante edición cuando ya no tiene incidencias pendientes.

## Uso

- **Catálogo:** busca por código, descripción o dibujo. Filtra por estado y origen. El botón **Imprimir** de cada fila abre una vista previa PDF de esa ruta; también está **Imprimir ruta** en el detalle. Puedes marcar rutas activas de la página o todas las del filtro (hasta 200) y llevarlas a la tabla temporal de órdenes.
- **Edición:** añade o reordena operaciones mediante su posición. La versión del formulario impide sobrescribir una edición concurrente sin aviso. Duplicar crea una ruta **Por revisar**.
- **Selección temporal de órdenes:** entra en **Seleccionar órdenes**. Descarga la plantilla `.xlsx`, llena hasta 200 filas con SHOP ORDER, ITEM PADRE, CANTIDAD, SEMANA, RE y Secuencia, y pulsa **Cargar a la tabla**; también puedes escribir o pegar celdas directamente. Los archivos anteriores de nueve columnas siguen aceptándose. LINEA, PLANNER y RESPONSABLE son tres campos comunes arriba de la tabla: se aplican a todas las rutas y se recuerdan en el almacenamiento local de ese navegador para ese usuario hasta que se cambien. La SEMANA puede variar por orden. `RE` se calcula a partir de los componentes RM. **Crear PDF de las órdenes** produce un solo archivo con las etiquetas de todas las filas. El archivo subido, las filas y el PDF no se guardan en la base ni en el volumen de medios. Una ruta Por revisar puede verse en este PDF temporal, marcado **NO APROBADA**; si hay códigos duplicados en un mismo libro, se toma la primera coincidencia como hacía la macro y se indica la fila utilizada. El flujo de programación persistente conserva el bloqueo de emisión hasta resolver incidencias.
- **Programación persistente:** el flujo anterior sigue disponible en `/programacion/nueva/` para quien necesite guardar un documento histórico. La vista previa de una ruta individual tampoco crea un documento emitido. La descarga de PDF no equivale a impresión física.

## Pruebas y comprobaciones

```text
docker compose exec web python manage.py check
docker compose exec web python manage.py test rutas --verbosity 2
```

La prueba usa una base PostgreSQL temporal. En el entorno de desarrollo de este proyecto se importaron las cuatro fuentes y se verificaron 326 filas de Familias, 279 filas de Ruta, 1,395 operaciones y 124 relaciones BOM. Tras la auditoría entre variantes quedaron 270 incidencias y 206 rutas por revisar; 73 siguen activas. Los totales son filas conservadas, no rutas únicas ni producción confirmada. Véanse `docs/analisis_excel.md` y `docs/validacion_impresion.md` para el alcance de la comprobación.

## Respaldo y restauración

Respalda **juntos** PostgreSQL y el volumen de PDFs. Ejemplo para la base:

```text
docker compose exec -T db pg_dump -U edh -Fc edh > edh.dump
```

Para restaurar en un entorno de desarrollo vacío, inicia la base, copia el dump al contenedor y ejecuta `pg_restore -U edh -d edh --clean --if-exists /ruta/edh.dump`. En este entorno se restauró un dump en una base temporal y se verificaron 279 rutas, 326 piezas, 1,395 operaciones y 270 incidencias; después se eliminó esa base temporal. Respalda y restaura también el volumen `media_data`; sin él, las filas de documentos no tendrán sus PDFs. La restauración conjunta del volumen de PDFs aún debe probarse en el equipo definitivo.

## Límites actuales

El PDF está compuesto en carta horizontal, dos etiquetas por hoja, según la captura recibida. No se ha medido contra una impresión física ni probado la impresora real. La captura muestra dos RM, pero no la etiqueta `1 DE 3` del padre ni el tratamiento general de PP/BR; esas reglas siguen pendientes de confirmación operativa. Falta una comparación visual lado a lado dentro de la pantalla de incidencias, así como métricas de rendimiento con carga representativa. No utilices el PDF provisional como sustituto definitivo de la etiqueta de producción sin esa validación.
