'use strict';

/* ── State ────────────────────────────────────────────────────────────────── */
const state = {
  sessions: [],
  currentSession: null,
  activeQueryId: null,
  runningJobId: null,
  sseSource: null,
  cacheEntries: [],
  contacts: [],
  contactsDismissed: [],
  contactsFilter: '',
  showDismissedContacts: false,
  theme: 'auto', // 'auto' | 'light' | 'dark' | 'tactical'
  drawers: {
    left: { open: false, pinned: false, activeTab: 'sessions' },
    right: { open: false, pinned: false, activeTab: 'contacts' }
  }
};

/* ── API ──────────────────────────────────────────────────────────────────── */
const API = '/api/v1';
async function api(method, path, body) {
  const res = await fetch(API + path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}
const apiGet   = p      => api('GET',    p);
const apiPost  = (p, b) => api('POST',   p, b);
const apiPut   = (p, b) => api('PUT',    p, b);
const apiDel   = p      => api('DELETE', p);
const apiPatch = (p, b) => api('PATCH',  p, b);

/* ── Notifications ────────────────────────────────────────────────────────── */
function notify(msg, type = 'info', ms = 3500) {
  const el = document.createElement('div');
  el.className = `notif ${type}`;
  el.innerHTML = `<div class="notif-dot"></div><span>${esc(msg)}</span>`;
  document.getElementById('notifications').appendChild(el);
  setTimeout(() => el.remove(), ms);
}

/* ── Theme ────────────────────────────────────────────────────────────────── */
function applyTheme(t) {
  state.theme = t;
  const html = document.documentElement;
  html.setAttribute('data-theme', t);
  const isDark = t === 'dark' || t === 'tactical' || (t === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  // Update three-theme selector
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === t);
  });

  localStorage.setItem('osint-theme', t);
  if (state.contacts.length) renderGraph();
}

// Three-theme selector
document.querySelectorAll('.theme-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    applyTheme(btn.dataset.theme);
  });
});

/* ── Drawer Management ─────────────────────────────────────────────────────── */
function initDrawers() {
  // Load drawer state from localStorage
  const savedDrawers = localStorage.getItem('osint-drawers');
  if (savedDrawers) {
    state.drawers = JSON.parse(savedDrawers);
  }

  // Set up left drawer
  setupDrawer('left');
  // Set up right drawer
  setupDrawer('right');

  // Apply initial states
  applyDrawerState('left');
  applyDrawerState('right');

  // Edge trigger hover effects
  document.getElementById('left-edge-trigger').addEventListener('mouseenter', () => {
    if (!state.drawers.left.open && !state.drawers.left.pinned) {
      toggleDrawer('left', true);
    }
  });
  document.getElementById('right-edge-trigger').addEventListener('mouseenter', () => {
    if (!state.drawers.right.open && !state.drawers.right.pinned) {
      toggleDrawer('right', true);
    }
  });

  // Edge trigger click
  document.getElementById('left-edge-trigger').addEventListener('click', () => {
    toggleDrawer('left', !state.drawers.left.open);
  });
  document.getElementById('right-edge-trigger').addEventListener('click', () => {
    toggleDrawer('right', !state.drawers.right.open);
  });

  // Close drawer on overlay click
  document.getElementById('drawer-overlay').addEventListener('click', () => {
    if (state.drawers.left.open && !state.drawers.left.pinned) toggleDrawer('left', false);
    if (state.drawers.right.open && !state.drawers.right.pinned) toggleDrawer('right', false);
  });
}

function setupDrawer(side) {
  const drawer = document.getElementById(`${side}-drawer`);
  const pinBtn = document.getElementById(`${side}-pin-btn`);
  const closeBtn = document.getElementById(`${side}-close-btn`);

  // Pin button
  pinBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    pinDrawer(side, !state.drawers[side].pinned);
  });

  // Close button
  closeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleDrawer(side, false);
  });

  // Remember active tab for right drawer
  if (side === 'right') {
    drawer.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        state.drawers.right.activeTab = btn.dataset.tab;
        saveDrawerState();
      });
    });
  }
}

function toggleDrawer(side, open) {
  state.drawers[side].open = open;
  applyDrawerState(side);
  saveDrawerState();
}

function pinDrawer(side, pinned) {
  state.drawers[side].pinned = pinned;
  state.drawers[side].open = pinned || state.drawers[side].open;
  applyDrawerState(side);
  saveDrawerState();
}

function applyDrawerState(side) {
  const drawer = document.getElementById(`${side}-drawer`);
  const pinBtn = document.getElementById(`${side}-pin-btn`);
  const edgeTrigger = document.getElementById(`${side}-edge-trigger`);
  const overlay = document.getElementById('drawer-overlay');
  
  const { open, pinned } = state.drawers[side];
  
  // Update drawer classes
  drawer.classList.toggle('open', open || pinned);
  drawer.classList.toggle('pinned', pinned);
  
  // Update pin button
  pinBtn.classList.toggle('pinned', pinned);
  
  // Update edge trigger visibility
  edgeTrigger.style.opacity = (open || pinned) ? '0' : '';
  
  // Update overlay
  const anyOpen = (state.drawers.left.open && !state.drawers.left.pinned) ||
                  (state.drawers.right.open && !state.drawers.right.pinned);
  overlay.classList.toggle('visible', anyOpen);
  
  // Update edge badges
  updateEdgeBadges();
  
  // Restore active tab for right drawer
  if (side === 'right' && (open || pinned)) {
    const activeTab = state.drawers.right.activeTab || 'contacts';
    drawer.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === activeTab);
    });
    drawer.querySelectorAll('.tab-pane').forEach(pane => {
      pane.classList.toggle('active', pane.id === `${activeTab}-tab`);
    });
    if (activeTab === 'contacts' && state.currentSession) renderGraph();
  }
}

function updateEdgeBadges() {
  const leftBadge = document.getElementById('left-edge-badge');
  const rightBadge = document.getElementById('right-edge-badge');
  
  leftBadge.textContent = state.sessions.length;
  leftBadge.classList.toggle('hidden', state.sessions.length === 0);
  
  rightBadge.textContent = state.contacts.length;
  rightBadge.classList.toggle('hidden', state.contacts.length === 0);
  rightBadge.classList.toggle('warning', state.contacts.length > 20);
}

function saveDrawerState() {
  localStorage.setItem('osint-drawers', JSON.stringify(state.drawers));
}

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;');
}
function fmtAge(iso) {
  if (!iso) return '—';
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60)    return `${Math.round(s)}s ago`;
  if (s < 3600)  return `${Math.round(s/60)}m ago`;
  if (s < 86400) return `${Math.round(s/3600)}h ago`;
  return `${Math.round(s/86400)}d ago`;
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/* ── Sessions Sidebar ─────────────────────────────────────────────────────── */
function renderSessionList() {
  const list = document.getElementById('session-list');
  if (!state.sessions.length) {
    list.innerHTML = '<div class="sidebar-empty">No sessions yet.<br>Create one to start an investigation.</div>';
    return;
  }
  list.innerHTML = state.sessions.map(s => `
    <div class="session-item ${state.currentSession?.session_id === s.session_id ? 'active' : ''}"
         onclick="loadSession('${s.session_id}')">
      <div class="session-item-icon">🔍</div>
      <div class="session-info">
        <div class="session-name">${esc(s.name)}</div>
        <div class="session-meta">${s.target_count} target${s.target_count!==1?'s':''} · ${s.query_count} quer${s.query_count!==1?'ies':'y'} · ${fmtAge(s.updated_at)}</div>
      </div>
      <button class="session-del" onclick="event.stopPropagation();deleteSession('${s.session_id}')" title="Delete">×</button>
    </div>
  `).join('');
}

async function refreshSessionList() {
  try {
    const data = await apiGet('/sessions');
    state.sessions = data.sessions;
    renderSessionList();
  } catch (e) { notify(`Could not load sessions: ${e.message}`, 'error'); }
}

