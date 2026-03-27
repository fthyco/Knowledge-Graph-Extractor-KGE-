/**
 * app.js — PDF Reader Web UI Controller
 *
 * Manages: library browsing, book upload, chapter selection,
 * prompt generation, study status tracking.
 */

const API = '';  // Same origin

// ── State ────────────────────────────────────────────

let books = [];
let selectedBookId = null;
let selectedChapterId = null;
let selectedMode = 'deep_dive';

// ── DOM refs ─────────────────────────────────────────

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const dom = {
  bookCount:      $('#book-count'),
  bookList:       $('#book-list'),
  viewEmpty:      $('#view-empty'),
  viewChapters:   $('#view-chapters'),
  viewPrompt:     $('#view-prompt'),
  selTitle:       $('#sel-title'),
  selStats:       $('#sel-stats'),
  chapterList:    $('#chapter-list'),
  chTitle:        $('#ch-title'),
  generateArea:   $('#generate-area'),
  loading:        $('#loading'),
  loadingText:    $('#loading-text'),
  promptOutput:   $('#prompt-output'),
  promptText:     $('#prompt-text'),
  promptStats:    $('#prompt-stats'),
  uploadOverlay:  $('#upload-overlay'),
  uploadStatus:   $('#upload-status'),
  uploadProgress: $('#upload-progress-fill'),
  toast:          $('#toast'),

  // Control Unit
  settingsOverlay: $('#settings-overlay'),
  cfgFastPath:     $('#cfg-fast-path'),
  cfgThreshold:    $('#cfg-threshold'),
  cfgExportDir:    $('#cfg-export-dir'),
};

// ── Init ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadBooks();
  loadConfig();
  bindEvents();
});

function bindEvents() {
  // Upload
  $('#btn-upload').addEventListener('click', () => $('#file-input').click());
  $('#file-input').addEventListener('change', handleUpload);

  // Scan
  $('#btn-scan').addEventListener('click', handleScan);

  // Navigation
  $('#btn-deselect').addEventListener('click', deselectBook);
  $('#btn-back').addEventListener('click', showChaptersView);

  // Modes
  $$('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.mode-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedMode = btn.dataset.mode;
      // Hide previous prompt
      dom.promptOutput.style.display = 'none';
      dom.generateArea.style.display = 'flex';
    });
  });

  // Generate
  $('#btn-generate').addEventListener('click', generatePrompt);

  // Copy
  $('#btn-copy').addEventListener('click', copyPrompt);

  // Download
  $('#btn-download').addEventListener('click', downloadPrompt);

  // Control Unit / Settings
  $('#btn-settings').addEventListener('click', () => dom.settingsOverlay.style.display = 'flex');
  $('#btn-close-settings').addEventListener('click', () => dom.settingsOverlay.style.display = 'none');
  $('#btn-save-settings').addEventListener('click', saveConfig);
  $('#btn-clear-library').addEventListener('click', clearLibrary);
  $('#btn-clear-errors').addEventListener('click', clearErrors);
}

// ── API Helpers ──────────────────────────────────────

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  return res.json();
}

async function apiPost(path, body) {
  return api(path, {
    method: 'POST',
    headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    body,
  });
}

// ── Books ────────────────────────────────────────────

async function loadBooks() {
  const res = await api('/warehouse/books');
  if (res.success) {
    books = res.books.filter(b => b.status === 'ready');
    renderBookList();
  }
}

function renderBookList() {
  dom.bookCount.textContent = `${books.length} book${books.length !== 1 ? 's' : ''}`;

  if (!books.length) {
    dom.bookList.innerHTML = `
      <div style="padding:20px 12px;text-align:center;color:var(--text-muted);font-size:12px;">
        No books yet. Upload a PDF to get started.
      </div>`;
    return;
  }

  dom.bookList.innerHTML = books.map(b => `
    <button class="book-item ${b.id === selectedBookId ? 'active' : ''}"
            data-id="${b.id}" title="${esc(b.title)}">
      <svg class="book-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/>
      </svg>
      <span class="book-name">${esc(b.title)}</span>
      <span class="book-chapters">${b.total_chapters || 0} ch</span>
    </button>
  `).join('');

  dom.bookList.querySelectorAll('.book-item').forEach(el => {
    el.addEventListener('click', () => selectBook(el.dataset.id));
  });
}

