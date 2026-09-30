# Prompt para Codex: sistema web de rutas de proceso

Actúa como desarrollador senior de Django y PostgreSQL, con experiencia en migración de aplicaciones de Excel/VBA y generación de documentos de producción. Trabaja directamente en esta carpeta del proyecto. Quiero que analices los archivos existentes y construyas una aplicación funcional, con datos persistentes, importación de las rutas actuales y formatos de impresión verificables.

## 1. Objetivo y contexto

Actualmente utilizamos archivos de Excel con macros para almacenar información de rutas de proceso y preparar etiquetas u hojas impresas que acompañan la fabricación. Una ruta de proceso es la información y la secuencia de operaciones que se debe seguir para fabricar una pieza; no me refiero a las URL de una aplicación.

Para un solo cliente tenemos cuatro archivos. El sistema actual resulta difícil de ampliar y tarda demasiado en preparar la impresión. Quiero centralizarlo en una aplicación web moderna, en español, desarrollada con Django y PostgreSQL, que permita:

- Conservar y consultar las rutas existentes.
- Registrar más rutas sin repartir el catálogo entre nuevos libros.
- Editar, duplicar y organizar rutas, preservando su historial.
- Buscar y seleccionar rápidamente la información que se necesita imprimir.
- Generar documentos individuales o por lote que permitan seguir correctamente el proceso.

El proyecto debe resolver el flujo completo de captura, almacenamiento, consulta e impresión. La interfaz debe ser práctica para personal de producción y funcionar desde varias computadoras en una red interna.

## 2. Archivos de origen y estado conocido

Localiza estos cuatro archivos, incluidos sus posibles subdirectorios:

1. `Macro Etiquetas de Corte Daikin Headers - Ramos A.12-08-2025.xlsm`
2. `Macro Etiquetas de Corte Daikin Individuales - Ramos A. 04-07-2025.xlsm`
3. `Macro Etiquetas de Corte Daikin SLP Headers - Ramos A. 11-04-2025.xlsm`
4. `Macro Etiquetas de Corte Daikin SLP Individuales - Ramos A. 05-03-2024.xlsm`

Los cuatro originales están cifrados. Al preparar este encargo se abrieron copias con la contraseña facilitada por el propietario y se verificó su integridad. Se inspeccionaron las hojas, fórmulas, estilos, relaciones de dibujos y el código fuente VBA de los cuatro libros. No se ejecutaron macros ni se realizó una impresión física. Los hallazgos siguientes provienen de ese análisis estático y deben contrastarse con los archivos que tengas disponibles, especialmente si cambiaron.

Si siguen cifrados, solicita la contraseña de apertura por un mecanismo local que no la registre, o copias guardadas sin cifrado de apertura y conservando el formato `.xlsm`. Mantén intactos los originales. No intentes adivinar contraseñas ni confundas el cifrado del archivo con protección de hojas o del proyecto VBA. Si necesitas el código VBA y continúa inaccesible, solicita su exportación o una copia accesible. No guardes claves en código, Git, documentación, argumentos visibles de comandos o registros.

La contraseña no se incluye en este documento. Si no la recibiste en tu sesión, solicítala para abrir copias locales. No confundas el análisis ya realizado con una migración: todavía no existe una base PostgreSQL poblada ni se ha validado un PDF contra una impresión física. Si temporalmente te falta acceso, avanza en componentes independientes y deja explícitamente pendientes las comprobaciones contra los originales.

Los cuatro libros tienen `DAIKIN` en `Datos!G2`. Los Headers contienen estructuras de ensambles y componentes, mientras que en Familias de Individuales todos los registros con código tienen tipo `FP`. Conserva `Headers`, `Individuales` y `SLP` como clasificaciones de origen y confirma su significado operativo antes de definir plantas o destinos. No conviertas los archivos automáticamente en cuatro clientes.

### 2.1. Inventario comprobado

Los conteos siguientes excluyen encabezados. Una fila de Ruta cuenta cuando su columna A contiene un código que no queda vacío al quitar espacios exteriores, incluidos espacios no separables. Los códigos distintos se cuentan dentro de cada libro después de esa limpieza; esto no autoriza fusionar sus registros.