/* ── Load Session ─────────────────────────────────────────────────────────── */
async function loadSession(id) {
  try {
    const session = await apiGet(`/sessions/${id}`);
    state.currentSession = session;
    state.activeQueryId = null;
    showSessionWorkspace(session);
    renderSessionList();
    await loadCacheStatus(); // Also refreshes target chip status
    await loadContacts();
    await loadMedia();
    await loadTimeline();
  } catch (e) { notify(`Failed to load session: ${e.message}`, 'error'); }
}

function showSessionWorkspace(session) {
  document.getElementById('empty-state').classList.add('hidden');
  const ws = document.getElementById('session-workspace');
  ws.classList.add('visible');
  document.getElementById('session-title').textContent = session.name;

  // Need to ensure target chips render with correct cache state if available
  renderTargetChips(session);
  renderHistory(session);

  // Auto-open left drawer if not pinned or open
  if (!state.drawers.left.open && !state.drawers.left.pinned) {
    toggleDrawer('left', true);
  }

  if (session.query_history?.length) {
    const latest = session.query_history[session.query_history.length - 1];
    showReport(latest);
    state.activeQueryId = latest.query_id;
    renderHistory(session);
  } else {
    // If there is no history, completely wipe the UI so ghost data doesn't bleed over
    clearWorkspace();
  }
}

function hideAllViews() {
  document.getElementById('progress-view').classList.remove('visible');
  document.getElementById('report-view').classList.remove('visible'); // FIX: previously .remove('active')
  document.getElementById('timeline-view').classList.remove('visible');
  
  // Select Report tab as active by default visually
  document.querySelectorAll('[data-center-tab]').forEach(b => b.classList.remove('active'));
  document.querySelector('[data-center-tab="report"]').classList.add('active');
}

function clearWorkspace() {
  hideAllViews();
  // Show report view but with empty state
  document.getElementById('report-view').classList.add('visible');
  
  document.getElementById('report-content').innerHTML = `
    <div style="text-align:center; padding: 60px 20px; color: var(--text-tertiary);">
      <svg style="width:48px;height:48px;margin-bottom:12px;opacity:0.5;stroke:currentColor;" viewBox="0 0 24 24" fill="none" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="M16.5 16.5L21 21"/></svg>
      <h3 style="font-family:var(--font-display);font-size:16px;color:var(--text-secondary);margin-bottom:8px;">No Analysis Run Yet</h3>
      <p style="font-size:12px;">Enter a query in the bar above to start extracting intelligence.</p>
    </div>
  `;
  document.getElementById('report-query-label-text').textContent = 'None';
  
  // Clear timeline
  document.getElementById('heatmap-container').innerHTML = '<div class="timeline-empty">Run an analysis to generate the pattern of life heatmap.</div>';
  document.getElementById('chronological-container').innerHTML = '<div class="timeline-empty">Run an analysis to generate the historical timeline.</div>';
  
  // Clear Right Panel
  document.getElementById('contacts-list').innerHTML = `
    <div class="contacts-empty" id="contacts-empty">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="1.5" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      No contacts discovered yet. Run an analysis to extract network contacts.
    </div>`;
  const badge = document.getElementById('contacts-badge');
  if (badge) badge.style.display = 'none';
  
  document.getElementById('graph-empty').style.display = 'flex';
  const container = document.getElementById('graph-container');
  container.querySelectorAll('svg.network-graph').forEach(s => s.remove());
  
  document.getElementById('entities-content').innerHTML = '<div style="color:var(--text-tertiary);text-align:center;padding:32px 16px;font-size:11px;">Run an analysis to extract selectors.</div>';
  document.getElementById('media-grid-content').innerHTML = '<div style="grid-column:1/-1;color:var(--text-tertiary);text-align:center;padding:32px 16px;font-size:11px;">No media files downloaded yet.</div>';
}

function setQueryBarDisabled(disabled) {
  document.getElementById('query-input').disabled = disabled;
  document.getElementById('fetch-count-input').disabled = disabled;
  document.getElementById('force-refresh-check').disabled = disabled;
}

/* ── Target Chips ─────────────────────────────────────────────────────────── */
function renderTargetChips(session) {
  const container = document.getElementById('target-chips');
  const form = document.getElementById('add-target-form');
  container.querySelectorAll('.target-chip').forEach(c => c.remove());

  for (const [platform, usernames] of Object.entries(session.platforms || {})) {
    for (const username of usernames) {
      const entry = state.cacheEntries.find(e => e.platform === platform && e.username === username);
      const dotClass = entry ? (entry.is_fresh ? 'fresh' : 'stale') : 'absent';
      const title = entry ? (entry.is_fresh ? `Fresh · ${entry.post_count} posts` : `Stale (${fmtAge(entry.cached_at)})`) : 'Not cached';
      const chip = document.createElement('div');
      chip.className = 'target-chip';
      chip.title = title;
      chip.innerHTML = `
        <div class="chip-dot ${dotClass}"></div>
        <span class="chip-platform">${esc(platform)}</span>
        <span>${esc(username)}</span>
        <button class="chip-remove" onclick="removeTarget('${esc(platform)}','${esc(username)}')">×</button>
      `;
      container.insertBefore(chip, form);
    }
  }
}

async function removeTarget(platform, username) {
  const s = state.currentSession;
  if (!s) return;
  const updated = {};
  for (const [p, users] of Object.entries(s.platforms || {})) {
    const rem = users.filter(u => !(p===platform && u===username));
    if (rem.length) updated[p] = rem;
  }
  if (!Object.keys(updated).length) { notify('Cannot remove the last target.', 'info'); return; }
  try {
    await apiPut(`/sessions/${s.session_id}/targets`, { platforms: updated });
    s.platforms = updated;
    renderTargetChips(s);
    notify(`Removed ${platform}/${username}`, 'info', 2000);
  } catch (e) { notify(`Remove failed: ${e.message}`, 'error'); }
}

document.getElementById('add-target-form').addEventListener('submit', async () => {
  const platform = document.getElementById('add-platform-select').value;
  const username = document.getElementById('add-username-input').value.trim().replace(/^@/,'');
  if (!username || !state.currentSession) return;
  const s = state.currentSession;
  const updated = JSON.parse(JSON.stringify(s.platforms || {}));
  if (!updated[platform]) updated[platform] = [];
  if (updated[platform].includes(username)) { notify(`Already added`, 'info', 2000); return; }
  updated[platform].push(username);
  try {
    await apiPut(`/sessions/${s.session_id}/targets`, { platforms: updated, fetch_options: s.fetch_options });
    s.platforms = updated;
    document.getElementById('add-username-input').value = '';
    
    // Refresh cache state so the new chip shows accurate color
    await loadCacheStatus();
    renderTargetChips(s);
    notify(`Added ${platform}/${username}`, 'success', 2000);
  } catch (e) { notify(`Failed: ${e.message}`, 'error'); }
});

/* ── Query History ────────────────────────────────────────────────────────── */
function renderHistory(session) {
  const list = document.getElementById('history-list');
  const history = session.query_history || [];
  if (!history.length) {
    list.innerHTML = '<div class="history-empty">No queries yet.</div>';
    return;
  }
  list.innerHTML = [...history].reverse().map(e => `
    <div class="history-item ${state.activeQueryId === e.query_id ? 'active' : ''}"
         onclick="showHistoryEntry('${e.query_id}')">
      <div class="history-query">${esc(e.query)}</div>
      <div class="history-ts">${fmtDate(e.timestamp)}</div>
    </div>
  `).join('');
}

function showHistoryEntry(qid) {
  const s = state.currentSession;
  if (!s) return;
  const entry = s.query_history?.find(e => e.query_id === qid);
  if (!entry) return;
  state.activeQueryId = qid;
  renderHistory(s);
  showReport(entry);
}

