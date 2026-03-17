/**
 * math-utils.js — Math Symbol Detection, Glyph Remapping & LaTeX Formatting
 * Handles: math font detection, glyph-to-Unicode mapping, superscript/subscript
 * detection, and inline LaTeX wrapping for mathematical expressions.
 */

// ─── Math Font Detection ────────────────────────────────────────

/**
 * Known math font family patterns.
 * Matches common TeX, OpenType math, and legacy PostScript math fonts.
 */
const MATH_FONT_PATTERNS = [
  // Computer Modern TeX fonts
  /^CMM[IR]/i,        // CMMI (Math Italic), CMMR
  /^CMSY/i,           // CM Symbols
  /^CMEX/i,           // CM Extended (large operators)
  /^CMR\d/i,          // CM Roman (used in math mode)
  /^CMBX/i,           // CM Bold Extended
  /^CMTI/i,           // CM Text Italic (sometimes math)
  // AMS fonts
  /^MSAM/i,           // AMS Symbol A
  /^MSBM/i,           // AMS Symbol B
  /^EUFM/i,           // Euler Fraktur
  /^EURM/i,           // Euler Roman
  // Symbol fonts
  /^Symbol$/i,
  /^Symbol-/i,
  /^MathematicalPi/i,
  /^MT\s?Extra/i,
  // Latin Modern Math
  /^LMMath/i,
  /^LM-Math/i,
  // STIX
  /^STIX/i,
  // Cambria Math
  /^CambriaMath/i,
  /^Cambria.*Math/i,
  // General math indicators in font names
  /Math/i,
  /Symbol/i,
  /^Glyph/i,
];

/**
 * Check if a font name corresponds to a math font.
 * @param {string} fontName — PDF font name (e.g. "CMMI10", "Symbol", "g_d0_f1")
 * @returns {boolean}
 */
function isMathFont(fontName) {
  if (!fontName) return false;
  // Strip subset prefix (e.g. "ABCDEF+CMMI10" → "CMMI10")
  const clean = fontName.replace(/^[A-Z]{6}\+/, '');
  return MATH_FONT_PATTERNS.some(pattern => pattern.test(clean));
}

/**
 * Get the specific math font family for targeted remapping.
 * @param {string} fontName
 * @returns {string|null} — family key or null
 */
function getMathFontFamily(fontName) {
  if (!fontName) return null;
  const clean = fontName.replace(/^[A-Z]{6}\+/, '');
  if (/^CMMI/i.test(clean)) return 'CMMI';
  if (/^CMSY/i.test(clean)) return 'CMSY';
  if (/^CMEX/i.test(clean)) return 'CMEX';
  if (/^CMR\d/i.test(clean)) return 'CMR';
  if (/^CMBX/i.test(clean)) return 'CMBX';
  if (/^MSAM/i.test(clean)) return 'MSAM';
  if (/^MSBM/i.test(clean)) return 'MSBM';
  if (/^Symbol/i.test(clean)) return 'Symbol';
  if (/^MT\s?Extra/i.test(clean)) return 'MTExtra';
  if (/Math/i.test(clean)) return 'GenericMath';
  return null;
}

// ─── Glyph-to-Unicode Mapping Tables ────────────────────────────

/**
 * CMMI (Computer Modern Math Italic)
 * Maps character codes to proper Unicode characters.
 * In CMMI, Latin letters at certain positions represent Greek letters.
 */
const CMMI_MAP = {
  // Greek uppercase (positions 0-10 in CMMI encoding)
  0: 'Γ', 1: 'Δ', 2: 'Θ', 3: 'Λ', 4: 'Ξ', 5: 'Π',
  6: 'Σ', 7: 'Υ', 8: 'Φ', 9: 'Ψ', 10: 'Ω',
  // Greek lowercase (positions 11-31)
  11: 'α', 12: 'β', 13: 'γ', 14: 'δ', 15: 'ε',
  16: 'ζ', 17: 'η', 18: 'θ', 19: 'ι', 20: 'κ',
  21: 'λ', 22: 'μ', 23: 'ν', 24: 'ξ', 25: 'π',
  26: 'ρ', 27: 'σ', 28: 'τ', 29: 'υ', 30: 'φ',
  31: 'χ', 32: 'ψ', 33: 'ω',  // extended
  // Variants
  34: 'ε',  // varepsilon
  35: 'ϑ',  // vartheta
  36: 'ϖ',  // varpi
  37: 'ϱ',  // varrho
  38: 'ς',  // varsigma
  39: 'ϕ',  // varphi
  // Punctuation for math
  58: '.', 59: ',', 60: '<', 61: '/', 62: '>', 63: '⋆',
  // Math italic letters (standard ASCII positions in CMMI)
  // These typically display as italic - we leave them as letters
};

