/**
 * layout.js — Reading Order Reconstruction & Structure Detection
 * Handles: reading order, column detection, heading detection,
 * list detection, and noise removal (headers/footers/page numbers).
 */

// ─── Configuration ───────────────────────────────────────────────
const LAYOUT_CONFIG = {
  LINE_Y_TOLERANCE: 5,           // Max Y difference to consider items on the same line
  COLUMN_GAP_RATIO: 0.15,       // Min gap ratio of page width to split columns
  HEADING_SIZE_RATIO: 1.2,      // fontSize > median * ratio → heading
  HEADING_GAP_RATIO: 2.5,       // Vertical gap > avg * ratio → section break
  NOISE_PAGE_THRESHOLD: 0.6,    // Text in >60% of pages → noise
  NOISE_Y_TOP_RATIO: 0.08,      // Top 8% of page → header zone
  NOISE_Y_BOTTOM_RATIO: 0.92,   // Bottom 8% of page → footer zone
};

// ─── Reading Order ───────────────────────────────────────────────

/**
 * Group text items into lines based on Y proximity.
 * @param {Array} items — text items from parser
 * @returns {Array<Array>} — grouped lines
 */
function groupIntoLines(items) {
  if (!items.length) return [];

  const sorted = [...items].sort((a, b) => a.y - b.y || a.x - b.x);
  const lines = [];
  let currentLine = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const prev = currentLine[0];
    const curr = sorted[i];
    if (Math.abs(curr.y - prev.y) <= LAYOUT_CONFIG.LINE_Y_TOLERANCE) {
      currentLine.push(curr);
    } else {
      currentLine.sort((a, b) => a.x - b.x);
      lines.push(currentLine);
      currentLine = [curr];
    }
  }
  currentLine.sort((a, b) => a.x - b.x);
  lines.push(currentLine);

  return lines;
}

/**
 * Detect multi-column layout and reorder lines accordingly.
 * @param {Array<Array>} lines — grouped lines
 * @param {number} pageWidth — total page width
 * @returns {Array<Array>} — reordered lines (column by column)
 */
function detectColumns(lines, pageWidth) {
  if (lines.length < 3) return lines;

  // Collect all X midpoints
  const midpoints = [];
  lines.forEach(line => {
    line.forEach(item => {
      midpoints.push(item.x + (item.width || 0) / 2);
    });
  });

  midpoints.sort((a, b) => a - b);
  const midPage = pageWidth / 2;
  const gapThreshold = pageWidth * LAYOUT_CONFIG.COLUMN_GAP_RATIO;

  // Check for a gap near the center
  let hasColumnGap = false;
  const leftItems = midpoints.filter(x => x < midPage - gapThreshold / 2);
  const rightItems = midpoints.filter(x => x > midPage + gapThreshold / 2);

  if (leftItems.length > lines.length * 0.3 && rightItems.length > lines.length * 0.3) {
    hasColumnGap = true;
  }

  if (!hasColumnGap) return lines;

  // Split into left and right columns
  const leftLines = [];
  const rightLines = [];

  lines.forEach(line => {
    const avgX = line.reduce((s, it) => s + it.x, 0) / line.length;
    if (avgX < midPage) {
      leftLines.push(line);
    } else {
      rightLines.push(line);
    }
  });

  return [...leftLines, ...rightLines];
}

/**
 * Reconstruct proper reading order for a page.
 * @param {Array} items — raw text items
 * @param {number} pageWidth — page width
 * @returns {Array<Array>} — ordered lines
 */
function reconstructReadingOrder(items, pageWidth) {
  const lines = groupIntoLines(items);
  return detectColumns(lines, pageWidth);
}

// ─── Heading Detection ──────────────────────────────────────────

/**
 * Calculate the median font size across all items.
 * @param {Array<Array>} allPagesItems — items from all pages
 * @returns {number}
 */
