'use strict';

/* ------------------------------------------------------------------ utils */
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  route: 'scan',
  includeDemo: localStorage.getItem('autoguard_include_demo') === '1',
  chatSession: localStorage.getItem('autoguard_chat_session') || null,
  chatMessages: [],
  chatBusy: false,
  scanFiles: [],
  scanPreviews: [],
  scanResults: [],
  scanning: false,
  review: { status: 'review', query: '', items: [], total: 0, selectedId: null, loading: false },
  archive: { status: 'all', query: '', items: [], total: 0, hasMore: false, loading: false },
  assistantStatus: null,
  assistantPlates: [],
  llmProbe: null,
  llmBusy: false,
  llmAutoTimer: null,
  cameraStream: null,
  pendingScanFile: null,
  summary: null,
  benchmark: null,
  gateCurve: null,
  intelTab: 'gate',
  restoreFile: null,
  restorePreview: null,
  restoreResult: null,
  routeToken: 0,
};

const ICONS = {
  scan: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M7 12h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 4.5 6.5v5.2c0 4.3 3.1 7.7 7.5 9.3 4.4-1.6 7.5-5 7.5-9.3V6.5L12 3Z" stroke="currentColor" stroke-width="1.6"/><path d="m8.8 12.2 2.1 2.1 4.4-4.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4 3.5 19h17L12 4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 9v4.5M12 16.2v.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none"><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" fill="currentColor" opacity=".7"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none"><path d="m5 12 4.2 4.2L19 6.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3.5c4.7 0 8.5 3.1 8.5 7s-3.8 7-8.5 7c-.9 0-1.8-.1-2.6-.3L5 20l.9-3.6c-1.5-1.3-2.4-3.2-2.4-5.9 0-3.9 3.8-7 8.5-7Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
  db: '<svg viewBox="0 0 24 24" fill="none"><ellipse cx="12" cy="5.5" rx="7" ry="2.8" stroke="currentColor" stroke-width="1.5"/><path d="M5 5.5v6c0 1.6 3.1 2.8 7 2.8s7-1.2 7-2.8v-6M5 11.5v6c0 1.6 3.1 2.8 7 2.8s7-1.2 7-2.8v-6" stroke="currentColor" stroke-width="1.5"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 19h16M7 16V9M12 16V5M17 16v-4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="6" stroke="currentColor" stroke-width="1.7"/><path d="m16 16 4 4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none"><path d="m4 4 17 8-17 8 3-8-3-8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M7 12h14" stroke="currentColor" stroke-width="1.7"/></svg>',
  image: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.6"/><circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" stroke-width="1.5"/><path d="m4 17 5-5 4 4 3-3 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  camera: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="7" width="18" height="13" rx="2.5" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="13.5" r="3.4" stroke="currentColor" stroke-width="1.6"/><path d="M8.5 7 9.7 4.6h4.6L15.5 7" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4v11m0 0 4-4m-4 4-4-4M5 19h14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none"><rect x="8" y="8" width="11" height="12" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h2" stroke="currentColor" stroke-width="1.6"/></svg>',
  sun: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.7"/><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  moon: '<svg viewBox="0 0 24 24" fill="none"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
};

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function num(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '0';
  return numeric.toLocaleString('en-IN');
}

function pct(value, digits = 1) {
  const numeric = Number(value);
  return `${(Number.isFinite(numeric) ? numeric * 100 : 0).toFixed(digits)}%`;
}

function pctCi(ci) {
  if (!Array.isArray(ci) || ci.length !== 2) return '—';
  return `${pct(ci[0])}–${pct(ci[1])}`;
}

function per100(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(numeric < 10 ? 2 : 1) : '0';
}

function score(value) {
  const numeric = Number(value);
  return (Number.isFinite(numeric) ? numeric : 0).toFixed(2);
}

function shortDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
}