/**
 * CMSY (Computer Modern Symbols)
 * Maps char codes to math operator Unicode symbols.
 */
const CMSY_MAP = {
  0: '−',   // minus
  1: '·',   // cdot
  2: '×',   // times
  3: '∗',   // asterisk operator
  4: '÷',   // divide
  5: '◇',   // diamond
  6: '±',   // plusminus
  7: '∓',   // minusplus
  8: '⊕',   // oplus
  9: '⊖',   // ominus
  10: '⊗',  // otimes
  11: '⊘',  // oslash
  12: '⊙',  // odot
  13: '○',  // bigcirc
  14: '∘',  // circ
  15: '•',  // bullet
  16: '≍',  // asymp
  17: '≡',  // equiv
  18: '⊆',  // subseteq
  19: '⊇',  // supseteq
  20: '≤',  // leq
  21: '≥',  // geq
  22: '≼',  // preceq
  23: '≽',  // succeq
  24: '∼',  // sim
  25: '≈',  // approx
  26: '⊂',  // subset
  27: '⊃',  // supset
  28: '≪',  // ll
  29: '≫',  // gg
  30: '≺',  // prec
  31: '≻',  // succ
  32: '←',  // leftarrow
  33: '→',  // rightarrow
  34: '↑',  // uparrow
  35: '↓',  // downarrow
  36: '↔',  // leftrightarrow
  37: '↗',  // nearrow
  38: '↘',  // searrow
  39: '≃',  // simeq
  40: '⇐',  // Leftarrow
  41: '⇒',  // Rightarrow
  42: '⇑',  // Uparrow
  43: '⇓',  // Downarrow
  44: '⇔',  // Leftrightarrow
  45: '↖',  // nwarrow
  46: '↙',  // swarrow
  47: '∝',  // propto
  48: '′',  // prime
  49: '∞',  // infty
  50: '∈',  // in
  51: '∋',  // ni
  52: '△',  // triangle
  53: '▽',  // triangledown
  54: '/',  // slash (not)
  // 55: reserved
  56: '∀',  // forall
  57: '∃',  // exists
  58: '¬',  // neg
  59: '∅',  // emptyset
  60: 'ℜ',  // Re
  61: 'ℑ',  // Im
  62: '⊤',  // top
  63: '⊥',  // bot / perp
  64: 'ℵ',  // aleph
  // Set operations and logic
  91: '∪',  // cup
  92: '∩',  // cap
  93: '⊎',  // uplus
  94: '∧',  // wedge / land
  95: '∨',  // vee / lor
  96: '⊢',  // vdash
  97: '⊣',  // dashv
  98: '⌊',  // lfloor
  99: '⌋',  // rfloor
  100: '⌈', // lceil
  101: '⌉', // rceil
  102: '{', // lbrace
  103: '}', // rbrace
  104: '⟨', // langle
  105: '⟩', // rangle
  106: '|', // vert
  107: '‖', // Vert
  110: '∖', // setminus
  111: '≀', // wr
  112: '√', // surd (square root)
  113: '∐', // coprod
  114: '∇', // nabla
  115: '∫', // int
  116: '⊔', // sqcup
  117: '⊓', // sqcap
  118: '⊑', // sqsubseteq
  119: '⊒', // sqsupseteq
  120: '§', // section
  121: '†', // dagger
  122: '‡', // ddagger
  123: '¶', // paragraph
  124: '♣', // clubsuit
  125: '♢', // diamondsuit
  126: '♡', // heartsuit
  127: '♠', // spadesuit
};

/**
 * CMEX (Computer Modern Extended) — large operators and delimiters
 */
