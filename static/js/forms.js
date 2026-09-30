function appendForm(prefix) {
  const total = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
  const template = document.querySelector(`template[data-formset-template="${prefix}"]`);
  const list = document.querySelector(`[data-formset-list][data-prefix="${prefix}"]`);
  if (!total || !template || !list) return null;
  const index = Number(total.value);
  const fragment = template.content.cloneNode(true);
  fragment.querySelectorAll('[name], [id], [for]').forEach(element => {
    for (const attribute of ['name', 'id', 'for']) {
      if (element.hasAttribute(attribute)) element.setAttribute(attribute, element.getAttribute(attribute).replaceAll('__prefix__', String(index)));
    }
  });
  const row = fragment.firstElementChild;
  list.append(fragment);
  total.value = index + 1;
  return row;
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-add-form]');
  if (!button) return;
  appendForm(button.dataset.addForm);
  updateOperationCount();
});

const routeEditor = document.querySelector('[data-route-editor]');
const routeDataEditor = document.querySelector('[data-route-data-editor]');
const routeDataPaste = routeDataEditor?.querySelector('[data-route-data-paste]');
const routeDataMessage = routeDataEditor?.querySelector('[data-route-data-message]');
const routeClient = routeDataEditor?.querySelector('[name="client"]');
const routePart = routeDataEditor?.querySelector('[name="part"]');
const routeDataFields = ['client', 'part', 'code', 'description', 'classification', 'revision', 'status'];
const normalizeRouteValue = value => value.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');

function showRouteDataMessage(message, error = false) {
  routeDataMessage.textContent = message;
  routeDataMessage.classList.toggle('field-error', error);
  routeDataMessage.classList.toggle('hint', !error);
}

function filterRouteParts() {
  if (!routeClient || !routePart) return;
  for (const option of routePart.options) {
    if (!option.value) continue;
    option.hidden = !!routeClient.value && option.dataset.clientId !== routeClient.value;
    option.disabled = option.hidden;
  }
  if (routePart.selectedOptions[0]?.disabled) routePart.value = '';
}

function pasteRouteData(values, startColumn) {
  if (startColumn + values.length > routeDataFields.length) {
    showRouteDataMessage('La fila tiene más columnas que Datos de la ruta.', true);
    return;
  }
  const updates = [];
  for (const [offset, raw] of values.entries()) {
    const fieldName = routeDataFields[startColumn + offset];
    const element = routeDataEditor.querySelector(`[name="${fieldName}"]`);
    const value = raw.trim();
    if (fieldName === 'client' || fieldName === 'status') {
      const match = [...element.options].find(option => option.value &&
        (normalizeRouteValue(option.value) === normalizeRouteValue(value) ||
         normalizeRouteValue(option.textContent) === normalizeRouteValue(value)));
      if (!match) {
        showRouteDataMessage(`No se encontró ${fieldName === 'client' ? 'el cliente' : 'el estado'} «${value}».`, true);
        return;
      }
      updates.push([element, match.value]);
    } else if (fieldName === 'part') {
      const clientUpdate = updates.find(([input]) => input === routeClient);
      const clientId = clientUpdate ? clientUpdate[1] : routeClient.value;
      const matches = [...element.options].filter(option => option.value && option.dataset.clientId === clientId &&
        (normalizeRouteValue(option.dataset.partCode || '') === normalizeRouteValue(value) || option.value === value));
      if (value && matches.length !== 1) {
        showRouteDataMessage(matches.length ? `La pieza «${value}» aparece varias veces; selecciónala manualmente.` :
          `No se encontró la pieza «${value}» para este cliente.`, true);
        return;
      }
      updates.push([element, value ? matches[0].value : '']);
    } else {
      updates.push([element, value]);
    }
  }
  updates.forEach(([element, value]) => { element.value = value; });
  filterRouteParts();
  routeDataPaste.value = '';
  showRouteDataMessage('Datos de la ruta pegados. Revisa los valores antes de guardar.');
}