function timeAgo(iso) {
  if (!iso) return 'unknown';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'unknown';
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)}d ago`;
  return shortDate(iso);
}

function dateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function loadingHtml(label = 'Loading…') {
  return `<div class="loading"><span class="spinner"></span><span>${esc(label)}</span></div>`;
}

function errorHtml(error) {
  return `<div class="error-box"><strong>Could not load this view.</strong><br>${esc(error.message || error)}</div>`;
}

function emptyHtml(title, copy, icon = ICONS.db) {
  return `<div class="empty-state">${icon}<strong>${esc(title)}</strong><p>${esc(copy)}</p></div>`;
}

async function api(path, options = {}) {
  const config = { ...options, headers: { ...(options.headers || {}) } };
  if (config.body && !(config.body instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json';
    if (typeof config.body !== 'string') config.body = JSON.stringify(config.body);
  }
  const response = await fetch(path, config);
  const contentType = response.headers.get('content-type') || '';
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      if (contentType.includes('application/json')) {
        const body = await response.json();
        detail = body.detail || body.message || detail;
        if (Array.isArray(detail)) detail = detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
      } else {
        detail = (await response.text()).slice(0, 300) || detail;
      }
    } catch (error) { /* keep default */ }
    throw new Error(detail);
  }
  if (contentType.includes('application/json')) return response.json();
  return response.text();
}

function copyText(text, label = 'Copied.') {
  const value = String(text || '');
  if (!value) { toast('Nothing to copy.', 'bad'); return; }
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(value).then(() => toast(label, 'ok')).catch(() => toast('Copy failed.', 'bad'));
  } else {
    const area = document.createElement('textarea');
    area.value = value;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast(label, 'ok');
  }
}

function downloadJson(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ------------------------------------------------------------------ toast / modal / drawer */
function toast(message, kind = '') {
  const root = $('#toast-root');
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.textContent = message;
  root.appendChild(node);
  setTimeout(() => { node.style.opacity = '0'; node.style.transition = 'opacity .25s'; }, 3400);
  setTimeout(() => node.remove(), 3750);
}

function closeModal() {
  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
  }
  $('#modal-root').innerHTML = '';
  document.body.style.overflow = '';
}

function openModal(title, bodyHtml) {
  $('#modal-root').innerHTML = `
    <div class="modal-backdrop" id="modal-backdrop">
      <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" id="modal-close" type="button" aria-label="Close">${ICONS.close}</button></div>
        <div class="modal-body">${bodyHtml}</div>
      </div>
    </div>`;
  document.body.style.overflow = 'hidden';
  $('#modal-close')?.addEventListener('click', closeModal);
  $('#modal-backdrop')?.addEventListener('click', (event) => { if (event.target.id === 'modal-backdrop') closeModal(); });
}

function citationModal(title, text) {
  openModal(title || 'Source', `<div class="msg-bubble">${markdownLite(text || '')}</div>`);
}

function openImageLightbox(src, alt) {
  if (!src) return;
  openModal(alt || 'Plate crop', `<div class="lightbox"><img src="${src}" alt="${esc(alt || 'Plate crop')}"></div>`);
}

function closeDrawer() {
  $('#drawer-root').innerHTML = '';
  document.body.style.overflow = '';
}

function openDrawer(eyebrow, title, bodyHtml, actionsHtml = '') {
  $('#drawer-root').innerHTML = `
    <div class="drawer-backdrop" id="drawer-backdrop">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="drawer-head">
          <div><p class="eyebrow">${esc(eyebrow)}</p><h2>${esc(title)}</h2></div>
          <button class="icon-btn" id="drawer-close" type="button" aria-label="Close">${ICONS.close}</button>
        </div>
        <div class="drawer-body">${bodyHtml}</div>
        ${actionsHtml ? `<div class="drawer-actions">${actionsHtml}</div>` : ''}
      </aside>
    </div>`;
  document.body.style.overflow = 'hidden';
  $('#drawer-close')?.addEventListener('click', closeDrawer);
  $('#drawer-backdrop')?.addEventListener('click', (event) => { if (event.target.id === 'drawer-backdrop') closeDrawer(); });
}

/* ------------------------------------------------------------------ command palette */
const PALETTE_ROUTES = [
  { label: 'Scan desk', meta: 'G then S', hint: 'Read a vehicle frame', hash: '#/scan' },
  { label: 'Review queue', meta: 'G then R', hint: 'Human decision desk', hash: '#/review' },
  { label: 'Plate archive', meta: 'G then A', hint: 'Evidence ledger', hash: '#/archive' },
  { label: 'Intelligence', meta: 'G then I', hint: 'Gate calibration + restoration', hash: '#/intel' },
  { label: 'Assistant', meta: 'G then C', hint: 'Ask your plate database', hash: '#/assistant' },
];

let paletteState = { items: [], active: 0, recent: [], matches: [] };
let paletteSearchTimer = 0;
let pendingG = 0;

async function openPalette() {
  $('#palette-root').innerHTML = `
    <div class="palette-backdrop" id="palette-backdrop">
      <div class="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <div class="palette-input">${ICONS.search}<input id="palette-input" placeholder="Jump to a page, reading or action…" autocomplete="off" aria-label="Search commands"><kbd>esc</kbd></div>
        <div class="palette-list" id="palette-list"></div>
        <div class="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span></div>
      </div>
    </div>`;
  const input = $('#palette-input');
  input.focus();
  const filter = () => renderPalette(input.value.trim().toLowerCase());
  input.addEventListener('input', () => {
    filter();
    clearTimeout(paletteSearchTimer);
    const query = input.value.trim();
    if (query.length < 2) { paletteState.matches = []; filter(); return; }
    paletteSearchTimer = setTimeout(() => searchPalette(query), 180);
  });
  input.addEventListener('keydown', (event) => {
    const items = paletteState.items;
    if (event.key === 'ArrowDown') { event.preventDefault(); paletteState.active = Math.min(items.length - 1, paletteState.active + 1); paintPaletteActive(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); paletteState.active = Math.max(0, paletteState.active - 1); paintPaletteActive(); }
    if (event.key === 'Enter') { event.preventDefault(); items[paletteState.active]?.run(); }
    if (event.key === 'Escape') closePalette();
  });
  $('#palette-backdrop').addEventListener('click', (event) => { if (event.target.id === 'palette-backdrop') closePalette(); });
  renderPalette('');
  try {
    const demo = state.includeDemo ? '1' : '0';
    const data = await api(`/api/plates?limit=6&include_demo=${demo}`);
    paletteState.recent = (data.items || []).map((plate) => ({
      group: 'Recent readings',
      label: plate.display_text || plate.ocr_text || 'Unreadable',
      meta: timeAgo(plate.created_at),
      chip: true,
      run: () => { closePalette(); openPlateDossier(plate.id); },
    }));
    if ($('#palette-input')) filter();
  } catch (error) { /* recent readings are optional */ }
}

async function searchPalette(query) {
  try {
    const demo = state.includeDemo ? '1' : '0';
    const data = await api(`/api/plates?q=${encodeURIComponent(query)}&limit=6&include_demo=${demo}`);
    paletteState.matches = (data.items || []).map((plate) => ({
      group: 'Matching readings',
      label: plate.display_text || plate.ocr_text || 'Unreadable',
      meta: `${statusLabel(plate)} · ${timeAgo(plate.created_at)}`,
      chip: true,
      run: () => { closePalette(); openPlateDossier(plate.id); },
    }));
  } catch (error) {
    paletteState.matches = [];
  }
  const input = $('#palette-input');
  if (input && input.value.trim() === query) renderPalette(query.toLowerCase());
}

function paletteItems(query) {
  const actions = [
    { group: 'Actions', label: 'Toggle demo data', meta: state.includeDemo ? 'on' : 'off', run: () => { closePalette(); setDemo(!state.includeDemo); } },
    { group: 'Actions', label: 'Switch light / dark theme', meta: 'T', run: () => { closePalette(); toggleTheme(); } },
    { group: 'Actions', label: 'Export evidence ledger (CSV)', meta: 'CSV', run: () => { closePalette(); exportLedger(); } },
    { group: 'Actions', label: 'Open a vehicle image', meta: 'scan', run: () => { closePalette(); location.hash = '#/scan'; setTimeout(() => $('#file-input')?.click(), 120); } },
  ];
  const routes = PALETTE_ROUTES.map((item) => ({ group: 'Navigate', ...item, run: () => { closePalette(); location.hash = item.hash; } }));
  const readings = query ? paletteState.matches : paletteState.recent;
  if (!query) return [...routes, ...actions, ...readings];
  const staticMatches = [...routes, ...actions].filter((item) => `${item.label} ${item.group} ${item.hint || ''}`.toLowerCase().includes(query));
  return [...staticMatches, ...readings];
}

function renderPalette(query) {
  const list = $('#palette-list');
  if (!list) return;
  paletteState.items = paletteItems(query);
  paletteState.active = 0;
  if (!paletteState.items.length) {
    list.innerHTML = `<div class="palette-empty">No matches. Try "scan", "review", "gate" or a plate number.</div>`;
    return;
  }
  let group = '';
  list.innerHTML = paletteState.items.map((item, index) => {
    const heading = item.group !== group ? `<div class="palette-group">${esc(item.group)}</div>` : '';
    group = item.group;
    return `${heading}<button class="palette-item" type="button" data-palette-index="${index}">${item.chip ? `<span class="plate-chip">${esc(item.label)}</span>` : `<span>${esc(item.label)}</span>`}${item.hint ? `<span class="muted-2">${esc(item.hint)}</span>` : ''}<small>${esc(item.meta || '')}</small></button>`;
  }).join('');
  $$('[data-palette-index]', list).forEach((button) => button.addEventListener('click', () => paletteState.items[Number(button.dataset.paletteIndex)]?.run()));
  paintPaletteActive();
}

function paintPaletteActive() {
  $$('#palette-list .palette-item').forEach((button) => button.classList.toggle('active', Number(button.dataset.paletteIndex) === paletteState.active));
  $$('#palette-list .palette-item')[paletteState.active]?.scrollIntoView({ block: 'nearest' });
}

function closePalette() { clearTimeout(paletteSearchTimer); paletteState.matches = []; $('#palette-root').innerHTML = ''; }

/* ------------------------------------------------------------------ camera / explain */
async function openCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    toast('This browser does not expose a camera here. Use file upload instead.', 'bad');
    return;
  }
  openModal('Capture a vehicle frame', `
    <div class="camera-box">
      <video id="camera-video" playsinline autoplay muted></video>
      <div class="camera-actions">
        <span>Point the camera at the plate and keep it steady.</span>
        <div class="camera-buttons">
          <button class="btn btn-ghost btn-small" id="camera-cancel" type="button">Cancel</button>
          <button class="btn btn-primary btn-small" id="camera-shoot" type="button" disabled>Capture frame</button>
        </div>
      </div>
    </div>`);
  const video = $('#camera-video');
  try {
    state.cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
    video.srcObject = state.cameraStream;
    video.addEventListener('loadedmetadata', () => { const button = $('#camera-shoot'); if (button) button.disabled = false; });
  } catch (error) {
    closeModal();
    toast(`Camera unavailable: ${error.message || 'permission denied'}.`, 'bad');
    return;
  }
  $('#camera-cancel')?.addEventListener('click', closeModal);
  $('#camera-shoot')?.addEventListener('click', () => {
    if (!video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) { toast('The capture produced no image. Try again.', 'bad'); return; }
      const file = new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' });
      closeModal();
      if (state.route === 'scan') {
        addScanFiles([file]);
      } else {
        state.pendingScanFile = file;
        location.hash = '#/scan';
      }
      toast('Frame captured. Check the crop, then analyze.', 'ok');
    }, 'image/jpeg', 0.92);
  });
}

async function openExplain(plateId) {
  try {
    const data = await api(`/api/plates/${plateId}/explain`);
    const citations = (data.citations || []).map((item) => `<button class="citation" data-cite-title="${esc(item.title)}" data-cite-text="${esc(item.snippet)}">${esc(item.section)}</button>`).join('');
    openModal(`Plate #${plateId} · failure explanation`, `
      <div class="msg-bubble">${markdownLite(data.reply || '')}</div>
      ${citations ? `<div class="citations">${citations}</div>` : ''}
    `);
    $$('#modal-root [data-cite-title]').forEach((button) => button.addEventListener('click', () => citationModal(button.dataset.citeTitle, button.dataset.citeText)));
  } catch (error) {
    toast(error.message, 'bad');
  }
}

/* ------------------------------------------------------------------ display helpers */
function statusLabel(plate) {
  if (plate.verification_status === 'corrected') return 'Corrected';
  if (plate.verification_status === 'confirmed') return 'Confirmed';
  if (plate.verification_status === 'rejected') return 'Rejected';
  return plate.review_status === 'candidate_passed_validation_gate' ? 'Gate passed' : 'Needs review';
}

function statusPill(plate) {
  if (plate.verification_status === 'corrected') return `<span class="pill info">Corrected</span>`;
  if (plate.verification_status === 'confirmed') return `<span class="pill ok">Confirmed</span>`;
  if (plate.verification_status === 'rejected') return `<span class="pill bad">Rejected</span>`;
  if (plate.review_status === 'candidate_passed_validation_gate') return `<span class="pill ok">Gate passed</span>`;
  if (!plate.ocr_text) return `<span class="pill bad">No reading</span>`;
  return `<span class="pill warn">Needs review</span>`;
}

function recoveryPill(outcome) {
  const map = {
    recovered: ['ok', 'Recovered'],
    unchanged: ['', 'Unchanged'],
    changed: ['warn', 'Low margin'],
    degraded: ['bad', 'Degraded'],
    no_reading: ['bad', 'Unreadable'],
    not_attempted: ['', 'No retry'],
  };
  const [kind, label] = map[outcome] || ['', outcome || 'Unknown'];
  return `<span class="pill ${kind}">${esc(label)}</span>`;
}

function scoreBar(value) {
  const numeric = Math.max(0, Math.min(1, Number(value) || 0));
  const kind = numeric >= 0.81 ? 'ok' : numeric >= 0.55 ? 'warn' : 'bad';
  return `<span class="mini-score"><span class="bar-track"><span class="bar-fill ${kind}" style="width:${numeric * 100}%"></span></span><span>${score(numeric)}</span></span>`;
}

function plateChip(text, unread = false) {
  const label = text || 'Unreadable';
  return `<span class="plate-chip ${unread || !text ? 'unread' : ''}">${esc(label)}</span>`;
}

function cropBox(plate, alt = 'Plate crop') {
  if (plate.crop_preview) return `<img src="${plate.crop_preview}" alt="${esc(alt)}" loading="lazy" data-lightbox="1" title="Click to view full size">`;
  return `<div class="plate-placeholder"><strong>${esc(plate.display_text || plate.ocr_text || 'UNREADABLE')}</strong><small>crop preview not stored</small></div>`;
}

function plateCells(text) {
  const clean = String(text || '').toUpperCase();
  if (!clean) return `<span class="plate-read-empty">Unreadable</span>`;
  return `<div class="plate-read">${[...clean].map((char) => `<b>${esc(char)}</b>`).join('')}</div>`;
}

function ringHtml(value, label = 'engine') {
  const numeric = Math.max(0, Math.min(1, Number(value) || 0));
  const color = numeric >= 0.81 ? 'mint' : numeric >= 0.55 ? 'amber' : 'red';
  return `<div class="score-ring" style="--value:${(numeric * 100).toFixed(1)};--ring-color:var(--${color})" title="OCR engine score ${score(numeric)} · not a probability"><div><b>${score(numeric)}</b><small>${esc(label)}</small></div></div>`;
}

function compareHtml(contact, uid) {
  const original = contact.crop_preview || '';
  const enhanced = contact.enhanced_preview || '';
  if (!original) return `<div class="crop-frame">${cropBox(contact)}</div>`;
  if (!enhanced) {
    return `<div class="compare-wrap"><img src="${original}" alt="Plate crop" data-lightbox="1"></div><div class="compare-label"><span>Original crop</span><span>no enhanced pass stored</span></div>`;
  }
  return `<div class="compare-wrap" data-compare="${esc(uid)}">
      <img class="before" src="${enhanced}" alt="Enhanced crop">
      <img class="after" src="${original}" alt="Original crop" style="clip-path:inset(0 50% 0 0)">
      <span class="compare-handle"></span>
    </div>
    <input class="compare-input" type="range" min="0" max="100" value="50" data-compare-input="${esc(uid)}" aria-label="Compare original and enhanced crop">
    <div class="compare-label"><span>Original</span><span>Enhanced</span></div>`;
}

function bindCompares(root = document) {
  $$('[data-compare-input]', root).forEach((input) => {
    input.addEventListener('input', () => {
      const value = Number(input.value);
      const wrap = $(`[data-compare="${input.dataset.compareInput}"]`, root);
      if (!wrap) return;
      const after = $('.after', wrap);
      const handle = $('.compare-handle', wrap);
      if (after) after.style.clipPath = `inset(0 ${100 - value}% 0 0)`;
      if (handle) handle.style.left = `${value}%`;
    });
  });
}

function traceStep(kind, number, title, copy) {
  return `<div class="trace-step ${kind}"><span class="trace-dot">${number}</span><div class="trace-copy"><strong>${esc(title)}</strong><span>${copy}</span></div></div>`;
}

function traceHtml(plate) {
  const flags = (plate.quality_flags || []).filter((flag) => String(flag).toLowerCase() !== 'none detected');
  const retryReasons = (plate.retry_reasons || [])
    .map((reason) => String(reason).replaceAll('_', ' '))
    .filter((reason) => reason.toLowerCase() !== 'non-standard or low-confidence reading');
  const detectorVerdict = Number(plate.detector_confidence) >= 0.25 ? 'ok' : 'warn';
  const qualityVerdict = flags.length ? 'warn' : 'ok';
  const firstRead = plate.original_prediction ?? plate.original_text ?? '';
  const firstScore = plate.original_ocr_score ?? plate.original_score;
  const originalVerdict = Number(firstScore) >= 0.65 ? 'ok' : 'warn';
  const retryVerdict = plate.recovery_outcome === 'recovered' ? 'ok' : plate.retry_attempted ? 'warn' : '';
  const verdict = plate.review_status === 'candidate_passed_validation_gate' ? 'ok' : 'bad';
  return `<div class="trace">
    ${traceStep(detectorVerdict, '1', 'Locate', `YOLOv8 box ${score(plate.detector_confidence)}${plate.merged_detections > 1 ? ` · merged ${plate.merged_detections} boxes` : ''}${plate.edge_touching ? ' · touches frame edge' : ''}.`)}
    ${traceStep(qualityVerdict, '2', 'Diagnose', flags.length ? `${flags.map(esc).join(', ')} · brightness ${score(plate.brightness)}, sharpness ${score(plate.blur_score)}.` : `No strong flag · brightness ${score(plate.brightness)}, sharpness ${score(plate.blur_score)}.`)}
    ${traceStep(originalVerdict, '3', 'First read', `<code>${esc(firstRead || '∅')}</code> at ${score(firstScore)}.`)}
    ${traceStep(retryVerdict, '4', 'Heal', plate.retry_attempted ? `${retryReasons.length ? retryReasons.map(esc).join(', ') : 'weak OCR signal'} → <code>${esc(plate.selected_method || '')}</code>.` : 'No retry needed at the current thresholds.')}
    ${traceStep(verdict, '5', 'Gate', plate.review_status === 'candidate_passed_validation_gate' ? 'Passed format + validation-selected score gate. Verify visually.' : 'Routed to human review: format or score did not meet the gate.')}
  </div>`;
}

/* ------------------------------------------------------------------ scan desk */
function scanView() {
  state.scanFiles = [];
  state.scanPreviews.forEach((url) => URL.revokeObjectURL(url));
  state.scanPreviews = [];
  state.scanResults = [];
  const view = $('#view');
  view.innerHTML = `
    <div class="scan-console">
      <section class="panel scan-intro">
        <div class="intro-copy">
          <p class="eyebrow">WHAT THIS IS</p>
          <h2>Self-healing number plate reader</h2>
          <p class="intro-line">Drop a vehicle photo and AutoGuard AI finds the plate, reads it, retries weak reads with enhancement, then accepts the text or sends it to human review.</p>
        </div>
        <div class="intro-steps">
          <div class="intro-step"><span class="how-num">1</span><div><strong>Upload a frame</strong><span>Drop up to 8 vehicle photos.</span></div></div>
          <div class="intro-step"><span class="how-num">2</span><div><strong>Analyze the batch</strong><span>Detection, OCR and healing run automatically.</span></div></div>
          <div class="intro-step"><span class="how-num">3</span><div><strong>Verify the read</strong><span>Confirm the text, correct it, or open the dossier.</span></div></div>
        </div>
        <div class="scan-plate-visual" aria-hidden="true">
          <div class="plate-mock"><span>MH 12 AB 3456</span><i class="sweep"></i></div>
          <div class="plate-visual-caption"><span>DETECT</span><span>READ</span><span>HEAL</span><span>GATE</span></div>
        </div>
      </section>
      <div class="scan-grid">
        <section class="panel intake-card">
          <div class="intake-head">
            <div><h2>Frame intake</h2></div>
          </div>
          <div class="dropzone" id="dropzone" tabindex="0" role="button" aria-label="Choose vehicle images">
            <input id="file-input" type="file" accept="image/jpeg,image/png,image/webp,image/bmp" multiple>
            <div class="drop-icon">${ICONS.image}</div>
            <strong>Drop vehicle images here</strong>
            <p class="hint">Click to browse · or drag files onto this panel</p>
            <div class="drop-actions">
              <button class="btn btn-ghost btn-small" id="camera-open" type="button">${ICONS.camera} Use camera</button>
            </div>
            <div class="drop-formats"><span>JPEG</span><span>PNG</span><span>WEBP</span><span>BMP</span><span>up to 8 frames</span></div>
          </div>
          <div id="selection"></div>
          <div id="scan-progress"></div>
        </section>
        <aside class="scan-side">
          <section class="panel side-card">
            <p class="eyebrow">PIPELINE</p>
            <div class="how-step pipeline-step"><div class="step-head"><strong>Detect</strong></div><span>Locate plate regions in each frame.</span></div>
            <div class="how-step pipeline-step"><div class="step-head"><strong>Diagnose</strong></div><span>Flag blur, glare and weak crops.</span></div>
            <div class="how-step pipeline-step"><div class="step-head"><strong>Read</strong></div><span>Recognise characters on the plate.</span></div>
            <div class="how-step pipeline-step"><div class="step-head"><strong>Heal</strong></div><span>Enhance weak crops and retry the read.</span></div>
            <div class="how-step pipeline-step"><div class="step-head"><strong>Gate</strong></div><span>Pass confident reads, queue the rest.</span></div>
          </section>
          <section class="panel side-card">
            <p class="eyebrow">LEDGER SNAPSHOT · 30 DAYS</p>
            <div class="bench-lines">
              <div class="bench-line"><span>Plate regions</span><b id="side-plates">${state.summary ? num(state.summary.total_plates) : '—'}</b></div>
              <div class="bench-line"><span>Gate passed</span><b id="side-passed">${state.summary ? num(state.summary.passed) : '—'}</b></div>
              <div class="bench-line"><span>Awaiting review</span><b id="side-review">${state.summary ? num(state.summary.review) : '—'}</b></div>
              <div class="bench-line"><span>Recovered reads</span><b id="side-recovered">${state.summary ? num(state.summary.recovered) : '—'}</b></div>
            </div>
            <a class="row-link" href="#/archive">Open the archive →</a>
          </section>
        </aside>
      </div>
      <section class="panel recent-panel" id="recent-panel">
        <div class="recent-head">
          <div><h2>Latest reads</h2></div>
          <a class="row-link" href="#/archive">Open the archive →</a>
        </div>
        <div class="recent-strip" id="recent-strip"><span class="recent-empty">Loading recent reads…</span></div>
      </section>
      <div id="scan-results" class="result-stack"></div>
    </div>`;
  const dropzone = $('#dropzone');
  const input = $('#file-input');
  dropzone.addEventListener('click', (event) => { if (event.target.tagName !== 'INPUT' && !event.target.closest('#camera-open')) input.click(); });
  dropzone.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); } });
  input.addEventListener('change', () => { addScanFiles([...input.files]); input.value = ''; });
  ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add('dragging'); }));
  ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove('dragging'); }));
  dropzone.addEventListener('drop', (event) => addScanFiles([...event.dataTransfer.files]));
  $('#camera-open')?.addEventListener('click', (event) => { event.stopPropagation(); openCamera(); });
  renderSelection();
  bindScanDelegates();
  loadRecentReads();
  if (state.pendingScanFile) {
    const pending = state.pendingScanFile;
    state.pendingScanFile = null;
    addScanFiles([pending]);
  }
}

async function loadRecentReads() {
  const strip = $('#recent-strip');
  if (!strip) return;
  try {
    const data = await api(`/api/plates?limit=6&include_demo=${state.includeDemo ? '1' : '0'}`);
    const items = data.items || [];
    if (!$('#recent-strip')) return;
    if (!items.length) {
      $('#recent-strip').innerHTML = '<span class="recent-empty">No frames yet — drop a plate image above and the newest reads will land here.</span>';
      return;
    }
    $('#recent-strip').innerHTML = items.map((plate) => `<button class="recent-card" type="button" data-recent="${plate.id}">
      <span class="recent-crop">${plate.crop_preview ? `<img src="${plate.crop_preview}" alt="">` : `<span class="recent-fallback">${esc(plate.display_text || plate.ocr_text || '∅')}</span>`}</span>
      <span class="recent-meta"><b>${esc(plate.display_text || plate.ocr_text || 'UNREADABLE')}</b><small>${plate.review_status === 'candidate_passed_validation_gate' ? 'Gate passed' : 'Needs review'} · ${score(plate.ocr_score)}</small></span>
    </button>`).join('');
    $$('[data-recent]').forEach((button) => button.addEventListener('click', () => openPlateDossier(Number(button.dataset.recent))));
  } catch (error) {
    strip.innerHTML = `<span class="recent-empty">${esc(error.message)}</span>`;
  }
}

function bindScanDelegates() {
  const root = $('#scan-results');
  if (!root || root.dataset.bound === '1') return;
  root.dataset.bound = '1';
  root.addEventListener('click', async (event) => {
    const dossier = event.target.closest('[data-dossier]');
    if (dossier) { openPlateDossier(Number(dossier.dataset.dossier)); return; }
    const verify = event.target.closest('[data-verify]');
    if (!verify) return;
    const box = verify.closest('.verify-box');
    await submitVerification(Number(box.dataset.plate), verify.dataset.verify, box);
  });
}

function addScanFiles(files) {
  const images = files.filter((file) => file.type.startsWith('image/') || /\.(jpe?g|png|webp|bmp)$/i.test(file.name));
  if (!images.length) { toast('Choose JPG, PNG, WEBP or BMP images.', 'bad'); return; }
  for (const file of images) {
    if (state.scanFiles.length >= 8) { toast('A batch is limited to 8 images.', 'bad'); break; }
    if (state.scanFiles.some((existing) => existing.name === file.name && existing.size === file.size)) continue;
    state.scanFiles.push(file);
    state.scanPreviews.push(URL.createObjectURL(file));
  }
  renderSelection();
}

function renderSelection() {
  const root = $('#selection');
  if (!root) return;
  if (!state.scanFiles.length) { root.innerHTML = ''; return; }
  const thumbs = state.scanFiles.map((file, index) => `<div class="file-thumb"><img src="${state.scanPreviews[index]}" alt="${esc(file.name)}"><span>${esc(file.name)}</span></div>`).join('');
  root.innerHTML = `
    <div class="file-strip">${thumbs}</div>
    <div class="selection-bar">
      <p><strong>${state.scanFiles.length}</strong> image(s) queued · CPU ~1–3 s per frame</p>
      <div>
        <button class="btn btn-ghost btn-small" id="clear-scan" type="button">Clear</button>
        <button class="btn btn-primary btn-small" id="analyze-btn" type="button" ${state.scanning ? 'disabled' : ''}>${state.scanning ? 'Analyzing…' : 'Analyze batch'}</button>
      </div>
    </div>`;
  $('#clear-scan')?.addEventListener('click', () => {
    if (state.scanning) return;
    state.scanFiles = [];
    state.scanPreviews.forEach((url) => URL.revokeObjectURL(url));
    state.scanPreviews = [];
    state.scanResults = [];
    renderSelection();
    if ($('#scan-results')) $('#scan-results').innerHTML = '';
    if ($('#scan-progress')) $('#scan-progress').innerHTML = '';
    document.querySelector('.scan-console')?.classList.remove('has-results');
    loadRecentReads();
  });
  $('#analyze-btn')?.addEventListener('click', analyzeFiles);
}

async function analyzeFiles() {
  if (state.scanning || !state.scanFiles.length) return;
  state.scanning = true;
  state.scanResults = [];
  renderSelection();
  const progress = $('#scan-progress');
  const results = $('#scan-results');
  progress.innerHTML = `<div class="progress-wrap"><div class="progress-track"><div class="progress-bar" id="progress-bar"></div></div><span class="progress-text" id="progress-text">0 / ${state.scanFiles.length}</span></div>`;
  results.innerHTML = '';
  for (let index = 0; index < state.scanFiles.length; index += 1) {
    const file = state.scanFiles[index];
    $('#progress-text').textContent = `${index + 1} / ${state.scanFiles.length} · ${file.name}`;
    $('#progress-bar').style.width = `${(index / state.scanFiles.length) * 100}%`;
    try {
      const form = new FormData();
      form.append('image', file);
      const data = await api('/api/analyze', { method: 'POST', body: form });
      state.scanResults.push({ ...data, filename: file.name, preview: state.scanPreviews[index] });
    } catch (error) {
      state.scanResults.push({ filename: file.name, error: error.message, plates: [] });
    }
    renderScanResults();
    $('#progress-bar').style.width = `${((index + 1) / state.scanFiles.length) * 100}%`;
  }
  state.scanning = false;
  renderSelection();
  $('#progress-text').textContent = `Finished ${state.scanFiles.length} frame(s)`;
  $('#scan-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const failed = state.scanResults.filter((item) => item.error).length;
  toast(`Processed ${state.scanFiles.length} frame(s)${failed ? ` · ${failed} failed` : ''}.`, failed ? 'bad' : 'ok');
  refreshSystem();
  updateReviewCount();
}

function renderScanResults() {
  const root = $('#scan-results');
  if (!root) return;
  const plates = state.scanResults.flatMap((item) => item.plates || []);
  const withText = plates.filter((plate) => plate.ocr_prediction).length;
  const merged = state.scanResults.reduce((sum, item) => sum + (item.detection?.merged_pairs || 0), 0);
  const summary = state.scanResults.length ? `<div class="batch-bar">
    <span><strong>${state.scanResults.length}</strong> frame(s) · <strong>${plates.length}</strong> plate region(s) · <strong>${withText}</strong> readable${merged ? ` · <strong>${merged}</strong> split box(es) merged` : ''}</span>
    <button class="btn btn-ghost btn-small" id="copy-batch" type="button">Copy all readings</button>
    <button class="btn btn-ghost btn-small" id="json-batch" type="button">${ICONS.download} Batch JSON</button>
  </div>` : '';
  root.innerHTML = summary + state.scanResults.map((item, index) => scanResultCard(item, index)).join('');
  document.querySelector('.scan-console')?.classList.toggle('has-results', state.scanResults.length > 0);
  $('#copy-batch')?.addEventListener('click', () => {
    const text = plates.map((plate) => plate.ocr_prediction || 'UNREADABLE').join('\n');
    copyText(text, `${plates.length} reading(s) copied.`);
  });
  $('#json-batch')?.addEventListener('click', () => downloadJson(`autoguard-batch-${Date.now()}.json`, state.scanResults.map((item) => ({
    filename: item.filename,
    processing_ms: item.processing_ms,
    detection: item.detection,
    plates: (item.plates || []).map(({ crop_preview, enhanced_preview, rectified_preview, annotated_image, ...rest }) => rest),
  }))));
}

function scanResultCard(item, index) {
  if (item.error) {
    return `<article class="panel result-card"><div class="result-card-head"><div><h3>${esc(item.filename)}</h3><p>processing failed</p></div><span class="pill bad">Failed</span></div><div class="result-card-body"><div class="error-box">${esc(item.error)}</div></div></article>`;
  }
  const plates = item.plates || [];
  const annotated = item.annotated_preview || item.annotated_image
    ? `<img class="annotated" src="${item.annotated_preview || item.annotated_image}" alt="Annotated source frame" data-lightbox="1">`
    : '';
  const merged = item.detection?.merged_pairs || 0;
  return `<article class="panel result-card">
    <div class="result-card-head">
      <div><h3>${esc(item.filename)}</h3><p>${plates.length} region(s) · ${num(item.processing_ms)} ms · 1280 px · ${merged ? `${merged} merge(s)` : 'no merges'} · ${item.saved ? 'saved' : 'not saved'}</p></div>
      <span class="pill ${plates.length ? 'info' : 'warn'}">${plates.length ? 'Analyzed' : 'No plate found'}</span>
    </div>
    <div class="result-card-body">
      ${annotated}
      ${plates.length ? plates.map((plate, plateIndex) => plateResultHtml(plate, `${index}-${plateIndex}`)).join('') : emptyHtml('No plate region detected', 'The detector did not find a plate at this confidence. Try a clearer frame or a larger plate.', ICONS.alert)}
    </div>
  </article>`;
}

function plateResultHtml(plate, uid) {
  const flags = (plate.quality_flags || []).filter((flag) => String(flag).toLowerCase() !== 'none detected');
  const retryReasons = (plate.retry_reasons || []).map((reason) => String(reason).replaceAll('_', ' '));
  const pool = [...(plate.candidates || [])].sort((a, b) => Number(b.score) - Number(a.score));
  const chosen = pool.find((candidate) => candidate.text === plate.ocr_prediction);
  const candidates = (chosen ? [chosen, ...pool.filter((candidate) => candidate !== chosen)] : pool).slice(0, 4);
  return `<div class="plate-result">
    <div class="plate-visual">
      ${compareHtml(plate, `scan-${uid}`)}
      <div class="crop-meta"><span>box ${esc(plate.box_xyxy ? plate.box_xyxy.join(', ') : '—')}</span><span>${plate.plate_id ? `#${plate.plate_id}` : ''}</span></div>
    </div>
    <div class="plate-main">
      <div class="plate-reading">
        ${plateCells(plate.ocr_prediction)}
        <span class="read-sub">detector ${score(plate.detector_confidence)}<br>${plate.merged_detections > 1 ? `${plate.merged_detections} boxes merged` : 'single box'}</span>
        <div class="read-side">${ringHtml(plate.ocr_engine_score)}</div>
      </div>
      <div class="status-row">${statusPill(plate)} ${recoveryPill(plate.recovery_outcome)} ${flags.map((flag) => `<span class="pill warn">${esc(flag)}</span>`).join('')}${plate.edge_touching ? '<span class="pill warn">touches edge</span>' : ''}</div>
      ${traceHtml(plate)}
      ${candidates.length ? `<div class="candidate-chips">${candidates.map((candidate) => `<span class="candidate-chip ${candidate.text === plate.ocr_prediction ? 'best' : ''}" title="${candidate.text === plate.ocr_prediction ? 'Selected reading' : 'Rejected alternative'}">${esc(candidate.text || '∅')}<small>${score(candidate.score)}</small></span>`).join('')}</div>` : ''}
      <div class="verify-controls" style="justify-content:flex-end">
        ${plate.plate_id ? `<button class="btn btn-ghost btn-small" data-dossier="${plate.plate_id}" type="button">Open dossier</button>` : ''}
        <button class="btn btn-quiet btn-small" data-copy="${esc(plate.ocr_prediction || '')}" type="button">Copy</button>
      </div>
      ${plate.plate_id ? `<div class="verify-box" data-plate="${plate.plate_id}">
        <label for="verified-${uid}">Visually checked text ${plate.verified_text ? `· already ${esc(plate.verification_status)}` : '(required for confirm / correction)'}</label>
        <div class="verify-controls">
          <input class="field" id="verified-${uid}" value="${esc(plate.verified_text || '')}" maxlength="20" placeholder="Type after visual check">
          <button class="btn btn-ghost btn-small" data-verify="confirmed" type="button">Confirm</button>
          <button class="btn btn-primary btn-small" data-verify="corrected" type="button">Save correction</button>
          <button class="btn btn-danger btn-small" data-verify="rejected" type="button">Reject</button>
        </div>
      </div>` : ''}
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ dossier drawer */
async function openPlateDossier(plateId) {
  try {
    const plate = await api(`/api/plates/${plateId}`);
    openDrawer('Evidence dossier', plate.display_text || plate.ocr_text || 'Unreadable', dossierHtml(plate), dossierActions(plate));
    bindCompares($('#drawer-root'));
    bindDossier(plate);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function dossierHtml(plate) {
  const flags = (plate.quality_flags || []).filter((flag) => String(flag).toLowerCase() !== 'none detected');
  const candidates = plate.candidates || [];
  const delta = Number(plate.recovery_delta);
  return `
    <div class="drawer-section">
      <h3>Visual evidence</h3>
      ${compareHtml(plate, `dossier-${plate.id}`)}
      ${plate.enhanced_preview ? '' : '<p class="hint">This legacy record has no enhanced pass stored.</p>'}
    </div>
    <div class="drawer-section">
      <h3>Reading</h3>
      <div class="plate-reading">${plateCells(plate.display_text || plate.ocr_text)}<div class="read-side">${ringHtml(plate.ocr_score)}</div></div>
      <div class="status-row">${statusPill(plate)} ${recoveryPill(plate.recovery_outcome)} ${flags.map((flag) => `<span class="pill warn">${esc(flag)}</span>`).join('')}</div>
      <div class="bench-lines">
        <div class="bench-line"><span>Original first read</span><b>${esc(plate.original_text || '∅')} · ${score(plate.original_score)}</b></div>
        <div class="bench-line"><span>Recovery delta</span><b>${delta > 0.005 ? '+' : ''}${delta.toFixed(3)}</b></div>
        <div class="bench-line"><span>Selected pass</span><b>${esc(plate.selected_method || '—')}</b></div>
        <div class="bench-line"><span>Detector</span><b>${score(plate.detector_confidence)}</b></div>
        <div class="bench-line"><span>Brightness / contrast / blur</span><b>${score(plate.brightness)} / ${score(plate.contrast)} / ${score(plate.blur_score)}</b></div>
        <div class="bench-line"><span>Captured</span><b>${dateTime(plate.created_at)}</b></div>
        <div class="bench-line"><span>Source frame</span><b>${esc(plate.filename || '—')}</b></div>
      </div>
    </div>
    <div class="drawer-section"><h3>Pipeline trace</h3>${traceHtml(plate)}</div>
    ${candidates.length ? `<div class="drawer-section"><h3>OCR candidates</h3><div class="table-scroll"><table class="data-table"><thead><tr><th>Reading</th><th>Engine</th><th>Pass</th></tr></thead><tbody>${candidates.map((candidate) => `<tr><td class="mono">${esc(candidate.text || '∅')}</td><td>${score(candidate.score)}</td><td class="muted-2">${esc(candidate.method || '')}</td></tr>`).join('')}</tbody></table></div></div>` : ''}
    ${plate.verified_text ? `<div class="drawer-section"><h3>Human decision</h3><p class="hint">${esc(plate.verification_status)} · <b class="mono">${esc(plate.verified_text)}</b> · ${dateTime(plate.verified_at)}</p></div>` : ''}`;
}

function dossierActions(plate) {
  return `<div class="verify-box" data-plate="${plate.id}" style="flex:1 1 100%">
      <label for="dossier-verified">Visually checked text</label>
      <div class="verify-controls"><input class="field" id="dossier-verified" value="${esc(plate.verified_text || plate.ocr_text || '')}" maxlength="20"><button class="btn btn-ghost btn-small" data-verify="confirmed" type="button">Confirm</button><button class="btn btn-primary btn-small" data-verify="corrected" type="button">Correct</button></div>
    </div>
    <button class="btn btn-ghost btn-small" id="dossier-copy" type="button">${ICONS.copy} Copy</button>
    <button class="btn btn-ghost btn-small" id="dossier-json" type="button">${ICONS.download} JSON</button>
    <button class="btn btn-ghost btn-small" data-explain="${plate.id}" type="button">Explain</button>
    <button class="btn btn-danger btn-small" data-delete="${plate.id}" type="button">Delete</button>`;
}

function bindDossier(plate) {
  const root = $('#drawer-root');
  $('#dossier-copy')?.addEventListener('click', () => copyText(plate.ocr_text, 'Plate text copied.'));
  $('#dossier-json')?.addEventListener('click', () => downloadJson(`plate-${plate.id}.json`, plate));
  root.querySelector('[data-explain]')?.addEventListener('click', () => openExplain(plate.id));
  root.querySelector('[data-delete]')?.addEventListener('click', async () => {
    if (!window.confirm(`Delete plate #${plate.id} permanently?`)) return;
    try {
      await api(`/api/plates/${plate.id}`, { method: 'DELETE' });
      closeDrawer();
      toast('Plate removed.');
      updateReviewCount();
      if (state.route === 'archive') loadArchive(true);
      if (state.route === 'review') loadReview(true);
    } catch (error) { toast(error.message, 'bad'); }
  });
  const verifyBox = root.querySelector('.verify-box');
  root.querySelectorAll('[data-verify]').forEach((button) => button.addEventListener('click', async () => {
    await submitVerification(plate.id, button.dataset.verify, verifyBox);
    closeDrawer();
  }));
}

/* ------------------------------------------------------------------ review desk */
async function reviewView() {
  state.review = { status: state.review.status || 'review', query: '', items: [], total: 0, selectedId: null, loading: false };
  const view = $('#view');
  view.innerHTML = `
    <div class="filter-bar">
      <div class="seg" id="review-tabs">
        <button data-status="review" class="${state.review.status === 'review' ? 'active' : ''}">Review queue</button>
        <button data-status="recovered" class="${state.review.status === 'recovered' ? 'active' : ''}">Recovered</button>
        <button data-status="corrected" class="${state.review.status === 'corrected' ? 'active' : ''}">Corrected</button>
        <button data-status="all" class="${state.review.status === 'all' ? 'active' : ''}">All readings</button>
      </div>
      <div class="search-box">${ICONS.search}<input id="review-search" type="search" placeholder="Search plate, file or ID" autocomplete="off" aria-label="Search readings"></div>
      <span class="kbd-hint"><kbd>J</kbd><kbd>K</kbd> move · <kbd>C</kbd> confirm · <kbd>X</kbd> reject</span>
    </div>
    <div class="review-layout">
      <section class="review-list" id="review-list">${loadingHtml('Loading the queue…')}</section>
      <aside class="panel inspector" id="review-inspector"><div class="inspector-empty">Select a reading to inspect it.</div></aside>
    </div>`;
  $$('#review-tabs button').forEach((tab) => tab.addEventListener('click', () => {
    $$('#review-tabs button').forEach((item) => item.classList.toggle('active', item === tab));
    state.review.status = tab.dataset.status;
    state.review.query = '';
    state.review.selectedId = null;
    loadReview(true);
  }));
  let debounce = null;
  $('#review-search').addEventListener('input', (event) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.review.query = event.target.value.trim();
      state.review.selectedId = null;
      loadReview(true);
    }, 300);
  });
  await loadReview(true);
}