const CMEX_MAP = {
  80: '∑',   // sum
  81: '∏',   // prod
  82: '∫',   // int
  83: '⋃',   // bigcup
  84: '⋂',   // bigcap
  85: '⊎',   // biguplus
  86: '⊗',   // bigotimes
  87: '⊕',   // bigoplus
  88: '⊙',   // bigodot
  89: '∮',   // oint
  90: '⊔',   // bigsqcup
  // Delimiters
  0: '(',    18: '(',
  1: ')',    19: ')',
  2: '[',    20: '[',
  3: ']',    21: ']',
  4: '⌊',   22: '⌊',
  5: '⌋',   23: '⌋',
  6: '⌈',   24: '⌈',
  7: '⌉',   25: '⌉',
  8: '{',    26: '{',
  9: '}',    27: '}',
  10: '⟨',   28: '⟨',
  11: '⟩',   29: '⟩',
  12: '|',   30: '|',
  14: '/',   32: '/',
  15: '\\',  33: '\\',
};

/**
 * Symbol font mapping
 */
const SYMBOL_MAP = {
  34: '∀',   // forall
  36: '∃',   // exists
  39: '∍',   // suchthat
  42: '∗',   // asterisk
  45: '−',   // minus
  64: '≅',   // congruent
  65: 'Α', 66: 'Β', 67: 'Χ', 68: 'Δ', 69: 'Ε',
  70: 'Φ', 71: 'Γ', 72: 'Η', 73: 'Ι', 74: 'ϑ',
  75: 'Κ', 76: 'Λ', 77: 'Μ', 78: 'Ν', 79: 'Ο',
  80: 'Π', 81: 'Θ', 82: 'Ρ', 83: 'Σ', 84: 'Τ',
  85: 'Υ', 86: 'ς', 87: 'Ω', 88: 'Ξ', 89: 'Ψ', 90: 'Ζ',
  97: 'α', 98: 'β', 99: 'χ', 100: 'δ', 101: 'ε',
  102: 'φ', 103: 'γ', 104: 'η', 105: 'ι', 106: 'ϕ',
  107: 'κ', 108: 'λ', 109: 'μ', 110: 'ν', 111: 'ο',
  112: 'π', 113: 'θ', 114: 'ρ', 115: 'σ', 116: 'τ',
  117: 'υ', 118: 'ϖ', 119: 'ω', 120: 'ξ', 121: 'ψ', 122: 'ζ',
  163: '≤', 165: '∞', 166: 'ƒ',
  171: '↔', 172: '←', 173: '↑', 174: '→', 175: '↓',
  176: '°', 177: '±', 178: '″', 179: '≥', 180: '×',
  181: '∝', 182: '∂', 183: '•', 184: '÷',
  185: '≠', 186: '≡', 187: '≈',
  196: '⊗', 197: '⊕',
  199: '∩', 200: '∪',
  201: '⊃', 202: '⊇', 203: '⊄', 204: '⊂', 205: '⊆',
  206: '∈', 207: '∉',
  208: '∠', 209: '∇',
  213: '∏', 214: '√',
  217: '∧', 218: '∨',
  220: '∴',
  225: '⟨', 241: '⟩',
  229: '∑',
  242: '∫',
};

/**
 * Common character substitutions for garbled output.
 * Maps frequently seen garbled sequences to proper characters.
 */
const COMMON_SUBSTITUTIONS = {
  // Hyphen/dash confusion
  '\u00AD': '-',     // soft hyphen → hyphen
  '\u2010': '-',     // hyphen
  '\u2011': '-',     // non-breaking hyphen
  '\u2012': '–',     // figure dash
  '\u2013': '–',     // en dash
  '\u2014': '—',     // em dash
  // Quotes
  '\u2018': "'",     // left single quote
  '\u2019': "'",     // right single quote
  '\u201C': '"',     // left double quote
  '\u201D': '"',     // right double quote
  // Spaces
  '\u00A0': ' ',     // non-breaking space
  '\u2002': ' ',     // en space
  '\u2003': ' ',     // em space
  '\u2009': ' ',     // thin space
  '\u200A': ' ',     // hair space
  '\u200B': '',      // zero-width space
  '\u200C': '',      // zero-width non-joiner
  '\u200D': '',      // zero-width joiner
  '\uFEFF': '',      // BOM
  // Common math that gets garbled
  '\u2212': '−',     // minus sign
  '\u00D7': '×',     // multiplication
  '\u00F7': '÷',     // division
  '\u2264': '≤',     // less than or equal
  '\u2265': '≥',     // greater than or equal
  '\u2260': '≠',     // not equal
  '\u221E': '∞',     // infinity
  '\u2202': '∂',     // partial differential
  '\u222B': '∫',     // integral
  '\u2211': '∑',     // summation
  '\u220F': '∏',     // product
  '\u221A': '√',     // square root
};

