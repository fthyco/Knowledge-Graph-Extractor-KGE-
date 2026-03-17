/**
 * marker-client.js — Communication with the local Marker Bridge server.
 * Provides functions to check server availability and send PDFs for
 * math-aware LaTeX conversion.
 */

const MARKER_CONFIG = {
  BASE_URL: 'http://localhost:8001',
  HEALTH_TIMEOUT: 2000,   // 2s timeout for health check
  CONVERT_TIMEOUT: 120000, // 2min timeout for conversion (marker is slow)
};

/**
 * Check if the Marker Bridge server is running.
 * @returns {Promise<boolean>}
 */
async function checkMarkerAvailable() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), MARKER_CONFIG.HEALTH_TIMEOUT);

    const response = await fetch(`${MARKER_CONFIG.BASE_URL}/health`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) return false;

    const data = await response.json();
    return data.status === 'ok';
  } catch (err) {
    // Server not running or unreachable
    console.log('[Marker] Server not available:', err.message);
    return false;
  }
}

/**
 * Send a PDF to the Marker Bridge for conversion.
 * @param {ArrayBuffer} pdfArrayBuffer — raw PDF data
 * @param {number[]} pageNumbers — 1-based page numbers to convert (empty = all)
 * @returns {Promise<{success: boolean, markdown: string, pages: Object}|null>}
 *          Returns null if the request fails.
 */
async function convertWithMarker(pdfArrayBuffer, pageNumbers = []) {
  try {
    const formData = new FormData();
    const blob = new Blob([pdfArrayBuffer], { type: 'application/pdf' });
    formData.append('pdf_file', blob, 'document.pdf');

    if (pageNumbers.length > 0) {
      formData.append('pages', pageNumbers.join(','));
    }

    formData.append('force_ocr', 'true');

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), MARKER_CONFIG.CONVERT_TIMEOUT);

    const response = await fetch(`${MARKER_CONFIG.BASE_URL}/convert`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('[Marker] Conversion failed:', errorData);
      return null;
    }

    const result = await response.json();

    if (!result.success) {
      console.error('[Marker] Conversion returned error:', result.error);
      return null;
    }

    console.log(`[Marker] Conversion successful — ${Object.keys(result.pages).length} page(s) returned`);
    return result;
  } catch (err) {
    if (err.name === 'AbortError') {
      console.error('[Marker] Conversion timed out');
    } else {
      console.error('[Marker] Conversion error:', err);
    }
    return null;
  }
}

/**
 * Send assembled Markdown to the Marker Bridge for a final latexfix pass.
 * @param {string} markdown - the assembled markdown
 * @returns {Promise<string|null>} - returns the fixed markdown or null on error
 */
async function fixWithLatexFix(markdown) {
  try {
    const formData = new FormData();
    formData.append('markdown', markdown);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), MARKER_CONFIG.CONVERT_TIMEOUT);

    const response = await fetch(`${MARKER_CONFIG.BASE_URL}/latexfix`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
        return null;
    }

    const result = await response.json();
    if (!result.success) {
        return null;
    }

    return result.markdown;
  } catch (err) {
    console.error('[Marker] LatexFix error:', err);
    return null;
  }
}
