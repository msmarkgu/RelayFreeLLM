/* ── State ────────────────────────────────────────────────── */
const state = {
  runs: [],
  currentRunId: null,
  currentResult: null,
  loading: false,
  abortController: null,
  theme: localStorage.getItem('rflm-agents-theme') || 'dark',
  sidebarOpen: window.innerWidth > 700,
  sidebarSearch: '',
};

/* ── DOM References ──────────────────────────────────────── */
const els = {};

function cacheElements() {
  const ids = ['results', 'input', 'btn-run', 'btn-stop', 'btn-theme',
    'empty-state', 'sidebar', 'sidebar-list', 'sidebar-overlay',
    'btn-sidebar', 'btn-sidebar-new', 'sidebar-search',
    'use-case', 'num-experts'];
  for (const id of ids) {
    els[id] = document.getElementById(id);
  }
}

/* ── Theme ────────────────────────────────────────────────── */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  els['btn-theme'].textContent = theme === 'dark' ? '\u{1F319}' : '\u2600\uFE0F';
  localStorage.setItem('rflm-agents-theme', theme);
  state.theme = theme;
}

/* ── Storage ──────────────────────────────────────────────── */
const STORAGE_KEY = 'rflm-agent-runs';

function loadRuns() {
  try {
    state.runs = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    state.runs = [];
  }
}

function saveRuns() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.runs));
}

function saveRun(run) {
  state.runs.unshift(run);
  if (state.runs.length > 50) state.runs = state.runs.slice(0, 50);
  saveRuns();
  renderSidebar();
}

function deleteRun(id) {
  state.runs = state.runs.filter(r => r.id !== id);
  saveRuns();
  if (state.currentRunId === id) {
    state.currentRunId = null;
    state.currentResult = null;
    renderResults();
  }
  renderSidebar();
}

/* ── Sidebar ──────────────────────────────────────────────── */
function renderSidebar() {
  const list = els['sidebar-list'];
  const query = state.sidebarSearch.toLowerCase().trim();
  const filtered = query
    ? state.runs.filter(r => (r.task || '').toLowerCase().includes(query))
    : state.runs;

  if (filtered.length === 0) {
    list.innerHTML = '<div class="sidebar-empty">' + (query ? 'No matching runs' : 'No runs yet') + '</div>';
    return;
  }

  let html = '';
  const now = new Date();
  const today = now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = yesterday.toDateString();

  const groups = { Today: [], Yesterday: [], Older: [] };

  for (const r of filtered) {
    const d = new Date(r.created_at);
    const dStr = d.toDateString();
    if (dStr === today) groups.Today.push(r);
    else if (dStr === yesterdayStr) groups.Yesterday.push(r);
    else groups.Older.push(r);
  }

  for (const [label, runs] of Object.entries(groups)) {
    if (runs.length === 0) continue;
    html += '<div class="sidebar-group-label">' + label + '</div>';
    for (const r of runs) {
      const active = r.id === state.currentRunId ? ' active' : '';
      const title = r.task.length > 40 ? r.task.slice(0, 37) + '...' : r.task;
      const meta = (r.use_case || 'general') + ' \u00B7 ' + (r.num_experts || 4) + ' experts';
      html += '<div class="sidebar-run' + active + '" onclick="selectRun(\'' + r.id + '\')">';
      html += '<span class="run-indicator">&#9679;</span>';
      html += '<div class="run-info">';
      html += '<div class="run-title">' + esc(title) + '</div>';
      html += '<div class="run-meta">' + esc(meta) + '</div>';
      html += '</div>';
      html += '<div class="run-actions">';
      html += '<button class="run-action run-action-del" onclick="deleteRun(\'' + r.id + '\', event)" title="Delete">&#10005;</button>';
      html += '</div>';
      html += '</div>';
    }
  }

  list.innerHTML = html;
}

function selectRun(id) {
  const run = state.runs.find(r => r.id === id);
  if (!run) return;
  state.currentRunId = id;
  state.currentResult = run.result;
  renderResults();
  renderSidebar();
  closeSidebar();
}

function toggleSidebar() {
  state.sidebarOpen = !state.sidebarOpen;
  els.sidebar.classList.toggle('closed', !state.sidebarOpen);
  els['sidebar-overlay'].classList.toggle('hidden', !state.sidebarOpen || window.innerWidth > 700);
}

function closeSidebar() {
  if (window.innerWidth <= 700) {
    state.sidebarOpen = false;
    els.sidebar.classList.add('closed');
    els['sidebar-overlay'].classList.add('hidden');
  }
}

