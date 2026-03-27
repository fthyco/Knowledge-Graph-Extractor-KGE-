/**
 * organizer.js — Book Organizer Controller
 * Manages the full-page organizer UI: book library, chapter browsing,
 * and study prompt generation.
 *
 * Supports multi-book selection — chapters from all selected books
 * are shown together, grouped by book.
 */

const API = 'http://localhost:8001';

// ─── DOM ─────────────────────────────────────────────────
const sidebar = document.getElementById('sidebar');
const bookList = document.getElementById('book-list');
const bookCount = document.getElementById('book-count');
const btnUpload = document.getElementById('btn-upload-book');
const btnScan = document.getElementById('btn-scan');
const fileInput = document.getElementById('file-input');
const btnClearLibrary = document.getElementById('btn-clear-library');
const btnStudyGuide = document.getElementById('btn-study-guide');
const studyGuideModal = document.getElementById('study-guide-modal');
const btnCloseGuide = document.getElementById('btn-close-guide');
const emptyState = document.getElementById('empty-state');
const chapterView = document.getElementById('chapter-view');
const selectionTitle = document.getElementById('selection-title');
const selectionStats = document.getElementById('selection-stats');
const chapterList = document.getElementById('chapter-list');
const btnDeselectAll = document.getElementById('btn-deselect-all');
const promptView = document.getElementById('prompt-view');
const chapterTitle = document.getElementById('chapter-title');
const btnBackChapters = document.getElementById('btn-back-chapters');
const modeBar = document.getElementById('mode-bar');
const btnGenerate = document.getElementById('btn-generate');
const generateArea = document.getElementById('generate-area');
const promptOutput = document.getElementById('prompt-output');
const promptText = document.getElementById('prompt-text');
const promptStats = document.getElementById('prompt-stats');
const btnCopyPrompt = document.getElementById('btn-copy-prompt');
const btnDownloadPrompt = document.getElementById('btn-download-prompt');
const loading = document.getElementById('loading');
const loadingText = document.getElementById('loading-text');
const uploadOverlay = document.getElementById('upload-overlay');
const uploadStatus = document.getElementById('upload-status');
const uploadStep = document.getElementById('upload-step');
const uploadProgressFill = document.getElementById('upload-progress-fill');
const toast = document.getElementById('toast');
const knowledgePanel = document.getElementById('knowledge-panel');
const knowledgeMatches = document.getElementById('knowledge-matches');
const knowledgeSubtitle = document.getElementById('knowledge-subtitle');

// ─── State ───────────────────────────────────────────────
let books = [];
let selectedBookIds = new Set();          // multi-select
let loadedChapters = {};                  // bookId → chapters[]
let currentChapter = null;                // single chapter for prompt view
let currentChapterBookId = null;          // which book owns currentChapter
let selectedMode = 'deep_dive';
let generatedPrompt = '';

// ─── Init ────────────────────────────────────────────────
loadBooks();

// ─── API Helpers ─────────────────────────────────────────

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  return res.json();
}

// ─── Books ───────────────────────────────────────────────

async function loadBooks() {
  try {
    const data = await api('/warehouse/books');
    if (data.success) {
      books = (data.books || []).filter(b => b.status !== 'error');
      renderBookList();
    }
  } catch (e) {
    console.error('Failed to load books:', e);
    books = [];
    renderBookList();
  }
}

function renderBookList() {
  bookList.innerHTML = '';
  bookCount.textContent = `${books.length} book${books.length !== 1 ? 's' : ''}`;

  if (books.length === 0) {
    selectedBookIds.clear();
    showView('empty');
    return;
  }

  books.forEach(book => {
    const isSelected = selectedBookIds.has(book.id);
    const btn = document.createElement('button');
    btn.className = 'book-item' + (isSelected ? ' active' : '');
    btn.innerHTML = `
      <span class="book-check">${isSelected ? '✓' : ''}</span>
      <svg class="book-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      </svg>
      <span class="book-name">${escapeHtml(book.title)}</span>
      <span class="book-chapters">${book.total_chapters || '?'}</span>
    `;
    btn.onclick = () => toggleBook(book);
    bookList.appendChild(btn);
  });
}