function computeMedianFontSize(allPagesItems) {
  const sizes = [];
  allPagesItems.forEach(items => {
    items.forEach(item => sizes.push(item.fontSize));
  });
  if (!sizes.length) return 12;
  sizes.sort((a, b) => a - b);
  const mid = Math.floor(sizes.length / 2);
  return sizes.length % 2 ? sizes[mid] : (sizes[mid - 1] + sizes[mid]) / 2;
}

/**
 * Compute average line spacing.
 * @param {Array<Array>} lines — grouped lines
 * @returns {number}
 */
function computeAvgLineGap(lines) {
  if (lines.length < 2) return 15;
  let totalGap = 0;
  let count = 0;
  for (let i = 1; i < lines.length; i++) {
    const gap = Math.abs(lines[i][0].y - lines[i - 1][0].y);
    if (gap > 0 && gap < 200) {
      totalGap += gap;
      count++;
    }
  }
  return count > 0 ? totalGap / count : 15;
}

/**
 * Classify a line as a heading and determine its level.
 * @param {Array} line — items in the line
 * @param {number} medianFontSize 
 * @param {number} avgLineGap
 * @param {number|null} gapBefore — vertical gap before this line
 * @returns {{isHeading: boolean, level: number}}
 */
function classifyHeading(line, medianFontSize, avgLineGap, gapBefore) {
  const lineText = line.map(it => it.text).join(' ').trim();
  
  // Hard rule: if it looks like a list item or is too long, it's not a heading
  if (detectListItem(lineText).isList || lineText.length > 150) {
      return { isHeading: false, level: 0 };
  }

  const maxFontSize = Math.max(...line.map(it => it.fontSize));
  const allBold = line.every(it => it.isBold);
  const largeFont = maxFontSize > medianFontSize * LAYOUT_CONFIG.HEADING_SIZE_RATIO;
  
  // If we rely on bold alone, it must have a significant gap before it to avoid breaking sentences
  const bigGap = gapBefore !== null && gapBefore > avgLineGap * LAYOUT_CONFIG.HEADING_GAP_RATIO;
  const isHeading = largeFont || (allBold && bigGap && lineText.length < 100);

  if (!isHeading) return { isHeading: false, level: 0 };

  // Assign level based on font size ratio
  const ratio = maxFontSize / medianFontSize;
  let level;
  if (ratio > 1.8) level = 1;
  else if (ratio > 1.35) level = 2;
  else level = 3;

  return { isHeading: true, level };
}

// ─── List Detection ─────────────────────────────────────────────

const LIST_BULLET_REGEX = /^(\s*)([-–•*]|\d+[.)]\s)/;

/**
 * Check if a line is a list item.
 * @param {string} text — line text
 * @returns {{isList: boolean, text: string}}
 */
function detectListItem(text) {
  const match = text.match(LIST_BULLET_REGEX);
  if (match) {
    const cleaned = text.slice(match[0].length).trim();
    return { isList: true, text: cleaned };
  }
  return { isList: false, text };
}

// ─── Noise Removal ──────────────────────────────────────────────

/**
 * Identify noise patterns (headers, footers, page numbers, watermarks).
 * @param {Array<{pageNum, width, height, items}>} pages — parsed pages
 * @returns {Set<string>} — set of noise text strings to remove
 */