| Archivo abreviado | Filas con código en Familias | Filas con código en Ruta | Códigos distintos en Ruta | Filas de Ruta con operaciones |
| --- | ---: | ---: | ---: | ---: |
| Headers, 12-08-2025 | 82 | 65 | 51 | 42 |
| Individuales, 04-07-2025 | 69 | 64 | 63 | 64 |
| SLP Headers, 11-04-2025 | 96 | 75 | 61 | 47 |
| SLP Individuales, 05-03-2024 | 79 | 75 | 74 | 75 |

Hay 279 filas con código en las cuatro hojas Ruta, antes de conciliar duplicados y variantes. No son 279 rutas únicas. Las filas sin operaciones en Headers incluyen códigos de ensambles; no inventes procesos ni las elimines automáticamente.

Los Headers tienen las hojas `PartList`, `Ruta`, `Familias`, `Etiqueta1`, `Datos` y `Etiqueta`. Los Individuales incluyen además `Hoja1`, sin valores en las copias examinadas. Todas estas hojas figuran visibles. El módulo principal es `Módulo1`, procedimiento `GETI1`, vinculado al botón de Datos en los cuatro libros. Su código es idéntico entre los dos Headers y también idéntico entre los dos Individuales; hay dos variantes de código principal. Existe además `frmComercial`, cuyo código referencia hojas `Semana` y `Respaldo` ausentes de estos libros. No asumas que ese formulario heredado representa un flujo operativo vigente.

### 2.2. Mapeo real de las fuentes

**Familias es el catálogo de piezas y la estructura de componentes.** Sus columnas son:

| Columna | Contenido |
| --- | --- |
| A | Tipo de pieza: aparecen `FP`, `RM`, `PP` y `BR` |
| B | Revisión BOM |
| C | Revisión de dibujo |
| D | Número de parte |
| E | Descripción |
| F | Número de dibujo |
| G | Cantidad por unidad |
| H | Tubería / diámetro exterior, encabezado `OD PULG` |
| I | Pared, encabezado `PULG` |
| J | Desarrollo, encabezado `MM` |
| K | Comentarios en Individuales; sin título en Headers, donde existe un valor en K41 |
| L | Fase |

En Headers, cada fila `FP` abre un bloque de ensamble; las siguientes filas se asocian a ese bloque hasta el siguiente `FP`. Esa relación está implícita en el orden físico, no en una columna de clave foránea. Registra explícitamente ensamble, componente, tipo, cantidad por unidad y posición original. Un componente repetido puede pertenecer a varios ensambles; su cantidad por unidad pertenece a esa relación y no debe perderse al compartir una pieza.

**Ruta contiene la secuencia de fabricación.** A identifica la pieza. Desde B se repiten grupos de cuatro columnas: número de secuencia, herramental, método de inspección y maquinaria. El nombre del proceso está en la fila 1 de la primera columna de cada grupo. Por ejemplo: B:E corresponde a CORTE y F:I a DOBLEZ 1. Los números dentro de la fila determinan el orden, no la posición de las columnas.

Se encontraron 32 grupos de proceso en Headers, 30 en Individuales y 33 en cada archivo SLP. Los grupos no coinciden por posición entre variantes: se añaden o desplazan operaciones como INDENTACION 2, REDUCCION 2 y CRIMPEADO. Importa según los encabezados de cada libro. Conserva la diferencia entre ocurrencias como DOBLEZ 1 y DOBLEZ 2. Normalizar acentos o nombres requiere un mapeo explícito, sin fusionar operaciones diferentes.

**Datos es la programación del trabajo**, con A=SHOP ORDER, B=ITEM PADRE, C=CANTIDAD, D=SEMANA, E=RE, F=Secuencia, G=LINEA, H=PLANNER e I=RESPONSABLE. `GETI1` toma semana de D2, línea/cliente de G2 y planner de H2 como datos comunes. La columna E recibe un conteo calculado. La semana puede ser alfanumérica, por ejemplo `31A` o `02M`; no la conviertas obligatoriamente en un entero o una semana ISO. Las órdenes también son texto libre. Las partidas conservadas en Datos son capturas a revisar: no hay evidencia suficiente para marcarlas automáticamente como órdenes fabricadas o entregadas.

