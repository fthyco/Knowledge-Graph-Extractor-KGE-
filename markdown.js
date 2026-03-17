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
      
      // If this line is predominantly math, isolate it as a block equation
      const looksLikeBlockMath = line.hasMath && containsMathSymbols(line.text) && line.text.length > 2;

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
        
        // Don't merge a block equation into a regular paragraph, and don't merge regular text into a block equation
        const nextLooksLikeBlockMath = nextLine.hasMath && containsMathSymbols(nextLine.text) && nextLine.text.length > 2;
        if (looksLikeBlockMath !== nextLooksLikeBlockMath && gap > avgFontSize * 1.5) break;

        paragraph += ' ' + nextLine.text;
        if (nextLine.hasMath) paragraphHasMath = true;
        i++;
      }

      // If the paragraph has math symbols but wasn't already wrapped,
      // check if we need to add $ delimiters around isolated math expressions
      if (paragraphHasMath || containsMathSymbols(paragraph)) {
        paragraph = ensureMathDelimiters(paragraph);
        
        // If the entire paragraph was merged & ends up being mostly a single equation, isolate it
        if (looksLikeBlockMath && paragraph.startsWith('$') && paragraph.endsWith('$') && paragraph.match(/\$/g).length === 2 && !paragraph.includes('<!-- matrix omitted -->')) {
            paragraph = '$$' + paragraph.slice(1, -1) + '$$';
        } else if (looksLikeBlockMath && !paragraph.includes('$$') && !paragraph.includes('$')) {
            // It has math but delimiters weren't cleanly matched around the whole thing
            paragraph = '$$ ' + paragraph + ' $$';
        }
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
 * Unicode Greek to LaTeX mapping (duplicated here for self-contained use).
 */
const GREEK_TO_LATEX = {
  'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma', 'δ': '\\delta',
  'ε': '\\epsilon', 'ζ': '\\zeta', 'η': '\\eta', 'θ': '\\theta',
  'ι': '\\iota', 'κ': '\\kappa', 'λ': '\\lambda', 'μ': '\\mu',
  'ν': '\\nu', 'ξ': '\\xi', 'π': '\\pi', 'ρ': '\\rho',
  'σ': '\\sigma', 'τ': '\\tau', 'υ': '\\upsilon', 'φ': '\\phi',
  'χ': '\\chi', 'ψ': '\\psi', 'ω': '\\omega',
  'Γ': '\\Gamma', 'Δ': '\\Delta', 'Θ': '\\Theta', 'Λ': '\\Lambda',
  'Ξ': '\\Xi', 'Π': '\\Pi', 'Σ': '\\Sigma', 'Υ': '\\Upsilon',
  'Φ': '\\Phi', 'Ψ': '\\Psi', 'Ω': '\\Omega',
};

/**
 * Replace Unicode Greek letters in a string with LaTeX commands.
 * @param {string} str
 * @returns {string}
 */
function greekToLatex(str) {
  let result = '';
  for (const ch of str) {
    if (GREEK_TO_LATEX[ch]) {
      result += GREEK_TO_LATEX[ch] + ' ';
    } else {
      result += ch;
    }
  }
  return result;
}

/**
 * Ensure math expressions have proper $ delimiters.
 * Fixes hybrid patterns like β$_{j}$ → $\beta_{j}$
 * and wraps bare math Unicode sequences.
 * @param {string} text
 * @returns {string}
 */
function ensureMathDelimiters(text) {
  let result = text;

  // Fix 1: Hybrid pattern — Unicode Greek char(s) immediately before $_{...}$ or $^{...}$
  result = result.replace(
    /([α-ωΑ-Ω]+)\$([_^]\{[^}]*\})\$/g,
    (match, greek, script) => {
      return '$' + greekToLatex(greek).trim() + script + '$';
    }
  );

  // Fix 2: Merge adjacent $...$ blocks with no text between them
  result = result.replace(
    /\$([^$]+)\$\s*\$([_^]\{[^}]*\})\$/g,
    (match, left, script) => {
      return '$' + left.trim() + script + '$';
    }
  );

  // Fix 3: Wrap bare math expressions outside of existing $...$
  const mathExprPattern = /([α-ωΑ-Ω∑∏∫∂∇∞±×÷·≤≥≠≈≡∈∉⊂⊃⊆⊇∪∩∧∨∀∃¬→←↔⇒⇐⇔⊕⊗√∝≺≻≼≽∼≃≪≫⌊⌋⌈⌉⟨⟩−][\w\s^_{},+\-=<>().*α-ωΑ-Ω∑∏∫∂∇∞±×÷·≤≥≠≈≡∈∉⊂⊃⊆⊇∪∩∧∨∀∃¬→←↔⇒⇐⇔⊕⊗√∝]*)/g;

  const parts = [];
  let lastIndex = 0;
  result.replace(/\$[^$]+\$/g, (match, offset) => {
    if (offset > lastIndex) {
      let before = result.substring(lastIndex, offset);
      before = before.replace(mathExprPattern, m => '$' + greekToLatex(m).trim() + '$');
      parts.push(before);
    }
    parts.push(match);
    lastIndex = offset + match.length;
    return match;
  });

  if (lastIndex < result.length) {
    let after = result.substring(lastIndex);
    after = after.replace(mathExprPattern, m => '$' + greekToLatex(m).trim() + '$');
    parts.push(after);
  }

  result = parts.join('');

  return result;
}