async function selectBook(bookId) {
  selectedBookId = bookId;
  selectedChapterId = null;
  renderBookList();

  const book = books.find(b => b.id === bookId);
  if (!book) return;

  dom.selTitle.textContent = book.title;
  const wordCount = book.total_words ? `${(book.total_words / 1000).toFixed(1)}k words` : '';
  const chCount = `${book.total_chapters || 0} chapters`;
  dom.selStats.textContent = `${chCount} · ${wordCount}`;

  // Load chapters
  const res = await api(`/warehouse/books/${bookId}/chapters`);
  if (res.success) {
    renderChapterList(res.chapters);
    showView('chapters');
  }
}

function deselectBook() {
  selectedBookId = null;
  selectedChapterId = null;
  renderBookList();
  showView('empty');
}

function renderChapterList(chapters) {
  if (!chapters.length) {
    dom.chapterList.innerHTML = `
      <div style="padding:40px;text-align:center;color:var(--text-muted);">
        No chapters detected in this book.
      </div>`;
    return;
  }

  dom.chapterList.innerHTML = chapters.map(ch => {
    const statusIcon = ch.study_status === 'completed' ? '✓'
      : ch.study_status === 'in_progress' ? '◐' : '○';
    const statusClass = `status-${ch.study_status || 'not_started'}`;
    const words = ch.word_count ? `${(ch.word_count / 1000).toFixed(1)}k` : '';

    return `
      <button class="chapter-item" data-id="${ch.id}" data-book="${ch.book_id}">
        <span class="ch-status ${statusClass}" data-action="toggle-status"
              title="Click to change study status">${statusIcon}</span>
        <span class="ch-number">${String(ch.number).padStart(2, '0')}</span>
        <span class="ch-title">${esc(ch.title)}</span>
        <span class="ch-words">${words}</span>
        <span class="ch-analyze-btn">Study →</span>
      </button>
    `;
  }).join('');

  // Bind clicks
  dom.chapterList.querySelectorAll('.chapter-item').forEach(el => {
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-action="toggle-status"]')) {
        toggleStudyStatus(el.dataset.book, el.dataset.id, e.target);
        e.stopPropagation();
        return;
      }
      openChapter(el.dataset.book, el.dataset.id);
    });
  });
}

// ── Study Status ─────────────────────────────────────

async function toggleStudyStatus(bookId, chapterId, statusEl) {
  const cycle = { 'not_started': 'in_progress', 'in_progress': 'completed', 'completed': 'not_started' };
  const icons = { 'not_started': '○', 'in_progress': '◐', 'completed': '✓' };

  const current = statusEl.classList.contains('status-completed') ? 'completed'
    : statusEl.classList.contains('status-in_progress') ? 'in_progress' : 'not_started';
  const next = cycle[current];

  // Optimistic update
  statusEl.className = `ch-status status-${next}`;
  statusEl.textContent = icons[next];

  const form = new FormData();
  form.append('status', next);

  const res = await fetch(`${API}/warehouse/books/${bookId}/chapters/${chapterId}/status`, {
    method: 'PATCH', body: form,
  }).then(r => r.json());

  if (!res.success) {
    // Revert
    statusEl.className = `ch-status status-${current}`;
    statusEl.textContent = icons[current];
    toast('Failed to update status', 'error');
  }
}

// ── Chapter → Prompt View ────────────────────────────

async function openChapter(bookId, chapterId) {
  selectedBookId = bookId;
  selectedChapterId = chapterId;

  // Get chapter info
  const res = await api(`/warehouse/books/${bookId}/chapters/${chapterId}`);
  if (!res.success) {
    toast('Failed to load chapter');
    return;
  }

  const ch = res.chapter;
  dom.chTitle.textContent = `Ch ${ch.number}: ${ch.title}`;

  // Reset prompt area
  dom.generateArea.style.display = 'flex';
  dom.loading.style.display = 'none';
  dom.promptOutput.style.display = 'none';

  showView('prompt');
}