**PartList es una salida intermedia que la macro reconstruye**, no otro catálogo independiente. A=orden, B=cantidad programada, C=tipo, D=revisión BOM, E=revisión de dibujo, F=parte, G=descripción, H=dibujo, I=cantidad por unidad, J=OD, K=pared, L=desarrollo y M=ensamble padre, aunque M no tenga encabezado. N se titula Secuencias. Las hojas Etiqueta y Etiqueta1 son salidas preparadas y pueden contener restos de ejecuciones anteriores. No crees piezas ni un historial de producción confirmado únicamente a partir de esas salidas; concilia sus diferencias con el catálogo y conserva evidencia de las discrepancias.

### 2.3. Flujo y cálculos comprobados en GETI1

1. Lee las partidas de Datos y busca su ITEM PADRE en Familias.
2. Si encuentra un `FP` con H, I y J vacíos, lo trata como ensamble y recorre las filas siguientes del bloque. Si esos campos tienen contenido, lo trata como pieza individual. Conserva esta evidencia al migrar, pero modela explícitamente el tipo de pieza para que la web no dependa de dimensiones vacías.
3. Construye PartList. En el recorrido de componentes se insertan los `RM`; existen `PP`, `BR` y una fila sin tipo en el origen que no se deben perder por copiar solo los resultados de la macro. Decide y documenta cuáles requieren ruta e impresión; conserva todos en el catálogo/BOM.
4. Calcula piezas a correr como `cantidad programada × cantidad por unidad`.
5. Busca el número de parte en Ruta y coloca cada operación según su número de secuencia. Al encontrar un código coincidente termina la búsqueda, por lo que las filas duplicadas con diferencias merecen revisión.
6. Usa Etiqueta para el padre sin dimensiones y Etiqueta1 para los componentes o piezas individuales. La macro termina abriendo la vista previa de Etiqueta1. Que exista Etiqueta no demuestra que ambas salidas se impriman siempre.

Revisa también los contadores de partida `N DE M`: la macro calcula `PARTIDAS = RE + 1` y puede contar al ensamble padre aunque solo se muestre la vista previa de componentes. Conserva la trazabilidad y confirma cómo debe verse la numeración en la web. En la rama del padre existe lógica especial para listar componentes RM junto a SOLDADURA NIPLES; determina si sigue siendo parte del formato utilizado.

### 2.4. Formato de salida y discrepancias de impresión

Etiqueta1 muestra `EDH`, `Especificación Dimensional y Herramental - Macro`, `ETIQUETA DE CORTE` y la referencia `22 Sep-2014 Rev.00 FO-CP-08`. Incluye cliente, fechas de emisión y embarque, parte y descripción del padre, componente y descripción, cantidad a correr, shop order, planner, semana, secuencia y dimensiones. La tabla contempla ruta, máquina, herramental, inspección y espacios para cantidad de piezas, fecha y número de operador. Al pie hay instrucciones especiales, certificado, notas de calidad y plan de reacción. Mantén esos campos y los espacios necesarios para seguimiento en papel; no inventes que ya existe captura digital del avance de producción.

Los bloques de Etiqueta1 avanzan 29 filas en Headers y 27 en Individuales; Etiqueta utiliza saltos de 39 filas. La primera plantilla visible de Headers reserva filas 12:26 para operaciones, mientras que Individuales usa 12:24. Ambas tienen orientación horizontal. Las escalas guardadas son 73% en Headers, 72% en Individuales y 73% en SLP Individuales. Hay configuración binaria de impresora: confirma papel, dimensiones físicas y distribución por página con una referencia real, sin deducirlas solo de la cantidad de filas.

Hay discrepancias que NO debes reproducir a ciegas:

- En Headers, la rama de Etiqueta1 escribe `INSPE` en la columna X y `HERRA` en AR. En Individuales escribe `HERRA` en X e `INSPE` en AR. En ambos, Z11 dice Herramental; Headers no tiene el título Método de Inspección que aparece en AR11 de Individuales. Verifica y corrige la correspondencia semántica en la web con una comparación documentada.
- Las etiquetas dicen `Pulgadas /Milimetros /Milimetros`, aunque Familias declara tanto OD como pared en pulgadas. Algunas medidas incorporan `mm` dentro del texto. No conviertas unidades basándote únicamente en ese pie impreso.
- El Headers examinado tiene `Ruta!E3 = INTCU010` pero la etiqueta guardada de esa pieza muestra `Etiqueta1!O12 = FAHELAUT01`. Hay valores residuales o desactualizados. No uses la salida guardada como autoridad automática sobre la ruta vigente.
- En Etiqueta de ambos Individuales hay 270 celdas con error guardado `#REF!` y restos con cliente Rheem. Eso no demuestra que todo Etiqueta1 esté roto. Separa los errores de la salida heredada del catálogo vigente.

