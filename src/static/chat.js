/* ── State ────────────────────────────────────────────────── */
const state = {
  conversations: [],
  currentId: null,
  messages: [],
  model: 'meta-model',
  streaming: false,
  abortController: null,
  theme: localStorage.getItem('rflm-chat-theme') || 'dark',
  storageMode: localStorage.getItem('rflm-storage-mode') || 'browser',
  sidebarOpen: window.innerWidth > 700,
  sidebarSearch: '',
};

/* ── DOM References ──────────────────────────────────────── */
const els = {};

function cacheElements() {
  const ids = ['messages', 'input', 'btn-send', 'btn-stop', 'btn-new', 'btn-theme',
    'model-select', 'empty-state', 'empty-model', 'sidebar',
    'sidebar-list', 'sidebar-overlay', 'btn-sidebar', 'btn-sidebar-new',
    'sidebar-search',
    'storage-mode', 'migrate-modal', 'migrate-text',
    'modal-migrate-cancel', 'modal-migrate-keep', 'modal-migrate-import'];
  for (const id of ids) {
    els[id] = document.getElementById(id);
  }
}

/* ── Theme ────────────────────────────────────────────────── */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  els['btn-theme'].textContent = theme === 'dark' ? '\u{1F319}' : '\u2600\uFE0F';
  localStorage.setItem('rflm-chat-theme', theme);
  state.theme = theme;
}

/* ── Device ID (for server storage) ───────────────────────── */
function getDeviceId() {
  let id = localStorage.getItem('rflm-device-id');
  if (!id) {
    id = 'device_' + Math.random().toString(36).slice(2, 14) + Date.now().toString(36);
    localStorage.setItem('rflm-device-id', id);
  }
  return id;
}

/* ── Storage Backend ──────────────────────────────────────── */
const store = {};

/* Browser (localStorage) backend */
store.browser = {
  _key: 'rflm-conversations',

  _read() {
    try {
      return JSON.parse(localStorage.getItem(this._key)) || [];
    } catch { return []; }
  },

  _write(convs) {
    localStorage.setItem(this._key, JSON.stringify(convs));
  },

  async list() {
    const convs = this._read();
    return convs.map(c => ({
      id: c.id,
      title: c.title || '',
      model: c.model || 'meta-model',
      msg_count: (c.messages || []).length,
      created_at: c.created_at || '',
      updated_at: c.updated_at || '',
    })).sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  },

  async create(data) {
    const convs = this._read();
    const now = new Date().toISOString();
    const conv = {
      id: 'conv_' + Math.random().toString(36).slice(2, 14),
      title: data?.title || '',
      model: data?.model || 'meta-model',
      messages: [],
      created_at: now,
      updated_at: now,
    };
    convs.push(conv);
    this._write(convs);
    return { id: conv.id };
  },

  async get(id) {
    const convs = this._read();
    return convs.find(c => c.id === id) || null;
  },

  async update(id, data) {
    const convs = this._read();
    const conv = convs.find(c => c.id === id);
    if (!conv) return false;
    if (data.title !== undefined) conv.title = data.title;
    if (data.model !== undefined) conv.model = data.model;
    if (data.messages !== undefined) conv.messages = data.messages;
    conv.updated_at = new Date().toISOString();
    this._write(convs);
    return true;
  },

  async remove(id) {
    let convs = this._read();
    const before = convs.length;
    convs = convs.filter(c => c.id !== id);
    if (convs.length === before) return false;
    this._write(convs);
    return true;
  },

  async import(convs) {
    const existing = this._read();
    const existingIds = new Set(existing.map(c => c.id));
    let count = 0;
    for (const conv of convs) {
      if (!conv.id) continue;
      if (!existingIds.has(conv.id)) {
        existing.push(conv);
        existingIds.add(conv.id);
        count++;
      }
    }
    if (count > 0) this._write(existing);
    return { imported: count };
  },
};