// ─── Multi-Select Toggle ─────────────────────────────────

async function toggleBook(book) {
  if (selectedBookIds.has(book.id)) {
    selectedBookIds.delete(book.id);
    delete loadedChapters[book.id];
  } else {
    selectedBookIds.add(book.id);
    // Load chapters for this book
    try {
      const data = await api(`/warehouse/books/${book.id}/chapters`);
      if (data.success) {
        loadedChapters[book.id] = data.chapters || [];
      }
    } catch (e) {
      console.error('Failed to load chapters:', e);
      selectedBookIds.delete(book.id);
    }
  }

  renderBookList();

  if (selectedBookIds.size === 0) {
    showView('empty');
  } else {
    renderChapterView();
    showView('chapters');
  }
}

// ─── Chapter View (Multi-Book) ───────────────────────────

function renderChapterView() {
  const selectedBooks = books.filter(b => selectedBookIds.has(b.id));
  const totalChapters = selectedBooks.reduce((sum, b) => sum + (loadedChapters[b.id]?.length || 0), 0);
  const totalWords = selectedBooks.reduce((sum, b) => sum + (b.total_words || 0), 0);

  if (selectedBooks.length === 1) {
    selectionTitle.textContent = selectedBooks[0].title;
  } else {
    selectionTitle.textContent = `${selectedBooks.length} Books Selected`;
  }
  selectionStats.textContent = `${totalChapters} chapters · ${totalWords.toLocaleString()} words`;

  // Knowledge panel — show only for single book
  knowledgePanel.style.display = 'none';
  if (selectedBooks.length === 1) {
    loadKnowledgeMap(selectedBooks[0].id);
  }

  renderChapterList();
}

function renderChapterList() {
  chapterList.innerHTML = '';
  const selectedBooks = books.filter(b => selectedBookIds.has(b.id));
  const multiBook = selectedBooks.length > 1;

  selectedBooks.forEach(book => {
    const chapters = loadedChapters[book.id] || [];

    // Book group header (always shown, acts as a visual separator)
    if (multiBook) {
      const groupHeader = document.createElement('div');
      groupHeader.className = 'book-group-header';
      groupHeader.innerHTML = `
        <svg class="book-group-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        <span class="book-group-name">${escapeHtml(book.title)}</span>
        <span class="book-group-count">${chapters.length} ch</span>
      `;
      chapterList.appendChild(groupHeader);
    }

    chapters.forEach(ch => {
      let statusIcon = '○';
      let statusClass = 'status-not-started';
      if (ch.study_status === 'in_progress') {
        statusIcon = '◐';
        statusClass = 'status-in-progress';
      } else if (ch.study_status === 'completed') {
        statusIcon = '●';
        statusClass = 'status-completed';
      }

      const btn = document.createElement('button');
      btn.className = 'chapter-item';

      const statusSpan = document.createElement('span');
      statusSpan.className = `ch-status ${statusClass}`;
      statusSpan.textContent = statusIcon;
      statusSpan.title = 'Toggle Study Status';
      statusSpan.onclick = (e) => toggleStudyStatus(e, book.id, ch);

      const titleSpan = document.createElement('span');
      titleSpan.className = 'ch-title';
      titleSpan.textContent = ch.title;

      const numberSpan = document.createElement('span');
      numberSpan.className = 'ch-number';
      numberSpan.textContent = ch.number;

      const wordsSpan = document.createElement('span');
      wordsSpan.className = 'ch-words';
      wordsSpan.textContent = `${(ch.word_count || 0).toLocaleString()} words`;

      // Analyze button per chapter
      const analyzeBtn = document.createElement('button');
      analyzeBtn.className = 'ch-analyze-btn';
      analyzeBtn.textContent = '▶ Analyze';
      analyzeBtn.title = 'Generate study prompt for this chapter';
      analyzeBtn.onclick = (e) => {
        e.stopPropagation();
        selectChapter(book.id, ch);
      };

      btn.onclick = (e) => {
        if (e.target !== statusSpan && e.target !== analyzeBtn) {
          selectChapter(book.id, ch);
        }
      };

      btn.appendChild(statusSpan);
      btn.appendChild(numberSpan);
      btn.appendChild(titleSpan);
      btn.appendChild(wordsSpan);
      btn.appendChild(analyzeBtn);
      chapterList.appendChild(btn);
    });
  });
}