/* ── Report & Entities ────────────────────────────────────────────────────── */
function showReport(entry) {
  // Hide progress, ensure report tab is visible
  document.getElementById('progress-view').classList.remove('visible');

  // Automatically switch to report tab if we were watching progress
  document.querySelectorAll('[data-center-tab]').forEach(b => b.classList.remove('active'));
  document.querySelector('[data-center-tab="report"]').classList.add('active');
  document.getElementById('timeline-view').classList.remove('visible');
  document.getElementById('report-view').classList.add('visible');

  document.getElementById('report-query-label-text').textContent = entry.query;

  // Build report content with intel stats
  const intelStats = renderIntelStats(entry.stats);
  const reportHtml = marked.parse(entry.report || '*(no content)*');

  document.getElementById('report-content').innerHTML = '';
  if (intelStats) {
    document.getElementById('report-content').appendChild(intelStats);
  }
  document.getElementById('report-content').innerHTML += reportHtml;

  // Render entities to the right panel
  renderEntities(entry.entities);
}

function renderEntities(entities) {
  const container = document.getElementById('entities-content');
  if (!entities || Object.keys(entities).length === 0) {
    container.innerHTML = '<div style="color:var(--text-tertiary);text-align:center;padding:32px 16px;font-size:11px;">No entities extracted for this query.</div>';
    return;
  }
  
  let html = '';
  let foundAny = false;
  for (const [type, arr] of Object.entries(entities)) {
    if (arr && arr.length > 0) {
      foundAny = true;
      html += `<div class="entity-group"><div class="entity-title">${esc(type)}</div>`;
      arr.forEach(val => {
        html += `<div class="entity-pill">${esc(val)}</div>`;
      });
      html += `</div>`;
    }
  }

  container.innerHTML = foundAny ? html : '<div style="color:var(--text-tertiary);text-align:center;padding:32px 16px;font-size:11px;">No entities extracted for this query.</div>';
}

document.getElementById('btn-copy-report').addEventListener('click', () => {
  const entry = state.currentSession?.query_history?.find(e => e.query_id === state.activeQueryId);
  if (!entry) return;
  navigator.clipboard.writeText(entry.report || '').then(() => notify('Copied', 'success', 2000));
});

// Download MD Client-Side
document.getElementById('btn-download-md').addEventListener('click', () => {
  const entry = state.currentSession?.query_history?.find(e => e.query_id === state.activeQueryId);
  if (!entry || !state.currentSession) return;
  
  const blob = new Blob([entry.report || ''], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  
  const safeName = state.currentSession.name.replace(/[^a-z0-9]/gi, '_').toLowerCase();
  const dateStr = new Date().toISOString().split('T')[0];
  a.download = `osint_report_${safeName}_${dateStr}.md`;
  
  a.click();
  URL.revokeObjectURL(url);
  notify('Markdown downloaded', 'success', 2000);
});

/* ── Analysis ─────────────────────────────────────────────────────────────── */
document.getElementById('run-analysis-btn').addEventListener('click', async () => {
  const session = state.currentSession;
  if (!session) return;
  const query = document.getElementById('query-input').value.trim();
  if (!query) { notify('Enter an analysis query', 'info'); document.getElementById('query-input').focus(); return; }
  const forceRefresh = document.getElementById('force-refresh-check').checked;
  const fetchCount = parseInt(document.getElementById('fetch-count-input').value) || 50;
  const queryType = document.getElementById('query-type-select').value;
  const queryTemplate = document.getElementById('query-template-select').value;

  // Use the query directly - templates now populate the input field
  const finalQuery = query;

  try {
    const fetchOptions = { default_count: fetchCount, targets: session.fetch_options?.targets || {} };
    await apiPut(`/sessions/${session.session_id}/targets`, { platforms: session.platforms, fetch_options: fetchOptions });
    session.fetch_options = fetchOptions;
    const job = await apiPost(`/sessions/${session.session_id}/analyse`, { query: finalQuery, force_refresh: forceRefresh });
    startProgressView(job.job_id, finalQuery);
    collapseQueryBar();

    // Reset form after running
    queryInput.value = '';
    queryTemplateSelect.value = '';
    queryInput.placeholder = 'What are you investigating? e.g. "Identify network connections and travel patterns"';
  } catch (e) {
    if (e.message.includes('already has a running')) { notify('Analysis already running for this session.', 'info'); }
    else { notify(`Failed to start: ${e.message}`, 'error'); }
  }
});

/* ── Query Bar Progressive Disclosure ─────────────────────────────────────── */
const queryBar = document.getElementById('query-bar');
const queryInput = document.getElementById('query-input');
const queryExpanded = document.getElementById('query-expanded');
const queryTemplateSelect = document.getElementById('query-template-select');

function expandQueryBar() {
  queryBar.classList.add('expanded');
}

function collapseQueryBar() {
  queryBar.classList.remove('expanded');
}

queryInput.addEventListener('focus', expandQueryBar);
queryInput.addEventListener('blur', (e) => {
  // Only collapse if:
  // 1. Input is empty and no template is selected
  // 2. Focus is not going to another element within the query bar
  const relatedTarget = e.relatedTarget;
  const isClickingInsideQueryBar = relatedTarget && queryBar.contains(relatedTarget);

  if (!queryInput.value.trim() && !queryTemplateSelect.value && !isClickingInsideQueryBar) {
    setTimeout(collapseQueryBar, 150);
  }
});

queryTemplateSelect.addEventListener('change', () => {
  if (queryTemplateSelect.value) {
    expandQueryBar();

    // Define template texts
    const templates = {
      'network': 'Analyze network connections and interaction patterns between targets and their contacts',
      'behavior': 'Analyze posting patterns, activity frequency, and behavioral characteristics',
      'sentiment': 'Determine emotional tone, opinions, and sentiment expressed in posts',
      'entities': 'Extract and analyze all entities including people, locations, organizations, and other key identifiers'
    };

    // Populate query input with selected template
    const templateText = templates[queryTemplateSelect.value];
    if (templateText) {
      queryInput.value = templateText;
      // Focus the input so user can edit immediately
      queryInput.focus();
    }
  }
});

// Query type selector - update placeholder and focus
const queryTypeSelect = document.getElementById('query-type-select');
queryTypeSelect.addEventListener('change', () => {
  expandQueryBar();

  const placeholders = {
    'general': 'What are you investigating? e.g. "Identify network connections and travel patterns"',
    'sentiment': 'What sentiment analysis do you need? e.g. "Analyze emotional tone and opinions"',
    'network': 'What network aspects? e.g. "Identify key connectors and interaction patterns"',
    'timeline': 'What temporal patterns? e.g. "Analyze posting schedule and activity patterns"',
    'geolocation': 'What location intelligence? e.g. "Identify travel patterns and geographic references"'
  };

  queryInput.placeholder = placeholders[queryTypeSelect.value] || placeholders['general'];
  queryInput.focus();
});
// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && queryBar.classList.contains('expanded')) {
    collapseQueryBar();
  }
});

/* ── Intel Stat Cards ─────────────────────────────────────────────────────── */
function renderIntelStats(data) {
  if (!data) return;

  const statsContainer = document.createElement('div');
  statsContainer.className = 'intel-stats';

  const stats = [
    { label: 'Posts Analyzed', value: data.posts_count || 0 },
    { label: 'Contacts Found', value: data.contacts_count || state.contacts.length },
    { label: 'Entities Extracted', value: data.entities_count || 0 },
    { label: 'Media Files', value: data.media_count || 0 }
  ];

  statsContainer.innerHTML = stats.map(stat => `
    <div class="intel-stat-card">
      <div class="intel-stat-value">${stat.value}</div>
      <div class="intel-stat-label">${stat.label}</div>
    </div>
  `).join('');

  return statsContainer;
}

