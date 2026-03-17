/**
 * popup.js — Extension Popup Controller
 * Orchestrates the PDF → Layout → Markdown pipeline and manages the UI.
 */

// ─── DOM Elements ────────────────────────────────────────────
const btnProcess = document.getElementById('btn-process');
const btnUpload = document.getElementById('btn-upload');
const fileInput = document.getElementById('file-input');
const progressContainer = document.getElementById('progress-container');
const progressText = document.getElementById('progress-text');
const progressPercent = document.getElementById('progress-percent');
const progressFill = document.getElementById('progress-fill');
const statsRow = document.getElementById('stats-row');
const statPages = document.getElementById('stat-pages');
const statWords = document.getElementById('stat-words');
const statChunks = document.getElementById('stat-chunks');
const outputSection = document.getElementById('output-section');
const outputTextarea = document.getElementById('output-textarea');
const chunkNav = document.getElementById('chunk-nav');
const chunkIndicator = document.getElementById('chunk-indicator');
const btnPrevChunk = document.getElementById('btn-prev-chunk');
const btnNextChunk = document.getElementById('btn-next-chunk');
const btnCopy = document.getElementById('btn-copy');
const btnDownload = document.getElementById('btn-download');
const btnCopyAll = document.getElementById('btn-copy-all');
const btnChatGPT = document.getElementById('btn-chatgpt');
const bottomActions = document.getElementById('bottom-actions');
const errorMessage = document.getElementById('error-message');
const toast = document.getElementById('toast');

// ─── State ──────────────────────────────────────────────────
let fullMarkdown = '';
let chunks = [];
let currentChunkIndex = 0;
let documentTitle = 'document';

// ─── Progress ───────────────────────────────────────────────

function showProgress(text, percent) {
  progressContainer.classList.add('active');
  progressText.textContent = text;
  progressPercent.textContent = `${Math.round(percent)}%`;
  progressFill.style.width = `${percent}%`;
}

function hideProgress() {
  progressContainer.classList.remove('active');
}

function showError(msg) {
  errorMessage.textContent = msg;
  errorMessage.classList.add('active');
}

function hideError() {
  errorMessage.classList.remove('active');
  errorMessage.textContent = '';
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2200);
}

// ─── Results Display ────────────────────────────────────────

function displayResults(md, pageCount) {
  fullMarkdown = md;
  chunks = chunkMarkdown(md);
  currentChunkIndex = 0;

  // Stats
  const wordCount = md.split(/\s+/).filter(w => w.length > 0).length;
  statPages.textContent = pageCount;
  statWords.textContent = wordCount.toLocaleString();
  statChunks.textContent = chunks.length;
  statsRow.classList.add('active');

  // Output
  outputSection.classList.add('active');
  updateChunkDisplay();

  // Chunk navigation
  if (chunks.length > 1) {
    chunkNav.classList.add('active');
  } else {
    chunkNav.classList.remove('active');
  }

  // Bottom actions
  bottomActions.classList.add('active');

  hideProgress();
}

function updateChunkDisplay() {
  if (chunks.length === 0) return;

  outputTextarea.value = chunks[currentChunkIndex].content;
  chunkIndicator.textContent = `Chunk ${currentChunkIndex + 1} / ${chunks.length}`;

  btnPrevChunk.disabled = currentChunkIndex === 0;
  btnNextChunk.disabled = currentChunkIndex === chunks.length - 1;
}

// ─── Processing Pipeline ────────────────────────────────────

