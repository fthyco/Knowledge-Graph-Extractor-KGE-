"""
renderer.py — Render DetectedMatrix objects to LaTeX and
patch the original Markdown document.
"""

import math
import re
from typing import List, Optional

import numpy as np

from .detector import DetectedMatrix
from .matrix_extractor import matrix_to_latex, compute_and_render


# ─── Shape inference ────────────────────────────────────────────

_COLUMN_HINTS = re.compile(r'(?:y|b|beta|rhs|β)', re.IGNORECASE)
_SQUARE_HINTS = re.compile(r"(?:x'x|xtx|inv)", re.IGNORECASE)


def _best_shape(arr: np.ndarray, name: str = '') -> np.ndarray:
    """
    Reshape a flat or ambiguously-shaped array based on name hints.

    * Names containing ``y``, ``b``, ``beta``, ``rhs`` → column vector.
    * Names containing ``x'x``, ``xtx``, ``inv`` → square matrix
      (if element count is a perfect square).
    * Otherwise, leave unchanged.
    """
    if arr.ndim >= 2:
        return arr

    n = arr.size

    if _COLUMN_HINTS.search(name):
        return arr.reshape(-1, 1)

    if _SQUARE_HINTS.search(name):
        side = int(math.isqrt(n))
        if side * side == n:
            return arr.reshape(side, side)

    return arr


# ─── Single / batch rendering ──────────────────────────────────

def render(dm: DetectedMatrix, decimals: int = 5) -> str:
    """Render one ``DetectedMatrix`` to a LaTeX string."""
    if dm.array is None:
        return f"% empty matrix: {dm.name}"
    shaped = _best_shape(dm.array, dm.name)
    return matrix_to_latex(shaped, name=dm.name, decimals=decimals)


def render_all(matrices: List[DetectedMatrix], decimals: int = 5) -> str:
    """Render every detected matrix, separated by blank lines."""
    parts = [render(m, decimals=decimals) for m in matrices]
    return '\n\n'.join(parts)


# ─── Document patching ──────────────────────────────────────────

def _is_standalone_line(text: str, start: int, end: int) -> bool:
    """Check whether the raw_text occupies its own line(s)."""
    # Characters before start on the same line
    line_start = text.rfind('\n', 0, start)
    before = text[line_start + 1:start].strip() if line_start >= 0 else text[:start].strip()

    # Characters after end on the same line
    line_end = text.find('\n', end)
    after = text[end:line_end].strip() if line_end >= 0 else text[end:].strip()

    return not before and not after


def patch_document(text: str, matrices: List[DetectedMatrix], decimals: int = 5) -> str:
    """
    Replace every detected matrix's raw text in *text* with its
    LaTeX rendering, choosing the right delimiter style:

    * Standalone block → ``$$...$$``
    * Inline           → ``$...$``
    * Inside a Markdown table (Pattern 2) → full ``$$`` block
      replacing the entire table fragment.
    """
    if not matrices:
        return text

    # Process in reverse order so earlier offsets stay valid
    sorted_matrices = sorted(matrices, key=lambda m: m.start, reverse=True)

    for dm in sorted_matrices:
        latex = render(dm, decimals=decimals)

        if dm.pattern_type == 'table':
            replacement = f"\n$$\n{latex}\n$$\n"
        elif _is_standalone_line(text, dm.start, dm.end):
            replacement = f"\n$$\n{latex}\n$$\n"
        else:
            replacement = f"${latex}$"

        text = text[:dm.start] + replacement + text[dm.end:]

    return text


# ─── Jupyter display helpers ────────────────────────────────────

def display_latex(latex_str: str) -> None:
    """Display a LaTeX string in a Jupyter notebook."""
    try:
        from IPython.display import display, Math
        display(Math(latex_str))
    except ImportError:
        print(latex_str)


def display_all(matrices: List[DetectedMatrix], decimals: int = 5) -> None:
    """Display every detected matrix in Jupyter."""
    for m in matrices:
        latex = render(m, decimals=decimals)
        display_latex(latex)


# ─── Computation rendering ─────────────────────────────────────

def render_with_computation(
    dm: DetectedMatrix,
    op: str,
    *extra_arrays: np.ndarray,
    decimals: int = 5,
) -> str:
    """
    Extract the array from *dm*, execute operation *op*, and return
    LaTeX showing both the input and the output.

    Example output (``op='inv'``)::

        X'X = \\begin{bmatrix}25 & 219 \\\\ ...\\end{bmatrix}
        \\Rightarrow
        (X'X)^{-1} = \\begin{bmatrix}0.113 & ...\\end{bmatrix}
    """
    if dm.array is None:
        return f"% no array for {dm.name}"

    arr = _best_shape(dm.array, dm.name)
    result, latex = compute_and_render(
        op, arr, *extra_arrays, name=dm.name, decimals=decimals,
    )
    dm.computed = True
    dm.result_array = result
    return latex
