/**
 * markdown.js — Markdown Generation, Table Detection & Chunking
 * Converts structured layout data into clean Markdown output.
 */

// ─── Table Detection ────────────────────────────────────────────

const TABLE_CONFIG = {
  MIN_COLUMNS: 2,
  MIN_ROWS: 3,               // Need at least 3 rows (header + 2 data)
  MIN_ITEMS: 8,              // Need at least 8 text items to consider a table
  COLUMN_X_TOLERANCE: 15,    // Items within this X range → same column
  ROW_Y_TOLERANCE: 8,        // Items within this Y range → same row
  MIN_FILL_RATIO: 0.5,       // At least 50% of cells must have content
};

/**
 * Attempt to detect a table from consecutive lines.
 * Returns table data if detected, null otherwise.
 * @param {Array} lines — classified lines from layout
 * @param {number} startIdx — starting line index to check
 * @returns {{rows: Array<Array<string>>, endIdx: number}|null}
 */
function detectTable(lines, startIdx) {
  // Collect items from consecutive non-heading, non-list lines
  const candidateItems = [];
  let endIdx = startIdx;

  for (let i = startIdx; i < lines.length; i++) {
    const line = lines[i];
    if (line.isHeading || line.isList) break;
    if (!line.items || !line.items.length) break;

    candidateItems.push(...line.items.map(it => ({
      text: it.text.trim(),
      x: it.x,
      y: it.y
    })));
    endIdx = i;
  }

  if (candidateItems.length < TABLE_CONFIG.MIN_ITEMS) {
    return null;
  }

  // Cluster X positions into columns
  const xPositions = [...new Set(candidateItems.map(it => it.x))].sort((a, b) => a - b);
  const columns = [];
  let currentCol = [xPositions[0]];

  for (let i = 1; i < xPositions.length; i++) {
    if (xPositions[i] - currentCol[currentCol.length - 1] <= TABLE_CONFIG.COLUMN_X_TOLERANCE) {
      currentCol.push(xPositions[i]);
    } else {
      columns.push(currentCol.reduce((a, b) => a + b) / currentCol.length); // avg X
      currentCol = [xPositions[i]];
    }
  }
  columns.push(currentCol.reduce((a, b) => a + b) / currentCol.length);

  if (columns.length < TABLE_CONFIG.MIN_COLUMNS) return null;

  // Cluster Y positions into rows
  const yPositions = [...new Set(candidateItems.map(it => it.y))].sort((a, b) => a - b);
  const rows = [];
  let currentRow = [yPositions[0]];

  for (let i = 1; i < yPositions.length; i++) {
    if (yPositions[i] - currentRow[currentRow.length - 1] <= TABLE_CONFIG.ROW_Y_TOLERANCE) {
      currentRow.push(yPositions[i]);
    } else {
      rows.push(currentRow.reduce((a, b) => a + b) / currentRow.length);
      currentRow = [yPositions[i]];
    }
  }
  rows.push(currentRow.reduce((a, b) => a + b) / currentRow.length);

  if (rows.length < TABLE_CONFIG.MIN_ROWS) return null;

  // Build table grid
  const grid = rows.map(() => columns.map(() => ''));

  candidateItems.forEach(item => {
    // Find closest column
    let colIdx = 0;
    let minColDist = Infinity;
    columns.forEach((cx, ci) => {
      const dist = Math.abs(item.x - cx);
      if (dist < minColDist) {
        minColDist = dist;
        colIdx = ci;
      }
    });

    // Find closest row
    let rowIdx = 0;
    let minRowDist = Infinity;
    rows.forEach((ry, ri) => {
      const dist = Math.abs(item.y - ry);
      if (dist < minRowDist) {
        minRowDist = dist;
        rowIdx = ri;
      }
    });

    // Append text to cell (in case multiple items map to same cell)
    if (grid[rowIdx][colIdx]) {
      grid[rowIdx][colIdx] += ' ' + item.text;
    } else {
      grid[rowIdx][colIdx] = item.text;
    }
  });

  // Validate: cells must have sufficient content
  const totalCells = rows.length * columns.length;
  const filledCells = grid.flat().filter(c => c.trim()).length;
  if (filledCells / totalCells < TABLE_CONFIG.MIN_FILL_RATIO) return null;

  return { rows: grid, endIdx };
}

/**
 * Convert a table grid to Markdown.
 * @param {Array<Array<string>>} rows
 * @returns {string}
 */
function tableToMarkdown(rows) {
  if (!rows.length) return '';

  const header = rows[0];
  const separator = header.map(() => '---');
  const dataRows = rows.slice(1);

  let md = '| ' + header.join(' | ') + ' |\n';
  md += '| ' + separator.join(' | ') + ' |\n';
  dataRows.forEach(row => {
    md += '| ' + row.join(' | ') + ' |\n';
  });

  return md;
}

// ─── Markdown Generation ────────────────────────────────────────

/**
 * Convert processed layout pages to Markdown.
 * @param {Array<{pageNum, lines}>} processedPages — from processLayout()
 * @returns {string} — complete Markdown document
 */
