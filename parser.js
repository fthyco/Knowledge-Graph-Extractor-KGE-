/**
 * parser.js — PDF Text Extraction Module
 * Uses PDF.js to extract text items with position, font size, and font metadata.
 * Integrates math-utils.js for glyph remapping of mathematical symbols.
 * All processing is local — no data leaves the browser.
 */

/**
 * Load and parse a PDF document.
 * @param {string|ArrayBuffer} source — URL string or ArrayBuffer from file upload
 * @returns {Promise<Array<{pageNum: number, width: number, height: number, items: Array}>>}
 */
async function parsePDF(source) {
  // Configure PDF.js worker
  pdfjsLib.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL('lib/pdf.worker.min.js');

  const loadingParams = {};
  if (typeof source === 'string') {
    loadingParams.url = source;
  } else {
    loadingParams.data = source;
  }

  // Disable range/stream for cross-origin compatibility
  loadingParams.disableAutoFetch = false;
  loadingParams.disableStream = true;
  loadingParams.disableRange = true;

  const pdf = await pdfjsLib.getDocument(loadingParams).promise;
  const totalPages = pdf.numPages;
  const pages = [];

  // Reset math diagnostics for this document
  resetMathDiagnostics();

  for (let i = 1; i <= totalPages; i++) {
    const page = await pdf.getPage(i);
    const viewport = page.getViewport({ scale: 1.0 });
    const textContent = await page.getTextContent();

    const items = textContent.items
      .filter(item => item.str && item.str.trim().length > 0)
      .map(item => {
        const tx = item.transform; // [scaleX, skewX, skewY, scaleY, translateX, translateY]
        const fontSize = Math.abs(tx[3]) || Math.abs(tx[0]) || 12;
        const x = tx[4];
        // PDF coordinate system is bottom-up; convert to top-down
        const y = viewport.height - tx[5];
        const fontName = item.fontName || '';

        // ── Math glyph remapping ──
        const isMath = isMathFont(fontName);
        let processedText = item.str;

        _mathDiagnostics.totalItems++;

        if (isMath) {
          _mathDiagnostics.mathFontItems++;
          const remap = remapMathGlyphs(item.str, fontName);
          processedText = remap.text;
          if (remap.wasMapped) {
            _mathDiagnostics.remappedGlyphs++;
          }
        } else {
          // Apply common substitutions even for non-math fonts
          const remap = remapMathGlyphs(item.str, fontName);
          processedText = remap.text;
        }

        // Normalize the text
        processedText = normalizeText(processedText);

        return {
          text: processedText,
          x: Math.round(x * 100) / 100,
          y: Math.round(y * 100) / 100,
          width: item.width || 0,
          height: item.height || fontSize,
          fontSize: Math.round(fontSize * 100) / 100,
          fontName: fontName,
          isBold: /bold/i.test(fontName),
          isMathFont: isMath,
          hasEOL: item.hasEOL || false
        };
      });

    // ── Detect if this page has significant math content ──
    const mathItemCount = items.filter(it => it.isMathFont).length;
    const hasMathSymbols = items.some(it => containsMathSymbols(it.text));
    const pageHasMath = mathItemCount >= 3 || hasMathSymbols;

    pages.push({
      pageNum: i,
      width: viewport.width,
      height: viewport.height,
      items: items,
      hasMath: pageHasMath
    });
  }

  // Log math diagnostics
  logMathDiagnostics();

  return pages;
}