### 2.5. Hallazgos de rendimiento y límites del código

Los tamaños siguientes son la suma de las entradas internas del XLSM ya descifrado, expresada en MB decimales; no representan RAM medida ni tamaño del archivo cifrado:

| Variante | Tamaño interno aproximado | Objetos de imagen en Etiqueta1 | Estilos de celda con nombre |
| --- | ---: | ---: | ---: |
| Headers | 219.6 MB | 93,663 | 49,648 |
| Individuales | 94.3 MB | 29,611 | 48,407 |
| SLP Headers | 219.6 MB | 93,665 | 49,648 |
| SLP Individuales | 94.3 MB | 29,611 | 48,405 |

Solo hay tres o cuatro archivos de imagen en cada libro, reutilizados por muchos objetos. Etiqueta tiene aproximadamente 709,000 elementos de celda y cada Etiqueta1 más de 233,000. Datos declara dimensiones hasta filas cercanas a 1,048,000, aunque tiene muchos menos valores. No recorras un millón de filas por confiar sin más en `max_row` o en el rango usado declarado.

GETI1 hace búsquedas lineales y escrituras celda a celda, cambia de hoja repetidamente, limpia áreas hasta la fila 15,000 y selecciona `A1:CR9999` antes de abrir PrintPreview. Seleccionar ese rango no equivale por sí solo a fijar el área de impresión. Los límites escritos incluyen Datos hasta fila 120 en Individuales o 1,200 en Headers, Familias hasta 1,800, búsquedas de Ruta y PartList hasta 1,000 y hasta 100 iteraciones para componentes. Además, Individuales limpia PartList solo hasta fila 100 aunque otras ramas usan hasta 1,000.

La salida de componentes de Individuales tiene casos de secuencia 1:13; Headers tiene casos 1:40 aunque su primer bloque visible reserva 15 filas y varios contadores altos no están inicializados al comenzar. La rama de padre admite 1:17. Estos son límites y riesgos de implementación, no una capacidad universal de las macros de Excel. No los heredes: utiliza listas de operaciones, consultas indexadas y paginación documental.

En GETI1 se desactivan eventos y se cambia a cálculo manual, sin encontrar su restauración al terminar el procedimiento. La acumulación de objetos, estilos y recorridos es evidencia de causas plausibles de lentitud. No se han medido tiempos ejecutando Excel, así que no atribuyas porcentajes de mejora ni afirmes que se identificó una única causa.

### 2.6. Casos concretos para la conciliación

- En Headers y SLP Headers hay varias filas del mismo código con operaciones o recursos distintos. Por ejemplo `4PA17856-6` en Ruta, filas 4 y 57. No elijas simplemente la primera ni sustituyas una con otra.
- `4P663164-1` aparece en Ruta, filas 6 y 34 de ambos Individuales; la segunda forma tiene espacios exteriores, incluido un espacio no separable. En SLP sus contenidos difieren. Conserva el valor original y detecta el conflicto después de normalizar la clave.
- Headers y SLP Headers tienen secuencias repetidas: `4P669357-1`, fila 42, repite 3; `4P299934-1-A`, fila 63, repite 5. SLP Headers también repite 6 y 10 para `4P661645-1`, fila 9. Guardar por clave `(ruta, secuencia)` sin conciliación podría perder operaciones.
- Familias, fila 45 de ambos Headers, contiene la pieza `4P669357-1` pero no tiene tipo en A45. Conserva la fila y márcala para clasificación, sin asignarle un tipo por suposición.
- Existen piezas FP de Familias sin código equivalente en Ruta dentro del mismo libro: dos en Headers, seis en Individuales, una en SLP Headers y seis en SLP Individuales. Algunos códigos sí aparecen en otra variante. Muestra esas coincidencias para revisión sin trasladar rutas automáticamente entre destinos o versiones.
- Hay dimensiones como `7mm`, `7.9mm`, `3/8`, `223*` y `93*`, además de números decimales. Conserva texto, fracciones, unidad y calificadores. No elimines asteriscos ni fuerces todo a Decimal. Al normalizar, usa campos numéricos y unidades solo donde la interpretación esté confirmada.
- En ambos Individuales, Familias!J8 contiene la fórmula `124-1`, con valor guardado 123; J12 contiene `180-2`, con valor 178. Registra fórmula y resultado, y valida el cálculo al migrar.
- Los códigos con ceros iniciales, como `0210A00205`, son identificadores de texto. El número global de rutas distintas no debe deducirse sumando los conteos de los libros: SLP comparte numerosos códigos con las otras variantes y contiene diferencias.

