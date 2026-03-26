/**
 * organizer.js — Book Organizer Controller
 * Manages the full-page organizer UI: book library, chapter browsing,
 * and study prompt generation.
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
const bookTitle = document.getElementById('book-title');
const bookStats = document.getElementById('book-stats');
const chapterList = document.getElementById('chapter-list');
const btnBack = document.getElementById('btn-back');
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
const toast = document.getElementById('toast');
const knowledgePanel = document.getElementById('knowledge-panel');
const knowledgeMatches = document.getElementById('knowledge-matches');
const knowledgeSubtitle = document.getElementById('knowledge-subtitle');

// ─── State ───────────────────────────────────────────────
let books = [];
let currentBook = null;
let currentChapters = [];
let currentChapter = null;
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
      // Only show ready books (filter out errors)
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
    showView('empty');
    return;
  }

  books.forEach(book => {
    const btn = document.createElement('button');
    btn.className = 'book-item' + (currentBook && currentBook.id === book.id ? ' active' : '');
    btn.innerHTML = `
      <svg class="book-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      </svg>
      <span class="book-name">${escapeHtml(book.title)}</span>
      <span class="book-chapters">${book.total_chapters || '?'}</span>
    `;
    btn.onclick = () => selectBook(book);
    bookList.appendChild(btn);
  });
}

// ─── Scan Library ────────────────────────────────────────

btnScan.addEventListener('click', async () => {
  btnScan.disabled = true;
  btnScan.textContent = '⟳ Scanning...';

  uploadOverlay.style.display = '';
  uploadStatus.textContent = 'Scanning and processing PDFs...';

  try {
    const data = await api('/warehouse/scan', { method: 'POST' });

    if (data.success) {
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
    uploadOverlay.style.display = 'none';
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
      currentBook = null;
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

async function selectBook(book) {
  currentBook = book;
  renderBookList();

  bookTitle.textContent = book.title;
  bookStats.textContent = `${book.total_chapters || 0} chapters · ${(book.total_words || 0).toLocaleString()} words`;

  // Load chapters
  try {
    const data = await api(`/warehouse/books/${book.id}/chapters`);
    if (data.success) {
      currentChapters = data.chapters || [];
      renderChapterList();
      showView('chapters');
      loadKnowledgeMap(book.id);
    }
  } catch (e) {
    console.error('Failed to load chapters:', e);
  }
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
        card.onclick = () => selectBook(relatedBook);
      }
      knowledgeMatches.appendChild(card);
    });

    knowledgePanel.style.display = '';
  } catch (e) {
    console.error('Knowledge map error:', e);
  }
}

function renderChapterList() {
  chapterList.innerHTML = '';

  currentChapters.forEach(ch => {
    const btn = document.createElement('button');
    btn.className = 'chapter-item';
    btn.innerHTML = `
      <span class="ch-number">${ch.number}</span>
      <span class="ch-title">${escapeHtml(ch.title)}</span>
      <span class="ch-words">${(ch.word_count || 0).toLocaleString()} words</span>
    `;
    btn.onclick = () => selectChapter(ch);
    chapterList.appendChild(btn);
  });
}

async function selectChapter(chapter) {
  // Load full chapter data
  try {
    const data = await api(`/warehouse/books/${currentBook.id}/chapters/${chapter.id}`);
    if (data.success) {
      currentChapter = data.chapter;
      chapterTitle.textContent = `Ch. ${chapter.number}: ${chapter.title}`;
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

  uploadOverlay.style.display = '';
  uploadStatus.textContent = 'Uploading and processing...';

  try {
    const formData = new FormData();
    formData.append('pdf_file', file);
    formData.append('title', file.name.replace(/\.pdf$/i, ''));

    const data = await api('/warehouse/upload', {
      method: 'POST',
      body: formData,
    });

    if (data.success) {
      showToast('Book added successfully');
      await loadBooks();
      if (data.book) {
        // Select the new book
        const newBook = books.find(b => b.id === data.book.id) || data.book;
        selectBook(newBook);
      }
    } else {
      showToast('Upload failed: ' + (data.error || 'Unknown error'));
    }
  } catch (e) {
    showToast('Upload failed — is the server running?');
    console.error('Upload error:', e);
  } finally {
    uploadOverlay.style.display = 'none';
    fileInput.value = '';
  }
});

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
  if (!currentBook || !currentChapter) return;

  generateArea.style.display = 'none';
  promptOutput.style.display = 'none';
  loading.style.display = '';
  loadingText.textContent = 'Analyzing chapter...';

  try {
    const formData = new FormData();
    formData.append('mode', selectedMode);

    const data = await api(`/engine/prompt/${currentBook.id}/${currentChapter.id}`, {
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
    // Fallback
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
  const filename = `${currentBook?.title || 'prompt'}_ch${currentChapter?.number || ''}_${selectedMode}.md`;
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

btnBack.addEventListener('click', () => {
  currentBook = null;
  renderBookList();
  showView(books.length ? 'empty' : 'empty');
  // Actually show empty or just deselect
  showView('empty');
});

btnBackChapters.addEventListener('click', () => {
  currentChapter = null;
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