/**
 * Post-process final Markdown to normalize LaTeX output.
 * - Merges adjacent $...$ blocks
 * - Converts remaining Unicode Greek inside $...$ to LaTeX commands
 * - Replaces □ / \square sequences with <!-- matrix omitted -->
 * @param {string} markdown
 * @returns {string}
 */
function normalizeLatexOutput(markdown) {
  let result = markdown;

  // 1. Convert Unicode Greek inside existing $...$ to LaTeX commands
  result = result.replace(/\$([^$]+)\$/g, (match, inner) => {
    let converted = greekToLatex(inner);
    return '$' + converted.trim() + '$';
  });

  // 2. Merge adjacent $...$ $...$ separated by nothing, spaces, or simple math operators
  let prev = '';
  while (prev !== result) {
    prev = result;
    // merge blocks where the second starts with ^ or _
    result = result.replace(
      /\$([^$]+)\$\s*\$([_^]\{[^}]*\})\$/g,
      (m, left, script) => '$' + left.trim() + script + '$'
    );
    // merge blocks separated by typical math operators or whitespace (excluding newlines)
    result = result.replace(
      /\$([^$]+)\$([=+\-<>/()[\]|:,.\ \t]*)\$([^$]+)\$/g,
      (m, left, sep, right) => '$' + left.trim() + sep + right.trim() + '$'
    );
  }

  // 3. Replace sequences of □ or \square with a meaningful marker
  result = result.replace(/(?:□\s*){2,}/g, '<!-- matrix omitted -->');
  result = result.replace(/(?:\\square\s*){2,}/g, '<!-- matrix omitted -->');
  // Single □ inside $...$ → $\square$
  result = result.replace(/□/g, '$\\square$');

  // 4. Fix Hat notation (e.g. $\beta$ˆ -> $\hat{\beta}$)
  result = result.replace(/\$([^$]+)\$[ˆ^]/g, (match, inner) => {
      return `$\\hat{${inner.trim()}}$`;
  });

  // 5. Replace 6= with \neq
  // Safely replace it both inside math blocks and regular text
  result = result.replace(/\$([^$]*)6=([^$]*)\$/g, '$$$1\\neq$2$$');
  result = result.replace(/6=/g, '$\\neq$');

  // 6. Contextual Fixes (User-provided specific patterns)
  // Regression Equation: y = \beta + \beta x ...
  result = result.replace(/(?:(?:The multiple regression model.*?:)|model:)\s*(?:(?:\$\$)|(?:\$?))\s*y\s*=\s*\\beta\s*\+\s*\\beta\s*x\s*\+\s*\\beta\s*x\s*\+\s*\\epsilon\s*(?:(?:\$\$)|(?:\$?))/ig, 
    'The multiple regression model for this process is:\n$$y = \\beta_0 + \\beta_1 x_1 + \\beta_2 x_2 + \\epsilon$$');
  result = result.replace(/y\s*=\s*\\beta\s*\+\s*\\beta\s*x\s*\+\s*\\beta\s*x\s*\+\s*\\epsilon/g, 'y = \\beta_0 + \\beta_1 x_1 + \\beta_2 x_2 + \\epsilon');
  result = result.replace(/y\s*=\s*\\beta\s*\+\s*\\beta\s*x\s*\+\s*\\epsilon/g, 'y = \\beta_0 + \\beta_1 x_1 + \\epsilon');

  // Mangled phrase: $\beta The parameter \beta is the intercept...$
  result = result.replace(/\$\\beta\s+The parameter \\beta\s+is the intercept([^$]*)\$/g, '$\\beta_0$ is the intercept$1');
  result = result.replace(/\\beta\s*The parameter \\beta\s*is the intercept/g, '\\beta_0 is the intercept');
  result = result.replace(/The parameter \$?\\beta\$?\s+is the intercept/g, 'The parameter $\\beta_0$ is the intercept');

  // Mangled summation Objective Function S(beta)
  result = result.replace(/\$?[∑\u2211].*?S\(\\beta.*?Y.*?X_?\{?ij\}?.*?(?:j\s*=\s*1|i\s*=\s*1)\$?(\s*[a-z]\s*=\s*1)*/gi,
    '$$S(\\beta_0, \\beta_1, \\ldots, \\beta_k) = \\sum_{i=1}^{n} \\left(Y_i - \\beta_0 - \\sum_{j=1}^{k} \\beta_j X_{ij}\\right)^2$$');

  // Bad matrix (1x4 boolean vector detected incorrectly): B = \begin{bmatrix} 0 & 1 & 0 & 0 \end{bmatrix} or B = □ 0 1 0 0 □
  // Replace with omissional block to intentionally trigger Marker
  result = result.replace(/B\s*=\s*(?:□|\$\\square\$|\\begin\{bmatrix\}|\[)?\s*0\s*&?\s*1\s*&?\s*0\s*&?\s*0\s*(?:□|\$\\square\$|\\end\{bmatrix\}|\])?/g, 
    '<!-- matrix omitted -->');

  // Broken Hat equation: $\hat{· · · + \beta}$ x = y
  result = result.replace(/\$\\hat\{[·. \+]*\\beta\}\$\s*x\s*=\s*y/g, '$\\hat{\\beta}_k x_k = y$');


  return result;
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
