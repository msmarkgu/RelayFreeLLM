let limitsData = null;
let limitsDirty = false;

function toast(msg, type) {
  if (type === undefined) type = 'success';
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(function () {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.3s';
    setTimeout(function () { el.remove(); }, 300);
  }, 3000);
}

document.querySelectorAll('.tab-btn').forEach(function (btn) {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
    document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'usage') renderUsage();
  });
});

async function loadLimits() {
  const el = document.getElementById('limits-content');
  el.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    const res = await fetch('/admin/api/limits');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    limitsData = await res.json();
    limitsDirty = false;
    renderLimits();
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><p>Failed to load limits</p><div class="hint">' + e.message + '</div></div>';
  }
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function renderLimits() {
  const el = document.getElementById('limits-content');
  if (!limitsData || !limitsData.providers || limitsData.providers.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>No providers configured</p><div class="hint">Add a provider to get started.</div></div>';
    return;
  }

  var html = '';
  for (var pi = 0; pi < limitsData.providers.length; pi++) {
    var prov = limitsData.providers[pi];
    html += '<div class="provider-card" data-provider-index="' + pi + '">';
    html += '<div class="provider-header" onclick="toggleProvider(this)">';
    html += '<div><span class="chevron">\u25bc</span> <span class="name">' + esc(prov.name) + '</span> <span class="model-count">' + prov.models.length + ' model' + (prov.models.length !== 1 ? 's' : '') + '</span></div>';
    html += '<div><button class="btn btn-sm btn-danger" onclick="event.stopPropagation();removeProvider(' + pi + ')">Remove</button></div>';
    html += '</div>';
    html += '<div class="provider-body">';
    html += '<div class="table-wrap">';
    html += '<table class="model-table"><thead><tr>';
    html += '<th>Model Name</th><th>Type</th><th>Scale</th><th>Max Context</th>';
    html += '<th>Req/s</th><th>Req/min</th><th>Req/hr</th><th>Req/day</th>';
    html += '<th>Tok/min</th><th>Tok/hr</th><th>Tok/day</th>';
    html += '<th class="col-actions"></th>';
    html += '</tr></thead><tbody>';

    for (var mi = 0; mi < prov.models.length; mi++) {
      var model = prov.models[mi];
      var l = model.limits || {};
      html += '<tr data-model-index="' + mi + '">';
      html += '<td><input class="model-name-input" type="text" value="' + esc(model.name) + '" data-field="name" data-pi="' + pi + '" data-mi="' + mi + '"></td>';
      html += '<td><select data-field="type" data-pi="' + pi + '" data-mi="' + mi + '">' +
        typeOptions(model.type) + '</select></td>';
      html += '<td><select data-field="scale" data-pi="' + pi + '" data-mi="' + mi + '">' +
        scaleOptions(model.scale) + '</select></td>';
      html += '<td><input type="number" value="' + (model.Max_Context_Length || 4096) + '" data-field="Max_Context_Length" data-pi="' + pi + '" data-mi="' + mi + '"></td>';
      var fields = ['requests_per_second', 'requests_per_minute', 'requests_per_hour', 'requests_per_day', 'tokens_per_minute', 'tokens_per_hour', 'tokens_per_day'];
      for (var fi = 0; fi < fields.length; fi++) {
        var f = fields[fi];
        var v = l[f] !== undefined ? l[f] : '';
        html += '<td><input type="number" value="' + v + '" data-field="' + f + '" data-pi="' + pi + '" data-mi="' + mi + '"></td>';
      }
      html += '<td class="col-actions"><button class="btn btn-sm btn-danger" onclick="removeModel(' + pi + ',' + mi + ')">\u2715</button></td>';
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    html += '<div style="margin-top:8px;"><button class="btn btn-sm" onclick="addModel(' + pi + ')">+ Add Model</button></div>';
    html += '</div></div>';
  }

  el.innerHTML = html;

  el.querySelectorAll('input, select').forEach(function (el_) {
    el_.addEventListener('change', function () { limitsDirty = true; });
    el_.addEventListener('input', function () { limitsDirty = true; });
  });
}

function typeOptions(selected) {
  var types = ['text', 'coding', 'image', 'speech', 'embedding', 'moderation', 'ocr'];
  var opts = '';
  for (var i = 0; i < types.length; i++) {
    opts += '<option value="' + types[i] + '"' + (types[i] === selected ? ' selected' : '') + '>' + types[i] + '</option>';
  }
  return opts;
}

function scaleOptions(selected) {
  var scales = ['large', 'medium', 'small'];
  var opts = '';
  for (var i = 0; i < scales.length; i++) {
    opts += '<option value="' + scales[i] + '"' + (scales[i] === selected ? ' selected' : '') + '>' + scales[i] + '</option>';
  }
  return opts;
}

function toggleProvider(header) {
  header.classList.toggle('collapsed');
  header.nextElementSibling.classList.toggle('hidden');
}

function collectLimits() {
  var data = { providers: [] };
  var cards = document.querySelectorAll('.provider-card');
  for (var ci = 0; ci < cards.length; ci++) {
    var card = cards[ci];
    var pi = parseInt(card.dataset.providerIndex);
    var orig = limitsData.providers[pi];
    var provName = card.querySelector('.provider-header .name').textContent.trim();
    var models = [];
    var rows = card.querySelectorAll('.provider-body tbody tr');
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];
      var inputs = row.querySelectorAll('input, select');
      var model = { name: '', type: 'text', scale: 'medium', limits: {}, Max_Context_Length: 4096 };
      for (var ii = 0; ii < inputs.length; ii++) {
        var inp = inputs[ii];
        var f = inp.dataset.field;
        if (!f) continue;
        var val = inp.value;
        if (f === 'type' || f === 'scale' || f === 'name') {
          model[f] = val;
        } else if (f === 'Max_Context_Length') {
          model.Max_Context_Length = parseInt(val) || 4096;
        } else {
          model.limits[f] = val === '' ? 0 : parseInt(val);
        }
      }
      models.push(model);
    }
    data.providers.push({ name: provName, url: (orig && orig.url) || '', models: models });
  }
  return data;
}