async function loadKnowledgeMap(bookId) {
  knowledgePanel.style.display = 'none';
  knowledgeMatches.innerHTML = '';

  try {
    const data = await api(`/warehouse/books/${bookId}/knowledge-map`);
    if (!data.success || !data.knowledge_map) return;

    const matches = data.knowledge_map.matches.filter(m => m.total_score >= 0.15);
    if (matches.length === 0) return;

    knowledgeSubtitle.textContent =
      `${matches.length} related book${matches.length > 1 ? 's' : ''} found`;

    matches.forEach(match => {
      const relatedBook = books.find(b => b.id === match.warehouse_book_id);
      const bookName = relatedBook ? relatedBook.title : match.warehouse_book_id;
      const pct = Math.round(match.total_score * 100);

      const card = document.createElement('div');
      card.className = 'match-card';
      card.innerHTML = `
        <div class="match-top">
          <span class="match-name">${escapeHtml(bookName)}</span>
          <span class="match-score">${pct}%</span>
        </div>
        <div class="match-bar">
          <div class="match-fill" style="width:${pct}%"></div>
        </div>
        <div class="match-breakdown">
          <span title="Name similarity">N: ${Math.round(match.name_score * 100)}%</span>
          <span title="Chapter structure">S: ${Math.round(match.structure_score * 100)}%</span>
          <span title="Concept overlap">C: ${Math.round(match.concept_score * 100)}%</span>
        </div>
      `;
      if (relatedBook) {
        card.style.cursor = 'pointer';
        card.onclick = () => {
          if (!selectedBookIds.has(relatedBook.id)) {
            toggleBook(relatedBook);
          }
        };
      }
      knowledgeMatches.appendChild(card);
    });

    knowledgePanel.style.display = '';
  } catch (e) {
    console.error('Knowledge map error:', e);
  }
}

// ─── Study Status ────────────────────────────────────────

async function toggleStudyStatus(event, bookId, chapter) {
  event.stopPropagation();

  let nextStatus = 'not_started';
  if (chapter.study_status === 'not_started' || !chapter.study_status) {
    nextStatus = 'in_progress';
  } else if (chapter.study_status === 'in_progress') {
    nextStatus = 'completed';
  }

  try {
    const formData = new FormData();
    formData.append('status', nextStatus);

    const data = await api(`/warehouse/books/${bookId}/chapters/${chapter.id}/status`, {
      method: 'PATCH',
      body: formData
    });

    if (data.success) {
      chapter.study_status = nextStatus;
      renderChapterList();
    } else {
      showToast('Failed to update status');
    }
  } catch (e) {
    console.error('Status check error:', e);
    showToast('Failed to connect to server');
  }
}

// ─── Scan Library ────────────────────────────────────────