if (routeDataEditor) {
  routeClient.addEventListener('change', filterRouteParts);
  filterRouteParts();
  routeDataEditor.addEventListener('paste', event => {
    if (routeDataEditor.dataset.editorMode !== 'sheet') return;
    const pasteTarget = event.target.closest('[data-route-data-paste], .route-data-cell');
    if (!pasteTarget) return;
    const clipboard = event.clipboardData?.getData('text/plain') || '';
    if (!clipboard.includes('\t')) return;
    event.preventDefault();
    const lines = clipboard.replace(/\r\n?/g, '\n').trimEnd().split('\n');
    if (lines.length === 2 && normalizeRouteValue(lines[0].split('\t')[0]) === 'cliente') lines.shift();
    if (lines.length !== 1) {
      showRouteDataMessage('Pega una sola fila de datos de ruta a la vez.', true);
      return;
    }
    const values = lines[0].split('\t');
    const startColumn = pasteTarget.hasAttribute('data-route-data-paste') ? 0 : Number(pasteTarget.dataset.routeCol);
    if (pasteTarget.hasAttribute('data-route-data-paste') && values.length !== routeDataFields.length) {
      showRouteDataMessage('La fila debe contener las 7 columnas indicadas; deja la celda de Pieza vacía si no aplica.', true);
      return;
    }
    pasteRouteData(values, startColumn);
  });
}

const operationEditor = document.querySelector('[data-operation-editor]');
const operationList = operationEditor?.querySelector('[data-formset-list]');
const operationModeInput = document.querySelector('[data-editor-mode-input]');
const operationMessage = operationEditor?.querySelector('[data-operation-message]');
const operationColumns = ['position', 'source_sequence', 'name', 'machine', 'tooling', 'inspection', 'DELETE'];

function updateOperationCount() {
  if (!operationEditor) return;
  const count = [...operationList.querySelectorAll('[data-operation-row]')].filter(row =>
    row.querySelector('input[name$="-name"]')?.value.trim() && !row.querySelector('input[name$="-DELETE"]')?.checked
  ).length;
  operationEditor.querySelector('[data-operation-count]').textContent = `${count} ${count === 1 ? 'operación' : 'operaciones'} capturadas`;
}

if (operationEditor) {
  document.querySelectorAll('[data-editor-switch]').forEach(button => button.addEventListener('click', () => {
    operationEditor.dataset.editorMode = button.dataset.editorSwitch;
    routeDataEditor.dataset.editorMode = button.dataset.editorSwitch;
    operationModeInput.value = button.dataset.editorSwitch;
    document.querySelectorAll('[data-editor-switch]').forEach(item =>
      item.setAttribute('aria-pressed', String(item === button)));
  }));

  operationEditor.addEventListener('input', event => {
    if (event.target.matches('input[name$="-name"]') && event.target.value.trim()) {
      const row = event.target.closest('[data-operation-row]');
      const position = row.querySelector('input[name$="-position"]');
      const sequence = row.querySelector('input[name$="-source_sequence"]');
      const rowNumber = [...operationList.querySelectorAll('[data-operation-row]')].indexOf(row) + 1;
      if (!position.value) position.value = String(rowNumber);
      if (!sequence.value) sequence.value = position.value;
    }
    updateOperationCount();
  });
  operationEditor.addEventListener('change', updateOperationCount);
  operationEditor.addEventListener('paste', event => {
    if (operationEditor.dataset.editorMode !== 'sheet' || !event.target.matches('.operation-cell input')) return;
    const clipboard = event.clipboardData?.getData('text/plain') || '';
    if (!/[\t\r\n]/.test(clipboard)) return;
    event.preventDefault();
    const startRow = event.target.closest('[data-operation-row]');
    const startColumn = Number(event.target.closest('[data-op-col]').dataset.opCol);
    const startIndex = [...operationList.querySelectorAll('[data-operation-row]')].indexOf(startRow);
    const lines = clipboard.replace(/\r\n?/g, '\n').replace(/\n$/, '').split('\n');
    const cells = lines.map(line => line.split('\t'));
    if (startIndex + cells.length > 200 || cells.some(row => startColumn + row.length > operationColumns.length)) {
      operationMessage.textContent = 'El pegado supera 200 operaciones o las columnas disponibles. Selecciona la celda inicial correcta.';
      return;
    }
    while (operationList.querySelectorAll('[data-operation-row]').length < startIndex + cells.length) {
      appendForm(operationList.dataset.prefix);
    }
    const rows = operationList.querySelectorAll('[data-operation-row]');
    cells.forEach((line, rowOffset) => line.forEach((value, columnOffset) => {
      const input = rows[startIndex + rowOffset].querySelector(`[name$="-${operationColumns[startColumn + columnOffset]}"]`);
      if (!input) return;
      if (input.type === 'checkbox') input.checked = ['1', 'sí', 'si', 'true', 'x'].includes(value.trim().toLowerCase());
      else input.value = value.trim();
    }));
    rows.forEach((row, index) => {
      const name = row.querySelector('input[name$="-name"]');
      if (!name?.value.trim()) return;
      const position = row.querySelector('input[name$="-position"]');
      const sequence = row.querySelector('input[name$="-source_sequence"]');
      if (!position.value) position.value = String(index + 1);
      if (!sequence.value) sequence.value = position.value;
    });
    operationMessage.textContent = '';
    updateOperationCount();
  });
  updateOperationCount();
}