function startProgressView(jobId, query) {
  state.runningJobId = jobId;
  
  // Disable query inputs
  document.getElementById('run-analysis-btn').disabled = true;
  setQueryBarDisabled(true);
  
  setStatus('running', 'Running analysis…');
  
  // Show progress view in center panel
  document.querySelectorAll('[data-center-tab]').forEach(b => b.classList.remove('active'));
  document.querySelector('[data-center-tab="report"]').classList.add('active');
  document.getElementById('report-view').classList.remove('visible');
  document.getElementById('timeline-view').classList.remove('visible');
  
  const pv = document.getElementById('progress-view');
  pv.classList.add('visible');
  
  document.getElementById('progress-stage-label').textContent = 'Starting…';
  document.getElementById('progress-log').innerHTML = '';
  appendLog('info', `Query: ${query}`);

  if (state.sseSource) state.sseSource.close();
  const es = new EventSource(`${API}/jobs/${jobId}/stream`);
  state.sseSource = es;

  ['stage','log','status','complete','error'].forEach(t => {
    es.addEventListener(t, e => {
      try { handleJobEvent(t, JSON.parse(e.data), jobId); } catch {}
    });
  });
  es.onerror = () => { es.close(); pollJob(jobId); };
}

function handleJobEvent(type, data, jobId) {
  if (type === 'stage') {
    document.getElementById('progress-stage-label').textContent = data.message || '';
    appendLog('stage', `▶ ${data.message}`);
  } else if (type === 'log' || type === 'status') {
    appendLog('info', data.message);
  } else if (type === 'complete') {
    appendLog('complete', '✓ Analysis complete');
    finishAnalysis(jobId);
  } else if (type === 'error') {
    appendLog('error', `✗ ${data.message}`);
    setStatus('error', 'Error');
    document.getElementById('run-analysis-btn').disabled = false;
    setQueryBarDisabled(false);
    notify(`Analysis error: ${data.message}`, 'error', 6000);
  }
}

function appendLog(cls, msg) {
  const log = document.getElementById('progress-log');
  const line = document.createElement('span');
  line.className = `log-line ${cls}`;
  line.textContent = msg;
  log.appendChild(line);
  log.appendChild(document.createElement('br'));
  log.scrollTop = log.scrollHeight;
}

async function finishAnalysis(jobId) {
  if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }

  // Re-enable inputs
  document.getElementById('run-analysis-btn').disabled = false;
  setQueryBarDisabled(false);

  document.getElementById('force-refresh-check').checked = false;
  setStatus('', 'Ready');

  try {
    const session = await apiGet(`/sessions/${state.currentSession.session_id}`);
    state.currentSession = session;
    renderHistory(session);
    await refreshSessionList();
    if (session.query_history?.length) {
      const latest = session.query_history[session.query_history.length - 1];
      state.activeQueryId = latest.query_id;
      renderHistory(session);
      showReport(latest);
    }

    // Refresh background data
    await loadCacheStatus();
    renderTargetChips(session);
    await loadContacts();
    await loadMedia();
    await loadTimeline();

    // Auto-open right drawer if contacts found
    if (state.contacts.length > 0 && !state.drawers.right.open && !state.drawers.right.pinned) {
      toggleDrawer('right', true);
    }
  } catch (e) { notify(`Could not reload: ${e.message}`, 'error'); }
}

async function pollJob(jobId) {
  const poll = async () => {
    try {
      const job = await apiGet(`/jobs/${jobId}`);
      if (job.status === 'complete') { finishAnalysis(jobId); return; }
      if (job.status === 'error') {
        notify(`Analysis failed: ${job.error}`, 'error', 6000);
        document.getElementById('run-analysis-btn').disabled = false;
        setQueryBarDisabled(false);
        setStatus('error', 'Error');
        return;
      }
      if (job.progress?.message) document.getElementById('progress-stage-label').textContent = job.progress.message;
      setTimeout(poll, 2000);
    } catch { setTimeout(poll, 3000); }
  };
  poll();
}

/* ── Status bar ───────────────────────────────────────────────────────────── */
function setStatus(cls, text) {
  document.getElementById('status-dot').className = `status-dot ${cls}`;
  document.getElementById('status-text').textContent = text;
}

/* ── Session title edit ───────────────────────────────────────────────────── */
const titleEl = document.getElementById('session-title');
titleEl.addEventListener('blur', async () => {
  const name = titleEl.textContent.trim();
  if (!name || !state.currentSession || name === state.currentSession.name) return;
  try {
    await apiPatch(`/sessions/${state.currentSession.session_id}/rename`, { name });
    state.currentSession.name = name;
    await refreshSessionList();
    notify('Renamed', 'success', 2000);
  } catch (e) { titleEl.textContent = state.currentSession.name; notify(`Rename failed: ${e.message}`, 'error'); }
});
titleEl.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); titleEl.blur(); }
  if (e.key === 'Escape') { titleEl.textContent = state.currentSession?.name || ''; titleEl.blur(); }
});

/* ── Delete session ───────────────────────────────────────────────────────── */
document.getElementById('btn-delete-session').addEventListener('click', async () => {
  const s = state.currentSession;
  if (!s || !confirm(`Delete "${s.name}"?`)) return;
  await deleteSession(s.session_id);
});
async function deleteSession(id) {
  try {
    await apiDel(`/sessions/${id}`);
    if (state.currentSession?.session_id === id) {
      state.currentSession = null;
      document.getElementById('session-workspace').classList.remove('visible');
      document.getElementById('empty-state').classList.remove('hidden');
    }
    await refreshSessionList();
    notify('Session deleted', 'info', 2000);
  } catch (e) { notify(`Delete failed: ${e.message}`, 'error'); }
}

/* ── Full Session Export (Markdown) ────────────────────────────────────── */
document.getElementById('btn-export-session').addEventListener('click', () => {
  const s = state.currentSession;
  if (!s) return;

  // 1. Build Header
  let md = `# OSINT Investigation Report: ${s.name}\n`;
  md += `**Date:** ${new Date().toLocaleString()}\n`;
  md += `**Session ID:** \`${s.session_id}\`\n\n`;

  // 2. Targets Section
  md += `## Investigation Targets\n`;
  for (const [platform, users] of Object.entries(s.platforms || {})) {
    md += `- **${platform.toUpperCase()}:** ${users.join(', ')}\n`;
  }
  md += `\n---\n\n`;

  // 3. Analysis History
  md += `## Analysis History\n\n`;
  if (s.query_history && s.query_history.length > 0) {
    s.query_history.forEach((entry, idx) => {
      md += `### Query ${idx + 1}: ${entry.query}\n`;
      md += `*Timestamp: ${new Date(entry.timestamp).toLocaleString()}*\n\n`;
      md += `${entry.report}\n\n`;
      md += `--- \n\n`;
    });
  } else {
    md += `*No analysis queries recorded in this session.*\n\n`;
  }

  // 4. Consolidated Entities
  md += `## Consolidated Intelligence Selectors\n\n`;
  const allEntities = { locations: new Set(), emails: new Set(), phones: new Set(), crypto: new Set(), aliases: new Set() };
  s.query_history.forEach(entry => {
      if (entry.entities) {
          Object.keys(allEntities).forEach(key => {
              if (entry.entities[key]) entry.entities[key].forEach(val => allEntities[key].add(val));
          });
      }
  });

  let hasEntities = false;
  Object.keys(allEntities).forEach(key => {
      if (allEntities[key].size > 0) {
          hasEntities = true;
          md += `### ${key.toUpperCase()}\n`;
          allEntities[key].forEach(val => md += `- \`${val}\` \n`);
          md += `\n`;
      }
  });
  if (!hasEntities) md += `*No specific selectors extracted.*\n\n`;

  // 5. Network Contacts
  md += `## Discovered Network Connections\n\n`;
  if (state.contacts && state.contacts.length > 0) {
    md += `| Platform | Username | Interaction Weight | Types |\n`;
    md += `| :--- | :--- | :--- | :--- |\n`;
    state.contacts.slice(0, 20).forEach(c => {
      md += `| ${c.platform} | ${c.username} | ${c.weight} | ${c.interaction_types.join(', ')} |\n`;
    });
  } else {
    md += `*No network contacts extracted.*\n`;
  }

  // 6. Trigger Download
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  
  const safeName = s.name.replace(/[^a-z0-9]/gi, '_').toLowerCase();
  a.download = `OSINT_REPORT_${safeName}.md`;
  a.click();
  
  URL.revokeObjectURL(url);
  notify('Full Investigation Report Exported (MD)', 'success');
});