/**
 * Unicode to LaTeX command mapping for common math symbols.
 * Used when generating LaTeX-wrapped output.
 */
const UNICODE_TO_LATEX = {
  'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma', 'δ': '\\delta',
  'ε': '\\epsilon', 'ζ': '\\zeta', 'η': '\\eta', 'θ': '\\theta',
  'ι': '\\iota', 'κ': '\\kappa', 'λ': '\\lambda', 'μ': '\\mu',
  'ν': '\\nu', 'ξ': '\\xi', 'π': '\\pi', 'ρ': '\\rho',
  'σ': '\\sigma', 'τ': '\\tau', 'υ': '\\upsilon', 'φ': '\\phi',
  'χ': '\\chi', 'ψ': '\\psi', 'ω': '\\omega',
  'Γ': '\\Gamma', 'Δ': '\\Delta', 'Θ': '\\Theta', 'Λ': '\\Lambda',
  'Ξ': '\\Xi', 'Π': '\\Pi', 'Σ': '\\Sigma', 'Υ': '\\Upsilon',
  'Φ': '\\Phi', 'Ψ': '\\Psi', 'Ω': '\\Omega',
  '∞': '\\infty', '∂': '\\partial', '∇': '\\nabla',
  '∈': '\\in', '∉': '\\notin', '∋': '\\ni',
  '⊂': '\\subset', '⊃': '\\supset', '⊆': '\\subseteq', '⊇': '\\supseteq',
  '∪': '\\cup', '∩': '\\cap',
  '∧': '\\wedge', '∨': '\\vee',
  '∀': '\\forall', '∃': '\\exists',
  '¬': '\\neg', '⊥': '\\perp', '⊤': '\\top',
  '∅': '\\emptyset',
  '←': '\\leftarrow', '→': '\\rightarrow', '↑': '\\uparrow', '↓': '\\downarrow',
  '↔': '\\leftrightarrow',
  '⇐': '\\Leftarrow', '⇒': '\\Rightarrow', '⇔': '\\Leftrightarrow',
  '∑': '\\sum', '∏': '\\prod', '∫': '\\int', '∮': '\\oint',
  '√': '\\sqrt', '±': '\\pm', '∓': '\\mp',
  '×': '\\times', '÷': '\\div', '·': '\\cdot', '∘': '\\circ',
  '⊕': '\\oplus', '⊗': '\\otimes',
  '≤': '\\leq', '≥': '\\geq', '≠': '\\neq',
  '≈': '\\approx', '≡': '\\equiv', '∼': '\\sim', '≃': '\\simeq',
  '≪': '\\ll', '≫': '\\gg',
  '≺': '\\prec', '≻': '\\succ', '≼': '\\preceq', '≽': '\\succeq',
  '∝': '\\propto',
  '⌊': '\\lfloor', '⌋': '\\rfloor', '⌈': '\\lceil', '⌉': '\\rceil',
  '⟨': '\\langle', '⟩': '\\rangle',
  '†': '\\dagger', '‡': '\\ddagger',
  'ℵ': '\\aleph', 'ℜ': '\\Re', 'ℑ': '\\Im',
  '′': "'",
};

// ─── Glyph Remapping ────────────────────────────────────────────

/**
 * Get the appropriate mapping table for a font family.
 * @param {string} family — from getMathFontFamily()
 * @returns {Object|null}
 */
function getMappingTable(family) {
  switch (family) {
    case 'CMMI': return CMMI_MAP;
    case 'CMSY': return CMSY_MAP;
    case 'CMEX': return CMEX_MAP;
    case 'Symbol': return SYMBOL_MAP;
    default: return null;
  }
}

/**
 * Remap a single text item's characters using its font's mapping table.
 * @param {string} text — original extracted text
 * @param {string} fontName — PDF font name
 * @returns {{text: string, wasMapped: boolean}}
 */