async function loadReview(reset = false) {
  const list = $('#review-list');
  if (!list) return;
  if (state.review.loading) return;
  state.review.loading = true;
  if (reset) list.innerHTML = loadingHtml('Loading plate records…');
  try {
    const query = new URLSearchParams({
      status: state.review.status,
      q: state.review.query,
      limit: '60',
      include_demo: state.includeDemo ? '1' : '0',
    });
    const data = await api(`/api/plates?${query.toString()}`);
    state.review.items = data.items || [];
    state.review.total = data.total || 0;
    if (reset || !state.review.items.some((item) => item.id === state.review.selectedId)) {
      state.review.selectedId = state.review.items[0]?.id || null;
    }
    renderReviewList();
    renderReviewInspector();
  } catch (error) {
    list.innerHTML = errorHtml(error);
  } finally {
    state.review.loading = false;
  }
}

function renderReviewList() {
  const list = $('#review-list');
  if (!list) return;
  const { items, status } = state.review;
  if (!items.length) {
    list.innerHTML = emptyHtml(
      status === 'review' ? 'The review queue is clear' : 'No records in this filter',
      status === 'review' ? 'Nothing needs a human decision right now.' : 'Try another filter or search term.',
      ICONS.check,
    );
    return;
  }
  list.innerHTML = items.map((plate) => {
    const flags = (plate.failure_reasons || []).slice(0, 3);
    return `<button class="review-item ${plate.id === state.review.selectedId ? 'active' : ''}" type="button" data-review-id="${plate.id}">
      <span class="review-thumb">${plate.crop_preview ? `<img src="${plate.crop_preview}" alt="">` : plateChip(plate.display_text, !plate.ocr_text)}</span>
      <span class="review-main">
        <span class="review-title">${plateChip(plate.display_text, !plate.ocr_text)} ${statusPill(plate)}</span>
        <span class="review-meta">${esc(plate.filename || '—')} · ${timeAgo(plate.created_at)} · ${plate.is_demo ? 'demo' : 'live'}</span>
        <span class="review-reasons">${flags.map((reason) => `<span class="pill warn">${esc(reason)}</span>`).join('') || '<span class="pill">no strong flag</span>'}</span>
      </span>
      <span class="review-score"><b>${score(plate.ocr_score)}</b></span>
    </button>`;
  }).join('');
  $$('[data-review-id]', list).forEach((button) => button.addEventListener('click', () => {
    state.review.selectedId = Number(button.dataset.reviewId);
    renderReviewList();
    renderReviewInspector();
  }));
}

