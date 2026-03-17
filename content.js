/**
 * content.js — Content Script for PDF Page Detection
 * Detects if the current page is a PDF and communicates with the popup.
 */

(function () {
  // Listen for messages from the popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'getPDFUrl') {
      const url = window.location.href;
      const isPDF =
        url.toLowerCase().endsWith('.pdf') ||
        document.contentType === 'application/pdf' ||
        url.includes('/pdf/') ||
        document.querySelector('embed[type="application/pdf"]') !== null;

      sendResponse({
        url: url,
        isPDF: isPDF,
        title: document.title || 'document'
      });
    }
    return true; // Keep message channel open for async response
  });
})();