function showChaptersView() {
  if (selectedBookId) {
    selectBook(selectedBookId);
  } else {
    showView('empty');
  }
}

// ── Generate Prompt ──────────────────────────────────

async function generatePrompt() {
  if (!selectedBookId || !selectedChapterId) return;

  dom.generateArea.style.display = 'none';
  dom.loading.style.display = 'flex';
  dom.loadingText.textContent = 'Analyzing chapter structure...';
  dom.promptOutput.style.display = 'none';

  try {
    const form = new FormData();
    form.append('mode', selectedMode);

    const res = await fetch(`${API}/engine/prompt/${selectedBookId}/${selectedChapterId}`, {
      method: 'POST', body: form,
    }).then(r => r.json());

    if (!res.success) {
      throw new Error(res.error || 'Failed to generate prompt');
    }

    dom.loading.style.display = 'none';
    dom.promptText.textContent = res.prompt;
    dom.promptStats.textContent = `${res.word_count.toLocaleString()} words · ~${res.est_tokens.toLocaleString()} tokens${res.cached ? ' · cached' : ''}`;
    dom.promptOutput.style.display = 'block';

  } catch (err) {
    dom.loading.style.display = 'none';
    dom.generateArea.style.display = 'flex';
    toast(err.message, 'error');
  }
}

// ── Copy + Download ──────────────────────────────────

async function copyPrompt() {
  const text = dom.promptText.textContent;
  try {
    await navigator.clipboard.writeText(text);
    toast('Prompt copied to clipboard');
  } catch {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    toast('Prompt copied to clipboard');
  }
}

function downloadPrompt() {
  const text = dom.promptText.textContent;
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `prompt_${selectedMode}_${selectedChapterId}.txt`;
  a.click();
  URL.revokeObjectURL(url);
  toast('Prompt downloaded');
}

// ── Upload ───────────────────────────────────────────

async function handleUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = '';

  showUploadOverlay('Uploading PDF...', 'Preparing...', 5);

  const form = new FormData();
  form.append('pdf_file', file);
  form.append('title', file.name.replace('.pdf', '').replace(/_/g, ' '));
  form.append('background', 'true');

  try {
    const res = await fetch(`${API}/warehouse/upload`, {
      method: 'POST', body: form,
    }).then(r => r.json());

    if (!res.success) throw new Error(res.error || 'Upload failed');

    if (res.job_id) {
      trackProgress(res.job_id);
    } else if (res.book) {
      hideUploadOverlay();
      await loadBooks();
      selectBook(res.book.id);
      toast('Book ingested successfully');
    }
  } catch (err) {
    hideUploadOverlay();
    toast(err.message, 'error');
  }
}

// ── Scan ─────────────────────────────────────────────

async function handleScan() {
  showUploadOverlay('Scanning Library...', 'Looking for new PDFs...', 10);

  try {
    const res = await fetch(`${API}/warehouse/scan`, {
      method: 'POST',
    }).then(r => r.json());

    if (!res.success) throw new Error(res.error || 'Scan failed');

    if (res.job_id) {
      trackProgress(res.job_id);
    } else {
      hideUploadOverlay();
      await loadBooks();
      toast(`Scan complete: ${res.count || 0} new books`);
    }
  } catch (err) {
    hideUploadOverlay();
    toast(err.message, 'error');
  }
}

// ── Progress Tracking (SSE) ──────────────────────────

function trackProgress(jobId) {
  const source = new EventSource(`${API}/warehouse/progress/${jobId}`);

  source.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.status === 'not_found') {
      source.close();
      hideUploadOverlay();
      return;
    }

    updateUploadOverlay(data);

    if (data.status === 'done') {
      source.close();
      completeProcess(true);
      hideUploadOverlay();
      loadBooks().then(() => {
        if (data.book_id) {
          selectBook(data.book_id);
          toast(`"${data.book_title || 'Book'}" ingested successfully`);
        } else {
          toast(`Scan complete: ${data.count || 0} new books`);
        }
      });
    }

    if (data.status === 'error') {
      source.close();
      addLogLine(data.error || 'Processing failed', 'error');
      completeProcess(false);
      setTimeout(() => {
        hideUploadOverlay();
        toast(data.error || 'Processing failed', 'error');
      }, 2000);
    }
  };

  source.onerror = () => {
    source.close();
    // Try polling fallback
    pollProgress(jobId);
  };
}