function renderReviewInspector() {
  const root = $('#review-inspector');
  if (!root) return;
  const plate = state.review.items.find((item) => item.id === state.review.selectedId);
  if (!plate) {
    root.innerHTML = `<div class="inspector-empty">Select a reading to inspect it.</div>`;
    return;
  }
  const flags = (plate.failure_reasons || []);
  root.innerHTML = `
    <div class="inspector-head">
      <div><h2>${esc(plate.display_text || plate.ocr_text || 'UNREADABLE')}</h2><p>${esc(plate.filename || '—')} · ${dateTime(plate.created_at)}</p></div>
      ${statusPill(plate)}
    </div>
    <div class="inspector-body">
      ${compareHtml(plate, `review-${plate.id}`)}
      <div class="status-row">${recoveryPill(plate.recovery_outcome)}${flags.map((flag) => `<span class="pill warn">${esc(flag)}</span>`).join('')}${plate.is_demo ? '<span class="pill violet">demo</span>' : ''}</div>
      <div class="bench-lines">
        <div class="bench-line"><span>Engine score</span><b>${score(plate.ocr_score)}</b></div>
        <div class="bench-line"><span>First read</span><b>${esc(plate.original_text || '∅')} · ${score(plate.original_score)}</b></div>
        <div class="bench-line"><span>Selected pass</span><b>${esc(plate.selected_method || '—')}</b></div>
        <div class="bench-line"><span>Detector</span><b>${score(plate.detector_confidence)}</b></div>
      </div>
      ${traceHtml(plate)}
    </div>
    <div class="inspector-actions">
      <div class="verify-box" data-plate="${plate.id}">
        <label for="review-verified">Visually checked text</label>
        <div class="verify-controls">
          <input class="field" id="review-verified" value="${esc(plate.verified_text || plate.ocr_text || '')}" maxlength="20">
          <div class="row">
            <button class="btn btn-ghost btn-small" data-verify="confirmed" type="button">Confirm</button>
            <button class="btn btn-primary btn-small" data-verify="corrected" type="button">Correct</button>
            <button class="btn btn-danger btn-small" data-verify="rejected" type="button">Reject</button>
            <button class="btn btn-quiet btn-small" data-explain="${plate.id}" type="button">Explain</button>
          </div>
        </div>
      </div>
    </div>`;
  bindCompares(root);
  root.querySelector('[data-explain]')?.addEventListener('click', () => openExplain(plate.id));
  const box = root.querySelector('.verify-box');
  root.querySelectorAll('[data-verify]').forEach((button) => button.addEventListener('click', () => submitVerification(plate.id, button.dataset.verify, box)));
}

function reviewNavigate(step) {
  const items = state.review.items;
  if (!items.length) return;
  const index = Math.max(0, items.findIndex((item) => item.id === state.review.selectedId));
  const next = items[(index + step + items.length) % items.length];
  state.review.selectedId = next.id;
  renderReviewList();
  renderReviewInspector();
}

function reviewQuickVerify(kind) {
  const plate = state.review.items.find((item) => item.id === state.review.selectedId);
  if (!plate) return;
  const input = $('#review-verified');
  const text = input?.value.trim() || '';
  if (kind !== 'rejected' && !text) { toast('The checked text is empty.', 'bad'); input?.focus(); return; }
  submitVerification(plate.id, kind, $('.inspector .verify-box'));
}