Convierte estos ejemplos en pruebas y reportes de conciliación. Las ambigüedades deben conservar todos los datos de origen y quedar visibles antes de habilitar su emisión definitiva. No renumeres operaciones ni completes rutas automáticamente para hacer que la importación parezca limpia.

## 3. Análisis antes de definir el modelo definitivo

Lee primero las instrucciones del repositorio y revisa si ya existe código aprovechable. Después, cuando el contenido sea accesible, analiza los cuatro libros sin modificarlos y sin ejecutar automáticamente sus macros.

Investiga y documenta:

- Hojas visibles y ocultas, tablas, rangos con nombre, validaciones, fórmulas, vínculos externos, imágenes, controles, formularios y módulos VBA relevantes.
- Dónde están los registros maestros, dónde se capturan datos y dónde se construye la salida impresa. Distingue las plantillas repetidas y los cálculos auxiliares de los registros reales.
- Cómo funcionan las acciones de guardar, buscar, modificar, seleccionar y preparar la impresión. Examina el código VBA disponible mediante análisis estático y sigue las referencias entre hojas.
- Qué identifica una ruta y cómo se relaciona con cliente, planta o destino, familia, pieza y revisión, únicamente según la evidencia disponible.
- Qué información es fija de la ruta y cuál se captura en cada emisión, como cantidades, fechas o lotes, si esos campos existen.
- Cómo se ordenan las operaciones, qué campos son obligatorios y qué reglas o cálculos modifican el contenido impreso.
- Diferencias y coincidencias entre los cuatro archivos. Determina si necesitan distintas plantillas, distintas clasificaciones, o ambas.
- Duplicados, posibles revisiones, registros incompletos, códigos con ceros iniciales, unidades, decimales, fechas y errores de fórmulas.
- Áreas de impresión, tamaño del papel, orientación, márgenes, escala, saltos, etiquetas por página, logos, encabezados y espacios de firmas o seguimiento, cuando existan.
- Posibles causas de lentitud: recálculos, búsquedas repetidas, formatos excesivos, recorridos VBA, hojas duplicadas o generación de etiquetas innecesarias. Diferencia hipótesis de causas medidas.

Usa herramientas de lectura adecuadas para Excel y extracción de VBA. Si utilizas `openpyxl`, recuerda que no ejecuta macros ni calcula fórmulas: contrasta las fórmulas con sus valores almacenados y señala valores ausentes o posiblemente desactualizados. Inspecciona los objetos y ajustes de impresión con herramientas adicionales cuando haga falta. No confundas una extracción de celdas con una reproducción visual validada.

Entrega `docs/analisis_excel.md` con un inventario por archivo, conteos definidos con claridad, campos encontrados, reglas con referencias a hojas/celdas/módulos y asuntos sin resolver. Prepara también `docs/mapeo_migracion.md`, que relacione cada campo de origen con su destino. Si necesitas una muestra impresa o un PDF exportado desde Excel para resolver una diferencia visual, pídelo específicamente.

## 4. Arquitectura y tecnologías

- Backend: Django. Como punto de partida, utiliza Django 5.2 LTS con su parche de seguridad vigente; verifica que siga soportado cuando implementes y que las versiones de Python y demás dependencias sean compatibles. Documenta la selección y fija versiones reproducibles.
- Base de datos: PostgreSQL en una versión soportada, con persistencia real. Usa PostgreSQL también para verificar las migraciones y las pruebas de integración que dependan de sus restricciones. No sustituyas la base por almacenamiento del navegador.
- Frontend: plantillas Django con HTMX y Tailwind CSS, compilado para uso real, como opción inicial. Construye una interfaz propia para producción. Django Admin puede servir para administración técnica.
- Documentos: generación de PDF en el servidor mediante una biblioteca mantenida, seleccionada según las necesidades reales del formato. La consulta, edición e impresión cotidiana deben funcionar sin Excel instalado.
- Organización: un monolito modular con servicios para importación y generación documental. Evita microservicios y dependencias operativas que el volumen real no justifique.
- Ejecución: entorno local reproducible y Docker Compose con la aplicación y PostgreSQL, volúmenes persistentes, comprobaciones de disponibilidad y `.env.example` sin secretos.