/* ── Contacts ─────────────────────────────────────────────────────────────── */
async function loadContacts() {
  const s = state.currentSession;
  if (!s) return;
  try {
    const data = await apiGet(`/sessions/${s.session_id}/contacts`);
    state.contacts = data.contacts || [];
    state.contactsDismissed = data.dismissed || [];
    state.showDismissedContacts = false;
    renderContacts();
    renderGraph();
    const badge = document.getElementById('contacts-badge');
    if (state.contacts.length) {
      badge.textContent = state.contacts.length;
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }
  } catch (e) {
    state.contacts = [];
    renderContacts();
  }
}

document.getElementById('btn-refresh-contacts').addEventListener('click', () => loadContacts());
document.getElementById('btn-toggle-dismissed').addEventListener('click', () => {
  state.showDismissedContacts = !state.showDismissedContacts;
  renderContacts();
});
document.getElementById('contacts-search').addEventListener('input', e => {
  state.contactsFilter = e.target.value.toLowerCase();
  renderContacts();
});

function renderContacts() {
  const list = document.getElementById('contacts-list');
  const toggleBtn = document.getElementById('btn-toggle-dismissed');

  // Show/hide toggle button based on whether there are dismissed contacts
  if (state.contactsDismissed && state.contactsDismissed.length > 0) {
    toggleBtn.style.display = '';
    toggleBtn.title = state.showDismissedContacts ? 'Hide dismissed contacts' : 'Show dismissed contacts';
  } else {
    toggleBtn.style.display = 'none';
  }

  let contacts = state.contacts;
  let dismissedContacts = [];

  // Parse dismissed contacts from "platform/username" format
  if (state.showDismissedContacts && state.contactsDismissed) {
    dismissedContacts = state.contactsDismissed.map(d => {
      const parts = d.split('/');
      if (parts.length === 2) {
        return { platform: parts[0], username: parts[1], isDismissed: true };
      }
      return null;
    }).filter(c => c !== null);
  }

  // Apply filter to both lists
  if (state.contactsFilter) {
    contacts = contacts.filter(c =>
      c.username.toLowerCase().includes(state.contactsFilter) ||
      c.platform.toLowerCase().includes(state.contactsFilter)
    );
    dismissedContacts = dismissedContacts.filter(c =>
      c.username.toLowerCase().includes(state.contactsFilter) ||
      c.platform.toLowerCase().includes(state.contactsFilter)
    );
  }

  // Inject the empty state directly if there are no contacts
  if (!contacts.length && !dismissedContacts.length) {
    list.innerHTML = `
      <div class="contacts-empty" id="contacts-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke-width="1.5" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        ${state.showDismissedContacts ? 'No dismissed contacts found.' : 'No contacts discovered yet. Run an analysis to extract network contacts.'}
      </div>
    `;
    return;
  }

  const maxWeight = Math.max(...contacts.map(c => c.weight), 1);

  let html = '';

  // Render active contacts
  if (contacts.length > 0) {
    if (dismissedContacts.length > 0) {
      html += `<div class="contacts-section-header">Active Contacts (${contacts.length})</div>`;
    }
    html += contacts.map(c => {
      const barW = Math.max(8, Math.round((c.weight / maxWeight) * 100));
      const initials = c.username.slice(0, 2).toUpperCase();
      const itypePills = (c.interaction_types || []).map(t =>
        `<span class="itype-pill ${t}">${esc(t.replace('_',' '))}</span>`
      ).join('');

      return `
        <div class="contact-row" data-username="${esc(c.username)}" data-platform="${esc(c.platform)}">
          <div class="contact-avatar">${esc(initials)}</div>
          <div class="contact-info">
            <div class="contact-name">${esc(c.username)}</div>
            <div class="contact-detail">
              <span class="plat-badge">${esc(c.platform)}</span>
              ${itypePills}
            </div>
          </div>
          <div class="contact-weight">
            <div class="weight-bar-wrap">
              <div class="weight-bar" style="width:${barW}%"></div>
            </div>
            <span class="weight-num">${c.weight}</span>
          </div>
          <div class="contact-actions">
            <button class="contact-action-btn add" title="Add to session"
                    onclick="addContactToSession('${esc(c.platform)}','${esc(c.username)}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
            </button>
            <button class="contact-action-btn dismiss" title="Dismiss"
                    onclick="dismissContact('${esc(c.platform)}','${esc(c.username)}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  // Render dismissed contacts
  if (dismissedContacts.length > 0) {
    html += `<div class="contacts-section-header">Dismissed Contacts (${dismissedContacts.length})</div>`;
    html += dismissedContacts.map(c => {
      const initials = c.username.slice(0, 2).toUpperCase();
      return `
        <div class="contact-row dismissed" data-username="${esc(c.username)}" data-platform="${esc(c.platform)}">
          <div class="contact-avatar">${esc(initials)}</div>
          <div class="contact-info">
            <div class="contact-name">${esc(c.username)}</div>
            <div class="contact-detail">
              <span class="plat-badge">${esc(c.platform)}</span>
              <span class="dismissed-badge">Dismissed</span>
            </div>
          </div>
          <div class="contact-actions">
            <button class="contact-action-btn add" title="Add to session"
                    onclick="addContactToSession('${esc(c.platform)}','${esc(c.username)}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
            </button>
            <button class="contact-action-btn undismiss" title="Restore"
                    onclick="undismissContact('${esc(c.platform)}','${esc(c.username)}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 10h10a5 5 0 0 1 5 5v2a5 5 0 0 1-10 0v-2"/><path d="M7 6l5-5 5 5"/></svg>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  list.innerHTML = html;
}

async function dismissContact(platform, username) {
  const s = state.currentSession;
  if (!s) return;
  try {
    await apiPost(`/sessions/${s.session_id}/contacts/dismiss`, { platform, username });
    notify(`Dismissed ${username}`, 'info', 2000);
    await loadContacts();
    updateEdgeBadges();
  } catch (e) { notify(`Failed: ${e.message}`, 'error'); }
}

async function undismissContact(platform, username) {
  const s = state.currentSession;
  if (!s) return;
  try {
    await apiPost(`/sessions/${s.session_id}/contacts/undismiss`, { platform, username });
    notify(`Restored ${username}`, 'success', 2000);
    await loadContacts();
    renderGraph();
  } catch (e) { notify(`Failed: ${e.message}`, 'error'); }
}

async function addContactToSession(platform, username) {
  const s = state.currentSession;
  if (!s) return;
  const updated = JSON.parse(JSON.stringify(s.platforms || {}));
  if (!updated[platform]) updated[platform] = [];
  if (updated[platform].includes(username)) { notify(`Already in session`, 'info', 2000); return; }
  updated[platform].push(username);
  try {
    await apiPut(`/sessions/${s.session_id}/targets`, { platforms: updated, fetch_options: s.fetch_options });
    s.platforms = updated;
    await loadCacheStatus(); // update UI cache states
    renderTargetChips(s);
    notify(`Added ${platform}/${username} to session`, 'success', 2500);
  } catch (e) { notify(`Failed: ${e.message}`, 'error'); }
}

/* ── Force-directed Graph ──────────────────────────────────────────────────── */
function renderGraph() {
  const container = document.getElementById('graph-container');
  const emptyMsg = document.getElementById('graph-empty');
  
  container.querySelectorAll('svg.network-graph').forEach(s => s.remove());

  const contacts = state.contacts.slice(0, 40); // Cap for performance
  const session = state.currentSession;

  if (!contacts.length || !session) {
    emptyMsg.style.display = 'flex';
    return;
  }
  emptyMsg.style.display = 'none';

  const W = container.clientWidth || 300;
  const H = 220;

  // Build nodes: source targets + top contacts
  const sourceNodes = [];
  for (const [platform, users] of Object.entries(session.platforms || {})) {
    for (const u of users) sourceNodes.push({ id: `${platform}/${u}`, label: u, type: 'source' });
  }

  const contactNodes = contacts.map(c => ({
    id: `${c.platform}/${c.username}`,
    label: c.username,
    type: 'contact',
    weight: c.weight,
  }));

  // Deduplicate
  const allIds = new Set(sourceNodes.map(n => n.id));
  const filteredContacts = contactNodes.filter(n => !allIds.has(n.id));
  const nodes = [...sourceNodes, ...filteredContacts];

  // Edges: source -> contact (based on contacts data)
  const links = [];
  contacts.forEach(c => {
    const cId = `${c.platform}/${c.username}`;
    sourceNodes.forEach(s => {
      if (s.id.split('/')[0] === c.platform) {
        links.push({ source: s.id, target: cId, weight: c.weight });
      }
    });
  });

  const validIds = new Set(nodes.map(n => n.id));
  const validLinks = links.filter(l => validIds.has(l.source) && validIds.has(l.target));

  const svg = d3.select(container).append('svg')
    .attr('class', 'network-graph')
    .attr('width', W)
    .attr('height', H);

  const cssVars = getComputedStyle(document.documentElement);
  const accentColor   = cssVars.getPropertyValue('--accent').trim();
  const borderMedium  = cssVars.getPropertyValue('--border-medium').trim();
  const bgRaised      = cssVars.getPropertyValue('--bg-raised').trim();
  const bgSurface     = cssVars.getPropertyValue('--bg-surface').trim();
  const textSecondary = cssVars.getPropertyValue('--text-secondary').trim();

  const maxW = Math.max(...contacts.map(c => c.weight), 1);

  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(validLinks).id(d => d.id).distance(55).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-90))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(16));

  const link = svg.append('g').selectAll('line')
    .data(validLinks).join('line')
    .attr('class', 'graph-link')
    .style('stroke-width', d => 0.6 + (d.weight / maxW) * 1.8);

  const node = svg.append('g').selectAll('g')
    .data(nodes).join('g')
    .attr('class', d => d.type === 'source' ? 'node-source' : 'node-contact')
    .call(d3.drag()
      .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
      .on('end', (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append('circle')
    .attr('r', d => d.type === 'source' ? 9 : 5 + (d.weight || 1) / maxW * 5)
    .style('fill', d => d.type === 'source' ? accentColor : bgRaised)
    .style('stroke', d => d.type === 'source' ? bgSurface : borderMedium)
    .style('stroke-width', d => d.type === 'source' ? '2.5px' : '1.5px');

  node.append('text')
    .attr('class', 'node-label')
    .attr('dy', d => -(( d.type === 'source' ? 9 : 8) + 3))
    .attr('text-anchor', 'middle')
    .style('fill', textSecondary)
    .text(d => d.label.length > 12 ? d.label.slice(0,11) + '…' : d.label);

  sim.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${Math.max(14,Math.min(W-14,d.x))},${Math.max(14,Math.min(H-14,d.y))})`);
  });
}

/* ── Timeline D3 Charts ────────────────────────────────────────────────────── */
async function loadTimeline() {
  const s = state.currentSession;
  if (!s) return;
  const chronoContainer = document.getElementById('chronological-container');
  const heatmapContainer = document.getElementById('heatmap-container');
  
  try {
    const res = await apiGet(`/sessions/${s.session_id}/timeline`);
    if (!res.events || !res.events.length) {
      chronoContainer.innerHTML = '<div class="timeline-empty">No timestamp data found. Run an analysis.</div>';
      heatmapContainer.innerHTML = '<div class="timeline-empty">No timestamp data found. Run an analysis.</div>';
      return;
    }

    renderChronologicalChart(res.events, chronoContainer);
    renderHeatmap(res.events, heatmapContainer);

  } catch (e) {
    chronoContainer.innerHTML = `<div style="color:var(--red);font-size:11px;">Error loading timeline: ${esc(e.message)}</div>`;
    heatmapContainer.innerHTML = '';
  }
}

function renderChronologicalChart(events, container) {
  container.innerHTML = '';
  
  // Parse dates and group by YYYY-MM-DD
  const parseDate = d3.timeParse("%Y-%m-%dT%H:%M:%S.%LZ");
  const formatDate = d3.timeFormat("%Y-%m-%d");
  
  const dailyCounts = {};
  events.forEach(e => {
    // Basic fix for string formats
    const dt = new Date(e.timestamp);
    const dayStr = formatDate(dt);
    dailyCounts[dayStr] = (dailyCounts[dayStr] || 0) + 1;
  });

  const data = Object.keys(dailyCounts).map(d => ({
    date: d3.timeParse("%Y-%m-%d")(d),
    count: dailyCounts[d]
  })).sort((a,b) => a.date - b.date);

  const containerWidth = container.clientWidth || 600;
  const height = 180;
  const margin = {top: 10, right: 20, bottom: 20, left: 30};
  const width = containerWidth - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  const svg = d3.select(container).append("svg")
      .attr("width", containerWidth)
      .attr("height", height)
    .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

  // X scale
  const x = d3.scaleTime()
    .domain(d3.extent(data, d => d.date))
    .range([0, width]);

  // Y scale
  const y = d3.scaleLinear()
    .domain([0, d3.max(data, d => d.count)])
    .range([innerHeight, 0]);

  // Axes
  svg.append("g")
    .attr("class", "axis")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(d3.axisBottom(x).ticks(6));

  svg.append("g")
    .attr("class", "axis")
    .call(d3.axisLeft(y).ticks(4).tickFormat(d3.format("d")));

  // Tooltip
  const tooltip = d3.select("#d3-tooltip");

  // Bars
  const barWidth = Math.max(2, width / data.length - 1);
  
  svg.selectAll(".bar")
    .data(data)
    .enter().append("rect")
      .attr("class", "bar")
      .attr("x", d => x(d.date) - barWidth/2)
      .attr("y", d => y(d.count))
      .attr("width", barWidth)
      .attr("height", d => innerHeight - y(d.count))
      .on("mouseover", (event, d) => {
         tooltip.transition().duration(100).style("opacity", 1);
         tooltip.html(`<strong>${formatDate(d.date)}</strong><br/>${d.count} posts`)
           .style("left", (event.pageX - 30) + "px")
           .style("top", (event.pageY - 40) + "px");
      })
      .on("mouseout", () => {
         tooltip.transition().duration(200).style("opacity", 0);
      });
}

function renderHeatmap(events, container) {
  // Initialize 7 days x 24 hours matrix
  const matrix = Array.from({length: 7}, () => Array(24).fill(0));
  let max = 1;
  
  events.forEach(e => {
    const dt = new Date(e.timestamp);
    // getDay() is 0 (Sun) to 6 (Sat)
    matrix[dt.getUTCDay()][dt.getUTCHours()]++;
    if(matrix[dt.getUTCDay()][dt.getUTCHours()] > max) max = matrix[dt.getUTCDay()][dt.getUTCHours()];
  });

  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  let html = `<div class="heatmap-grid">`;
  // Header row for hours
  html += `<div style="grid-column: 2 / 26; display:flex; justify-content:space-between; font-size:9px; color:var(--text-tertiary); margin-bottom:4px;"><span>00:00 UTC</span><span>12:00</span><span>23:00</span></div>`;
  
  for(let d=0; d<7; d++) {
    html += `<div class="heatmap-label">${days[d]}</div>`;
    for(let h=0; h<24; h++) {
      const val = matrix[d][h];
      const opacity = val === 0 ? 0.05 : Math.max(0.2, val / max); 
      html += `<div class="heatmap-cell" style="background: rgba(37,99,235, ${opacity})" title="${days[d]} ${String(h).padStart(2,'0')}:00 UTC&#10;${val} posts"></div>`;
    }
  }
  html += `</div>`;
  container.innerHTML = html;
}

/* ── Media Gallery ─────────────────────────────────────────────────────────── */
async function loadMedia() {
  const s = state.currentSession;
  if (!s) return;
  const container = document.getElementById('media-grid-content');
  
  try {
    const res = await apiGet(`/sessions/${s.session_id}/media`);
    if (!res.media || !res.media.length) {
      container.innerHTML = '<div style="grid-column:1/-1;color:var(--text-tertiary);text-align:center;padding:32px 16px;font-size:11px;">No local media files downloaded.</div>';
      return;
    }

    container.innerHTML = res.media.map(m => {
      const imgUrl = `/api/v1/sessions/${s.session_id}/media/file?path=${encodeURIComponent(m.path)}`;
      return `
        <div class="media-item-container">
          <a href="${esc(imgUrl)}" target="_blank">
            <img src="${esc(imgUrl)}" class="media-item" loading="lazy" alt="Target media">
          </a>
          <div class="media-analysis-overlay">${esc(m.analysis || 'No vision analysis available')}</div>
        </div>
      `;
    }).join('');
    
  } catch (e) {
    container.innerHTML = `<div style="grid-column:1/-1;color:var(--red);font-size:11px;">Error loading media: ${esc(e.message)}</div>`;
  }
}

/* ── Cache Modal (Top Level) ──────────────────────────────────────────────── */
async function loadCacheStatus() {
  try {
    const data = await apiGet('/cache');
    state.cacheEntries = data.entries;
  } catch { state.cacheEntries = []; }
}

document.getElementById('btn-cache-mgr').addEventListener('click', async () => {
  await loadCacheStatus();
  openCacheModal();
});

function openCacheModal() {
  const modal = document.getElementById('modal');
  
  function render() {
    const entries = state.cacheEntries;
    
    modal.innerHTML = `
      <div class="modal-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
        Cache Manager
      </div>
      <div style="font-size:12px; color:var(--text-secondary); margin-bottom:16px;">
        View and selectively purge cached JSON responses. Media files and PDF reports are purged via 'Purge All'.
      </div>
      <div style="max-height:300px; overflow-y:auto; border:1px solid var(--border-subtle); border-radius:var(--radius-sm); margin-bottom:16px;">
        <table style="width:100%; border-collapse:collapse;">
          <thead style="background:var(--bg-raised); position:sticky; top:0;">
            <tr>
              <th style="padding:8px; text-align:left; border-bottom:1px solid var(--border-subtle);"><input type="checkbox" id="cache-select-all"></th>
              <th style="padding:8px; text-align:left; border-bottom:1px solid var(--border-subtle); font-size:11px; text-transform:uppercase; color:var(--text-tertiary);">Target</th>
              <th style="padding:8px; text-align:right; border-bottom:1px solid var(--border-subtle); font-size:11px; text-transform:uppercase; color:var(--text-tertiary);">Posts</th>
              <th style="padding:8px; text-align:right; border-bottom:1px solid var(--border-subtle); font-size:11px; text-transform:uppercase; color:var(--text-tertiary);">Age</th>
            </tr>
          </thead>
          <tbody>
            ${entries.length ? entries.map(e => `
              <tr style="border-bottom:1px solid var(--border-subtle);">
                <td style="padding:8px;"><input type="checkbox" class="cache-cb" value="${esc(e.platform)}_${esc(e.username)}"></td>
                <td style="padding:8px; font-size:12px;"><strong>${esc(e.platform)}</strong> / ${esc(e.username)}</td>
                <td style="padding:8px; font-size:12px; text-align:right;">${e.post_count}</td>
                <td style="padding:8px; font-size:12px; text-align:right; color:${e.is_fresh ? 'var(--green)' : 'var(--amber)'}">${e.is_fresh ? 'Fresh' : 'Stale'}</td>
              </tr>
            `).join('') : `<tr><td colspan="4" style="padding:16px; text-align:center; color:var(--text-tertiary); font-size:12px;">Cache is empty.</td></tr>`}
          </tbody>
        </table>
      </div>
      <div class="modal-actions" style="justify-content:space-between;">
        <button class="btn danger" onclick="cachePurgeAll()">Purge Entire Cache (All Targets + Media)</button>
        <div style="display:flex; gap:8px;">
          <button class="btn" onclick="closeModal()">Close</button>
          <button class="btn primary" onclick="cachePurgeSelected()">Purge Selected</button>
        </div>
      </div>
    `;

    setTimeout(() => {
      const selectAll = document.getElementById('cache-select-all');
      if (selectAll) {
        selectAll.addEventListener('change', (e) => {
          document.querySelectorAll('.cache-cb').forEach(cb => cb.checked = e.target.checked);
        });
      }
    }, 10);
  }

  window.cachePurgeSelected = async () => {
    const keys = Array.from(document.querySelectorAll('.cache-cb:checked')).map(cb => cb.value);
    if (!keys.length) { notify('No targets selected.', 'info'); return; }
    if (!confirm(`Delete cached data for ${keys.length} target(s)?`)) return;
    
    try {
      await apiPost('/cache/purge', { targets: ["specific"], keys });
      await loadCacheStatus();
      if (state.currentSession) renderTargetChips(state.currentSession);
      notify(`Purged ${keys.length} targets`, 'success', 2000);
      render(); // Re-render modal list
    } catch (e) { notify(`Purge failed: ${e.message}`, 'error'); }
  };

  window.cachePurgeAll = async () => {
    if (!confirm('Purge all cached data, media, and outputs? This is irreversible.')) return;
    try {
      await apiPost('/cache/purge', { targets: ['all'] });
      await loadCacheStatus();
      if (state.currentSession) renderTargetChips(state.currentSession);
      notify('Entire cache purged', 'success', 2500);
      closeModal();
    } catch (e) { notify(`Purge failed: ${e.message}`, 'error'); }
  };

  modal.className = "modal large";
  render();
  document.getElementById('modal-overlay').classList.add('visible');
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */

// Right Panel Tabs (Contacts, Entities, Media)
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tabId = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `${tabId}-tab`));
    if (tabId === 'contacts' && state.currentSession) renderGraph();
  });
});

// Center Panel Tabs (Report, Timeline)
document.querySelectorAll('.center-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tabId = btn.dataset.centerTab;
    document.querySelectorAll('.center-tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    document.getElementById('report-view').classList.toggle('visible', tabId === 'report');
    document.getElementById('timeline-view').classList.toggle('visible', tabId === 'timeline');
  });
});

/* ── New Session Modal ────────────────────────────────────────────────────── */
document.getElementById('btn-new-session').addEventListener('click', openNewSessionModal);

function openNewSessionModal() {
  const modal = document.getElementById('modal');
  modal.className = "modal";
  const targets = [];

  function render() {
    modal.innerHTML = `
      <div class="modal-title">
        <svg viewBox="0 0 24 24" fill="none" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v8M8 12h8"/></svg>
        New Investigation Session
      </div>
      <label class="form-label">Session Name</label>
      <input id="ns-name" class="form-input" type="text" placeholder="Operation Nightfall" autocomplete="off">

      <label class="form-label">Targets</label>
      <div class="targets-list" id="ns-targets">
        ${targets.map((t,i) => `
          <div class="target-row">
            <span class="plat-badge">${esc(t.platform)}</span>
            <span class="target-row-name">${esc(t.username)}</span>
            <button class="target-row-remove" onclick="nsRemove(${i})">×</button>
          </div>
        `).join('') || '<div style="font-size:11px;color:var(--text-tertiary);padding:4px 0">No targets yet.</div>'}
      </div>
      <div class="add-row">
        <select id="ns-platform" class="form-select">
          <option value="twitter">twitter</option>
          <option value="reddit">reddit</option>
          <option value="github">github</option>
          <option value="bluesky">bluesky</option>
          <option value="mastodon">mastodon</option>
          <option value="hackernews">hackernews</option>
        </select>
        <input id="ns-username" class="form-input" type="text" placeholder="username" autocomplete="off" autocorrect="off" spellcheck="false">
        <button class="btn" onclick="nsAdd()" style="flex-shrink:0">Add</button>
      </div>

      <label class="form-label">Initial Post Count</label>
      <input id="ns-count" class="form-input" type="number" value="50" min="10" max="200" step="10">
      <div class="form-help">Posts to fetch per target on first analysis. You can change this later.</div>

      <div class="modal-actions">
        <button class="btn danger" onclick="closeModal()">Cancel</button>
        <button class="btn primary" onclick="nsSubmit()">Create Session</button>
      </div>
    `;
    setTimeout(() => document.getElementById('ns-name')?.focus(), 40);
  }

  window.nsRemove = i => { targets.splice(i,1); render(); };
  window.nsAdd = () => {
    const p = document.getElementById('ns-platform').value;
    const u = document.getElementById('ns-username').value.trim().replace(/^@/,'');
    if (!u) return;
    if (targets.find(t => t.platform === p && t.username === u)) return;

    // Preserve session name before re-rendering
    const nameInput = document.getElementById('ns-name');
    const countInput = document.getElementById('ns-count');
    const savedName = nameInput ? nameInput.value : '';
    const savedCount = countInput ? countInput.value : '50';

    targets.push({ platform: p, username: u });
    document.getElementById('ns-username').value = '';
    render();

    // Restore session name and count after re-rendering
    setTimeout(() => {
      const newNameInput = document.getElementById('ns-name');
      const newCountInput = document.getElementById('ns-count');
      if (newNameInput) newNameInput.value = savedName;
      if (newCountInput) newCountInput.value = savedCount;
    }, 10);
  };
  window.nsSubmit = async () => {
    const name  = document.getElementById('ns-name')?.value.trim();
    const count = parseInt(document.getElementById('ns-count')?.value) || 50;
    if (!name) { notify('Enter a session name', 'info'); return; }
    if (!targets.length) { notify('Add at least one target', 'info'); return; }
    const platforms = {};
    targets.forEach(({ platform, username }) => { if (!platforms[platform]) platforms[platform] = []; platforms[platform].push(username); });
    try {
      const s = await apiPost('/sessions', { name, platforms, fetch_options: { default_count: count, targets: {} } });
      closeModal();
      await refreshSessionList();
      await loadSession(s.session_id);
      notify(`Session "${name}" created`, 'success', 2500);
    } catch (e) { notify(`Failed: ${e.message}`, 'error'); }
  };

  render();
  document.getElementById('modal-overlay').classList.add('visible');
}

/* ── Manage Targets Modal ──────────────────────────────────────────────────── */
document.getElementById('btn-manage-targets').addEventListener('click', openManageTargetsModal);

function openManageTargetsModal() {
  if (!state.currentSession) return;
  const s = state.currentSession;
  const modal = document.getElementById('modal');
  modal.className = "modal";
  const targets = [];
  for (const [p, users] of Object.entries(s.platforms || {})) for (const u of users) targets.push({ platform: p, username: u });

  function render() {
    modal.innerHTML = `
      <div class="modal-title">
        <svg viewBox="0 0 24 24" fill="none" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1-1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        Manage Targets
      </div>
      <div class="targets-list">
        ${targets.map((t,i) => `
          <div class="target-row">
            <span class="plat-badge">${esc(t.platform)}</span>
            <span class="target-row-name">${esc(t.username)}</span>
            <button class="target-row-remove" onclick="mtRemove(${i})">×</button>
          </div>
        `).join('') || '<div style="font-size:11px;color:var(--text-tertiary);padding:4px 0">No targets.</div>'}
      </div>
      <div class="add-row" style="margin-top:8px">
        <select id="mt-platform" class="form-select">
          <option value="twitter">twitter</option>
          <option value="reddit">reddit</option>
          <option value="github">github</option>
          <option value="bluesky">bluesky</option>
          <option value="mastodon">mastodon</option>
          <option value="hackernews">hackernews</option>
        </select>
        <input id="mt-username" class="form-input" type="text" placeholder="username" autocomplete="off" autocorrect="off" spellcheck="false">
        <button class="btn" onclick="mtAdd()" style="flex-shrink:0">Add</button>
      </div>
      <div class="modal-actions">
        <button class="btn danger" onclick="closeModal()">Cancel</button>
        <button class="btn primary" onclick="mtSave()">Save Changes</button>
      </div>
    `;
  }

  window.mtRemove = i => { targets.splice(i,1); render(); };
  window.mtAdd = () => {
    const p = document.getElementById('mt-platform').value;
    const u = document.getElementById('mt-username').value.trim().replace(/^@/,'');
    if (!u) return;
    if (targets.find(t => t.platform===p && t.username===u)) return;
    targets.push({ platform: p, username: u });
    document.getElementById('mt-username').value = '';
    render();
  };
  window.mtSave = async () => {
    if (!targets.length) { notify('Add at least one target', 'info'); return; }
    const platforms = {};
    targets.forEach(({ platform, username }) => { if (!platforms[platform]) platforms[platform] = []; platforms[platform].push(username); });
    try {
      await apiPut(`/sessions/${s.session_id}/targets`, { platforms, fetch_options: s.fetch_options });
      s.platforms = platforms;
      closeModal();
      
      // Update cache status to reflect additions
      await loadCacheStatus();
      renderTargetChips(s);
      
      await refreshSessionList();
      notify('Targets updated', 'success', 2000);
    } catch (e) { notify(`Save failed: ${e.message}`, 'error'); }
  };

  render();
  document.getElementById('modal-overlay').classList.add('visible');
}

/* ── Modal ────────────────────────────────────────────────────────────────── */
function closeModal() { document.getElementById('modal-overlay').classList.remove('visible'); }
document.getElementById('modal-overlay').addEventListener('click', e => { if (e.target === document.getElementById('modal-overlay')) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ── Keyboard shortcut ────────────────────────────────────────────────────── */
document.getElementById('query-input').addEventListener('keydown', e => {
  // Execute run ONLY if button is not disabled
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      if (!document.getElementById('run-analysis-btn').disabled) {
          document.getElementById('run-analysis-btn').click();
      }
  }
});

/* ── Resizable panes ──────────────────────────────────────────────────────── */
function makeResizable(handleId, targetEl, direction = 'right', min = 160, max = 480) {
  const handle = document.getElementById(handleId);
  if (!handle) return;
  let startX, startW;

  handle.addEventListener('mousedown', e => {
    e.preventDefault();
    startX = e.clientX;
    startW = targetEl.getBoundingClientRect().width;
    handle.classList.add('dragging');

    const onMove = e => {
      const delta = direction === 'right' ? e.clientX - startX : startX - e.clientX;
      const newW = Math.max(min, Math.min(max, startW + delta));
      targetEl.style.width = newW + 'px';
      if (targetEl.id === 'right-panel' || targetEl.id === 'sidebar') {
        targetEl.style.setProperty('--w', newW + 'px');
      }
    };
    const onUp = () => {
      handle.classList.remove('dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (state.contacts.length) renderGraph();
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

makeResizable('sidebar-resize',  document.getElementById('sidebar'),        'right', 160, 400);
makeResizable('history-resize',  document.getElementById('history-sidebar'), 'right', 120, 320);
makeResizable('right-resize',    document.getElementById('right-panel'),     'left',  220, 520);

/* ── Init ─────────────────────────────────────────────────────────────────── */
(async function init() {
  // Restore theme
  const saved = localStorage.getItem('osint-theme') || 'auto';
  applyTheme(saved);

  // Initialize drawer system
  initDrawers();

  await refreshSessionList();
  await loadCacheStatus();

  // Listen for OS theme changes in auto mode
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (state.theme === 'auto') applyTheme('auto');
  });
})();