function generateMarkdown(processedPages) {
  const mdParts = [];
  let prevWasList = false;

  for (const page of processedPages) {
    const lines = page.lines;
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // Skip empty lines
      if (!line.text.trim()) {
        i++;
        continue;
      }

      // Heading
      if (line.isHeading) {
        if (mdParts.length > 0) mdParts.push('');
        const prefix = '#'.repeat(line.headingLevel);
        mdParts.push(`${prefix} ${line.text}`);
        mdParts.push('');
        prevWasList = false;
        i++;
        continue;
      }

      // List item
      if (line.isList) {
        if (!prevWasList && mdParts.length > 0) mdParts.push('');
        mdParts.push(`- ${line.listText}`);
        prevWasList = true;
        i++;
        continue;
      }

      // Try table detection — only if the line has multiple items
      // (a single-item line is never part of a table)
      if (line.items && line.items.length >= 2) {
        const table = detectTable(lines, i);
        if (table && table.rows.length >= TABLE_CONFIG.MIN_ROWS) {
          if (mdParts.length > 0) mdParts.push('');
          mdParts.push(tableToMarkdown(table.rows));
          prevWasList = false;
          i = table.endIdx + 1;
          continue;
        }
      }

      // Regular paragraph text
      if (prevWasList) mdParts.push('');
      prevWasList = false;

      // Merge consecutive paragraph lines
      let paragraph = line.text;
      let paragraphHasMath = line.hasMath || false;

      while (i + 1 < lines.length) {
        const nextLine = lines[i + 1];
        if (nextLine.isHeading || nextLine.isList || !nextLine.text.trim()) break;
        // Check if lines are close enough to be the same paragraph
        const gap = Math.abs(nextLine.items[0].y - lines[i].items[0].y);
        const avgFontSize = line.items[0].fontSize;
        if (gap > avgFontSize * 2.5) break; // Too much gap = new paragraph
        paragraph += ' ' + nextLine.text;
        if (nextLine.hasMath) paragraphHasMath = true;
        i++;
      }

      // If the paragraph has math symbols but wasn't already wrapped,
      // check if we need to add $ delimiters around isolated math expressions
      if (paragraphHasMath || containsMathSymbols(paragraph)) {
        paragraph = ensureMathDelimiters(paragraph);
      }

      mdParts.push(paragraph);
      mdParts.push('');
      i++;
    }
  }

  // Clean up excessive blank lines
  let result = mdParts.join('\n');
  result = result.replace(/\n{3,}/g, '\n\n');
  return result.trim();
}

/**
 * Ensure math expressions have proper $ delimiters.
 * Scans text for sequences of math symbols not already inside $...$ and wraps them.
 * @param {string} text
 * @returns {string}
 */
function ensureMathDelimiters(text) {
  // If already has $ delimiters, leave it alone
  if (/\$[^$]+\$/.test(text)) return text;

  // Pattern: sequences containing Greek/math symbols possibly mixed with
  // Latin letters, digits, and math operators that look like expressions.
  // This regex finds sequences with at least one math Unicode character.
  const mathExprPattern = /([α-ωΑ-Ω∑∏∫∂∇∞±×÷·≤≥≠≈≡∈∉⊂⊃⊆⊇∪∩∧∨∀∃¬→←↔⇒⇐⇔⊕⊗√∝≺≻≼≽∼≃≪≫⌊⌋⌈⌉⟨⟩−][\w\s^_{},+\-=<>().*αβγδεζηθικλμνξπρσςτυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ∑∏∫∂∇∞±×÷·≤≥≠≈≡∈∉⊂⊃⊆⊇∪∩∧∨∀∃¬→←↔⇒⇐⇔⊕⊗√∝]*)/g;

  return text.replace(mathExprPattern, (match) => {
    // Don't wrap if it's already inside $ delimiters
    return '$' + match.trim() + '$';
  });
}

// ─── Chunking ───────────────────────────────────────────────────

const CHUNK_CONFIG = {
  MIN_WORDS: 500,
  MAX_WORDS: 1000,
};

/**
 * Split Markdown into chunks of 500-1000 words.
 * Prefers splitting at heading boundaries.
 * @param {string} markdown — full Markdown text
 * @returns {Array<{index: number, content: string, wordCount: number}>}
 */
function chunkMarkdown(markdown) {
  const lines = markdown.split('\n');
  const chunks = [];
  let currentChunk = [];
  let currentWordCount = 0;

  function pushChunk() {
    if (currentChunk.length === 0) return;
    const content = currentChunk.join('\n').trim();
    if (content) {
      chunks.push({
        index: chunks.length + 1,
        content,
        wordCount: currentWordCount
      });
    }
    currentChunk = [];
    currentWordCount = 0;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const words = line.trim().split(/\s+/).filter(w => w.length > 0).length;

    // If we hit a heading and current chunk is big enough, split
    if (/^#{1,3}\s/.test(line) && currentWordCount >= CHUNK_CONFIG.MIN_WORDS) {
      pushChunk();
    }

    currentChunk.push(line);
    currentWordCount += words;

    // Force split if we exceed max
    if (currentWordCount >= CHUNK_CONFIG.MAX_WORDS) {
      pushChunk();
    }
  }

  // Push remaining
  pushChunk();

  // If the last chunk is too small, merge with the previous one
  if (chunks.length > 1 && chunks[chunks.length - 1].wordCount < CHUNK_CONFIG.MIN_WORDS / 2) {
    const last = chunks.pop();
    chunks[chunks.length - 1].content += '\n\n' + last.content;
    chunks[chunks.length - 1].wordCount += last.wordCount;
  }

  return chunks;
}