/* ------------------------------------------------------------------ archive */
async function archiveView() {
  state.archive = { status: state.archive.status || 'all', query: '', items: [], total: 0, hasMore: false, loading: false };
  const view = $('#view');
  view.innerHTML = `
    <div class="toolbar">
      <div class="seg" id="archive-tabs">
        <button data-status="all" class="${state.archive.status === 'all' ? 'active' : ''}">All</button>
        <button data-status="review" class="${state.archive.status === 'review' ? 'active' : ''}">Needs review</button>
        <button data-status="recovered" class="${state.archive.status === 'recovered' ? 'active' : ''}">Recovered</button>
        <button data-status="corrected" class="${state.archive.status === 'corrected' ? 'active' : ''}">Corrected</button>
      </div>
      <div class="search-box">${ICONS.search}<input id="archive-search" type="search" placeholder="Search plate, file or ID" autocomplete="off" aria-label="Search archive"></div>
      <button class="btn btn-ghost btn-small" id="archive-export" type="button">${ICONS.download} Export CSV</button>
    </div>
    <section class="panel ledger">
      <div class="ledger-head"><span>Plate</span><span>Status</span><span>Engine</span><span>Source frame</span><span class="when">Captured</span><span></span></div>
      <div id="archive-body">${loadingHtml('Opening the evidence ledger…')}</div>
    </section>`;
  $$('#archive-tabs button').forEach((tab) => tab.addEventListener('click', () => {
    $$('#archive-tabs button').forEach((item) => item.classList.toggle('active', item === tab));
    state.archive.status = tab.dataset.status;
    state.archive.query = '';
    loadArchive(true);
  }));
  let debounce = null;
  $('#archive-search').addEventListener('input', (event) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.archive.query = event.target.value.trim(); loadArchive(true); }, 300);
  });
  $('#archive-export')?.addEventListener('click', exportLedger);
  $('#archive-body').addEventListener('click', (event) => {
    const open = event.target.closest('[data-plate-open]');
    if (open) openPlateDossier(Number(open.dataset.plateOpen));
    if (event.target.closest('#load-more')) { state.archive.offset = state.archive.items.length; loadArchive(false); }
  });
  await loadArchive(true);
}

async function loadArchive(reset = false) {
  const body = $('#archive-body');
  if (!body) return;
  if (state.archive.loading) return;
  state.archive.loading = true;
  if (reset) body.innerHTML = loadingHtml('Reading the ledger…');
  try {
    const offset = reset ? 0 : state.archive.items.length;
    const query = new URLSearchParams({
      status: state.archive.status,
      q: state.archive.query,
      limit: '30',
      offset: String(offset),
      include_demo: state.includeDemo ? '1' : '0',
    });
    const data = await api(`/api/plates?${query.toString()}`);
    state.archive.items = reset ? (data.items || []) : [...state.archive.items, ...(data.items || [])];
    state.archive.total = data.total || 0;
    state.archive.hasMore = Boolean(data.has_more);
    renderArchive();
  } catch (error) {
    body.innerHTML = errorHtml(error);
  } finally {
    state.archive.loading = false;
  }
}

function renderArchive() {
  const body = $('#archive-body');
  if (!body) return;
  if (!state.archive.items.length) {
    body.innerHTML = emptyHtml('No records match', 'Clear the filters or scan a new frame.', ICONS.db);
    body.style.padding = '16px';
    return;
  }
  body.style.padding = '';
  body.innerHTML = state.archive.items.map((plate) => `
    <div class="ledger-row" data-plate-open="${plate.id}" role="button" tabindex="0">
      <span>${plateChip(plate.display_text, !plate.ocr_text)} ${plate.is_demo ? '<span class="pill violet" style="font-size:.55rem">demo</span>' : ''}</span>
      <span class="status-cell">${statusPill(plate)}</span>
      <span>${scoreBar(plate.ocr_score)}</span>
      <span class="file" title="${esc(plate.filename || '')}">${esc(plate.filename || '—')}</span>
      <span class="when">${timeAgo(plate.created_at)}</span>
      <span><button class="row-link" type="button" data-plate-open="${plate.id}">Open</button></span>
    </div>`).join('') + (state.archive.hasMore ? `<div class="pager"><button class="btn btn-ghost btn-small" id="load-more" type="button">Load more · ${num(state.archive.total - state.archive.items.length)} left</button></div>` : `<div class="pager hint">${num(state.archive.total)} record(s) · end of ledger</div>`);
  $$('[data-plate-open]', body).forEach((row) => row.addEventListener('keydown', (event) => { if (event.key === 'Enter') openPlateDossier(Number(row.dataset.plateOpen)); }));
}

function exportLedger() {
  location.href = `/api/analytics/export?days=365&include_demo=${state.includeDemo ? '1' : '0'}`;
}

/* ------------------------------------------------------------------ intelligence */
function curveAt(curve, threshold) {
  const points = curve || [];
  if (!points.length) return null;
  return points.reduce((best, point) => (Math.abs(point.threshold - threshold) < Math.abs(best.threshold - threshold) ? point : best));
}