function identifyNoise(pages) {
  const totalPages = pages.length;
  if (totalPages < 3) return new Set();

  // Count text occurrences in header/footer zones
  const textCounts = {};

  pages.forEach(page => {
    const topThreshold = page.height * LAYOUT_CONFIG.NOISE_Y_TOP_RATIO;
    const bottomThreshold = page.height * LAYOUT_CONFIG.NOISE_Y_BOTTOM_RATIO;
    const seenOnPage = new Set();

    page.items.forEach(item => {
      const inHeaderZone = item.y <= topThreshold;
      const inFooterZone = item.y >= bottomThreshold;

      if (inHeaderZone || inFooterZone) {
        const normalized = item.text.trim().toLowerCase();
        if (normalized && !seenOnPage.has(normalized)) {
          seenOnPage.add(normalized);
          textCounts[normalized] = (textCounts[normalized] || 0) + 1;
        }
      }
    });
  });

  const noiseTexts = new Set();
  const threshold = totalPages * LAYOUT_CONFIG.NOISE_PAGE_THRESHOLD;

  for (const [text, count] of Object.entries(textCounts)) {
    if (count >= threshold) {
      noiseTexts.add(text);
    }
  }

  // Add standalone page numbers or "Page X of Y" / "X / Y"
  const pageNumRegex = /^\s*(?:Page\s+)?\d{1,4}\s*(?:(?:of|\/)\s*\d{1,4})?\s*$/i;
  pages.forEach(page => {
    page.items.forEach(item => {
      if (pageNumRegex.test(item.text.trim())) {
        const inHeaderZone = item.y <= page.height * LAYOUT_CONFIG.NOISE_Y_TOP_RATIO;
        const inFooterZone = item.y >= page.height * LAYOUT_CONFIG.NOISE_Y_BOTTOM_RATIO;
        if (inHeaderZone || inFooterZone) {
          noiseTexts.add(item.text.trim().toLowerCase());
        }
      }
    });
  });

  return noiseTexts;
}

/**
 * Remove noise items from a page's items.
 * @param {Array} items 
 * @param {Set<string>} noiseTexts 
 * @returns {Array}
 */
function removeNoise(items, noiseTexts) {
  if (!noiseTexts.size) return items;
  return items.filter(item => {
    const normalized = item.text.trim().toLowerCase();
    return !noiseTexts.has(normalized);
  });
}

// ─── Main Layout Pipeline ───────────────────────────────────────

/**
 * Process all pages through the layout pipeline.
 * @param {Array<{pageNum, width, height, items}>} pages — from parser
 * @returns {Array<{pageNum, lines: Array<{items, isHeading, headingLevel, isList, listText}>}>} 
 */
function processLayout(pages) {
  // Step 1: Identify noise across all pages
  const noiseTexts = identifyNoise(pages);

  // Step 2: Compute document-wide median font size
  const allItems = pages.map(p => p.items);
  const medianFontSize = computeMedianFontSize(allItems);

  // Step 3: Process each page
  const result = [];

  for (const page of pages) {
    // Remove noise
    const cleanItems = removeNoise(page.items, noiseTexts);

    // Reconstruct reading order
    const orderedLines = reconstructReadingOrder(cleanItems, page.width);

    // Compute average line gaps for this page
    const avgLineGap = computeAvgLineGap(orderedLines);

    // Classify each line
    const classifiedLines = orderedLines.map((line, idx) => {
      // ── Detect superscripts/subscripts in this line ──
      const annotatedLine = detectScripts(line);

      // Update diagnostics
      annotatedLine.forEach(it => {
        if (it.isSuperscript) _mathDiagnostics.superscripts++;
        if (it.isSubscript) _mathDiagnostics.subscripts++;
      });

      // Check if this line has any math content
      const hasMath = annotatedLine.some(it =>
        it.isMathFont || it.isSuperscript || it.isSubscript
      );

      // Build line text — use math-aware formatting if math is present
      const lineText = hasMath
        ? formatMathLine(annotatedLine)
        : annotatedLine.map(it => it.text).join(' ').trim();

      // Gap before this line
      let gapBefore = null;
      if (idx > 0) {
        gapBefore = Math.abs(annotatedLine[0].y - orderedLines[idx - 1][0].y);
      }

      const { isHeading, level } = classifyHeading(annotatedLine, medianFontSize, avgLineGap, gapBefore);
      const { isList, text: listText } = detectListItem(lineText);

      return {
        items: annotatedLine,
        text: lineText,
        isHeading,
        headingLevel: level,
        isList,
        listText: isList ? listText : lineText,
        hasMath
      };
    });

    result.push({
      pageNum: page.pageNum,
      lines: classifiedLines
    });
  }

  return result;
}