/* Server (fetch) backend */
store.server = {
  _headers() {
    return {
      'Content-Type': 'application/json',
      'X-Device-ID': getDeviceId(),
    };
  },

  async _fetch(url, opts) {
    const res = await fetch(url, { ...opts, headers: { ...this._headers(), ...opts?.headers } });
    if (!res.ok) {
      let detail;
      try { detail = (await res.json()).detail; } catch { detail = 'HTTP ' + res.status; }
      throw new Error(detail);
    }
    return res.json();
  },

  async list() { return this._fetch('/api/conversations'); },

  async create(data) {
    return this._fetch('/api/conversations', {
      method: 'POST',
      body: JSON.stringify(data || {}),
    });
  },

  async get(id) { return this._fetch('/api/conversations/' + id); },

  async update(id, data) {
    return this._fetch('/api/conversations/' + id, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async remove(id) {
    return this._fetch('/api/conversations/' + id, { method: 'DELETE' });
  },

  async import(convs) {
    return this._fetch('/api/conversations/import', {
      method: 'POST',
      body: JSON.stringify({ conversations: convs }),
    });
  },
};

function getStore() {
  return store[state.storageMode];
}

/* ── Storage Mode Switching ───────────────────────────────── */
let storageSwitchInProgress = false;

function setupStorageModeListener() {
  els['storage-mode'].addEventListener('change', async function () {
  if (storageSwitchInProgress) return;
  const newMode = this.value;
  if (newMode === state.storageMode) return;

  const oldMode = state.storageMode;
  const oldConvs = state.conversations;

  if (oldConvs.length === 0) {
    // No conversations to worry about, just switch
    state.storageMode = newMode;
    localStorage.setItem('rflm-storage-mode', newMode);
    await loadConversations();
    return;
  }

  // Ask user what to do
  const modal = els['migrate-modal'];
  const text = els['migrate-text'];
  const importBtn = els['modal-migrate-import'];
  const keepBtn = els['modal-migrate-keep'];

  modal.classList.remove('hidden');
  text.textContent = 'Switch from "' + oldMode + '" to "' + newMode + '"? Your current conversations in ' + oldMode + ' won\'t be visible while using ' + newMode + '.';

  if (oldMode === 'browser' && newMode === 'server') {
    importBtn.classList.remove('hidden');
    importBtn.textContent = 'Import from Browser';
    importBtn.onclick = async () => {
      modal.classList.add('hidden');
      storageSwitchInProgress = true;
      try {
        const browserConvs = store.browser._read();
        const result = await store.server.import(browserConvs);
        state.storageMode = newMode;
        localStorage.setItem('rflm-storage-mode', newMode);
        await loadConversations();
        showToast('Switched to Server. ' + result.imported + ' conversations imported.');
      } catch (e) {
        showToast('Import failed: ' + e.message, 'error');
        els['storage-mode'].value = oldMode;
      } finally {
        storageSwitchInProgress = false;
      }
    };
  } else {
    importBtn.classList.add('hidden');
  }

  keepBtn.onclick = async () => {
    modal.classList.add('hidden');
    state.storageMode = newMode;
    localStorage.setItem('rflm-storage-mode', newMode);
    await loadConversations();
  };

  els['modal-migrate-cancel'].onclick = () => {
    modal.classList.add('hidden');
    els['storage-mode'].value = oldMode;
  };
  });
}

/* ── Conversation Management ─────────────────────────────── */
async function loadConversations() {
  try {
    state.conversations = await getStore().list();
    renderSidebar();
  } catch (e) {
    console.error('Failed to load conversations:', e);
    showToast('Failed to load conversations: ' + e.message, 'error');
  }
}

async function selectConversation(id) {
  try {
    const conv = await getStore().get(id);
    if (!conv) {
      showToast('Conversation not found', 'error');
      return;
    }
    state.currentId = conv.id;
    state.model = conv.model || 'meta-model';
    state.messages = conv.messages || [];
    els['model-select'].value = state.model;
    els['empty-model'].textContent = state.model;
    renderMessages();
    renderSidebar();
    closeSidebar();
  } catch (e) {
    showToast('Failed to load conversation: ' + e.message, 'error');
  }
}

async function deleteConversation(id, e) {
  e.stopPropagation();
  try {
    await getStore().remove(id);
    if (state.currentId === id) {
      state.currentId = null;
      state.messages = [];
      renderMessages();
    }
    await loadConversations();
  } catch (e) {
    showToast('Failed to delete: ' + e.message, 'error');
  }
}

async function renameConversation(id, e) {
  e.stopPropagation();
  const conv = state.conversations.find(c => c.id === id);
  if (!conv) return;
  const newTitle = prompt('Rename conversation:', conv.title || '');
  if (newTitle === null || newTitle.trim() === '') return;
  try {
    await getStore().update(id, { title: newTitle.trim() });
    // Also update the current title if this is the active conversation
    await loadConversations();
  } catch (e) {
    showToast('Failed to rename: ' + e.message, 'error');
  }
}

async function copyConversation(id, e) {
  e.stopPropagation();
  try {
    let conv = state.conversations.find(c => c.id === id);
    if (!conv) return;
    // Get full conversation with messages
    if (id === state.currentId && state.messages.length > 0) {
      conv = { messages: state.messages.map(m => ({ role: m.role, content: m.content })) };
    } else {
      conv = await getStore().get(id);
    }
    if (!conv || !conv.messages || conv.messages.length === 0) {
      showToast('No messages to copy', 'error');
      return;
    }
    const text = conv.messages.map(m => {
      const prefix = m.role === 'user' ? 'You' : 'Assistant';
      return prefix + ':\n' + m.content;
    }).join('\n\n');
    await navigator.clipboard.writeText(text);
    showToast('Conversation copied');
  } catch (e) {
    showToast('Failed to copy: ' + e.message, 'error');
  }
}

async function createNewConversation() {
  try {
    const result = await getStore().create({ model: state.model });
    state.currentId = result.id;
    state.messages = [];
    await loadConversations();
    renderMessages();
    els.input.focus();
    closeSidebar();
  } catch (e) {
    showToast('Failed to create conversation: ' + e.message, 'error');
  }
}

async function saveCurrentConversation() {
  if (!state.currentId) return;
  if (state.messages.length === 0) return;
  try {
    const msgs = state.messages.map(m => ({
      role: m.role,
      content: m.content,
      ...(m.provider && { provider: m.provider }),
      ...(m.actualModel && { actualModel: m.actualModel }),
    }));
    const title = deriveTitle(state.messages);
    await getStore().update(state.currentId, {
      messages: msgs,
      model: state.model,
      title: title,
    });
    // Refresh sidebar to update title and ordering
    await loadConversations();
  } catch (e) {
    console.error('Failed to save conversation:', e);
  }
}

function deriveTitle(messages) {
  const first = messages.find(m => m.role === 'user');
  if (!first) return '';
  let title = first.content.replace(/[\n\r]+/g, ' ').trim();
  if (title.length > 45) title = title.slice(0, 42) + '...';
  return title;
}

/* ── Edit / Delete Messages ────────────────────────────── */

function deleteMessage(msg) {
  const idx = state.messages.indexOf(msg);
  if (idx === -1) return;
  state.messages.splice(idx, 1);
  renderMessages();
  saveCurrentConversation();
}

function regenerateResponse() {
  if (state.streaming) return;
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (state.messages[i].role === 'assistant') {
      state.messages.splice(i, 1);
      break;
    }
  }
  renderMessages();
  performStreamingSend();
}

function editMessage(msg) {
  if (msg.role !== 'user') return;
  const idx = state.messages.indexOf(msg);
  if (idx === -1) return;

  // Remove all messages after this one
  state.messages.splice(idx + 1);

  // Find the bubble DOM element for this message
  const bubbles = els.messages.querySelectorAll('.message.user');
  const bubbleEl = bubbles[idx]?.querySelector('.bubble');
  if (!bubbleEl) return;

  // Replace bubble content with a textarea + action buttons
  const textarea = document.createElement('textarea');
  textarea.className = 'edit-textarea';
  textarea.value = msg.content;
  textarea.rows = Math.min(5, msg.content.split('\n').length);

  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn btn-primary btn-sm';
  saveBtn.textContent = 'Save';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn-sm';
  cancelBtn.textContent = 'Cancel';

  const editActions = document.createElement('div');
  editActions.className = 'edit-actions';
  editActions.appendChild(saveBtn);
  editActions.appendChild(cancelBtn);

  const editWrap = document.createElement('div');
  editWrap.className = 'edit-wrap';
  editWrap.appendChild(textarea);
  editWrap.appendChild(editActions);

  bubbleEl.innerHTML = '';
  bubbleEl.appendChild(editWrap);
  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);

  const cleanup = () => {
    bubbleEl.innerHTML = renderMarkdown(msg.content);
  };

  const submitEdit = () => {
    const newText = textarea.value.trim();
    if (!newText) return;
    msg.content = newText;
    // Re-render up to this message
    renderMessages();
    els.input.focus();
    performStreamingSend();
  };

  saveBtn.onclick = submitEdit;
  cancelBtn.onclick = cleanup;

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitEdit();
    }
    if (e.key === 'Escape') {
      cleanup();
    }
  });
}