## 5. Modelo de datos y trazabilidad

Diseña un modelo relacional a partir del análisis. Considera cliente, clasificación de origen/destino confirmada, pieza, revisión de BOM, componente de ensamble con cantidad por unidad, ruta y revisión, operaciones ordenadas, lote de programación, partidas programadas, plantilla de impresión, ejecución de importación y documento emitido. La BOM debe representar piezas reutilizadas en varios ensambles. La programación equivale al flujo de Datos y debe generar las cantidades de componentes sin modificar sus cantidades maestras.

Requisitos del modelo:

- Reunir el catálogo en una base central y permitir futuros clientes sin duplicar aplicaciones.
- Conservar las diferencias de planta, destino, familia y formato cuando estén presentes. Define claves compuestas y restricciones después de analizar el origen; un código podría repetirse legítimamente en otro contexto.
- Permitir tantas rutas y operaciones como admita la infraestructura, sin topes heredados de filas o casillas de Excel. No prometas capacidad infinita.
- Guardar identificadores como texto si pueden contener ceros iniciales o letras. Para medidas, conservar la representación original y añadir valor decimal, unidad y calificador cuando su interpretación esté validada. La semana y el shop order admiten texto.
- Separar el dato original y su transformación. Mantener archivo, hash, hoja, fila o rango de procedencia y los valores originales relevantes para auditoría.
- Conservar información no mapeada en un registro auxiliar de importación y reportarla; no descartarla silenciosamente ni convertir todo el modelo de negocio en un único JSON.
- Mantener revisiones e historial de cambios. Archivar rutas cuando dejen de usarse, preservando documentos e historial relacionados.
- Evitar que dos usuarios sobrescriban cambios sin advertencia. Implementar una estrategia sencilla de control de concurrencia.
- Separar el catálogo maestro de los parámetros de cada emisión. Editar una ruta no debe cambiar un documento histórico ya emitido.

## 6. Migración completa y repetible

Implementa un comando de Django y una pantalla de importación que compartan el mismo servicio. Deben aceptar las variantes reales encontradas en los archivos, no una plantilla inventada que obligue a capturar todo nuevamente.

La importación debe:

1. Validar el archivo, detectar su estructura y permitir una simulación sin escribir datos de negocio.
2. Mostrar cuántas rutas y operaciones se encontraron, cuáles son válidas, cuáles ya existen y cuáles requieren revisión.
3. Procesar bloques reales de datos, aunque una ruta ocupe varias filas o esté distribuida entre hojas. No asumir que una fila equivale a una ruta.
4. Aplicar transformaciones explícitas y trazables. No borrar ceros iniciales ni sustituir valores faltantes por ceros sin una regla comprobada.
5. Ser idempotente: importar otra vez el mismo contenido no debe duplicar rutas, operaciones o revisiones. La detección debe considerar tanto el origen como la identidad de negocio validada.
6. Detectar coincidencias entre libros sin fusionar rutas diferentes solo porque comparten un código o una descripción. Conservar todas las procedencias cuando haya un duplicado real.
7. Tratar una ruta existente con datos distintos como un conflicto o una propuesta de nueva revisión. No sobrescribir cambios realizados en la web de forma silenciosa.
8. Usar transacciones con un alcance definido y evitar rutas parcialmente importadas. Para archivos grandes, procesar lotes y permitir reintentos seguros.
9. Generar un informe descargable con altas, coincidencias, conflictos y errores, indicando el origen exacto y cómo resolverlos. Todo registro de origen debe tener un resultado trazable.

Conserva copias originales fuera del repositorio y calcula sus hashes. Importa los cuatro archivos en la base de desarrollo una vez que sean accesibles. Reconcilia los totales del origen y destino, explicando por separado duplicados, revisiones y registros pendientes. No declares que migraste todo mientras existan pérdidas sin explicar.

