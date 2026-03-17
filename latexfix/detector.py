"""
detector.py — Detect broken matrices in Markdown text extracted from PDF.

Supports three patterns:
  Pattern 1: □-bracket matrices (U+25A1 / box-drawing chars)
  Pattern 2: Markdown table matrices with □ noise
  Pattern 3: Inline broken numbers (e.g. "12 . 03" or "- . 00444")
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


# ─── Known matrix / vector names ────────────────────────────────

KNOWN_NAMES = {
    "x'x": "X'X", "x′x": "X'X", "xtx": "X'X",
    "x'y": "X'y", "x′y": "X'y", "xty": "X'y",
    "beta": r"\hat{\beta}", "β": r"\hat{\beta}",
    "b̂": r"\hat{\beta}", "β̂": r"\hat{\beta}",
    "inv": "(X'X)^{-1}",
    "a": "A", "b": "B", "c": "C",
}

# Unicode box / bracket characters used as matrix delimiters
_BOX_CHARS = (
    "\u25A1"                          # □
    "\uF8EE\uF8EF\uF8F0"             # left bracket pieces
    "\uF8F1\uF8F2\uF8F3"             # right bracket pieces
    "\uF8F4\uF8F5\uF8F6"             # more bracket pieces
    "\uF8F7\uF8F8\uF8F9"             # more bracket pieces
    "\uF8FA\uF8FB"                    # remaining
)

_BOX_RE = re.compile(f"[{re.escape(_BOX_CHARS)}]")


# ─── DetectedMatrix dataclass ───────────────────────────────────

@dataclass
class DetectedMatrix:
    """A matrix (or vector) detected in the source text."""
    name: str = ""                          # e.g. "X'X", "X'y"
    raw_text: str = ""                      # original text slice
    start: int = 0                          # char offset in source
    end: int = 0                            # char offset end
    array: Optional[np.ndarray] = None      # parsed numpy array
    shape: tuple = ()                       # (rows, cols)
    pattern_type: str = ""                  # "box", "table", "inline"
    computed: bool = False                  # has a computation been done?
    result_array: Optional[np.ndarray] = field(default=None, repr=False)


# ─── Name inference ─────────────────────────────────────────────

def _infer_name(text: str, start: int, end: int) -> str:
    """
    Try to find a known matrix name near the detected block.
    Looks in a 60-char window *before* and a 40-char window *after*.
    """
    window_before = text[max(0, start - 60):start].lower()
    window_after = text[end:end + 40].lower()

    for alias, canonical in KNOWN_NAMES.items():
        if alias in window_before:
            return canonical
        if alias in window_after:
            return canonical

    # Try to grab something like "A =" or "Matrix B" just before
    m = re.search(r'([A-Z][A-Za-z\'′]*)\s*=?\s*$', text[max(0, start - 30):start])
    if m:
        return m.group(1)

    return ""


# ─── Pattern detectors ──────────────────────────────────────────

def _detect_box_matrices(text: str) -> List[DetectedMatrix]:
    """
    Pattern 1: rows delimited by □ or box-drawing characters.

    Example:
        □ 25   219    10232  □
        □ 219  3055   133899 □
        □ 10232 133899 6725688 □
    """
    from .matrix_extractor import extract_box_matrix

    results = []

    # Match blocks of consecutive lines that contain box chars
    # A "box line" = line that starts or ends with a box char (after strip)
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if _BOX_RE.search(line):
            # Start of a potential box-matrix block
            block_lines = []
            block_start = text.index(line, sum(len(l) + 1 for l in lines[:i]))
            while i < len(lines) and (_BOX_RE.search(lines[i]) or
                                       re.search(r'[\d.]+', lines[i])):
                block_lines.append(lines[i])
                i += 1
            raw = '\n'.join(block_lines)
            block_end = block_start + len(raw)

            arr = extract_box_matrix(raw)
            if arr is not None and arr.size > 0:
                name = _infer_name(text, block_start, block_end)
                results.append(DetectedMatrix(
                    name=name,
                    raw_text=raw,
                    start=block_start,
                    end=block_end,
                    array=arr,
                    shape=arr.shape,
                    pattern_type="box",
                ))
        else:
            i += 1

    return results


def _detect_table_matrices(text: str) -> List[DetectedMatrix]:
    """
    Pattern 2: matrices embedded in Markdown tables with □ noise.

    Example:
        |  | 25 | 219 | 10232 |  |
        |  | = □ 219 | 3055 | 133899 □ |  |
        |  | 10232 | 133899 | 6725688 |  |
    """
    from .matrix_extractor import extract_table_matrix

    results = []

    # Find runs of Markdown table rows that contain numbers
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('|') and re.search(r'\d', line):
            block_lines = []
            # compute character offset
            block_start = sum(len(lines[j]) + 1 for j in range(i))
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith('|') and re.search(r'\d', stripped):
                    block_lines.append(lines[i])
                    i += 1
                elif stripped.startswith('|') and re.match(r'^\|[\s|:_-]*\|$', stripped):
                    # separator row — skip it
                    block_lines.append(lines[i])
                    i += 1
                else:
                    break

            if len(block_lines) >= 2:
                raw = '\n'.join(block_lines)
                block_end = block_start + len(raw)
                arr = extract_table_matrix(raw)
                if arr is not None and arr.size > 0:
                    name = _infer_name(text, block_start, block_end)
                    results.append(DetectedMatrix(
                        name=name,
                        raw_text=raw,
                        start=block_start,
                        end=block_end,
                        array=arr,
                        shape=arr.shape,
                        pattern_type="table",
                    ))
        else:
            i += 1

    return results


def _fix_broken_numbers(text: str) -> str:
    """
    Pattern 3: fix inline broken decimals throughout the text.
      "12 . 03"    → "12.03"
      "- . 00444"  → "-0.00444"
      "-  .  5"    → "-0.5"
    """
    result = re.sub(r'-\s*\.\s*(\d)', r'-0.\1', text)
    result = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', result)
    return result


# ─── Public API ─────────────────────────────────────────────────

def detect_matrices(text: str) -> List[DetectedMatrix]:
    """
    Detect all broken matrices in *text* and return them as
    ``DetectedMatrix`` objects with parsed numpy arrays.

    The text is first cleaned (Pattern 3 — broken numbers), then
    scanned for Pattern 1 (box brackets) and Pattern 2 (tables).
    """
    cleaned = _fix_broken_numbers(text)

    matrices: List[DetectedMatrix] = []
    matrices.extend(_detect_box_matrices(cleaned))
    matrices.extend(_detect_table_matrices(cleaned))

    # De-duplicate overlapping detections (prefer earlier/larger)
    matrices.sort(key=lambda m: (m.start, -(m.end - m.start)))
    deduped: List[DetectedMatrix] = []
    last_end = -1
    for m in matrices:
        if m.start >= last_end:
            deduped.append(m)
            last_end = m.end

    return deduped