async function pollProgress(jobId) {
  const maxPolls = 120;
  for (let i = 0; i < maxPolls; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const data = await api(`/warehouse/job/${jobId}`);
      updateUploadOverlay(data);

      if (data.status === 'done') {
        hideUploadOverlay();
        await loadBooks();
        if (data.book_id) selectBook(data.book_id);
        toast('Processing complete');
        return;
      }
      if (data.status === 'error') {
        hideUploadOverlay();
        toast(data.error || 'Processing failed', 'error');
        return;
      }
    } catch {
      // Keep polling
    }
  }
  hideUploadOverlay();
  toast('Processing timed out', 'error');
}

// ── Process Overlay ──────────────────────────────────

let _processStartTime = null;
let _elapsedTimer = null;
let _lastStep = null;

const PIPELINE_ORDER = [
  'uploading', 'extracting_markdown', 'detecting_chapters',
  'analyzing_chapters', 'done'
];

const STEP_LABELS = {
  uploading: 'Uploading PDF...',
  extracting_markdown: 'Extracting markdown via Marker (no OCR)...',
  detecting_chapters: 'Detecting chapter boundaries...',
  analyzing_chapters: 'Analyzing concepts, formulas & dependencies...',
  building_knowledge_map: 'Building knowledge map (background)...',
  clearing_errors: 'Clearing failed books...',
  scanning_directory: 'Scanning raw_source/ for new PDFs...',
  preparing_scan: 'Preparing library scan...',
};

function showUploadOverlay(title, step, percent) {
  _processStartTime = Date.now();
  _lastStep = null;

  dom.uploadStatus.textContent = title;
  dom.uploadStep.textContent = STEP_LABELS[step] || step;
  dom.uploadProgress.style.width = `${percent}%`;
  dom.uploadOverlay.style.display = 'flex';

  // Clear activity log
  const log = $('#activity-log');
  log.innerHTML = '';
  addLogLine('Process started');

  // Reset pipeline icons
  $$('.pipe-step').forEach(el => {
    el.classList.remove('active', 'done', 'error');
    el.querySelector('.pipe-icon').textContent = '○';
  });
  $$('.pipe-connector').forEach(el => el.classList.remove('done'));

  // Mark first step active
  updatePipelineStep(step);

  // Start elapsed timer
  clearInterval(_elapsedTimer);
  _elapsedTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - _processStartTime) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    $('#elapsed-time').textContent = mins > 0
      ? `Elapsed: ${mins}m ${secs}s`
      : `Elapsed: ${secs}s`;
  }, 500);
}

function updateUploadOverlay(data) {
  const step = data.step || '';
  const stepLabel = STEP_LABELS[step] || step || 'Working...';

  dom.uploadStatus.textContent = data.book_title
    ? `Processing: ${data.book_title}` : 'Processing...';
  dom.uploadStep.textContent = stepLabel;
  dom.uploadProgress.style.width = `${data.percent || 0}%`;

  // Log new steps
  if (step && step !== _lastStep) {
    addLogLine(stepLabel);
    updatePipelineStep(step);
    _lastStep = step;
  }

  // Log extra info from data
  if (data.count !== undefined && data.status === 'done') {
    addLogLine(`Found ${data.count} new book(s)`, 'success');
  }
  if (data.cleared_errors && data.cleared_errors > 0) {
    addLogLine(`Cleared ${data.cleared_errors} failed book(s)`, 'warn');
  }
}

function updatePipelineStep(currentStep) {
  const currentIdx = PIPELINE_ORDER.indexOf(currentStep);
  if (currentIdx === -1) return;

  const steps = $$('.pipe-step');
  const connectors = $$('.pipe-connector');

  steps.forEach((el, i) => {
    el.classList.remove('active', 'done');
    const icon = el.querySelector('.pipe-icon');

    if (i < currentIdx) {
      el.classList.add('done');
      icon.textContent = '✓';
    } else if (i === currentIdx) {
      el.classList.add('active');
      icon.textContent = '◉';
    } else {
      icon.textContent = '○';
    }
  });

  connectors.forEach((el, i) => {
    el.classList.toggle('done', i < currentIdx);
  });
}