function riskChart(curve, threshold) {
  const validation = curve.validation_curve || [];
  const test = curve.test_curve || [];
  if (!validation.length && !test.length) return `<div class="chart-empty">No calibration curve has been generated yet.</div>`;
  const width = 720, height = 320;
  const pad = { top: 18, right: 18, bottom: 40, left: 46 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const yMin = 0.8, yMax = 1.0;
  const xMin = 0.35, xMax = 0.82;
  const x = (coverage) => pad.left + ((Math.max(xMin, Math.min(xMax, coverage)) - xMin) / (xMax - xMin)) * innerW;
  const y = (accuracy) => pad.top + innerH - ((Math.max(yMin, Math.min(yMax, accuracy)) - yMin) / (yMax - yMin)) * innerH;
  const grid = [0.8, 0.85, 0.9, 0.95, 1].map((value) => {
    const yy = y(value);
    return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" class="chart-grid-line"/><text x="${pad.left - 8}" y="${yy + 3}" text-anchor="end" class="chart-axis-label">${Math.round(value * 100)}%</text>`;
  }).join('');
  const xTicks = [0.4, 0.5, 0.6, 0.7, 0.8].map((value) => `<text x="${x(value)}" y="${height - 14}" text-anchor="middle" class="chart-axis-label">${Math.round(value * 100)}%</text>`).join('');
  const target = curve.target_accuracy || 0.92;
  const targetLine = `<line x1="${pad.left}" y1="${y(target)}" x2="${width - pad.right}" y2="${y(target)}" class="risk-target-line"/><text x="${width - pad.right - 4}" y="${y(target) - 6}" text-anchor="end" class="chart-axis-label">target ${Math.round(target * 100)}%</text>`;
  const line = (points) => points.map((point, index) => `${index ? 'L' : 'M'} ${x(point.coverage).toFixed(1)} ${y(point.selective_accuracy).toFixed(1)}`).join(' ');
  const valPoint = curveAt(validation, threshold);
  const testPoint = curveAt(test, threshold);
  const marker = (point, color, label) => point
    ? `<circle cx="${x(point.coverage)}" cy="${y(point.selective_accuracy)}" r="5" fill="${color}" stroke="var(--card)" stroke-width="2"><title>${esc(label)}: ${pct(point.selective_accuracy)} at ${pct(point.coverage)} coverage</title></circle>`
    : '';
  const recommended = curve.recommended?.threshold;
  const recommendedMarker = validation.length && recommended != null
    ? `<circle cx="${x(curve.recommended.coverage)}" cy="${y(curve.recommended.selective_accuracy)}" r="8" fill="none" stroke="var(--mint)" stroke-width="1.6" stroke-dasharray="3 3"><title>Validation-selected threshold ${Number(recommended).toFixed(2)}</title></circle>`
    : '';
  return `<svg class="chart-svg risk-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Risk-coverage curve for validation and test splits">
    ${grid}${xTicks}${targetLine}
    <path d="${line(validation)}" class="risk-line val"/>
    <path d="${line(test)}" class="risk-line test"/>
    ${recommendedMarker}${marker(valPoint, 'var(--mint)', 'Validation')}${marker(testPoint, 'var(--indigo-2)', 'Test')}
    <text x="${pad.left + innerW / 2}" y="${height - 1}" text-anchor="middle" class="chart-axis-label">coverage · share accepted without human review</text>
  </svg>`;
}

function gateReadout(curve, threshold) {
  const validation = curveAt(curve.validation_curve, threshold);
  const test = curveAt(curve.test_curve, threshold);
  const targetError = curve.target_error ?? 0.08;
  return `
    <div class="gate-metric-grid">
      <div class="gate-metric"><span>Validation</span><strong>${validation ? pct(validation.selective_accuracy) : '—'}</strong><small>${validation ? pct(validation.coverage) + ' coverage' : 'no point'}</small></div>
      <div class="gate-metric"><span>Test accuracy</span><strong>${test ? pct(test.selective_accuracy) : '—'}</strong><small>${test ? pct(test.coverage) + ' coverage' : 'no point'}</small></div>
      <div class="gate-metric"><span>Test error</span><strong>${test ? pct(test.selective_error) : '—'}</strong><small>ceiling ${pct(targetError)}</small></div>
      <div class="gate-metric"><span>Risk budget</span>${test ? (test.selective_error <= targetError ? '<strong class="ok-text">Held</strong><small>inside the ceiling</small>' : '<strong class="bad-text">Breached</strong><small>above the ceiling</small>') : '<strong>—</strong><small>no point</small>'}</div>
    </div>`;
}

async function intelView() {
  const view = $('#view');
  if (!state.gateCurve && !state.gateError) {
    view.innerHTML = loadingHtml('Loading the calibrated risk curve…');
    try {
      state.gateCurve = await api('/api/analytics/gate-curve');
    } catch (error) {
      state.gateError = error.message || 'Calibration report unavailable.';
    }
  }
  view.innerHTML = `
    <div class="intel-tabs" id="intel-tabs">
      <button type="button" data-intel="gate" class="${state.intelTab === 'gate' ? 'active' : ''}">Review gate</button>
      <button type="button" data-intel="restore" class="${state.intelTab === 'restore' ? 'active' : ''}">Restoration lab</button>
      <button type="button" data-intel="data" class="${state.intelTab === 'data' ? 'active' : ''}">Training &amp; data</button>
    </div>
    <div id="intel-content"></div>`;
  $$('#intel-tabs button').forEach((tab) => tab.addEventListener('click', () => {
    state.intelTab = tab.dataset.intel;
    history.replaceState(null, '', `#/intel/${state.intelTab}`);
    $$('#intel-tabs button').forEach((item) => item.classList.toggle('active', item === tab));
    renderIntelContent();
  }));
  renderIntelContent();
}

function renderIntelContent() {
  const root = $('#intel-content');
  if (!root) return;
  if (state.intelTab === 'restore') { renderRestoreTab(root); return; }
  if (state.intelTab === 'data') { renderDataTab(root); return; }
  if (!state.gateCurve) {
    root.innerHTML = `
      <div class="panel panel-pad">
        <div class="empty-state">
          ${ICONS.chart || ''}
          <strong>The calibration report is missing</strong>
          <p>${esc(state.gateError || 'Run the gate calibration to populate the risk–coverage explorer.')}</p>
          <p class="hint" style="margin-top:10px"><code>python scripts/calibrate_gate.py</code> then reload this page.</p>
        </div>
      </div>`;
    return;
  }
  const curve = state.gateCurve;
  const recommended = curve.recommended?.threshold ?? 0.81;
  const targetError = curve.target_error ?? 0.08;
  const points = [0.6, 0.7, 0.75, 0.8, recommended, 0.85, 0.9].filter((value, index, list) => list.indexOf(value) === index).sort((a, b) => a - b);
  const rows = points.map((value) => {
    const val = curveAt(curve.validation_curve, value);
    const test = curveAt(curve.test_curve, value);
    const isRecommended = Math.abs(value - recommended) < 0.004;
    return `<tr class="${isRecommended ? 'risk-row-recommended' : ''}">
      <td class="mono">${isRecommended ? '<span class="risk-marker" title="Selected on validation">●</span> ' : ''}${value.toFixed(2)}</td>
      <td>${val ? pct(val.coverage) : '—'}</td>
      <td>${test ? pct(test.coverage) : '—'}</td>
      <td>${test ? pct(test.selective_accuracy) : '—'}</td>
      <td>${test ? `<span class="pill ${test.selective_error <= targetError ? 'ok' : 'warn'}">${pct(test.selective_error)}</span>` : '—'}</td>
    </tr>`;
  }).join('');
  const ocr = state.benchmark?.ocr || {};
  root.innerHTML = `
    <div class="intel-grid gate-grid">
      <section class="panel panel-pad gate-main">
        <div class="panel-head">
          <div><h2>Risk–coverage explorer</h2></div>
          <span class="pill ${curve.risk_target_met_on_test ? 'ok' : 'warn'}">${curve.risk_target_met_on_test ? 'Risk target met' : 'Risk target missed'}</span>
        </div>
        <div class="gate-current">
          <div class="gate-threshold"><span>Score threshold</span><strong id="gate-threshold-value">${Number(recommended).toFixed(2)}</strong></div>
          <input class="range" id="gate-threshold" type="range" min="0.50" max="0.95" step="0.01" value="${Number(recommended)}" aria-label="Review gate score threshold">
          <div class="gate-scale"><span>0.50 · more coverage</span><span>0.95 · more precision</span></div>
        </div>
        <div id="gate-readout">${gateReadout(curve, recommended)}</div>
        <div id="gate-chart">${riskChart(curve, recommended)}</div>
        <div class="chart-legend">
          <span><i class="swatch mint"></i>Validation curve</span>
          <span><i class="swatch cyan"></i>Test curve</span>
          <span><i class="swatch ghost"></i>Selected threshold</span>
          <span><i class="swatch dash"></i>${pct(curve.target_accuracy || 0.92)} target</span>
        </div>
      </section>
      <aside class="intel-side">
        <section class="panel panel-pad">
          <div class="panel-head"><div><h2>Review workload</h2></div></div>
          <div class="bench-lines">
            <div class="bench-line"><span>Auto-passed</span><b>${per100(ocr.workload?.auto_pass_per_100)}</b></div>
            <div class="bench-line"><span>Sent to human review</span><b>${per100(ocr.workload?.review_per_100)}</b></div>
            <div class="bench-line"><span>Residual errors</span><b>${per100(ocr.workload?.residual_errors_per_100)}</b></div>
          </div>
        </section>
        <section class="panel table-panel">
          <div class="panel-head" style="padding:14px 16px 0;margin:0"><div><h2>Operating points</h2></div></div>
          <div class="table-scroll" style="padding:8px 6px 12px"><table class="data-table"><thead><tr><th>Gate</th><th>Val cov.</th><th>Test cov.</th><th>Test acc.</th><th>Err.</th></tr></thead><tbody>${rows}</tbody></table></div>
        </section>
      </aside>
    </div>`;
  const slider = $('#gate-threshold');
  slider?.addEventListener('input', () => {
    const value = Number(slider.value);
    $('#gate-threshold-value').textContent = value.toFixed(2);
    $('#gate-readout').innerHTML = gateReadout(curve, value);
    $('#gate-chart').innerHTML = riskChart(curve, value);
  });
}

function renderDataTab(root) {
  const benchmark = state.benchmark || {};
  const training = benchmark.training || {};
  const external = benchmark.external_iurs || {};
  const ocr = benchmark.ocr || {};
  const models = benchmark.models || {};
  const composition = benchmark.composition || {};
  const vote = benchmark.frame_vote || {};
  const votePlates = vote.all_plates || {};
  const voteMulti = vote.multi_frame_plates || {};
  const voteIurs = vote.iurs?.all_plates || {};
  const train = training.train || {};
  const prepared = Number(train.origin?.['data/prepared_corrected'] || 0);
  const iurs = Number(train.origin?.['data/iurs_plates'] || 0);
  const total = prepared + iurs || 1;
  const splitRows = ['train', 'val', 'test'].map((name) => {
    const entry = training[name];
    if (!entry) return '';
    const origin = entry.origin || {};
    return `<tr><td class="mono">${name}</td><td><b>${num(entry.rows)}</b></td><td>${num(origin['data/prepared_corrected'] || 0)}</td><td>${num(origin['data/iurs_plates'] || 0)}</td></tr>`;
  }).join('');
  const checkpoint = (label, meta, active) => {
    if (!meta || !meta.file) return '';
    return `<div class="checkpoint-row">
      <span class="checkpoint-icon">${label}</span>
      <div><strong>${esc(meta.file)}</strong><small>${num(meta.size_mb)} MB · ${esc(String(meta.modified || '').replace('T', ' '))}</small></div>
      <span class="pill ${active ? 'ok' : ''}">${active ? 'active' : 'available'}</span>
    </div>`;
  };
  root.innerHTML = `
    <div class="data-grid">
      <section class="panel panel-pad">
        <div class="panel-head">
          <div><h2>Training composition</h2></div>
        </div>
        <div class="tile-row">
          <article class="stat-tile">
            <span class="tile-icon">${ICONS.db}</span>
            <div class="tile-copy"><span class="tile-label">Training rows</span><b>${train.rows ? num(train.rows) : '—'}</b></div>
          </article>
          <article class="stat-tile teal">
            <span class="tile-icon">${ICONS.scan}</span>
            <div class="tile-copy"><span class="tile-label">IURS rows</span><b>${iurs ? num(iurs) : '—'}</b></div>
          </article>
        </div>
        <div class="split-bar" aria-label="Training origin split">
          <span class="split-seg a" style="width:${(prepared / total) * 100}%"></span>
          <span class="split-seg b" style="width:${(iurs / total) * 100}%"></span>
        </div>
        <div class="split-legend">
          <span><i class="a"></i>Prepared crops · ${num(prepared)}</span>
          <span><i class="b"></i>IURS plates · ${num(iurs)}</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr><th>Split</th><th>Rows</th><th>Prepared</th><th>IURS</th></tr></thead>
            <tbody>${splitRows || '<tr><td colspan="4" class="muted">Training summary not found.</td></tr>'}</tbody>
          </table>
        </div>
        <div class="panel-head" style="margin:18px 0 8px"><div><h2>What the retrain bought</h2></div></div>
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr><th>Domain</th><th>Crops</th><th>Baseline exact</th><th>Shipped exact</th><th>Gain</th><th>Baseline CER</th><th>Shipped CER</th></tr></thead>
            <tbody>
              <tr><td>Internal prepared</td><td>${num(ocr.samples || 0)}</td><td>${pct(ocr.baseline_exact_match)}</td><td><b>${pct(ocr.exact_match)}</b></td><td class="ok-text">${ocr.samples ? `+${((ocr.exact_match - ocr.baseline_exact_match) * 100).toFixed(1)} pts` : '—'}</td><td>${pct(ocr.baseline_cer)}</td><td><b>${pct(ocr.cer)}</b></td></tr>
              <tr><td>IURS external</td><td>${num(external.samples || 0)}</td><td>${pct(external.baseline_exact_match)}</td><td><b>${pct(external.exact_match)}</b></td><td class="ok-text">${external.samples ? `+${((external.exact_match - external.baseline_exact_match) * 100).toFixed(1)} pts` : '—'}</td><td>${pct(external.baseline_cer)}</td><td><b>${pct(external.cer)}</b></td></tr>
            </tbody>
          </table>
        </div>
        <div class="panel-head" style="margin:18px 0 8px"><div><h2>Shipped checkpoints</h2></div><span class="pill ok">On disk</span></div>
        ${checkpoint('OCR', models.ocr, true)}
        ${checkpoint('DET', models.detector, true)}
      </section>
      <aside class="intel-side">
        <section class="panel panel-pad">
          <div class="panel-head"><div><h2>Domain check</h2></div></div>
          <div class="domain-row">
            <div class="domain-name"><strong>Internal prepared</strong><span>${num(ocr.samples || 0)} crops</span></div>
            <div><b>${pct(ocr.exact_match)}</b><span class="hint"> exact</span></div>
            <div><b>${pct(ocr.cer)}</b><span class="hint"> CER</span></div>
          </div>
          <div class="domain-row">
            <div class="domain-name"><strong>IURS external</strong><span>${num(external.samples || 0)} crops</span></div>
            <div><b>${pct(external.exact_match)}</b><span class="hint"> exact</span></div>
            <div><b>${pct(external.cer)}</b><span class="hint"> CER</span></div>
          </div>
        </section>
        <section class="panel panel-pad">
          <div class="panel-head"><div><h2>Test composition</h2></div><span class="pill info">${num(composition.unique_plates)} plates</span></div>
          <div class="bench-lines">
            <div class="bench-line"><span>Crops / unique plates</span><b>${num(composition.samples)} / ${num(composition.unique_plates)}</b></div>
            <div class="bench-line"><span>Multi-crop plates</span><b>${num(voteMulti.plates)} · ${num(voteMulti.frames)} crops</b></div>
            <div class="bench-line"><span>Largest plate ${esc(composition.dominant_plate || '')}</span><b>${num(composition.dominant_plate_crops)} · ${pct(composition.dominant_share_of_test)}</b></div>
            <div class="bench-line"><span>Exact without largest plate</span><b>${pct(composition.frame_exact_match_without_dominant)}</b></div>
            <div class="bench-line"><span>Plate-macro (95% CI)</span><b>${pct(composition.plate_macro_exact_match)} · ${pctCi(composition.plate_macro_ci95)}</b></div>
          </div>
        </section>
        <section class="panel panel-pad">
          <div class="panel-head"><div><h2>Repeat-read voting</h2></div><span class="pill ${votePlates.majority_vote ? 'ok' : ''}">${votePlates.majority_vote ? `+${((votePlates.majority_vote.rate - votePlates.first_frame.rate) * 100).toFixed(1)} pts` : 'Not run'}</span></div>
          <div class="bench-lines">
            <div class="bench-line"><span>First crop only</span><b>${votePlates.first_frame ? pct(votePlates.first_frame.rate) : '—'}</b></div>
            <div class="bench-line"><span>Majority vote</span><b>${votePlates.majority_vote ? pct(votePlates.majority_vote.rate) : '—'}</b></div>
            <div class="bench-line"><span>Any crop correct</span><b>${votePlates.any_crop ? pct(votePlates.any_crop.rate) : '—'}</b></div>
            <div class="bench-line"><span>Multi-crop first → vote</span><b>${voteMulti.first_frame ? `${pct(voteMulti.first_frame.rate)} → ${pct(voteMulti.majority_vote.rate)}` : '—'}</b></div>
            <div class="bench-line"><span>IURS block vote</span><b>${voteIurs.majority_vote ? pct(voteIurs.majority_vote.rate) : '—'}</b></div>
          </div>
        </section>
      </aside>
    </div>`;
}


function renderRestoreTab(root) {
  root.innerHTML = `
    <div class="restore-layout">
      <section class="panel panel-pad">
        <div class="panel-head">
          <div><h2>Restoration lab</h2></div>
          <span class="pill violet">Experimental</span>
        </div>
        <div class="restore-drop" id="restore-drop" tabindex="0" role="button" aria-label="Choose a plate crop">
          <input id="restore-file" type="file" accept="image/jpeg,image/png,image/webp,image/bmp">
          <div class="drop-icon">${ICONS.image}</div>
          <strong>Drop a low-resolution plate crop</strong>
          <p class="hint">Click to browse</p>
        </div>
        <div id="restore-preview"></div>
        <div class="restore-actions">
          <button class="btn btn-primary" id="restore-run" type="button" disabled>Restore plate</button>
          <span class="hint" id="restore-status">Choose a crop to begin.</span>
        </div>
      </section>
      <aside class="panel panel-pad">
        <div class="panel-head"><div><h2>What this tests</h2></div></div>
        <div class="how-step pipeline-step"><div class="step-head"><strong>Bicubic 4×</strong></div><span>Classic upscaling baseline for comparison.</span></div>
        <div class="how-step pipeline-step"><div class="step-head"><strong>Real-ESRGAN 4×</strong></div><span>Learned super-resolution on the same crop.</span></div>
        <div class="how-step pipeline-step"><div class="step-head"><strong>RefineNet</strong></div><span>Residual pass trained on real plate crops.</span></div>
        <div class="how-step pipeline-step"><div class="step-head"><strong>OCR before / after</strong></div><span>Compares the read before and after restoration.</span></div>
      </aside>
    </div>
    <div id="restore-results">${state.restoreResult ? renderRestoration(state.restoreResult) : ''}</div>`;
  state.restoreFile = null;
  const drop = $('#restore-drop');
  const input = $('#restore-file');
  drop.addEventListener('click', (event) => { if (event.target.tagName !== 'INPUT') input.click(); });
  drop.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); } });
  input.addEventListener('change', () => setRestoreFile(input.files[0]));
  ['dragenter', 'dragover'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.add('dragging'); }));
  ['dragleave', 'drop'].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.remove('dragging'); }));
  drop.addEventListener('drop', (event) => setRestoreFile(event.dataTransfer.files[0]));
  $('#restore-run')?.addEventListener('click', runRestore);
}

function setRestoreFile(file) {
  const looksLikeImage = file && (file.type.startsWith('image/') || /\.(jpe?g|png|webp|bmp)$/i.test(file.name));
  if (!looksLikeImage) { toast('Choose a JPG, PNG, WEBP or BMP image.', 'bad'); return; }
  state.restoreFile = file;
  if (state.restorePreview) URL.revokeObjectURL(state.restorePreview);
  state.restorePreview = URL.createObjectURL(file);
  const root = $('#restore-preview');
  if (root) root.innerHTML = `<div class="restore-preview"><img src="${state.restorePreview}" alt="Selected plate crop"><div><strong>${esc(file.name)}</strong><p>${Math.round(file.size / 1024)} KB · ready for 4× restoration</p></div></div>`;
  const button = $('#restore-run');
  if (button) button.disabled = false;
  const status = $('#restore-status');
  if (status) status.textContent = 'Ready. This may take a few seconds on CPU.';
}

async function runRestore() {
  if (!state.restoreFile) return;
  const button = $('#restore-run');
  const status = $('#restore-status');
  const results = $('#restore-results');
  button.disabled = true;
  status.textContent = 'Loading models and restoring… first run can take 10–20 seconds.';
  results.innerHTML = `<div class="panel panel-pad" style="margin-top:16px">${loadingHtml('Running Real-ESRGAN and RefineNet…')}</div>`;
  try {
    const form = new FormData();
    form.append('image', state.restoreFile);
    const data = await api('/api/restore', { method: 'POST', body: form });
    state.restoreResult = data;
    results.innerHTML = renderRestoration(data);
    status.textContent = `Restored in ${num(Math.round(data.processing_ms))} ms.`;
  } catch (error) {
    results.innerHTML = errorHtml(error);
    status.textContent = 'Restoration failed.';
  } finally {
    button.disabled = false;
  }
}