async function processPDFSource(source, title) {
  hideError();
  documentTitle = title || 'document';

  try {
    // Disable buttons during processing
    btnProcess.disabled = true;
    btnUpload.disabled = true;

    // Step 1: Parse PDF
    showProgress('Extracting text from PDF...', 10);
    const pages = await parsePDF(source);

    if (!pages || pages.length === 0) {
      throw new Error('No pages found in the PDF.');
    }

    // Count total extracted items for diagnostics
    const totalItems = pages.reduce((sum, p) => sum + p.items.length, 0);
    console.log(`[PDF→MD] Parsed ${pages.length} pages, ${totalItems} text items`);

    if (totalItems === 0) {
      throw new Error('No text could be extracted from this PDF. It may be an image-based (scanned) document.');
    }

    // Step 2: Identify math pages
    const mathPageNumbers = pages
      .filter(p => p.hasMath)
      .map(p => p.pageNum);
    const nonMathPages = pages.filter(p => !p.hasMath);

    console.log(`[PDF→MD] Math pages: [${mathPageNumbers.join(', ')}], Non-math pages: ${nonMathPages.length}`);

    // Step 3: Process non-math pages through current pipeline
    showProgress('Reconstructing layout...', 30);
    await new Promise(r => setTimeout(r, 50));

    let nonMathMdByPage = {};
    if (nonMathPages.length > 0) {
      const processedNonMath = processLayout(nonMathPages);
      // Generate markdown per-page for non-math pages
      for (const processed of processedNonMath) {
        const pageMd = generateMarkdown([processed]);
        if (pageMd.trim()) {
          nonMathMdByPage[processed.pageNum] = pageMd;
        }
      }
    }

    // Step 4: Process math pages through Marker (if available)
    let markerMdByPage = {};
    if (mathPageNumbers.length > 0) {
      showProgress('Checking Marker server...', 45);
      await new Promise(r => setTimeout(r, 50));

      const markerAvailable = await checkMarkerAvailable();

      if (markerAvailable) {
        showProgress('Processing math pages with Marker...', 50);
        await new Promise(r => setTimeout(r, 50));

        // We need the original PDF source as ArrayBuffer for marker
        let pdfBuffer;
        if (source instanceof ArrayBuffer) {
          pdfBuffer = source;
        } else if (typeof source === 'string') {
          // Fetch the PDF from URL to get ArrayBuffer
          try {
            const resp = await fetch(source);
            pdfBuffer = await resp.arrayBuffer();
          } catch (fetchErr) {
            console.warn('[PDF→MD] Could not fetch PDF for Marker:', fetchErr);
            pdfBuffer = null;
          }
        }

        if (pdfBuffer) {
          const markerResult = await convertWithMarker(pdfBuffer, mathPageNumbers);

          if (markerResult && markerResult.success) {
            // Use marker's per-page output
            for (const [pageStr, pageMd] of Object.entries(markerResult.pages)) {
              if (pageMd.trim()) {
                markerMdByPage[parseInt(pageStr)] = pageMd;
              }
            }
            console.log(`[PDF→MD] Marker returned ${Object.keys(markerMdByPage).length} page(s)`);
          } else {
            console.warn('[PDF→MD] Marker conversion failed, falling back to current method for math pages');
          }
        }
      } else {
        console.warn('[PDF→MD] Marker server not available, using current method for math pages');
      }

      // Fallback: process math pages through current pipeline if marker didn't handle them
      const unhandledMathPages = pages.filter(
        p => p.hasMath && !markerMdByPage[p.pageNum]
      );
      if (unhandledMathPages.length > 0) {
        const processedFallback = processLayout(unhandledMathPages);
        for (const processed of processedFallback) {
          const pageMd = generateMarkdown([processed]);
          if (pageMd.trim()) {
            nonMathMdByPage[processed.pageNum] = pageMd;
          }
        }
      }
    }

    // Step 5: Merge all pages in order
    showProgress('Generating Markdown...', 85);
    await new Promise(r => setTimeout(r, 50));

    const allPageMd = [];
    for (let i = 1; i <= pages.length; i++) {
      if (markerMdByPage[i]) {
        allPageMd.push(markerMdByPage[i]);
      } else if (nonMathMdByPage[i]) {
        allPageMd.push(nonMathMdByPage[i]);
      }
    }

    let md = allPageMd.join('\n\n');

    // Fallback: if merged output is empty but we have raw text
    if (!md.trim() && totalItems > 0) {
      console.log('[PDF→MD] Merged pipeline returned empty, using raw text fallback');
      md = generateRawFallback(pages);
    }

    if (!md.trim()) {
      throw new Error('No text could be extracted from this PDF. It may be an image-based (scanned) document.');
    }

    // Clean up excessive blank lines
    md = md.replace(/\n{3,}/g, '\n\n').trim();

    showProgress('Complete!', 100);
    await new Promise(r => setTimeout(r, 300));

    // Display
    displayResults(md, pages.length);

    // Save last result
    chrome.storage.local.set({
      lastResult: md,
      lastTitle: documentTitle,
      timestamp: Date.now()
    });

  } catch (err) {
    hideProgress();
    showError(`Error: ${err.message}`);
    console.error('PDF processing error:', err);
  } finally {
    btnProcess.disabled = false;
    btnUpload.disabled = false;
  }
}

/**
 * Raw text fallback — concatenate all items page by page when
 * the structured pipeline fails to produce output.
 */