## 7. Funciones e interfaz

Construye los siguientes flujos completos:

- Inicio de sesión y permisos sencillos: administración, edición de rutas y consulta/impresión. Comprueba los permisos en el servidor, también para archivos y PDF.
- Catálogo central con búsqueda por los identificadores reales y filtros pertinentes. Usa paginación y ordenamiento en el servidor.
- Detalle de ruta con todos sus datos, secuencia de operaciones, revisión y procedencia cuando resulte útil.
- Alta y edición con validación clara. Permite añadir, eliminar y reordenar operaciones; el orden debe persistir correctamente.
- Duplicación de una ruta para crear una variante sin alterar la original.
- Archivo de rutas e historial de cambios con usuario y fecha.
- Selección individual o múltiple para preparar documentos, indicando con claridad si se selecciona la página actual o todos los resultados del filtro.
- Pantalla de programación que permita capturar varias partidas con shop order, pieza o ensamble, cantidad y secuencia, y los datos comunes de semana, cliente/línea, planner y responsable. Debe desglosar componentes según la BOM y mostrar las cantidades calculadas antes de emitir.
- Vista previa, generación y descarga de PDF, y acceso a documentos anteriores para reimpresión.
- Importación con simulación, resultados comprensibles y resolución de incidencias.

La interfaz debe ser limpia, rápida, consistente y estar en español. Prioriza tablas legibles, formularios bien agrupados, navegación clara, búsqueda visible y acciones evidentes para crear, editar e imprimir. Usa estados de carga y mensajes útiles. Debe funcionar bien en escritorio y adaptarse a tabletas. Evita animaciones que retrasen el trabajo y pantallas de métricas decorativas.

## 8. Impresión: parte central del proyecto

Reproduce los formatos operativos que se identifiquen en Excel, conservando sus campos, orden y contenido. Moderniza la pantalla web sin alterar por su cuenta la información que necesita el personal para seguir la ruta.

- Comprueba cuántas plantillas diferentes son realmente necesarias. Si las cuatro variantes son distintas, permite seleccionar la correcta de forma clara y reproducible.
- Genera solo los documentos seleccionados y sus copias necesarias. No cargues todo el catálogo ni recrees todas las hojas para imprimir unas pocas rutas.
- Respeta papel, orientación, dimensiones de etiquetas, márgenes, distribución por página y zonas de corte cuando existan. No supongas A4, Carta o una impresora térmica sin evidencia.
- Preserva textos, símbolos técnicos, unidades, logos e imágenes necesarios. Si existen códigos de barras, valida que su contenido y representación se conserven; no los inventes como sustitutos de datos.
- Maneja textos largos y rutas con más operaciones que una página. Evita recortes, solapamientos, filas divididas indebidamente y páginas vacías.
- Separa cantidad de piezas, cantidad por etiqueta, número de etiquetas y copias cuando esos conceptos existan. Reproduce los cálculos comprobados en las macros y valida sus casos límite.
- Permite impresión individual y por lote, con orden y copias verificables.
- Conserva una instantánea inmutable del contenido emitido y de la plantilla utilizada, o el PDF original protegido, para reproducir documentos históricos sin usar datos modificados después.
- Registra correctamente si el documento fue generado o descargado. La aplicación no debe afirmar que hubo una impresión física solo porque abrió el diálogo del navegador.

Compara visualmente muestras de cada variante con el formato original accesible o con PDFs de referencia. Verifica también los valores y el orden de operaciones. Si no puedes probar la impresora física, indícalo y deja un procedimiento de comprobación a escala real. Si faltan referencias por el cifrado, marca el diseño como provisional.

## 9. Rendimiento y operación

El tiempo de consulta e impresión es un requisito central:

- Usa índices según las búsquedas reales, consultas paginadas y carga relacionada eficiente. Evita consultas por cada fila u operación.
- Consulta PostgreSQL para el trabajo diario. Leer los cuatro Excel debe ser una actividad de importación, no un paso de cada búsqueda o impresión.
- Genera PDF por demanda y reutiliza documentos ya emitidos cuando corresponda. Evita recalcular todo el catálogo.
- Mide búsqueda, carga de detalle y generación de PDF para una ruta y para lotes representativos. Registra equipo, volumen, concurrencia y resultados.
- Si las tareas grandes exceden tiempos razonables de petición, introduce procesamiento en segundo plano con progreso, reintentos y estado persistente. No agregues una cola distribuida por costumbre.
- Prueba crecimiento con datos sintéticos separados e identificados. No presentes tiempos medidos con pocos registros como garantía para cualquier volumen.