function renderRestoration(data) {
  const ocr = data.ocr || {};
  const sourceText = ocr.source?.text || '—';
  const sourceScore = ocr.source?.score != null ? score(ocr.source.score) : '—';
  const cards = (data.variants || []).map((item) => {
    const reading = ocr[item.name] || {};
    return `<article class="panel restore-card">
      <div class="restore-card-head"><div><h3>${esc(item.label)}</h3><p>${num(item.width)} × ${num(item.height)} · sharpness ${num(item.sharpness)}</p></div><span class="pill ${item.name === 'refined' ? 'violet' : 'info'}">${esc(item.name)}</span></div>
      <div class="restore-card-body"><img src="${item.data_url}" alt="${esc(item.label)}"></div>
      <div class="restore-card-foot"><div><span>OCR reading</span><strong class="mono">${esc(reading.text || 'Unreadable')}</strong></div><div><span>Engine score</span><strong>${reading.score != null ? score(reading.score) : '—'}</strong></div></div>
    </article>`;
  }).join('');
  return `<div class="panel panel-pad restore-result-panel">
    <div class="panel-head"><div><h2>Restoration comparison</h2></div><a class="btn btn-ghost btn-small" href="#/scan">Back to scan</a></div>
    <div class="restore-source">
      <div class="restore-source-image"><img src="${data.source.data_url}" alt="Original plate crop"></div>
      <div><span class="eyebrow">ORIGINAL INPUT</span><h3>${num(data.source.width)} × ${num(data.source.height)} · sharpness ${num(data.source.sharpness)}</h3><p>OCR: <strong class="mono">${esc(sourceText)}</strong> · engine ${sourceScore}</p><div class="status-row" style="margin-top:7px"><span class="pill ${data.refiner_available ? 'ok' : ''}">${data.refiner_available ? 'RefineNet loaded' : 'RefineNet not trained yet'}</span><span class="pill">4× output</span></div></div>
    </div>
    <div class="restore-grid">${cards}</div>
  </div>`;
}

/* ------------------------------------------------------------------ assistant */
async function assistantView() {
  const view = $('#view');
  view.innerHTML = loadingHtml('Opening the grounded assistant…');
  try {
    state.assistantStatus = await api('/api/assistant/status');
    try {
      const plates = await api(`/api/plates?limit=4&include_demo=${state.includeDemo ? '1' : '0'}`);
      state.assistantPlates = plates.items || [];
    } catch (error) {
      state.assistantPlates = [];
    }
    if (state.chatSession) {
      try {
        const history = await api(`/api/assistant/session/${state.chatSession}`);
        state.chatMessages = (history.messages || []).map((message) => ({
          role: message.role,
          content: message.content,
          meta: message.meta || {},
          created_at: message.created_at,
        }));
      } catch (error) {
        state.chatSession = null;
        localStorage.removeItem('autoguard_chat_session');
        state.chatMessages = [];
      }
    }
    renderAssistant(view);
  } catch (error) {
    view.innerHTML = errorHtml(error);
  }
}

function renderAssistant(view) {
  const status = state.assistantStatus || { llm: { available: false, provider: 'local', model: '' }, knowledge_chunks: 0 };
  const modeLabel = status.llm?.available ? `${esc(status.llm.provider)} · ${esc(status.llm.model)}` : 'Local grounded mode';
  view.innerHTML = `
    <div class="assistant-layout">
      <section class="panel chat-panel">
        <div class="chat-head">
          <div class="chat-identity">
            <span class="chat-avatar">${ICONS.chat}</span>
            <div><strong>AutoGuard assistant</strong></div>
          </div>
          <button class="btn btn-ghost btn-small" id="new-chat" type="button" style="margin-left:auto">New chat</button>
        </div>
        <div class="chat-messages" id="chat-messages"></div>
        <div class="chat-suggestions" id="chat-suggestions"></div>
        <div class="chat-composer">
          <div class="composer-box">
            <textarea id="chat-input" rows="1" placeholder="Ask about counts, a plate ID, a failure, or how the system works…" aria-label="Message the assistant"></textarea>
            <button class="composer-send" id="chat-send" type="button" aria-label="Send message">${ICONS.send}</button>
          </div>
          <div class="composer-note"><span>Enter to send · Shift+Enter for a new line</span></div>
        </div>
      </section>
      <aside class="assistant-side">
        ${llmPanelHtml(status)}
        ${evidencePanelHtml()}
        ${knowledgePanelHtml()}
      </aside>
    </div>`;
  renderChatMessages();
  bindAssistantEvents();
  bindLlmPanel();
  scheduleAutoConnect();
  $$('[data-evidence]', view).forEach((button) => button.addEventListener('click', () => openPlateDossier(Number(button.dataset.evidence))));
}

const KNOWLEDGE_DOCS = [
  ['01', 'System overview'],
  ['02', 'Failure taxonomy'],
  ['03', 'Preprocessing'],
  ['04', 'Recovery policy'],
  ['05', 'Metrics & ethics'],
  ['06', 'Assistant grounding'],
];

function evidencePanelHtml() {
  const plates = state.assistantPlates || [];
  const rows = plates.length
    ? plates.map((plate) => `<div class="evidence-row">
        ${plateChip(plate.display_text, !plate.ocr_text)}
        <span class="evidence-meta">${plate.review_status === 'candidate_passed_validation_gate' ? 'Gate passed' : 'Needs review'} · ${score(plate.ocr_score)}</span>
        <button class="row-link" type="button" data-evidence="${plate.id}">Inspect</button>
      </div>`).join('')
    : '<p class="aside-note">No plate records yet. Scans you run become citable evidence.</p>';
  return `<section class="panel panel-pad">
    <div class="panel-head"><div><h2>Recent evidence</h2></div></div>
    <div class="evidence-list">${rows}</div>
  </section>`;
}

function knowledgePanelHtml() {
  return `<section class="panel panel-pad knowledge-panel">
    <div class="panel-head"><div><h2>Grounded knowledge</h2></div></div>
    <div class="doc-grid">${KNOWLEDGE_DOCS.map(([n, title]) => `<span class="doc-chip"><i>${n}</i>${esc(title)}</span>`).join('')}</div>
  </section>`;
}

function llmPanelHtml(status) {
  const llm = status.llm || {};
  const auto = status.auto_connect || {};
  const connected = Boolean(llm.available);
  const probe = state.llmProbe;
  if (connected) {
    return `<section class="panel panel-pad llm-panel">
      <div class="panel-head"><div><h2>Live LLM</h2></div><span class="pill ok">Connected</span></div>
      <div class="llm-live"><span class="status-dot ok"></span><div><strong>${esc(llm.provider)} · ${esc(llm.model)}</strong><small>${auto.enabled ? 'Auto-connect on' : 'Auto-connect paused'}</small></div></div>
      <button class="btn btn-ghost btn-small" id="llm-off" type="button" ${state.llmBusy ? 'disabled' : ''}>${state.llmBusy ? 'Disconnecting…' : 'Disconnect'}</button>
    </section>`;
  }
  const savedUrl = auto.url || localStorage.getItem('autoguard_ollama_url') || 'http://127.0.0.1:11434';
  const autoNote = !auto.enabled
    ? 'Auto-connect paused.'
    : auto.reachable === false
      ? 'No server answered — run <code>ollama serve</code>.'
      : auto.reachable && !(auto.models || []).length
        ? 'Ollama has no models — run <code>ollama pull llama3.2</code>.'
        : 'Attaches automatically when <code>ollama serve</code> is running locally.';
  const installed = probe?.models || [];
  const models = probe?.reachable && installed.length
    ? `<label class="llm-label" for="llm-model">Installed model</label>
    <div class="llm-row"><select id="llm-model">${installed.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join('')}</select><button class="btn btn-primary btn-small" id="llm-connect" type="button" ${state.llmBusy ? 'disabled' : ''}>Connect</button></div>`
    : probe?.reachable
      ? `<p class="llm-hint">No models installed at <code>${esc(probe.url || savedUrl)}</code>. Run <code>ollama pull llama3.2</code>.</p>`
      : probe
        ? `<p class="llm-hint">No server answered at <code>${esc(probe.url || savedUrl)}</code>.</p>`
        : `<p class="llm-hint">Detect a local Ollama server to list models.</p>`;
  return `<section class="panel panel-pad llm-panel">
    <div class="panel-head"><div><h2>Live LLM</h2></div><span class="pill ${auto.enabled ? 'info' : ''}">${auto.enabled ? 'Auto' : 'Paused'}</span></div>
    <label class="llm-label" for="llm-url">Ollama base URL</label>
    <div class="llm-row"><input id="llm-url" value="${esc(savedUrl)}" placeholder="http://127.0.0.1:11434" ${state.llmBusy ? 'disabled' : ''}><button class="btn btn-ghost btn-small" id="llm-detect" type="button" ${state.llmBusy ? 'disabled' : ''}>${state.llmBusy ? 'Checking…' : 'Detect'}</button></div>
    <div id="llm-models">${models}</div>
    <p class="llm-hint">${autoNote}</p>
  </section>`;
}

function bindLlmPanel() {
  $('#llm-off')?.addEventListener('click', async () => {
    if (state.llmBusy) return;
    state.llmBusy = true;
    renderAssistant($('#view'));
    try {
      const data = await api('/api/assistant/llm', { method: 'POST', body: { provider: 'off' } });
      state.assistantStatus = { ...data.status, auto_connect: data.auto_connect };
      state.llmProbe = null;
      toast('Live LLM disconnected. Grounded local mode is active; auto-connect is paused.');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      state.llmBusy = false;
      renderAssistant($('#view'));
    }
  });
  $('#llm-detect')?.addEventListener('click', async () => {
    if (state.llmBusy) return;
    const url = $('#llm-url')?.value.trim() || 'http://127.0.0.1:11434';
    state.llmBusy = true;
    renderAssistant($('#view'));
    try {
      const probe = await api(`/api/assistant/detect?url=${encodeURIComponent(url)}`);
      state.llmProbe = { ...probe, url };
      localStorage.setItem('autoguard_ollama_url', url);
      const hasModels = Boolean(probe.models?.length);
      const message = !probe.reachable
        ? 'Ollama did not respond. Is it running?'
        : hasModels
          ? `Found ${probe.models.length} installed model(s).`
          : 'Ollama is running, but it has no models. Run: ollama pull llama3.2';
      toast(message, hasModels ? 'ok' : (probe.reachable ? '' : 'bad'));
    } catch (error) {
      state.llmProbe = { reachable: false, url };
      toast(error.message, 'bad');
    } finally {
      state.llmBusy = false;
      renderAssistant($('#view'));
    }
  });
  $('#llm-connect')?.addEventListener('click', async () => {
    if (state.llmBusy) return;
    const url = state.llmProbe?.url || localStorage.getItem('autoguard_ollama_url') || 'http://127.0.0.1:11434';
    const model = $('#llm-model')?.value || '';
    state.llmBusy = true;
    renderAssistant($('#view'));
    try {
      const data = await api('/api/assistant/llm', { method: 'POST', body: { provider: 'ollama', url, model } });
      state.assistantStatus = { ...data.status, auto_connect: data.auto_connect };
      state.llmProbe = null;
      toast(`Connected to ${data.model}. Auto-connect is on — it will reattach after a restart.`, 'ok');
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      state.llmBusy = false;
      renderAssistant($('#view'));
    }
  });
}

function scheduleAutoConnect() {
  clearTimeout(state.llmAutoTimer);
  const status = state.assistantStatus || {};
  const auto = status.auto_connect || {};
  if (state.route !== 'assistant' || status.llm?.available || !auto.enabled) return;
  const token = state.routeToken;
  state.llmAutoTimer = setTimeout(async () => {
    if (state.route !== 'assistant' || token !== state.routeToken || state.llmBusy) return;
    try {
      const next = await api('/api/assistant/status');
      if (token !== state.routeToken) return;
      state.assistantStatus = next;
      if (next.llm?.available) {
        state.llmProbe = null;
        toast(`Live LLM attached: ${next.llm.model}`, 'ok');
        renderAssistant($('#view'));
        return;
      }
    } catch (error) {
      /* Ollama not up yet; keep waiting. */
    }
    scheduleAutoConnect();
  }, 10000);
}

function renderChatMessages() {
  const root = $('#chat-messages');
  if (!root) return;
  const status = state.assistantStatus || {};
  if (!state.chatMessages.length) {
    const starters = (status.suggestions || []).slice(0, 4);
    const marks = [ICONS.db, ICONS.shield, ICONS.chart, ICONS.spark];
    root.innerHTML = `<div class="chat-empty">
      <div class="chat-hero">
        <span class="chat-hero-mark">${ICONS.chat}</span>
        <h2>Ask the ledger, not the internet</h2>
        <p>Answers come from the plate database and the project documents; a local model only rephrases them.</p>
      </div>
      <div class="chat-starters">${starters.map((text, index) => `<button class="chat-starter" type="button" data-suggestion="${esc(text)}">
        <span class="chat-starter-icon">${marks[index % marks.length]}</span>
        <span class="chat-starter-text">${esc(text)}</span>
        <span class="chat-starter-arrow">→</span>
      </button>`).join('')}</div>
    </div>`;
  } else {
    root.innerHTML = state.chatMessages.map((message) => messageHtml(message)).join('');
  }
  const suggestions = $('#chat-suggestions');
  if (suggestions) {
    const lastAssistant = [...state.chatMessages].reverse().find((message) => message.role === 'assistant');
    const items = (lastAssistant?.meta?.suggestions?.length ? lastAssistant.meta.suggestions : (state.assistantStatus?.suggestions || [])).slice(0, 4);
    suggestions.innerHTML = state.chatMessages.length ? items.map((suggestion) => `<button class="suggestion" data-suggestion="${esc(suggestion)}" type="button">${esc(suggestion)}</button>`).join('') : '';
  }
  $$('[data-explain]', root).forEach((button) => button.addEventListener('click', () => openExplain(Number(button.dataset.explain))));
  $$('[data-cite-title]', root).forEach((button) => button.addEventListener('click', () => citationModal(button.dataset.citeTitle, button.dataset.citeText)));
  $$('[data-suggestion]').forEach((button) => button.addEventListener('click', () => {
    const input = $('#chat-input');
    input.value = button.dataset.suggestion;
    input.focus();
    sendChat();
  }));
  root.scrollTop = root.scrollHeight;
}