function completeProcess(success) {
  clearInterval(_elapsedTimer);

  const steps = $$('.pipe-step');
  const connectors = $$('.pipe-connector');

  if (success) {
    steps.forEach(el => {
      el.classList.remove('active');
      el.classList.add('done');
      el.querySelector('.pipe-icon').textContent = '✓';
    });
    connectors.forEach(el => el.classList.add('done'));

    const elapsed = Math.floor((Date.now() - _processStartTime) / 1000);
    addLogLine(`Done in ${elapsed}s`, 'success');
  } else {
    const activeStep = document.querySelector('.pipe-step.active');
    if (activeStep) {
      activeStep.classList.remove('active');
      activeStep.classList.add('error');
      activeStep.querySelector('.pipe-icon').textContent = '✗';
    }
  }

  dom.uploadProgress.style.width = success ? '100%' : dom.uploadProgress.style.width;
}

function hideUploadOverlay() {
  // Brief delay to let the user see "Done"
  setTimeout(() => {
    dom.uploadOverlay.style.display = 'none';
    clearInterval(_elapsedTimer);
  }, 800);
}

function addLogLine(message, type = '') {
  const log = $('#activity-log');
  const elapsed = _processStartTime
    ? `${((Date.now() - _processStartTime) / 1000).toFixed(1)}s`
    : '0.0s';

  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `<span class="log-time">[${elapsed}]</span><span class="log-msg ${type}">${esc(message)}</span>`;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

// ── Settings (Control Unit) ──────────────────────────

async function loadConfig() {
  try {
    const res = await api('/warehouse/config');
    if (res.success && res.config) {
      dom.cfgFastPath.checked = res.config.fast_path_enabled;
      dom.cfgThreshold.value = res.config.pypdf_threshold;
      dom.cfgExportDir.value = res.config.export_dir;
    }
  } catch (err) {
    console.error('Failed to load config', err);
  }
}

async function saveConfig() {
  const form = new FormData();
  form.append('fast_path_enabled', dom.cfgFastPath.checked);
  form.append('pypdf_threshold', dom.cfgThreshold.value);
  form.append('export_dir', dom.cfgExportDir.value);

  try {
    const res = await fetch(`${API}/warehouse/config`, { method: 'PATCH', body: form }).then(r => r.json());
    if (res.success) {
      dom.settingsOverlay.style.display = 'none';
      toast('Control Unit configuration saved');
    } else {
      throw new Error(res.error);
    }
  } catch (err) {
    toast(err.message || 'Failed to save config', 'error');
  }
}

async function clearErrors() {
  try {
    const res = await fetch(`${API}/warehouse/clear-errors`, { method: 'POST' }).then(r => r.json());
    if (res.success) {
      toast(`Cleared ${res.cleared || 0} error logs`);
    }
  } catch (err) {
    toast('Failed to clear error logs', 'error');
  }
}

// ── Clear Library ────────────────────────────────────

async function clearLibrary() {
  if (!confirm('Delete all books from the library? This cannot be undone.')) return;

  try {
    const res = await fetch(`${API}/warehouse/clear-all`, { method: 'POST' }).then(r => r.json());
    if (res.success) {
      books = [];
      selectedBookId = null;
      selectedChapterId = null;
      renderBookList();
      showView('empty');
      dom.settingsOverlay.style.display = 'none';
      toast(`Cleared ${res.cleared || 0} books`);
    }
  } catch (err) {
    toast('Failed to clear library', 'error');
  }
}

// ── View Management ──────────────────────────────────

function showView(name) {
  dom.viewEmpty.style.display = name === 'empty' ? 'flex' : 'none';
  dom.viewChapters.style.display = name === 'chapters' ? 'block' : 'none';
  dom.viewPrompt.style.display = name === 'prompt' ? 'block' : 'none';
}

// ── Toast ────────────────────────────────────────────

let toastTimer = null;

function toast(message) {
  dom.toast.textContent = message;
  dom.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => dom.toast.classList.remove('show'), 3000);
}

// ── Utils ────────────────────────────────────────────

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}
