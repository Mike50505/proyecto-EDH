# Universo Ramos y EDH

Universo Ramos proporciona la identidad y las características de las piezas. EDH conserva sus rutas, BOM, operaciones, revisiones, órdenes y documentos.

## Configuración

Configurar en `.env`, sin subir claves al repositorio:

```dotenv
UNIVERSO_BASE_URL=https://universo.mesaramos.com/api/v1/
UNIVERSO_API_KEY=
UNIVERSO_TIMEOUT=20
UNIVERSO_SYNC_INTERVAL=300
```

Crear una clave para EDH desde Integraciones en Universo. Las llamadas se realizan desde el servidor, por HTTPS; la clave no se entrega al navegador. EDH no escribe en Universo.

## Ejecución

`docker compose up --build -d` aplica las migraciones y levanta el servicio `universo-sync`, que consulta cambios cada cinco minutos. Una ejecución manual utiliza `python manage.py sync_universo`; `--watch` mantiene el proceso periódico.

La carga inicial descarga todas las piezas, incluyendo inactivas, y reproduce los eventos desde el cursor inicial. Las siguientes ejecuciones consultan únicamente cambios. Cada página de eventos y su cursor se confirman juntos en una transacción; un fallo permite reintentar sin duplicar piezas. Versiones antiguas no reemplazan versiones más recientes. Un turno temporal evita sincronizaciones simultáneas.

El catálogo local sigue disponible si Universo no responde. La pantalla muestra la última actualización y los errores. Una sincronización inicial incompleta se identifica explícitamente.

## Pantallas

En el menú aparece **Universo y cobertura** (`/universo/`). Los indicadores cuentan piezas centrales activas, no rutas:

- Con ruta activa: al menos una ruta vinculada activa.
- Por revisar: no tiene ruta activa, pero sí una vinculada por revisar.
- Sin ruta vigente: no tiene ruta activa ni por revisar; puede tener rutas archivadas.
- Las piezas inactivas se consultan mediante el filtro correspondiente y no forman parte del porcentaje.

El detalle de pieza muestra sus características, rutas vinculadas y códigos coincidentes pendientes. **Crear ruta para esta pieza** precarga código, cliente, diámetro y pared; exige revisar la captura y definir sus operaciones. No infiere unidades, descripción ni secuencia de fabricación.

## Vinculación existente

El catálogo principal de rutas solo muestra padres presentes en el universo activo, por UUID vinculado o por coincidencia exacta de código cuando el cliente todavía necesita vinculación manual. Se agrupa por número de parte normalizado: cada pieza aparece una vez y su detalle presenta las variantes de todos los orígenes junto con sus componentes. El contador y la paginación cuentan piezas únicas dentro del filtro. La selección por lote precarga una fila por pieza y exige elección de origen cuando varias rutas activas coinciden. Las variantes y sus componentes no se fusionan ni borran.

Cada ruta tiene un vínculo opcional al UUID central. Varias rutas y piezas locales de distintos libros pueden corresponder a una pieza central; las piezas locales y sus BOM no se fusionan.

Solo se vincula automáticamente un código y cliente exactamente coincidentes tras normalización NFKC, mayúsculas y eliminación de espacios en los extremos. No se quitan guiones ni ceros iniciales. No se presume que LENNOX equivale a LENNOX 1, ni que RHEEM equivale a todas sus divisiones. Los casos pendientes se revisan manualmente con confirmación explícita.

Los vínculos nuevos registran historial y actualizan la versión de ruta para evitar sobrescribir ediciones simultáneas. Duplicar una ruta conserva su vínculo. Retirar un vínculo manualmente desactiva la vinculación automática para esa ruta hasta que se vincule de nuevo de forma manual.

Cambiar o desactivar una pieza central no borra rutas ni modifica operaciones ni documentos emitidos. Si su código o cliente difiere del de una ruta vinculada, el detalle central avisa que se debe revisar. La cobertura indica existencia de rutas por identidad; no certifica que su contenido de fabricación esté actualizado o aprobado.

## Permisos

Consultar requiere `view_route`; actualizar manualmente y gestionar vínculos requiere `change_route`; crear una ruta desde una pieza requiere `add_route`. La sincronización periódica es una tarea de servidor.

## Vinculaci?n por n?mero de parte

La vinculaci?n autom?tica busca primero una coincidencia ?nica de n?mero y cliente. Si el cliente no coincide, acepta el n?mero exacto cuando identifica una sola pieza activa en Universo Ramos, aunque el nombre del cliente sea distinto (por ejemplo LENNOX y LENNOX 1). Si el n?mero identifica varias piezas y el cliente no permite distinguirlas, queda pendiente. Se conserva la desvinculaci?n manual y no se sustituyen v?nculos existentes. Todas las variantes y or?genes pueden enlazarse a la misma pieza central.