function updateReCount(routeSelect) {
  const source = document.getElementById('route-re-counts');
  if (!source || !routeSelect) return;
  const row = routeSelect.closest('.operation-form');
  const output = row?.querySelector('[data-re-count]');
  if (!output) return;
  const counts = JSON.parse(source.textContent);
  output.value = routeSelect.value ? (counts[routeSelect.value] ?? 0) : '';
}

document.querySelectorAll('[data-formset-list] select[name$="-route"]').forEach(updateReCount);

document.addEventListener('change', event => {
  if (event.target.matches('[data-formset-list] select[name$="-route"]')) updateReCount(event.target);
  if (!event.target.matches('[data-select-page]')) return;
  document.querySelectorAll('[data-route-checkbox]').forEach(box => { box.checked = event.target.checked; });
});

const importClient = document.querySelector('[data-import-client]');
const importVariant = document.querySelector('[data-import-variant]');
const sourceVariants = document.getElementById('source-variants');
if (importClient && importVariant && sourceVariants) {
  const variantsByClient = JSON.parse(sourceVariants.textContent);
  const filterVariants = () => {
    const allowed = variantsByClient[importClient.value] || [];
    for (const option of importVariant.options) {
      option.hidden = !allowed.includes(option.value);
      option.disabled = option.hidden;
    }
    if (!allowed.includes(importVariant.value)) importVariant.value = allowed[0] || '';
  };
  importClient.addEventListener('change', filterVariants);
  filterVariants();
}

const batchRows = document.querySelector('[data-order-rows]');
const batchTemplate = document.querySelector('[data-order-template]');
const batchCount = document.querySelector('[data-row-count]');
const batchReSource = document.getElementById('batch-re-map');
let batchReMap = batchReSource ? JSON.parse(batchReSource.textContent) : {};
const routeCatalogSource = document.getElementById('batch-route-catalog');
const routeCatalog = routeCatalogSource ? JSON.parse(routeCatalogSource.textContent) : {};
const orderCatalogSource = document.getElementById('batch-order-catalog');
const orderCatalog = orderCatalogSource ? JSON.parse(orderCatalogSource.textContent) : {};
const batchClient = document.querySelector('[data-batch-client]');
const batchVariant = document.querySelector('[data-batch-variant]');
const parentCodeOptions = document.getElementById('parent-code-options');
const shopOrderOptions = document.getElementById('shop-order-options');
const knownShopOrders = Object.fromEntries(Object.entries(orderCatalog).map(([client, orders]) => [client, new Set(orders)]));
const batchForm = document.querySelector('[data-batch-form]');
const commonFields = [...document.querySelectorAll('[data-common-field]')];
let currentBatchClient = batchClient?.value || 'DAIKIN';
if (batchForm && commonFields.length) {
  const key = client => `edh.batch.common.v2.${batchForm.dataset.user}.${client}`;
  const saveCommon = (client = currentBatchClient) => {
    const values = Object.fromEntries(commonFields.map(input => [input.dataset.commonField, input.value]));
    try { localStorage.setItem(key(client), JSON.stringify(values)); } catch (_) { /* Storage may be disabled. */ }
  };
  const loadCommon = (client, useRenderedValues = false) => {
    let saved = {};
    try {
      const legacy = client === 'DAIKIN' ? localStorage.getItem(`edh.batch.common.v1.${batchForm.dataset.user}`) : null;
      saved = JSON.parse(localStorage.getItem(key(client)) || legacy || '{}');
    } catch (_) { saved = {}; }
    for (const input of commonFields) {
      if (useRenderedValues && input.value.trim()) saved[input.dataset.commonField] = input.value;
      input.value = saved[input.dataset.commonField] || '';
    }
    saveCommon(client);
  };
  commonFields.forEach(input => input.addEventListener('input', () => saveCommon()));
  loadCommon(currentBatchClient, true);
  batchClient?.addEventListener('change', () => {
    saveCommon(currentBatchClient);
    currentBatchClient = batchClient.value;
    loadCommon(currentBatchClient);
    refreshBatchVariants();
    refreshBatchSuggestions();
  });
}