/* ── Sidebar ──────────────────────────────────────────────── */
function renderSidebar() {
  const list = els['sidebar-list'];

  // Filter conversations by search query
  const query = state.sidebarSearch.toLowerCase().trim();
  const filtered = query
    ? state.conversations.filter(c => (c.title || '').toLowerCase().includes(query))
    : state.conversations;

  if (filtered.length === 0) {
    list.innerHTML = '<div class="sidebar-empty">' + (query ? 'No matching conversations' : 'No conversations yet') + '</div>';
    return;
  }

  let html = '';
  const now = new Date();
  const today = now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = yesterday.toDateString();

  const groups = { Today: [], Yesterday: [], Older: [] };

  for (const c of filtered) {
    const d = new Date(c.updated_at || c.created_at);
    const dStr = d.toDateString();
    if (dStr === today) groups.Today.push(c);
    else if (dStr === yesterdayStr) groups.Yesterday.push(c);
    else groups.Older.push(c);
  }

  for (const [label, convs] of Object.entries(groups)) {
    if (convs.length === 0) continue;
    html += '<div class="sidebar-group-label">' + label + '</div>';
    for (const c of convs) {
      const active = c.id === state.currentId ? ' active' : '';
      const deleteConfirm = "'deleteConversation('" + c.id + "', event)'";
      html += '<div class="sidebar-conv' + active + '" onclick="selectConversation(\'' + c.id + '\')">';
      html += '<span class="conv-indicator">&#9679;</span>';
      html += '<div class="conv-info">';
      html += '<div class="conv-title">' + esc(c.title || 'New conversation') + '</div>';
      html += '<div class="conv-meta">' + c.msg_count + ' msg &middot; ' + (c.model || 'meta-model') + '</div>';
      html += '</div>';
      html += '<div class="conv-actions">';
      html += '<button class="conv-action conv-rename" onclick="renameConversation(\'' + c.id + '\', event)" title="Rename">&#9998;</button>';
      html += '<button class="conv-action conv-copy" onclick="copyConversation(\'' + c.id + '\', event)" title="Copy conversation">&#128203;</button>';
      html += '<button class="conv-action conv-del" onclick="deleteConversation(\'' + c.id + '\', event)" title="Delete">&#10005;</button>';
      html += '</div>';
      html += '</div>';
    }
  }

  list.innerHTML = html;
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

/* ── Model Loading ────────────────────────────────────────── */
async function loadModels() {
  // Always show meta-model option first (even if API fails)
  els['model-select'].innerHTML = '';
  const metaOption = document.createElement('option');
  metaOption.value = 'meta-model';
  metaOption.textContent = 'meta-model (auto)';
  els['model-select'].appendChild(metaOption);

  try {
    const res = await fetch('/v1/models');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const models = data.data || [];

    if (models.length > 1) {
      const optgroup = document.createElement('optgroup');
      optgroup.label = 'Specific models';
      const seen = new Set();
      for (const m of models) {
        if (m.id === 'meta-model' || seen.has(m.id)) continue;
        seen.add(m.id);
        const option = document.createElement('option');
        option.value = m.id;
        option.textContent = m.id + (m.status === 'cooldown' ? ' \u26A0\uFE0F (cooldown)' : '');
        optgroup.appendChild(option);
      }
      if (optgroup.children.length > 0) {
        els['model-select'].appendChild(optgroup);
      }
    }

    els['model-select'].value = state.model;
  } catch (e) {
    console.error('Failed to load models:', e);
  }
}

/* ── Markdown Rendering ──────────────────────────────────── */
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
      if (line.includes('</pre>')) {
        inPre = false;
      } else {
        result += '\n';
      }
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

/* ── Copy Code ────────────────────────────────────────────── */
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

/* ── Message Rendering ────────────────────────────────────── */
function renderMessages() {
  els['empty-state'].style.display = state.messages.length === 0 ? 'flex' : 'none';
  const existing = els.messages.querySelectorAll('.message');
  for (const el of existing) el.remove();
  for (const msg of state.messages) {
    appendMessageBubble(msg);
  }
  scrollToBottom();
}

function appendMessageBubble(msg) {
  const div = document.createElement('div');
  div.className = 'message ' + (msg.role === 'user' ? 'user' : 'assistant') + (msg.streaming ? ' streaming' : '');
  if (msg.error) div.classList.add('error');

  const label = document.createElement('div');
  label.className = 'label';
  if (msg.role === 'user') {
    label.textContent = 'You';
  } else {
    label.textContent = 'Assistant' + (msg.provider ? ' \u00B7 ' + msg.provider + ' / ' + msg.actualModel : '');
  }
  div.appendChild(label);

  const contentWrap = document.createElement('div');
  contentWrap.className = 'msg-content-wrap';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  if (msg.content) {
    bubble.innerHTML = renderMarkdown(msg.content);
  }
  contentWrap.appendChild(bubble);

  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'msg-actions';

  const copyBtn = document.createElement('button');
  copyBtn.className = 'msg-action';
  copyBtn.textContent = '\u{1F4CB}';
  copyBtn.title = 'Copy message';
  copyBtn.onclick = (e) => {
    e.stopPropagation();
    const text = msg.content;
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.textContent = 'Copied!';
      setTimeout(() => { copyBtn.textContent = '\u{1F4CB}'; }, 2000);
    }).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      copyBtn.textContent = 'Copied!';
      setTimeout(() => { copyBtn.textContent = '\u{1F4CB}'; }, 2000);
    });
  };
  actionsDiv.appendChild(copyBtn);

  if (!msg.streaming) {
    if (msg.role === 'user') {
      const editBtn = document.createElement('button');
      editBtn.className = 'msg-action';
      editBtn.textContent = '\u270F';
      editBtn.title = 'Edit message';
      editBtn.onclick = (e) => { e.stopPropagation(); editMessage(msg); };
      actionsDiv.appendChild(editBtn);
    }
    const delBtn = document.createElement('button');
    delBtn.className = 'msg-action msg-action-del';
    delBtn.textContent = '\u2716';
    delBtn.title = 'Delete message';
    delBtn.onclick = (e) => { e.stopPropagation(); deleteMessage(msg); };
    actionsDiv.appendChild(delBtn);
    if (msg.role === 'assistant' && state.messages.indexOf(msg) === state.messages.length - 1) {
      const regenBtn = document.createElement('button');
      regenBtn.className = 'msg-action msg-action-regen';
      regenBtn.textContent = '\u21BB';
      regenBtn.title = 'Regenerate response';
      regenBtn.onclick = (e) => { e.stopPropagation(); regenerateResponse(); };
      actionsDiv.appendChild(regenBtn);
    }
  }

  contentWrap.appendChild(actionsDiv);

  div.appendChild(contentWrap);
  els.messages.appendChild(div);
  scrollToBottom();
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