function remapMathGlyphs(text, fontName) {
  if (!text || !fontName) return { text: text || '', wasMapped: false };

  const family = getMathFontFamily(fontName);
  const table = family ? getMappingTable(family) : null;

  let result = '';
  let wasMapped = false;

  for (let i = 0; i < text.length; i++) {
    const charCode = text.charCodeAt(i);
    const char = text[i];

    // 1. Try font-specific mapping
    if (table && table[charCode] !== undefined) {
      result += table[charCode];
      wasMapped = true;
      continue;
    }

    // 2. Try common substitutions
    if (COMMON_SUBSTITUTIONS[char] !== undefined) {
      result += COMMON_SUBSTITUTIONS[char];
      wasMapped = true;
      continue;
    }

    // 3. Check for Private Use Area characters (often garbled math)
    if (charCode >= 0xE000 && charCode <= 0xF8FF) {
      // PUA character — likely a custom glyph that wasn't mapped
      // Try to use the font family hint
      if (family === 'CMMI' && charCode >= 0xE000 && charCode <= 0xE021) {
        const offset = charCode - 0xE000;
        if (CMMI_MAP[offset] !== undefined) {
          result += CMMI_MAP[offset];
          wasMapped = true;
          continue;
        }
      }
      if (family === 'CMSY' && charCode >= 0xE000 && charCode <= 0xE07F) {
        const offset = charCode - 0xE000;
        if (CMSY_MAP[offset] !== undefined) {
          result += CMSY_MAP[offset];
          wasMapped = true;
          continue;
        }
      }
      // Replace unknown PUA with placeholder
      result += '□';
      wasMapped = true;
      continue;
    }

    // 4. Check for control characters that shouldn't be in output
    if (charCode < 32 && charCode !== 10 && charCode !== 13 && charCode !== 9) {
      // Control character — try font-specific mapping by char code
      if (table && table[charCode] !== undefined) {
        result += table[charCode];
        wasMapped = true;
      }
      // else skip it
      continue;
    }

    // 5. Keep the character as-is
    result += char;
  }

  return { text: result, wasMapped };
}

// ─── Post-Processing ────────────────────────────────────────────

/**
 * Normalize and clean up extracted text after remapping.
 * @param {string} text
 * @returns {string}
 */
function normalizeText(text) {
  if (!text) return '';

  let result = text;

  // Normalize Unicode (NFC form)
  if (typeof result.normalize === 'function') {
    result = result.normalize('NFC');
  }

  // Fix double spacing
  result = result.replace(/  +/g, ' ');

  // Fix common ligature issues
  result = result.replace(/\uFB01/g, 'fi');  // fi ligature
  result = result.replace(/\uFB02/g, 'fl');  // fl ligature
  result = result.replace(/\uFB00/g, 'ff');  // ff ligature
  result = result.replace(/\uFB03/g, 'ffi'); // ffi ligature
  result = result.replace(/\uFB04/g, 'ffl'); // ffl ligature

  return result.trim();
}

// ─── Superscript / Subscript Detection ──────────────────────────

/**
 * Configuration for super/subscript detection.
 */
const SCRIPT_CONFIG = {
  SIZE_RATIO: 0.82,        // Item fontSize < baseline * ratio → is a script
  SUPER_Y_THRESHOLD: -1,   // Y offset above baseline to count as superscript
  SUB_Y_THRESHOLD: 2,      // Y offset below baseline to count as subscript
  MAX_X_GAP: 3,            // Max horizontal gap to attach script to base
};

/**
 * Detect superscripts and subscripts within a line of items.
 * Uses font size and vertical position relative to the baseline.
 * @param {Array} items — text items in a line (sorted by x)
 * @returns {Array} — items with isSuperscript/isSubscript flags added
 */
