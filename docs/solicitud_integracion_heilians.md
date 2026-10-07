# Solicitud para Codex: integración de Heilians con EDH

Revisa el repositorio de Heilians y genera un archivo llamado `HEILIANS_INTEGRACION_EDH.md` con los hallazgos solicitados abajo. Por ahora realiza únicamente inspección y documentación; no implementes cambios. Distingue lo que ya existe de lo que propones y cita archivos, modelos y funciones que respalden tus conclusiones.

## Objetivo

Desde Heilians, seleccionar una o varias órdenes que estén en proceso y usar su ITEM PADRE, SEMANA y CANTIDAD para generar un PDF de sus rutas de proceso en EDH. El usuario podrá revisar la selección e imprimir el PDF. Esto no requiere imprimir automáticamente en una impresora.

Los datos recibidos deben ser temporales en EDH: no crear registros de programación ni documentos emitidos persistentes como efecto de esta selección. Las rutas pueden pertenecer a distintos clientes y archivos de origen. Los campos comunes LINEA, PLANNER y RESPONSABLE son opcionales.

## Información que necesitamos de Heilians

1. **Código y arquitectura.** URL del repositorio, rama y commit inspeccionados, tecnologías del backend y frontend, base de datos y archivos relevantes. Describe cómo se ejecuta y si usa Docker.
2. **Conectividad.** URL y puerto de Heilians, ubicación de su servidor y si puede alcanzar EDH por red local, VPN o Internet. Indica qué parte conoces y qué queda por confirmar. No incluyas credenciales.
3. **Modelo de órdenes.** Identifica los nombres y tipos reales de los campos para identificador estable de orden, ITEM PADRE, SEMANA, CANTIDAD, cliente y estado. Aclara si el item pertenece al producto padre o a un componente. Incluye campos opcionales de línea, planner y responsable si existen.
4. **Cantidad y semana.** Explica si existen cantidades planeadas, pendientes, terminadas o en proceso, y cuál muestra actualmente la pantalla. No asumas cuál debemos imprimir: identifica las alternativas. La semana debe conservar su texto completo, incluyendo valores como `31A` y ceros iniciales.
5. **Estados y permisos.** Enumera los estados reales y qué significa “en proceso”. Propón el filtro correcto, excluyendo órdenes canceladas, eliminadas o terminadas según las reglas existentes. Describe permisos y separación por cliente o planta, si existen.
6. **API disponible.** Documenta endpoints existentes, métodos, filtros, paginación, formato de respuestas y errores. Describe la autenticación y permisos actuales. Si no hay API, indícalo y propone una alternativa concreta. Incluye nombres de variables de configuración necesarias, nunca sus valores secretos.
7. **Pantalla de selección.** Señala dónde conviene colocar “Imprimir rutas”, cómo seleccionar varias órdenes y cómo recibir el PDF. Indica archivos/componentes que habría que modificar.
8. **Identificación de rutas.** Comprueba si Heilians aporta cliente, planta u otro dato que permita distinguir dos rutas con el mismo ITEM PADRE. No elegir automáticamente la primera coincidencia cuando haya ambigüedad: proponer una revisión para que el usuario seleccione la ruta correcta. No exigir un archivo de origen que Heilians no conoce.
9. **Ejemplos.** Incluye dos o tres órdenes ficticias o anonimizadas con los nombres reales de sus campos. Mostrar una semana alfanumérica y, si el sistema lo admite, una cantidad decimal. No incluir datos personales reales.
10. **Propuesta técnica.** Recomienda una conexión basada en la arquitectura encontrada: llamada entre servidores o flujo desde el navegador. Explica autenticación, protección de permisos y cómo conservar la sesión de EDH si se usa una pantalla de revisión. Lista los cambios necesarios en cada repositorio y las decisiones pendientes.

## Contexto actual de EDH

- EDH utiliza Django, PostgreSQL, WeasyPrint y Docker. El servicio web usa el puerto 8000; actualmente funciona en una red local.
- `/imprimir-lote/` es un formulario HTML protegido por sesión y CSRF. **Todavía no existe una API JSON de integración externa.** No tratar este formulario como si ya fuera esa API.
- El servicio `rutas/services/batch_selection.py` contiene `build_pdf(rows, template_key="mesa-two-labels-v1", label_mode="components_only")` y admite hasta 200 filas.
- Cada fila necesita `parent_code`, `quantity` positiva y `week` no vacía. `route_id` puede resolver una selección concreta de ruta dentro de EDH.
- SHOP ORDER toma el valor de SEMANA; la secuencia se deriva del orden de las filas; RE lo calcula EDH. Heilians no debe pedir al usuario esos datos adicionales.
- LINEA, PLANNER y RESPONSABLE son valores comunes opcionales.
- Diseños disponibles: `mesa-two-labels-v1` (clásico) y `mesa-modern-v1` (moderno).
- Modos de etiquetas: `components_only` (componentes renumerados desde 1), `include_parent` (incluye etiqueta padre) y `original` (conserva la numeración original sin mostrar el padre).
- La selección temporal genera el PDF en memoria. Debe conservarse la diferencia entre una vista previa y una emisión aprobada: no saltar controles de aprobación. Las rutas archivadas no deben seleccionarse. Las rutas por revisar deben mantener su advertencia y tratamiento existente.
- Un mismo ITEM PADRE puede tener varias coincidencias; EDH debe resolverlas con datos disponibles o mediante selección explícita.

## Ejemplo de contrato propuesto, pendiente de acordar

Este JSON es una propuesta para explicar la intención; no es un endpoint existente ni exige que Heilians use estos nombres internamente.

```json
{
  "source": "heilians",
  "orders": [
    {
      "external_order_id": "H-001",
      "parent_code": "4P503730-1",
      "week": "31A",
      "quantity": "10",
      "client": "DAIKIN"
    }
  ],
  "print_options": {
    "template_key": "mesa-modern-v1",
    "label_mode": "components_only"
  },
  "common": {
    "line": "",
    "planner": "",
    "responsible": ""
  }
}
```

El identificador externo sirve para relacionar errores con la orden seleccionada; no implica almacenar la orden en EDH. Propón cómo devolver errores por fila, items inexistentes y coincidencias ambiguas. Valida cantidades y límites en el servidor y conserva los textos de item y semana sin transformaciones que pierdan información.

## Entrega solicitada

Genera `HEILIANS_INTEGRACION_EDH.md` con:

- Resumen de la arquitectura encontrada, con referencias al código.
- Tabla de correspondencia entre los campos reales de Heilians y los requeridos por EDH.
- Filtro exacto de órdenes en proceso y explicación de las cantidades disponibles.
- API y autenticación existentes; ejemplos anonimizados de solicitud/respuesta cuando estén disponibles.
- Contrato y flujo de integración recomendados, distinguiendo claramente lo nuevo.
- Cambios necesarios en cada aplicación y preguntas que no puedan resolverse inspeccionando el repositorio.

**No incluyas contraseñas, tokens, claves privadas, cookies, archivos `.env` completos ni datos personales.** Si una configuración sensible es necesaria, indica únicamente su nombre y cómo se utilizaría.