function generateRawFallback(pages) {
  const parts = [];
  for (const page of pages) {
    // Sort items top-to-bottom, left-to-right
    const sorted = [...page.items].sort((a, b) => a.y - b.y || a.x - b.x);
    let prevY = null;
    const lines = [];
    let currentLine = [];

    for (const item of sorted) {
      if (prevY !== null && Math.abs(item.y - prevY) > 5) {
        lines.push(currentLine.map(it => it.text).join(' '));
        currentLine = [];
      }
      currentLine.push(item);
      prevY = item.y;
    }
    if (currentLine.length) {
      lines.push(currentLine.map(it => it.text).join(' '));
    }

    parts.push(lines.join('\n'));
  }
  return parts.join('\n\n---\n\n');
}

// ─── Event Handlers ─────────────────────────────────────────

// Process active tab PDF
btnProcess.addEventListener('click', async () => {
  hideError();

  try {
    // Get the active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab) {
      showError('No active tab found.');
      return;
    }

    // First, inject the content script
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });
    } catch (e) {
      // Content script might already be injected, ignore error
    }

    // Try to communicate with the content script
    let response;
    try {
      response = await chrome.tabs.sendMessage(tab.id, { action: 'getPDFUrl' });
    } catch (e) {
      // If content script communication fails, check the URL directly
      const url = tab.url || '';
      const isPDF = url.toLowerCase().endsWith('.pdf') ||
                    url.includes('.pdf?') ||
                    url.includes('/pdf/');

      if (isPDF) {
        response = { url, isPDF: true, title: tab.title || 'document' };
      } else {
        showError('Could not detect a PDF in the active tab. Try uploading the file manually.');
        return;
      }
    }

    if (!response || !response.isPDF) {
      showError('The active tab does not appear to be a PDF. Try uploading the file instead.');
      return;
    }

    await processPDFSource(response.url, response.title);

  } catch (err) {
    showError(`Error: ${err.message}`);
  }
});

// Upload local PDF
btnUpload.addEventListener('click', () => {
  fileInput.click();
});

fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    showError('Please select a valid PDF file.');
    return;
  }

  const arrayBuffer = await file.arrayBuffer();
  const title = file.name.replace(/\.pdf$/i, '');
  await processPDFSource(arrayBuffer, title);

  // Reset file input
  fileInput.value = '';
});

// Chunk navigation
btnPrevChunk.addEventListener('click', () => {
  if (currentChunkIndex > 0) {
    currentChunkIndex--;
    updateChunkDisplay();
  }
});

btnNextChunk.addEventListener('click', () => {
  if (currentChunkIndex < chunks.length - 1) {
    currentChunkIndex++;
    updateChunkDisplay();
  }
});

// Copy current chunk
btnCopy.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(outputTextarea.value);
    showToast('Chunk copied to clipboard!');
  } catch {
    outputTextarea.select();
    document.execCommand('copy');
    showToast('Copied!');
  }
});

// Copy all
btnCopyAll.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(fullMarkdown);
    showToast('Full document copied!');
  } catch {
    outputTextarea.value = fullMarkdown;
    outputTextarea.select();
    document.execCommand('copy');
    showToast('Copied!');
  }
});

// Download .md
btnDownload.addEventListener('click', () => {
  const blob = new Blob([fullMarkdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${documentTitle}.md`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('Downloading...');
});

// Open in ChatGPT
btnChatGPT.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(fullMarkdown);
    chrome.tabs.create({ url: 'https://chat.openai.com/' });
    showToast('Text copied! Paste it in ChatGPT.');
  } catch {
    showToast('Could not copy. Please copy manually.');
  }
});

// ─── Restore Last Result ────────────────────────────────────

chrome.storage.local.get(['lastResult', 'lastTitle', 'timestamp'], (data) => {
  if (data.lastResult && data.timestamp) {
    const ageMs = Date.now() - data.timestamp;
    // Only restore if less than 30 minutes old
    if (ageMs < 30 * 60 * 1000) {
      fullMarkdown = data.lastResult;
      documentTitle = data.lastTitle || 'document';
      chunks = chunkMarkdown(fullMarkdown);
      currentChunkIndex = 0;

      const wordCount = fullMarkdown.split(/\s+/).filter(w => w.length > 0).length;
      statWords.textContent = wordCount.toLocaleString();
      statChunks.textContent = chunks.length;
      statPages.textContent = '—';
      statsRow.classList.add('active');
      outputSection.classList.add('active');
      updateChunkDisplay();
      if (chunks.length > 1) chunkNav.classList.add('active');
      bottomActions.classList.add('active');
    }
  }
});