btnScan.addEventListener('click', async () => {
  btnScan.disabled = true;
  btnScan.textContent = '⟳ Scanning...';
  showProgressOverlay('Scanning library...');

  try {
    const data = await api('/warehouse/scan', { method: 'POST' });

    if (data.success && data.job_id) {
      await trackJobProgress(data.job_id, (state) => {
        if (state.status === 'done') {
          const count = state.count || 0;
          if (count > 0) {
            showToast(`Ingested ${count} new book${count > 1 ? 's' : ''}`);
          } else {
            showToast('No new PDFs found in raw_source/');
          }
          loadBooks();
        } else if (state.status === 'error') {
          showToast('Scan failed: ' + (state.error || 'Unknown error'));
        }
      });
    } else if (data.success) {
      const count = data.count || 0;
      if (count > 0) {
        showToast(`Ingested ${count} new book${count > 1 ? 's' : ''}`);
      } else {
        showToast('No new PDFs found in raw_source/');
      }
      await loadBooks();
    } else {
      showToast('Scan failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    showToast('Scan failed — is the server running?');
    console.error('Scan error:', e);
  } finally {
    hideProgressOverlay();
    btnScan.disabled = false;
    btnScan.textContent = '⟳ Scan Library';
  }
});

btnClearLibrary.addEventListener('click', async () => {
  if (!confirm("Are you sure you want to clear the entire library? This cannot be undone.")) return;

  btnClearLibrary.disabled = true;
  try {
    const data = await api('/warehouse/clear-all', { method: 'POST' });
    if (data.success) {
      showToast('Library cleared');
      selectedBookIds.clear();
      loadedChapters = {};
      currentChapter = null;
      showView('empty');
      await loadBooks();
    } else {
      showToast('Failed to clear library: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    showToast('Error clearing library — is the server running?');
    console.error('Clear error:', e);
  } finally {
    btnClearLibrary.disabled = false;
  }
});

btnStudyGuide.addEventListener('click', () => {
  studyGuideModal.style.display = 'flex';
});

btnCloseGuide.addEventListener('click', () => {
  studyGuideModal.style.display = 'none';
});

studyGuideModal.addEventListener('click', (e) => {
  if (e.target === studyGuideModal) {
    studyGuideModal.style.display = 'none';
  }
});

// ─── Chapter Selection → Prompt View ─────────────────────

async function selectChapter(bookId, chapter) {
  try {
    const data = await api(`/warehouse/books/${bookId}/chapters/${chapter.id}`);
    if (data.success) {
      currentChapter = data.chapter;
      currentChapterBookId = bookId;
      const book = books.find(b => b.id === bookId);
      const bookLabel = book ? book.title : '';
      chapterTitle.textContent = `${bookLabel} — Ch. ${chapter.number}: ${chapter.title}`;
      generatedPrompt = '';
      promptOutput.style.display = 'none';
      generateArea.style.display = '';
      loading.style.display = 'none';
      showView('prompt');
    }
  } catch (e) {
    console.error('Failed to load chapter:', e);
  }
}

// ─── Upload ──────────────────────────────────────────────

btnUpload.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  showProgressOverlay('Uploading PDF...');

  try {
    const formData = new FormData();
    formData.append('pdf_file', file);
    formData.append('title', file.name.replace(/\.pdf$/i, ''));
    formData.append('background', 'true');

    const data = await api('/warehouse/upload', {
      method: 'POST',
      body: formData,
    });

    if (data.success && data.job_id) {
      await trackJobProgress(data.job_id, (state) => {
        if (state.status === 'done') {
          showToast('Book added successfully');
          loadBooks().then(() => {
            if (state.book_id) {
              const newBook = books.find(b => b.id === state.book_id);
              if (newBook) toggleBook(newBook);
            }
          });
        } else if (state.status === 'error') {
          showToast('Upload failed: ' + (state.error || 'Unknown error'));
        }
      });
    } else if (data.success && data.book) {
      showToast('Book added successfully');
      await loadBooks();
      const newBook = books.find(b => b.id === data.book.id) || data.book;
      toggleBook(newBook);
    } else {
      showToast('Upload failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    showToast('Upload failed — is the server running?');
    console.error('Upload error:', e);
  } finally {
    hideProgressOverlay();
    fileInput.value = '';
  }
});

// ─── Progress Tracking Helpers ───────────────────────────

const STEP_LABELS = {
  uploading: '📤 Uploading...',
  extracting_markdown: '📄 Extracting text from PDF...',
  applying_latexfix: '🔧 Fixing LaTeX formulas...',
  detecting_chapters: '📖 Detecting chapters...',
  analyzing_chapters: '🔍 Analyzing content...',
  building_knowledge_map: '🧠 Building knowledge map...',
  preparing_scan: '🔍 Preparing scan...',
  clearing_errors: '🧹 Clearing errors...',
  scanning_directory: '📂 Scanning for new PDFs...',
};

function showProgressOverlay(statusText) {
  uploadOverlay.style.display = '';
  uploadStatus.textContent = statusText;
  uploadStep.textContent = 'Preparing...';
  uploadProgressFill.style.width = '0%';
}

function hideProgressOverlay() {
  uploadOverlay.style.display = 'none';
}

function updateProgressUI(step, percent) {
  uploadStep.textContent = STEP_LABELS[step] || step;
  uploadProgressFill.style.width = `${Math.min(percent || 0, 100)}%`;
}

function trackJobProgress(jobId, onTerminal) {
  return new Promise((resolve) => {
    try {
      const evtSource = new EventSource(`${API}/warehouse/progress/${jobId}`);

      evtSource.onmessage = (event) => {
        const state = JSON.parse(event.data);
        updateProgressUI(state.step, state.percent);

        if (state.status === 'done' || state.status === 'error' || state.status === 'not_found') {
          evtSource.close();
          onTerminal(state);
          resolve(state);
        }
      };

      evtSource.onerror = () => {
        evtSource.close();
        pollJobProgress(jobId, onTerminal).then(resolve);
      };
    } catch {
      pollJobProgress(jobId, onTerminal).then(resolve);
    }
  });
}

async function pollJobProgress(jobId, onTerminal) {
  while (true) {
    try {
      const state = await api(`/warehouse/job/${jobId}`);
      if (state.success) {
        updateProgressUI(state.step, state.percent);
        if (state.status === 'done' || state.status === 'error') {
          onTerminal(state);
          return state;
        }
      }
    } catch {
      // Server might be busy, keep trying
    }
    await new Promise(r => setTimeout(r, 1000));
  }
}

// ─── Mode Selection ──────────────────────────────────────

modeBar.addEventListener('click', (e) => {
  const btn = e.target.closest('.mode-btn');
  if (!btn) return;

  modeBar.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  selectedMode = btn.dataset.mode;
});

// ─── Generate Prompt ─────────────────────────────────────

btnGenerate.addEventListener('click', async () => {
  if (!currentChapterBookId || !currentChapter) return;

  generateArea.style.display = 'none';
  promptOutput.style.display = 'none';
  loading.style.display = '';
  loadingText.textContent = 'Analyzing chapter...';

  try {
    const formData = new FormData();
    formData.append('mode', selectedMode);

    const data = await api(`/engine/prompt/${currentChapterBookId}/${currentChapter.id}`, {
      method: 'POST',
      body: formData,
    });

    if (data.success) {
      generatedPrompt = data.prompt;
      promptText.textContent = data.prompt;
      promptStats.textContent = `${data.word_count?.toLocaleString() || '?'} words · ~${data.est_tokens?.toLocaleString() || '?'} tokens${data.cached ? ' · cached' : ''}`;
      promptOutput.style.display = '';
    } else {
      showToast('Failed: ' + (data.error || 'Unknown error'));
      generateArea.style.display = '';
    }
  } catch (e) {
    showToast('Engine error — is the server running?');
    generateArea.style.display = '';
    console.error('Generate error:', e);
  } finally {
    loading.style.display = 'none';
  }
});

// ─── Copy & Download ─────────────────────────────────────

btnCopyPrompt.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(generatedPrompt);
    showToast('Copied to clipboard');
  } catch {
    const ta = document.createElement('textarea');
    ta.value = generatedPrompt;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('Copied');
  }
});

btnDownloadPrompt.addEventListener('click', () => {
  const book = books.find(b => b.id === currentChapterBookId);
  const filename = `${book?.title || 'prompt'}_ch${currentChapter?.number || ''}_${selectedMode}.md`;
  const blob = new Blob([generatedPrompt], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  showToast('Downloading...');
});

// ─── Navigation ──────────────────────────────────────────

btnDeselectAll.addEventListener('click', () => {
  selectedBookIds.clear();
  loadedChapters = {};
  currentChapter = null;
  renderBookList();
  showView('empty');
});

btnBackChapters.addEventListener('click', () => {
  currentChapter = null;
  currentChapterBookId = null;
  showView('chapters');
});

// ─── View Management ─────────────────────────────────────

function showView(view) {
  emptyState.style.display = 'none';
  chapterView.style.display = 'none';
  promptView.style.display = 'none';

  switch (view) {
    case 'empty':
      emptyState.style.display = '';
      break;
    case 'chapters':
      chapterView.style.display = '';
      break;
    case 'prompt':
      promptView.style.display = '';
      break;
  }
}

// ─── Helpers ─────────────────────────────────────────────

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2200);
}