function refreshBatchVariants() {
  if (!batchVariant) return;
  const variants = Object.keys(routeCatalog[currentBatchClient] || {}).filter(Boolean).sort();
  batchVariant.replaceChildren(new Option('Seleccionar si hay duplicados', ''),
    ...variants.map(variant => new Option(variant, variant)));
  batchVariant.value = variants[0] || '';
}

function refreshBatchSuggestions() {
  if (!batchVariant || !parentCodeOptions || !shopOrderOptions) return;
  const variants = routeCatalog[currentBatchClient] || {};
  const selected = batchVariant.value ? [variants[''] || {}, variants[batchVariant.value] || {}] : Object.values(variants);
  const routes = Object.assign({}, ...selected);
  batchReMap = Object.fromEntries(Object.entries(routes).map(([code, count]) => [code.toUpperCase(), count]));
  parentCodeOptions.replaceChildren(...Object.keys(routes).sort().map(code => new Option('', code)));
  const orders = knownShopOrders[currentBatchClient] || new Set();
  shopOrderOptions.replaceChildren(...[...orders].sort().map(order => new Option('', order)));
  batchRows?.querySelectorAll('[data-parent-code]').forEach(updateBatchRe);
}
batchVariant?.addEventListener('change', refreshBatchSuggestions);

function addOrderRow() {
  if (!batchRows || !batchTemplate || Number(batchCount.value) >= 200) return null;
  const index = Number(batchCount.value);
  const html = batchTemplate.innerHTML.replaceAll('__index__', String(index)).replaceAll('__number__', String(index + 1));
  batchRows.insertAdjacentHTML('beforeend', html);
  batchCount.value = index + 1;
  return batchRows.lastElementChild;
}

function updateBatchRe(input) {
  if (!input) return;
  const re = input.closest('tr')?.querySelector('[data-re]');
  if (re) re.value = batchReMap[input.value.trim().toUpperCase()] ?? '';
}

function rememberShopOrder(input) {
  const value = input?.value.trim();
  if (!value || !shopOrderOptions) return;
  const known = knownShopOrders[currentBatchClient] ||= new Set();
  if ([...known].some(order => order.toLocaleLowerCase() === value.toLocaleLowerCase())) return;
  shopOrderOptions.append(new Option('', value));
  known.add(value);
}

document.querySelector('[data-add-order-row]')?.addEventListener('click', () => addOrderRow()?.querySelector('input')?.focus());
batchRows?.addEventListener('input', event => {
  if (event.target.matches('[data-parent-code]')) updateBatchRe(event.target);
});
batchRows?.addEventListener('change', event => {
  if (event.target.matches('[data-shop-order]')) rememberShopOrder(event.target);
});
batchRows?.querySelectorAll('[data-parent-code]').forEach(updateBatchRe);

batchRows?.addEventListener('paste', event => {
  const input = event.target.closest('input');
  const pasted = event.clipboardData?.getData('text/plain');
  if (!input || !pasted || !/[\t\r\n]/.test(pasted)) return;
  event.preventDefault();
  const startColumn = [...input.closest('tr').querySelectorAll('input')].indexOf(input);
  let row = input.closest('tr');
  const matrix = pasted.trimEnd().split(/\r?\n/).map(line => line.split('\t'));
  if (matrix[0]?.[0]?.trim().toUpperCase() === 'SHOP ORDER') matrix.shift();
  for (const cells of matrix) {
    if (!row) row = addOrderRow();
    if (!row) break;
    if (row === batchRows.firstElementChild && startColumn === 0 && cells.length >= 9) {
      commonFields.forEach((field, offset) => {
        field.value = cells[6 + offset]?.trim() || '';
        field.dispatchEvent(new Event('input', { bubbles: true }));
      });
    }
    const inputs = [...row.querySelectorAll('input')];
    cells.forEach((value, offset) => {
      const target = inputs[startColumn + offset];
      if (target && !target.readOnly) target.value = value.trim();
    });
    updateBatchRe(row.querySelector('[data-parent-code]'));
    rememberShopOrder(row.querySelector('[data-shop-order]'));
    row = row.nextElementSibling;
  }
});