/* ── Sending Messages ─────────────────────────────────────── */
async function sendMessage() {
  const text = els.input.value.trim();
  if (!text || state.streaming) return;

  // Ensure we have a conversation
  if (!state.currentId) {
    try {
      const result = await getStore().create({ model: state.model });
      state.currentId = result.id;
      await loadConversations();
    } catch (e) {
      showToast('Failed to create conversation: ' + e.message, 'error');
      return;
    }
  }

  // Add user message
  state.messages.push({ role: 'user', content: text });
  els.input.value = '';
  autoResizeInput();
  renderMessages();

  await performStreamingSend();
}

async function performStreamingSend() {
  // Add placeholder assistant message
  const assistantMsg = { role: 'assistant', content: '', streaming: true };
  state.messages.push(assistantMsg);
  appendMessageBubble(assistantMsg);

  // UI state
  state.streaming = true;
  state.abortController = new AbortController();
  els['btn-send'].classList.add('hidden');
  els['btn-stop'].classList.remove('hidden');
  els.input.disabled = true;

  try {
    const body = {
      model: state.model,
      messages: state.messages.filter(m => m.role !== 'system' && !(m.streaming && !m.content)).map(m => ({
        role: m.role === 'error' ? 'assistant' : m.role,
        content: m.content,
      })),
      stream: true,
    };

    const res = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: state.abortController.signal,
    });

    if (!res.ok) {
      let detail = 'HTTP ' + res.status;
      try { const err = await res.json(); detail = err.detail || detail; } catch (_) {}
      throw new Error(detail);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') continue;
        try {
          const parsed = JSON.parse(raw);
          const delta = parsed.choices?.[0]?.delta?.content;
          const provider = parsed.provider;
          const model = parsed.model;

          const lastMsg = state.messages[state.messages.length - 1];
          if (!lastMsg || !lastMsg.streaming) continue;

          if (provider) {
            lastMsg.provider = provider;
            lastMsg.actualModel = model;
          }

          if (delta) {
            lastMsg.content += delta;
          }

          if (delta || provider) {
            const bubbles = els.messages.querySelectorAll('.message.assistant');
            const lastBubble = bubbles[bubbles.length - 1];
            if (lastBubble) {
              const labelEl = lastBubble.querySelector('.label');
              if (labelEl) {
                labelEl.textContent = 'Assistant' + (lastMsg.provider ? ' \u00B7 ' + lastMsg.provider + ' / ' + lastMsg.actualModel : '');
              }
              const bubbleEl = lastBubble.querySelector('.bubble');
              if (bubbleEl && delta) {
                bubbleEl.innerHTML = renderMarkdown(lastMsg.content);
              }
              scrollToBottom();
            }
          }
        } catch (_) {}
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      // User stopped, save whatever we have
      const lastMsg = state.messages[state.messages.length - 1];
      if (lastMsg) lastMsg.streaming = false;
      await saveCurrentConversation();
      return;
    }
    const lastMsg = state.messages[state.messages.length - 1];
    if (lastMsg && lastMsg.streaming) {
      lastMsg.error = true;
      lastMsg.content = 'Error: ' + e.message;
      lastMsg.streaming = false;
      const bubbles = els.messages.querySelectorAll('.message.assistant');
      const lastBubble = bubbles[bubbles.length - 1];
      if (lastBubble) {
        lastBubble.classList.add('error');
        lastBubble.classList.remove('streaming');
        const bubbleEl = lastBubble.querySelector('.bubble');
        if (bubbleEl) bubbleEl.textContent = 'Error: ' + e.message;
      }
    }
  } finally {
    const lastMsg = state.messages[state.messages.length - 1];
    if (lastMsg) lastMsg.streaming = false;
    state.streaming = false;
    state.abortController = null;
    els['btn-send'].classList.remove('hidden');
    els['btn-stop'].classList.add('hidden');
    els.input.disabled = false;
    els.input.focus();
    const bubbles = els.messages.querySelectorAll('.message.assistant');
    const lastBubble = bubbles[bubbles.length - 1];
    if (lastBubble) {
      lastBubble.classList.remove('streaming');
      const actionsDiv = lastBubble.querySelector('.msg-actions');
      if (actionsDiv) {
        if (!actionsDiv.querySelector('.msg-action-del')) {
          const delBtn = document.createElement('button');
          delBtn.className = 'msg-action msg-action-del';
          delBtn.textContent = '\u2716';
          delBtn.title = 'Delete message';
          delBtn.onclick = (e) => { e.stopPropagation(); deleteMessage(lastMsg); };
          actionsDiv.appendChild(delBtn);
        }
        if (!actionsDiv.querySelector('.msg-action-regen')) {
          const regenBtn = document.createElement('button');
          regenBtn.className = 'msg-action msg-action-regen';
          regenBtn.textContent = '\u21BB';
          regenBtn.title = 'Regenerate response';
          regenBtn.onclick = (e) => { e.stopPropagation(); regenerateResponse(); };
          actionsDiv.appendChild(regenBtn);
        }
      }
    }

    // Save after every response
    await saveCurrentConversation();
  }
}

function stopStreaming() {
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
  el.style.cssText = 'padding:10px 16px;border-radius:8px;color:#fff;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,0.4);animation:slideIn 0.2s ease;max-width:400px;background:' + (type === 'error' ? '#da3633' : '#238636') + ';';
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

  els['storage-mode'].value = state.storageMode;
  setupStorageModeListener();

  els['btn-sidebar'].addEventListener('click', toggleSidebar);
  els['sidebar-overlay'].addEventListener('click', toggleSidebar);
  els['btn-sidebar-new'].addEventListener('click', createNewConversation);

  els['sidebar-search'].addEventListener('input', () => {
    state.sidebarSearch = els['sidebar-search'].value;
    renderSidebar();
  });

  els['model-select'].addEventListener('change', () => {
    state.model = els['model-select'].value;
    els['empty-model'].textContent = state.model;
  });

  els.input.addEventListener('input', autoResizeInput);
  els.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  els['btn-send'].addEventListener('click', sendMessage);
  els['btn-stop'].addEventListener('click', stopStreaming);
  els['btn-new'].addEventListener('click', async () => {
    await createNewConversation();
  });

  applyTheme(state.theme);
  loadModels();
  loadConversations();
  els.input.focus();
}

init();