function detectScripts(items) {
  if (!items || items.length < 2) return items;

  // Find the dominant (most common) font size in this line as the baseline size
  const sizeFreq = {};
  items.forEach(it => {
    const s = Math.round(it.fontSize * 10) / 10;
    sizeFreq[s] = (sizeFreq[s] || 0) + 1;
  });
  const baselineSize = parseFloat(
    Object.entries(sizeFreq).sort((a, b) => b[1] - a[1])[0][0]
  );

  // Find the dominant Y position as the baseline Y
  const yFreq = {};
  items.forEach(it => {
    const y = Math.round(it.y);
    yFreq[y] = (yFreq[y] || 0) + 1;
  });
  const baselineY = parseFloat(
    Object.entries(yFreq).sort((a, b) => b[1] - a[1])[0][0]
  );

  return items.map(item => {
    const sizeRatio = item.fontSize / baselineSize;
    const yDiff = item.y - baselineY; // positive = below baseline (remember Y is top-down)

    // Skip items at the baseline size — they're not scripts
    if (sizeRatio >= SCRIPT_CONFIG.SIZE_RATIO) {
      return { ...item, isSuperscript: false, isSubscript: false };
    }

    // Smaller font size — check position
    if (yDiff < SCRIPT_CONFIG.SUPER_Y_THRESHOLD) {
      return { ...item, isSuperscript: true, isSubscript: false };
    } else if (yDiff > SCRIPT_CONFIG.SUB_Y_THRESHOLD) {
      return { ...item, isSuperscript: false, isSubscript: true };
    }

    // Default: treat as superscript if above middle, subscript if below
    return {
      ...item,
      isSuperscript: yDiff <= 0,
      isSubscript: yDiff > 0
    };
  });
}

// ─── Line Math Formatting ───────────────────────────────────────

/**
 * Format a line's items into text with LaTeX math notation.
 * Wraps math-font spans in $...$ and converts super/subscripts.
 * @param {Array} items — items with isMathFont, isSuperscript, isSubscript flags
 * @returns {string} — formatted text
 */
function formatMathLine(items) {
  if (!items || items.length === 0) return '';

  let result = '';
  let inMath = false;
  let mathBuffer = '';
  let prevItem = null;

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const text = item.text;
    const isMath = item.isMathFont || item.isSuperscript || item.isSubscript;

    if (isMath && !inMath) {
      // Entering math mode
      inMath = true;
      mathBuffer = '';
    }

    if (isMath) {
      // Build math content
      if (item.isSuperscript) {
        mathBuffer += '^{' + text + '}';
      } else if (item.isSubscript) {
        mathBuffer += '_{' + text + '}';
      } else {
        // Convert Unicode math symbols to LaTeX commands
        let latexText = '';
        for (const ch of text) {
          if (UNICODE_TO_LATEX[ch]) {
            latexText += UNICODE_TO_LATEX[ch] + ' ';
          } else {
            latexText += ch;
          }
        }
        mathBuffer += latexText;
      }
    }

    if (!isMath && inMath) {
      // Exiting math mode — flush the buffer
      result += '$' + mathBuffer.trim() + '$ ';
      mathBuffer = '';
      inMath = false;
    }

    if (!isMath) {
      // Regular text
      if (prevItem) {
        // Add space between items if there's a gap
        const gap = item.x - (prevItem.x + (prevItem.width || 0));
        if (gap > prevItem.fontSize * 0.25) {
          result += ' ';
        }
      }
      result += text;
    }

    prevItem = item;
  }

  // Close any remaining math span
  if (inMath && mathBuffer) {
    result += '$' + mathBuffer.trim() + '$';
  }

  return result.trim();
}

/**
 * Check if a string contains math-significant Unicode characters.
 * @param {string} text
 * @returns {boolean}
 */
function containsMathSymbols(text) {
  if (!text) return false;
  // Greek letters, math operators, arrows, etc.
  return /[α-ωΑ-Ω∑∏∫∂∇∞±×÷·≤≥≠≈≡∈∉⊂⊃⊆⊇∪∩∧∨∀∃¬→←↔⇒⇐⇔⊕⊗√∝≺≻≼≽∼≃≪≫⌊⌋⌈⌉⟨⟩]/.test(text);
}

// ─── Diagnostics ────────────────────────────────────────────────

let _mathDiagnostics = {
  totalItems: 0,
  mathFontItems: 0,
  remappedGlyphs: 0,
  superscripts: 0,
  subscripts: 0,
};

function resetMathDiagnostics() {
  _mathDiagnostics = {
    totalItems: 0,
    mathFontItems: 0,
    remappedGlyphs: 0,
    superscripts: 0,
    subscripts: 0,
  };
}

function logMathDiagnostics() {
  console.log('[Math-Utils] Diagnostics:', {
    totalItems: _mathDiagnostics.totalItems,
    mathFontItems: _mathDiagnostics.mathFontItems,
    remappedGlyphs: _mathDiagnostics.remappedGlyphs,
    superscripts: _mathDiagnostics.superscripts,
    subscripts: _mathDiagnostics.subscripts,
  });
}
