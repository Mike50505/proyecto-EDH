document.addEventListener('click', event => {
  const button = event.target.closest('[data-add-form]');
  if (!button) return;
  const prefix = button.dataset.addForm;
  const total = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
  const template = document.querySelector(`template[data-formset-template="${prefix}"]`);
  const list = document.querySelector(`[data-formset-list][data-prefix="${prefix}"]`);
  if (!total || !template || !list) return;
  const index = Number(total.value);
  const fragment = template.content.cloneNode(true);
  fragment.querySelectorAll('[name], [id], [for]').forEach(element => {
    for (const attribute of ['name', 'id', 'for']) {
      if (element.hasAttribute(attribute)) element.setAttribute(attribute, element.getAttribute(attribute).replaceAll('__prefix__', String(index)));
    }
  });
  list.append(fragment);
  total.value = index + 1;
});

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

const batchRows = document.querySelector('[data-order-rows]');
const batchTemplate = document.querySelector('[data-order-template]');
const batchCount = document.querySelector('[data-row-count]');
const batchReSource = document.getElementById('batch-re-map');
const batchReMap = batchReSource ? JSON.parse(batchReSource.textContent) : {};
const shopOrderOptions = document.getElementById('shop-order-options');
const knownShopOrders = new Set([...(shopOrderOptions?.options || [])].map(option => option.value.toLocaleLowerCase()));
const batchForm = document.querySelector('[data-batch-form]');
const commonFields = [...document.querySelectorAll('[data-common-field]')];
if (batchForm && commonFields.length) {
  const key = `edh.batch.common.v1.${batchForm.dataset.user}`;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch (_) { saved = {}; }
  for (const input of commonFields) {
    if (input.value.trim()) saved[input.dataset.commonField] = input.value;
    else input.value = saved[input.dataset.commonField] || '';
  }
  const saveCommon = () => {
    const values = Object.fromEntries(commonFields.map(input => [input.dataset.commonField, input.value]));
    try { localStorage.setItem(key, JSON.stringify(values)); } catch (_) { /* Storage may be disabled. */ }
  };
  commonFields.forEach(input => input.addEventListener('input', saveCommon));
  saveCommon();
}

function addOrderRow() {
  if (!batchRows || !batchTemplate || Number(batchCount.value) >= 200) return null;
  const index = Number(batchCount.value);
  const html = batchTemplate.innerHTML.replaceAll('__index__', String(index)).replaceAll('__number__', String(index + 1));
  batchRows.insertAdjacentHTML('beforeend', html);
  batchCount.value = index + 1;
  return batchRows.lastElementChild;
}

function updateBatchRe(input) {
  const re = input.closest('tr')?.querySelector('[data-re]');
  if (re) re.value = batchReMap[input.value.trim().toUpperCase()] ?? '';
}

function rememberShopOrder(input) {
  const value = input?.value.trim();
  if (!value || !shopOrderOptions || knownShopOrders.has(value.toLocaleLowerCase())) return;
  shopOrderOptions.append(new Option('', value));
  knownShopOrders.add(value.toLocaleLowerCase());
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