function messageHtml(message) {
  const isUser = message.role === 'user';
  const meta = message.meta || {};
  const citations = (meta.citations || []).map((item) => `<button class="citation" data-cite-title="${esc(item.title)}" data-cite-text="${esc(item.snippet)}">${esc(item.section || item.title || 'Source')}</button>`).join('');
  const plates = (meta.plates || []).map((plate) => `<div class="msg-plate">${plateChip(plate.text, !plate.machine_text)}<span class="score">engine ${score(plate.score)}</span><button class="row-link" data-explain="${plate.id}" type="button">Inspect</button></div>`).join('');
  return `<div class="msg ${isUser ? 'user' : 'assistant'}">
    <span class="msg-avatar">${isUser ? 'YOU' : 'AG'}</span>
    <div class="msg-body">
      <div class="msg-bubble">${markdownLite(message.content || '')}</div>
      ${plates ? `<div class="msg-plates">${plates}</div>` : ''}
      ${citations ? `<div class="citations">${citations}</div>` : ''}
      <div class="msg-meta">${isUser ? 'You' : (meta.mode === 'llm' ? 'LLM + grounded context' : meta.mode === 'local_fallback' ? 'Local fallback (model unavailable)' : 'Grounded local answer')}${message.created_at ? ` · ${timeAgo(message.created_at)}` : ''}</div>
    </div>
  </div>`;
}

function bindAssistantEvents() {
  const input = $('#chat-input');
  const send = $('#chat-send');
  if (!input || !send) return;
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 100)}px`;
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendChat(); }
  });
  send.addEventListener('click', sendChat);
  $('#new-chat')?.addEventListener('click', () => {
    state.chatSession = null;
    state.chatMessages = [];
    localStorage.removeItem('autoguard_chat_session');
    renderChatMessages();
    toast('Started a new conversation.');
  });
  input.focus();
}

async function sendChat() {
  if (state.chatBusy) return;
  const input = $('#chat-input');
  const message = input?.value.trim();
  if (!message) return;
  state.chatBusy = true;
  input.value = '';
  input.style.height = 'auto';
  state.chatMessages.push({ role: 'user', content: message, meta: {}, created_at: new Date().toISOString() });
  renderChatMessages();
  const root = $('#chat-messages');
  const typing = document.createElement('div');
  typing.className = 'msg assistant';
  typing.innerHTML = `<span class="msg-avatar">AG</span><div class="msg-body"><div class="msg-bubble"><div class="typing"><span></span><span></span><span></span></div></div></div>`;
  root.appendChild(typing);
  root.scrollTop = root.scrollHeight;
  try {
    const data = await api('/api/assistant/chat', { method: 'POST', body: { message, session_id: state.chatSession } });
    state.chatSession = data.session_id;
    localStorage.setItem('autoguard_chat_session', data.session_id);
    state.chatMessages.push({
      role: 'assistant',
      content: data.reply,
      meta: { citations: data.citations, plates: data.plates, mode: data.mode, intent: data.intent, suggestions: data.suggestions, metrics: data.metrics },
      created_at: data.created_at,
    });
  } catch (error) {
    state.chatMessages.push({ role: 'assistant', content: `I could not answer that request: ${error.message}`, meta: { mode: 'local_fallback' }, created_at: new Date().toISOString() });
  } finally {
    state.chatBusy = false;
    renderChatMessages();
    input.focus();
  }
}

/* ------------------------------------------------------------------ markdown */
function markdownLite(text) {
  const escaped = esc(text || '');
  const lines = escaped.split(/\r?\n/);
  const blocks = [];
  let list = [];
  let ordered = false;
  const flushList = () => {
    if (!list.length) return;
    const tag = ordered ? 'ol' : 'ul';
    blocks.push(`<${tag}>${list.map((item) => `<li>${inline(item)}</li>`).join('')}</${tag}>`);
    list = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { flushList(); continue; }
    const bullet = line.match(/^[•\-]\s+(.*)$/);
    const step = line.match(/^\d+\.\s+(.*)$/);
    if (bullet) {
      if (ordered) flushList();
      ordered = false;
      list.push(bullet[1]);
      continue;
    }
    if (step) {
      if (!ordered) flushList();
      ordered = true;
      list.push(step[1]);
      continue;
    }
    flushList();
    ordered = false;
    blocks.push(`<p>${inline(line)}</p>`);
  }
  flushList();
  return blocks.join('') || '<p></p>';
}

function inline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

/* ------------------------------------------------------------------ verification */
async function submitVerification(plateId, status, box) {
  const input = box?.querySelector('input');
  const text = input?.value.trim() || '';
  if (status === 'rejected') {
    if (!window.confirm(`Reject and permanently delete plate #${plateId}?`)) return;
    try {
      await api(`/api/plates/${plateId}`, { method: 'DELETE' });
      toast(`Plate #${plateId} removed.`, 'ok');
      await afterVerification();
    } catch (error) {
      toast(error.message, 'bad');
    }
    return;
  }
  if (!text) {
    toast('Enter the visually checked text first.', 'bad');
    input?.focus();
    return;
  }
  try {
    const plate = await api(`/api/plates/${plateId}/verify`, { method: 'POST', body: { verified_text: text, status } });
    toast(`Plate #${plateId} ${status === 'corrected' ? 'corrected' : 'confirmed'}.`, 'ok');
    const result = state.scanResults.flatMap((item) => item.plates || []).find((item) => item.plate_id === plateId);
    if (result) {
      result.verification_status = plate.verification_status;
      result.verified_text = plate.verified_text;
      if ($('#scan-results')) renderScanResults();
    }
    await afterVerification();
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function afterVerification() {
  updateReviewCount();
  if (state.route === 'review' && $('#review-list')) {
    state.review.selectedId = null;
    await loadReview(true);
  }
  if (state.route === 'archive' && $('#archive-body')) loadArchive(true);
}

/* ------------------------------------------------------------------ shell */
function setDemo(value) {
  state.includeDemo = Boolean(value);
  localStorage.setItem('autoguard_include_demo', state.includeDemo ? '1' : '0');
  const label = $('#demo-toggle-label');
  if (label) label.textContent = `Demo: ${state.includeDemo ? 'on' : 'off'}`;
  updateReviewCount();
  renderRoute();
}

async function refreshSystem() {
  try {
    const health = await api('/api/health');
    const dot = $('#system-dot');
    if (dot) dot.className = `pulse ${health.pipeline_ready ? 'ok' : ''}`;
    const label = $('#system-label');
    if (label) label.textContent = health.pipeline_ready ? 'ready' : 'loading';
  } catch (error) {
    const dot = $('#system-dot');
    if (dot) dot.className = 'pulse bad';
    const label = $('#system-label');
    if (label) label.textContent = 'offline';
  }
}

async function updateReviewCount() {
  try {
    state.summary = await api(`/api/analytics/summary?days=30&include_demo=${state.includeDemo ? '1' : '0'}`);
    const badge = $('#review-count');
    const count = Number(state.summary.review) || 0;
    if (badge) {
      badge.hidden = count === 0;
      badge.textContent = count > 99 ? '99+' : String(count);
    }
    const snapshot = {
      '#side-plates': state.summary.total_plates,
      '#side-passed': state.summary.passed,
      '#side-review': state.summary.review,
      '#side-recovered': state.summary.recovered,
    };
    for (const [selector, value] of Object.entries(snapshot)) {
      const node = $(selector);
      if (node && value != null) node.textContent = num(value);
    }
  } catch (error) { /* non-critical */ }
}

async function refreshBenchmark() {
  try {
    const benchmark = await api('/api/analytics/benchmark');
    state.benchmark = benchmark;
    if (state.route === 'intel' && state.intelTab === 'data') renderIntelContent();
  } catch (error) { /* non-critical */ }
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('autoguard_theme', next);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const button = $('#theme-toggle');
  if (button) button.innerHTML = theme === 'dark' ? ICONS.sun : ICONS.moon;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#070c17' : '#312e81');
}

const ROUTES = {
  scan: { title: 'Scan desk', eyebrow: 'AUTOGUARD / SCAN DESK', render: scanView },
  review: { title: 'Review queue', eyebrow: 'AUTOGUARD / HUMAN REVIEW', render: reviewView },
  archive: { title: 'Plate archive', eyebrow: 'AUTOGUARD / EVIDENCE LEDGER', render: archiveView },
  intel: { title: 'Intelligence', eyebrow: 'AUTOGUARD / CALIBRATION LAB', render: intelView },
  assistant: { title: 'Assistant', eyebrow: 'AUTOGUARD / GROUNDED CONVERSATION', render: assistantView },
};

function currentRoute() {
  const raw = (location.hash || '#/scan').replace(/^#\/?/, '').split('?')[0];
  const [name, sub] = raw.split('/');
  if (name === 'intel' && (sub === 'gate' || sub === 'restore' || sub === 'data')) state.intelTab = sub;
  if (name === 'dashboard') return 'scan';
  if (name === 'recovery') return 'review';
  if (name === 'lab' || name === 'restore') { state.intelTab = 'restore'; return 'intel'; }
  return ROUTES[name] ? name : 'scan';
}

function renderRoute() {
  const route = currentRoute();
  state.route = route;
  const definition = ROUTES[route];
  $('#page-title').textContent = definition.title;
  $('#page-eyebrow').textContent = definition.eyebrow;
  $$('.mainnav a').forEach((link) => link.classList.toggle('active', link.dataset.route === route));
  ++state.routeToken;
  if (route !== 'assistant') clearTimeout(state.llmAutoTimer);
  window.scrollTo({ top: 0, behavior: 'instant' });
  definition.render();
}

function startClock() {
  const tick = () => {
    const now = new Date();
    const clock = $('#clock');
    if (clock) clock.textContent = now.toLocaleString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  };
  tick();
  setInterval(tick, 30000);
}

function init() {
  const params = new URLSearchParams(location.search);
  const themeParam = params.get('theme');
  const savedTheme = ['light', 'dark'].includes(themeParam) ? themeParam : (localStorage.getItem('autoguard_theme') || 'light');
  applyTheme(savedTheme);
  localStorage.setItem('autoguard_theme', savedTheme);
  $('#theme-toggle')?.addEventListener('click', toggleTheme);

  const demoLabel = $('#demo-toggle-label');
  if (demoLabel) demoLabel.textContent = `Demo: ${state.includeDemo ? 'on' : 'off'}`;
  $('#demo-toggle')?.addEventListener('click', () => setDemo(!state.includeDemo));
  $('#export-csv')?.addEventListener('click', exportLedger);
  $('#palette-open')?.addEventListener('click', openPalette);
  $('#new-scan')?.addEventListener('click', () => {
    if (state.route === 'scan') { $('#file-input')?.click(); return; }
    location.hash = '#/scan';
    setTimeout(() => $('#file-input')?.click(), 150);
  });

  window.addEventListener('hashchange', renderRoute);
  window.addEventListener('keydown', (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName || '');
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if ($('#palette-root').innerHTML) closePalette(); else openPalette();
      return;
    }
    if (event.key === 'Escape') {
      if ($('#palette-root').innerHTML) closePalette();
      if ($('#drawer-root').innerHTML) closeDrawer();
      closeModal();
      return;
    }
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === '?') { openPalette(); return; }
    if (pendingG) {
      const target = { s: '#/scan', r: '#/review', a: '#/archive', i: '#/intel', c: '#/assistant' }[event.key.toLowerCase()];
      clearTimeout(pendingG);
      pendingG = 0;
      if (target) { event.preventDefault(); location.hash = target; return; }
    }
    if (event.key.toLowerCase() === 'g') {
      clearTimeout(pendingG);
      pendingG = setTimeout(() => { pendingG = 0; }, 900);
      return;
    }
    if (state.route === 'review' && !event.shiftKey) {
      if (event.key.toLowerCase() === 'j') { event.preventDefault(); reviewNavigate(1); }
      if (event.key.toLowerCase() === 'k') { event.preventDefault(); reviewNavigate(-1); }
      if (event.key.toLowerCase() === 'c') { event.preventDefault(); reviewQuickVerify('confirmed'); }
      if (event.key.toLowerCase() === 'x') { event.preventDefault(); reviewQuickVerify('rejected'); }
    }
  });
  document.addEventListener('click', (event) => {
    const image = event.target.closest('img[data-lightbox]');
    if (image) {
      event.preventDefault();
      openImageLightbox(image.getAttribute('src'), image.getAttribute('alt'));
      return;
    }
    const copy = event.target.closest('[data-copy]');
    if (copy) copyText(copy.dataset.copy, 'Plate text copied.');
  });
  startClock();
  refreshSystem();
  refreshBenchmark();
  updateReviewCount();
  renderRoute();
}

document.addEventListener('DOMContentLoaded', init);