/* ── Markdown Rendering (from chat.js) ─────────────────────── */
function esc(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function renderMarkdown(text) {
  let html = esc(text);

  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, function (match, lang, code) {
    const langAttr = lang ? ' class="language-' + esc(lang) + '"' : '';
    const langLabel = lang ? '<span style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:block;text-transform:uppercase">' + esc(lang) + '</span>' : '';
    return '<pre><button class="copy-btn" onclick="copyCode(this)">Copy</button>' + langLabel + '<code' + langAttr + '>' + esc(code.trim()) + '</code></pre>';
  });

  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/_([^_]+)_/g, '<em>$1</em>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  html = html.replace(/^---$/gm, '<hr>');

  const lines = html.split('\n');
  let result = '';
  let inP = false;
  let inL = false;
  let inPre = false;

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (inPre) {
      result += rawLine;
      if (line.includes('</pre>')) { inPre = false; }
      else { result += '\n'; }
      continue;
    }

    if (!line) {
      if (inP) { result += '</p>'; inP = false; }
      if (inL) { result += '</ul>'; inL = false; }
      continue;
    }
    if (line.startsWith('<h') || line.startsWith('<pre') || line.startsWith('<blockquote') || line.startsWith('<hr')) {
      if (inP) { result += '</p>'; inP = false; }
      if (inL) { result += '</ul>'; inL = false; }
      result += line;
      if (line.startsWith('<pre')) inPre = true;
      continue;
    }
    if (line.startsWith('<li>')) {
      if (inP) { result += '</p>'; inP = false; }
      if (!inL) { result += '<ul>'; inL = true; }
      result += line;
      continue;
    }
    if (!inP) { result += '<p>' + line; inP = true; }
    else { result += '<br>' + line; }
  }
  if (inP) result += '</p>';
  if (inL) result += '</ul>';

  return result;
}

function copyCode(btn) {
  const pre = btn.closest('pre');
  const code = pre.querySelector('code');
  const text = code.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 2000);
  });
}

/* ── Results Rendering ────────────────────────────────────── */
function renderResults() {
  const container = els.results;
  const result = state.currentResult;

  if (!result) {
    container.innerHTML = '';
    const empty = document.createElement('div');
    empty.id = 'empty-state';
    empty.innerHTML = '<div class="empty-icon">&#129504;</div>' +
      '<p>Describe a task and let multiple AI experts solve it together</p>' +
      '<p class="hint">Each expert tackles a different angle, then results are synthesized</p>';
    container.appendChild(empty);
    return;
  }

  let html = '';

  // Task card
  html += '<div class="task-card">';
  html += '<div class="task-label">Task</div>';
  html += '<div class="task-text">' + esc(result.task) + '</div>';
  html += '</div>';

  // Expert cards
  if (result.subtasks && result.subtasks.length > 0) {
    html += '<div class="expert-grid">';
    for (const st of result.subtasks) {
      html += '<div class="expert-card">';
      html += '<div class="expert-header" onclick="toggleExpert(this)">';
      html += '<span class="expert-chevron">&#9660;</span>';
      html += '<div class="expert-badges">';
      html += '<span class="badge badge-provider">' + esc(st.provider) + '</span>';
      html += '<span class="badge badge-model">' + esc(st.model) + '</span>';
      html += '</div>';
      html += '<span class="expert-desc">' + esc(st.description) + '</span>';
      html += '</div>';
      html += '<div class="expert-body">' + renderMarkdown(st.result || '') + '</div>';
      html += '</div>';
    }
    html += '</div>';
  }

  // Synthesis card
  if (result.final_answer) {
    const synthProvider = result.meta?.synthesizer_provider || '';
    const synthModel = result.meta?.synthesizer_model || '';

    html += '<div class="synthesis-card">';
    html += '<div class="synthesis-header">';
    html += '<span class="synthesis-title">Synthesis</span>';
    if (synthProvider) {
      html += '<span class="badge badge-synth">' + esc(synthProvider) + ' / ' + esc(synthModel) + '</span>';
    }
    html += '</div>';
    html += '<div class="synthesis-body">' + renderMarkdown(result.final_answer) + '</div>';
    html += '</div>';
  }

  // Metadata footer
  if (result.meta) {
    const m = result.meta;
    const latency = m.latency_ms ? (m.latency_ms / 1000).toFixed(1) + 's' : 'N/A';
    const completed = m.subtasks_completed || 0;
    const failed = m.subtasks_failed || 0;

    html += '<div class="meta-footer">';
    html += '<span>&#9201; ' + latency + '</span>';
    html += '<span>&#9734; ' + completed + ' expert' + (completed !== 1 ? 's' : '') + '</span>';
    if (failed > 0) {
      html += '<span style="color:var(--btn-danger-bg)">&#10007; ' + failed + ' failed</span>';
    }
    html += '</div>';
  }

  container.innerHTML = html;
  scrollToBottom();
}

function toggleExpert(headerEl) {
  const card = headerEl.closest('.expert-card');
  card.classList.toggle('collapsed');
}

function scrollToBottom() {
  els.results.scrollTop = els.results.scrollHeight;
}

