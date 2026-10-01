# EDH · Rutas de proceso

Aplicación interna en español para consultar rutas de DAIKIN, LENNOX y RHEEM, conservar la procedencia de siete libros, editar operaciones, programar partidas y generar PDF. La interfaz usa superficies, tipografía de sistema, color y patrones de interacción inspirados en las interfaces de Apple. El PDF reproduce la composición de la captura de referencia recibida y sigue **provisional** hasta cotejarlo a escala real con una impresión aprobada.

## Requisitos

- Docker Desktop / Docker Engine con Compose.
- Los siete `.xlsm` originales disponibles localmente. No se incluyen en la imagen ni en Git.
- Puerto 8000 libre en el equipo servidor.

Se fijan Django 5.2.17 LTS, PostgreSQL 16.15, Python 3.13 y las demás versiones en `requirements.txt`. Las dependencias y parches deben revisarse periódicamente.

## Arranque

1. Copia `.env.example` a `.env`. Genera valores aleatorios propios para `DJANGO_SECRET_KEY` y `POSTGRES_PASSWORD`. Configura `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS` para el nombre o IP de la red interna.
2. Ejecuta `docker compose up -d --build`.
3. Crea el administrador con `docker compose exec web python manage.py createsuperuser`.
4. Crea los roles con `docker compose exec web python manage.py bootstrap_roles`. Después, entra con el superusuario y abre **Usuarios** para crear cuentas operativas y asignarles un rol.
5. Abre `http://localhost:8000/` o la dirección interna configurada.

La aplicación no publica PDFs ni archivos importados como medios estáticos; cada descarga pasa por permisos de Django. Los volúmenes `postgres_data` y `media_data` guardan los datos. `docker compose down` no los borra. No uses `down -v` para una instalación con datos que deban conservarse.

La sección **Usuarios** es exclusiva para superusuarios. Permite buscar cuentas, crear usuarios operativos, cambiar sus datos y rol, activar o desactivar el acceso y establecer una contraseña nueva. Las cuentas con permisos de superusuario o de personal administrativo se gestionan desde `/admin/`.

## Acceso desde la red local

Docker publica TCP 8000 en el equipo servidor. Añade la IP local a `DJANGO_ALLOWED_HOSTS` y su origen `http://IP:8000` a `DJANGO_CSRF_TRUSTED_ORIGINS` en `.env`; después ejecuta `docker compose up -d --no-deps --force-recreate web`. En Windows, permite TCP 8000 en el firewall solo para la interfaz y la subred local que usarán los demás dispositivos.

Desde otro dispositivo de la misma red, abre `http://IP-DEL-SERVIDOR:8000/`. Si cambia la IP del equipo, actualiza `.env` y la dirección local de la regla del firewall.

## Importación

Desde **Importar Excel**, selecciona el cliente y la variante de origen, el archivo `.xlsm` e introduce la contraseña de apertura. Ejecuta primero **Solo simular**. La contraseña no se almacena ni se registra. Revisa el CSV de incidencias y repite sin esa casilla para confirmar. También se puede usar el comando:

```text
docker compose exec web python manage.py import_workbooks /ruta/libro.xlsm --client LENNOX --variant General
docker compose exec web python manage.py import_workbooks /ruta/libro.xlsm --client LENNOX --variant General --commit
docker compose exec web python manage.py reconcile_sources
```

El comando solicita la contraseña por entrada sin eco. Para usarlo en Docker, monta los libros cifrados como volumen de solo lectura o cópialos temporalmente al contenedor. La importación usa `Familias`, `Ruta` y `Datos`; no ejecuta macros y no toma `PartList` o `Etiqueta` como catálogo. El cliente seleccionado prevalece sobre el texto de `Datos!G2`; una discrepancia queda registrada como incidencia. El hash evita duplicar el mismo libro, y cada fila de Ruta mantiene su propio registro. Las rutas nuevas quedan **Por revisar** hasta resolver incidencias y aprobar su formato de impresión. La pantalla de importación muestra incidencias y permite descargar un CSV; la resolución detallada se hace con edición/admin y el informe.

El comando `reconcile_sources` compara contenidos entre variantes y reporta FP sin Ruta en el mismo libro. No fusiona variantes ni traslada procesos de un archivo a otro. En **Incidencias**, el administrador documenta la decisión para cada registro; esa acción no activa automáticamente la ruta. Se revisa el detalle y se activa mediante edición cuando ya no tiene incidencias pendientes.

## Uso