Implementa configuración por variables de entorno, contraseñas con el sistema de Django, protección CSRF, controles de acceso y límites razonables para archivos importados. Conserva datos de producción, archivos originales, claves y PDF privados fuera de Git y de URLs públicas. Incluye instrucciones de respaldo y restauración de PostgreSQL y documentos, y verifica una restauración en desarrollo. Prepara el despliegue en red interna sin publicar automáticamente el sistema en Internet.

## 10. Verificación y criterios de aceptación

Incluye pruebas que demuestren los flujos y las reglas importantes:

- Lectura e importación de cada estructura real encontrada, incluida la detección comprensible de archivos cifrados.
- Reimportación sin duplicados, conflictos entre archivos y conservación de códigos y unidades.
- Correspondencia entre registros de origen y destino, con toda incidencia documentada.
- Reconstrucción de ensambles y componentes, multiplicación de cantidades, conservación de materiales PP/BR y gestión de la fila sin tipo. Verifica que las salidas intermedias no se importen como catálogos duplicados.
- Alta, modificación y persistencia de rutas y operaciones después de reiniciar la aplicación.
- Preservación del orden de operaciones y manejo de cambios concurrentes.
- Permisos de edición, importación, generación y descarga de documentos.
- PDF de cada variante, textos largos, múltiples páginas, número de copias y orden de un lote.
- Ubicación correcta de herramental e inspección en las dos variantes, conservación de semanas alfanuméricas y dimensiones con unidad o asterisco, y conciliación de secuencias repetidas sin sobrescritura.
- Reimpresión de un documento histórico después de editar la ruta.
- Mediciones de rendimiento con volumen y entorno declarados.

La aplicación estará terminada cuando pueda iniciarse siguiendo el README, permita trabajar con PostgreSQL, tenga los cuatro orígenes migrados y reconciliados, admita nuevas rutas y produzca documentos visualmente comprobados. Si una contraseña, una regla desconocida o una referencia faltante impide cumplir un criterio, documenta el bloqueo exacto y no lo des por resuelto.

## 11. Entregables y forma de trabajar

Entrega en el repositorio:

- Código funcional, modelos, migraciones, formularios, vistas, interfaz y permisos.
- Importador por consola y por web, con informes y trazabilidad.
- Plantillas y generación de PDF individual y por lote.
- Pruebas significativas y sus resultados reales.
- Configuración de entorno y Docker Compose, sin credenciales fijas.
- `README.md` con instalación, configuración, creación del administrador, importación, arranque, uso, pruebas y respaldo/restauración.
- `docs/analisis_excel.md`, `docs/mapeo_migracion.md`, `docs/validacion_impresion.md` y un registro de pendientes y decisiones.

Trabaja por etapas: inspección, modelo y mapeo, importación, gestión de rutas, impresión y verificación. Explica brevemente los hallazgos y continúa con el trabajo que puedas resolver. Pregunta cuando falte acceso o una ambigüedad pueda provocar pérdida de información, una fusión incorrecta o una impresión equivocada. Toma y documenta decisiones técnicas rutinarias.

Quiero implementación real: no termines únicamente con un plan, un prototipo de pantallas o un importador genérico sin comprobar. No inventes hojas, campos, reglas, resultados de pruebas ni cantidades importadas. Al finalizar, explica qué funciona, cómo ejecutarlo, qué validaste y qué sigue pendiente.

## Referencias técnicas para verificar al implementar

- Versiones soportadas de Django: https://www.djangoproject.com/download/
- Lectura de libros, VBA y valores almacenados de fórmulas con openpyxl: https://openpyxl.readthedocs.io/en/stable/tutorial.html
- Limitación de evaluación de fórmulas de openpyxl: https://openpyxl.readthedocs.io/en/3.1/simple_formulae.html

Estas referencias respaldan decisiones de herramientas. Los archivos originales accesibles y las muestras de impresión deben ser la fuente de las reglas de negocio.