/* ── Loading State ────────────────────────────────────────── */
function showLoading(task, useCase, numExperts) {
  state.currentResult = null;
  const container = els.results;

  let html = '';
  html += '<div class="task-card">';
  html += '<div class="task-label">Task</div>';
  html += '<div class="task-text">' + esc(task) + '</div>';
  html += '<div class="task-meta">';
  html += '<span>' + esc(useCase) + '</span>';
  html += '<span>' + numExperts + ' experts</span>';
  html += '</div>';
  html += '</div>';

  html += '<div class="loading-card">';
  html += '<div class="spinner"></div>';
  html += '<span class="loading-text">Running ' + numExperts + ' experts across providers...</span>';
  html += '</div>';

  container.innerHTML = html;
  scrollToBottom();
}

function hideLoading() {
  const loading = els.results.querySelector('.loading-card');
  if (loading) loading.remove();
}

/* ── API Call ─────────────────────────────────────────────── */
async function performRun() {
  const task = els.input.value.trim();
  if (!task || state.loading) return;

  const useCase = els['use-case'].value;
  const numExperts = parseInt(els['num-experts'].value) || 4;

  // Enter loading state
  state.loading = true;
  state.abortController = new AbortController();
  els['btn-run'].classList.add('hidden');
  els['btn-stop'].classList.remove('hidden');
  els.input.disabled = true;
  els['use-case'].disabled = true;
  els['num-experts'].disabled = true;

  showLoading(task, useCase, numExperts);

  try {
    const res = await fetch('/v1/agents/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task: task,
        use_case: useCase,
        num_experts: numExperts,
      }),
      signal: state.abortController.signal,
    });

    if (!res.ok) {
      let detail = 'HTTP ' + res.status;
      try { const err = await res.json(); detail = err.detail || detail; } catch (_) {}
      throw new Error(detail);
    }

    const data = await res.json();

    // Save run
    const runId = 'run_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    const run = {
      id: runId,
      task: task,
      use_case: useCase,
      num_experts: numExperts,
      created_at: new Date().toISOString(),
      result: data,
    };

    state.currentRunId = runId;
    state.currentResult = data;
    saveRun(run);
    renderResults();

  } catch (e) {
    if (e.name === 'AbortError') {
      hideLoading();
      showToast('Run cancelled', 'success');
      return;
    }
    hideLoading();
    showToast('Error: ' + e.message, 'error');

    // Show error in results
    state.currentResult = {
      task: task,
      subtasks: [],
      final_answer: 'Error: ' + e.message,
      meta: {},
    };
    renderResults();
  } finally {
    state.loading = false;
    state.abortController = null;
    els['btn-run'].classList.remove('hidden');
    els['btn-stop'].classList.add('hidden');
    els.input.disabled = false;
    els['use-case'].disabled = false;
    els['num-experts'].disabled = false;
    els.input.focus();
  }
}

function stopRun() {
  if (state.abortController) {
    state.abortController.abort();
  }
}

/* ── Input Handling ───────────────────────────────────────── */
function autoResizeInput() {
  els.input.style.height = 'auto';
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + 'px';
}

/* ── Toast ────────────────────────────────────────────────── */
function showToast(msg, type) {
  if (type === undefined) type = 'success';
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.style.cssText = 'padding:10px 16px;border-radius:8px;color:#fff;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,0.4);animation:fadeIn 0.2s ease;max-width:400px;background:' + (type === 'error' ? '#da3633' : '#238636') + ';';
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.3s';
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

/* ── Window Resize ─────────────────────────────────────────── */
window.addEventListener('resize', () => {
  if (window.innerWidth > 700 && state.sidebarOpen) {
    els['sidebar-overlay'].classList.add('hidden');
  }
});

/* ── Init ──────────────────────────────────────────────────── */
function init() {
  cacheElements();

  els['btn-theme'].addEventListener('click', () => {
    applyTheme(state.theme === 'dark' ? 'light' : 'dark');
  });

  els['btn-sidebar'].addEventListener('click', toggleSidebar);
  els['sidebar-overlay'].addEventListener('click', toggleSidebar);

  els['sidebar-search'].addEventListener('input', () => {
    state.sidebarSearch = els['sidebar-search'].value;
    renderSidebar();
  });

  document.getElementById('btn-clear-history').addEventListener('click', () => {
    if (confirm('Clear all run history?')) {
      state.runs = [];
      saveRuns();
      state.currentRunId = null;
      state.currentResult = null;
      renderResults();
      renderSidebar();
    }
  });

  els.input.addEventListener('input', autoResizeInput);
  els.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      performRun();
    }
  });

  els['btn-run'].addEventListener('click', performRun);
  els['btn-stop'].addEventListener('click', stopRun);

  applyTheme(state.theme);
  loadRuns();
  renderSidebar();
  els.input.focus();
}

/* ── Global functions for inline handlers ─────────────────── */
window.selectRun = selectRun;
window.deleteRun = function(id, event) {
  event.stopPropagation();
  deleteRun(id);
};
window.toggleExpert = toggleExpert;
window.copyCode = copyCode;

document.addEventListener('DOMContentLoaded', init);