- **Catálogo:** busca por código, descripción o dibujo. Filtra por cliente, estado y variante de origen. El botón **Imprimir** de cada fila abre una vista previa PDF de esa ruta; también está **Imprimir ruta** en el detalle. Puedes marcar rutas activas de la página o todas las del filtro (hasta 200) y llevarlas a la tabla temporal de órdenes.
- **Creación de rutas:** la cuadrícula **Datos de Familias** sigue exactamente `Familias!A:L`: Tipo, BOM, Dibujo rev, Parte, Descripción, Número dibujo, Cantidad, OD, Pared, Desarrollo, Comentario y Fase. Puedes pegar una fila copiada de Excel. Cliente, Origen, Revisión y Estado son configuración de la ruta en la app; no son columnas de Familias. Al guardar se crea una pieza manual vinculada a la ruta. **Edición:** conserva la pieza vinculada y permite cambiar datos de ruta y operaciones. El selector **Celdas / Formulario** cambia la presentación; las operaciones admiten hasta 200 filas. La versión del formulario impide sobrescribir una edición concurrente sin aviso. Duplicar crea una ruta **Por revisar**.
- **Selección temporal de órdenes:** entra en **Seleccionar órdenes**, elige el cliente y la variante y descarga la plantilla `.xlsx`. Llena hasta 200 filas con SHOP ORDER, ITEM PADRE, CANTIDAD, SEMANA, RE y Secuencia y pulsa **Cargar a la tabla**; también puedes escribir o pegar celdas directamente. Los archivos anteriores de nueve columnas siguen aceptándose. LINEA, PLANNER y RESPONSABLE son tres campos comunes arriba de la tabla: se aplican a todas las rutas y se recuerdan por usuario y cliente en el almacenamiento local del navegador hasta que se cambien. La SEMANA puede variar por orden. `RE` se calcula a partir de los componentes RM. **Crear PDF de las órdenes** produce un solo archivo con las etiquetas de todas las filas. El archivo subido, las filas y el PDF no se guardan en la base ni en el volumen de medios. Una ruta Por revisar puede verse en este PDF temporal, marcado **NO APROBADA**; si hay códigos duplicados en un mismo libro, se toma la primera coincidencia como hacía la macro y se indica la fila utilizada. El flujo de programación persistente conserva el bloqueo de emisión hasta resolver incidencias y aprobar el formato.
- **Programación persistente:** el flujo anterior sigue disponible en `/programacion/nueva/` para quien necesite guardar un documento histórico. La vista previa de una ruta individual tampoco crea un documento emitido. La descarga de PDF no equivale a impresión física.

## Pruebas y comprobaciones

```text
docker compose exec web python manage.py check
docker compose exec web python manage.py test rutas --verbosity 2
docker compose exec web python manage.py audit_print_sources --large-batch
docker compose exec web python manage.py benchmark_catalog --requests 40 --workers 4
```

La prueba usa una base PostgreSQL temporal. En este entorno se importaron las siete fuentes: 4,171 filas de Familias, 2,468 filas de Ruta y 11,534 grupos de operaciones. Hay 279 rutas DAIKIN, 282 LENNOX y 1,907 RHEEM; las 2,189 rutas nuevas siguen Por revisar. Los totales son filas conservadas, no rutas únicas ni producción confirmada. Véanse `docs/fuentes_multicliente.md` y `docs/validacion_impresion.md` para el alcance de la comprobación.

## Respaldo y restauración

Respalda **juntos** PostgreSQL y el volumen de PDFs. Ejemplo para la base:

```text
docker compose exec -T db pg_dump -U edh -Fc edh > edh.dump
```

Para restaurar en un entorno de desarrollo vacío, inicia la base, copia el dump al contenedor y ejecuta `pg_restore -U edh -d edh --clean --if-exists /ruta/edh.dump`. En este entorno se restauró un dump en una base temporal y se verificaron 279 rutas, 326 piezas, 1,395 operaciones y 270 incidencias; después se eliminó esa base temporal. Respalda y restaura también el volumen `media_data`; sin él, las filas de documentos no tendrán sus PDFs. La restauración conjunta del volumen de PDFs aún debe probarse en el equipo definitivo.

En Windows, `powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify_backup.ps1` crea una copia bajo `tmp/`, restaura PostgreSQL en una base temporal, compara conteos y comprueba los hashes de los PDFs que existan. Esta comprobación se hizo con 2,468 rutas y 4,171 piezas; todavía no hay documentos emitidos para validar el vínculo con un PDF real. Para un respaldo operativo, pausa las escrituras de documentos durante la copia de la base y el volumen.

## Límites actuales

El PDF está compuesto en carta horizontal, dos etiquetas por hoja, según la captura recibida. No se ha medido contra una impresión física ni probado la impresora real. La captura muestra dos RM, pero no la etiqueta `1 DE 3` del padre ni el tratamiento general de PP/BR; esas reglas siguen pendientes de confirmación operativa. Falta una comparación visual lado a lado dentro de la pantalla de incidencias, así como métricas de rendimiento con carga representativa. No utilices el PDF provisional como sustituto definitivo de la etiqueta de producción sin esa validación.