document.getElementById('btn-save-limits').addEventListener('click', async function () {
  if (!limitsDirty) { toast('No changes to save.', 'error'); return; }
  var data = collectLimits();
  try {
    var res = await fetch('/admin/api/limits', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('HTTP ' + res.status + ': ' + await res.text());
    var result = await res.json();
    toast(result.message || 'Limits saved successfully.');
    limitsDirty = false;
    await loadLimits();
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  }
});

document.getElementById('btn-refresh-limits').addEventListener('click', loadLimits);

function addModel(pi) {
  var prov = limitsData.providers[pi];
  if (!prov) return;
  prov.models.push({
    name: 'new-model',
    type: 'text',
    scale: 'medium',
    Max_Context_Length: 4096,
    limits: { requests_per_second: 1, requests_per_minute: 5, requests_per_hour: 60, requests_per_day: 100, tokens_per_minute: 250000, tokens_per_hour: -1, tokens_per_day: -1 }
  });
  limitsDirty = true;
  renderLimits();
}

function removeModel(pi, mi) {
  if (!limitsData.providers[pi]) return;
  limitsData.providers[pi].models.splice(mi, 1);
  limitsDirty = true;
  renderLimits();
}

function removeProvider(pi) {
  if (!confirm('Remove provider "' + limitsData.providers[pi].name + '" and all its models?')) return;
  limitsData.providers.splice(pi, 1);
  limitsDirty = true;
  renderLimits();
}

document.getElementById('btn-add-provider').addEventListener('click', function () {
  document.getElementById('new-provider-name').value = '';
  document.getElementById('add-provider-modal').classList.remove('hidden');
  document.getElementById('new-provider-name').focus();
});
document.getElementById('modal-provider-cancel').addEventListener('click', function () {
  document.getElementById('add-provider-modal').classList.add('hidden');
});
document.getElementById('modal-provider-confirm').addEventListener('click', function () {
  var name = document.getElementById('new-provider-name').value.trim();
  if (!name) { toast('Provider name is required.', 'error'); return; }
  for (var i = 0; i < limitsData.providers.length; i++) {
    if (limitsData.providers[i].name.toLowerCase() === name.toLowerCase()) {
      toast('Provider "' + name + '" already exists.', 'error');
      return;
    }
  }
  limitsData.providers.push({ name: name, url: '', models: [] });
  limitsDirty = true;
  document.getElementById('add-provider-modal').classList.add('hidden');
  renderLimits();
  toast('Provider "' + name + '" added. Don\'t forget to save.');
});

async function renderUsage() {
  var el = document.getElementById('usage-content');
  el.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
  try {
    var res = await fetch('/admin/api/usage');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var data = await res.json();
    renderUsageData(data, el);
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><p>Failed to load usage stats</p><div class="hint">' + e.message + '</div></div>';
  }
}

function renderUsageData(data, el) {
  var total = data.total || { prompt_tokens: 0, completion_tokens: 0, requests: 0 };
  var totalTokens = total.prompt_tokens + total.completion_tokens;
  var providers = data.providers || {};

  var html = '';

  html += '<div class="summary-cards">';
  html += card('Total Requests', total.requests);
  html += card('Prompt Tokens', total.prompt_tokens);
  html += card('Completion Tokens', total.completion_tokens);
  html += card('Total Tokens', totalTokens);
  html += '</div>';

  var provNames = Object.keys(providers);
  if (provNames.length === 0) {
    html += '<div class="empty-state"><p>No usage data yet</p></div>';
  } else {
    for (var pi = 0; pi < provNames.length; pi++) {
      var pName = provNames[pi];
      var p = providers[pName];
      var models = p.models || {};
      var modelNames = Object.keys(models);
      html += '<div class="usage-provider"><h3>' + esc(pName) + ' <span>' + (p.requests || 0) + ' req \u00b7 ' + fmt(p.prompt_tokens || 0) + ' / ' + fmt(p.completion_tokens || 0) + ' tok</span></h3>';
      html += '<div class="table-wrap"><table class="usage-table"><thead><tr>';
      html += '<th>Model</th><th class="num">Requests</th><th class="num">Prompt Tokens</th><th class="num">Completion Tokens</th><th class="num">Total Tokens</th>';
      html += '</tr></thead><tbody>';
      for (var mi = 0; mi < modelNames.length; mi++) {
        var mName = modelNames[mi];
        var m = models[mName];
        var mTotal = (m.prompt_tokens || 0) + (m.completion_tokens || 0);
        html += '<tr><td>' + esc(mName) + '</td><td class="num">' + (m.requests || 0) + '</td><td class="num">' + fmt(m.prompt_tokens || 0) + '</td><td class="num">' + fmt(m.completion_tokens || 0) + '</td><td class="num">' + fmt(mTotal) + '</td></tr>';
      }
      html += '</tbody></table></div></div>';
    }
  }

  el.innerHTML = html;
}

function card(label, value) {
  return '<div class="summary-card"><div class="value">' + fmt(value) + '</div><div class="label">' + label + '</div></div>';
}

function fmt(n) { return typeof n === 'number' ? n.toLocaleString() : n; }

document.getElementById('btn-refresh-usage').addEventListener('click', renderUsage);

document.getElementById('btn-reset-usage').addEventListener('click', function () {
  document.getElementById('reset-modal').classList.remove('hidden');
});
document.getElementById('modal-reset-cancel').addEventListener('click', function () {
  document.getElementById('reset-modal').classList.add('hidden');
});
document.getElementById('modal-reset-confirm').addEventListener('click', async function () {
  document.getElementById('reset-modal').classList.add('hidden');
  try {
    var res = await fetch('/admin/api/usage/reset', { method: 'POST' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    toast('Usage stats reset.');
    await renderUsage();
  } catch (e) {
    toast('Reset failed: ' + e.message, 'error');
  }
});

loadLimits();
renderUsage();

setInterval(function () {
  var usageTab = document.querySelector('.tab-btn[data-tab="usage"]');
  if (usageTab && usageTab.classList.contains('active')) {
    renderUsage();
  }
}, 30000);
