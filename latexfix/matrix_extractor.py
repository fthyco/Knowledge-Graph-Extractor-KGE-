"""
matrix_extractor.py — Parse broken matrix text into numpy arrays,
render arrays as LaTeX, and perform matrix computations.
"""

import re
from typing import Callable, Optional, Tuple, List

import numpy as np


# ─── Number parsing ─────────────────────────────────────────────

# Characters to strip when cleaning matrix cell text
_NOISE_CHARS = re.compile(r'[□\u25A1\uF8EE-\uF8FB=|]')


def _parse_numbers(text: str) -> List[float]:
    """
    Extract a list of floats from *text*, after fixing broken
    decimals and minus signs (Pattern 3).

    Handles:
      "12 . 03"    → 12.03
      "- . 00444"  → -0.00444
      "- 3"        → -3.0   (only when clearly a sign)
    """
    # Fix broken minus-dot  e.g.  "- . 00444" → "-0.00444"
    text = re.sub(r'-\s*\.\s*(\d)', r'-0.\1', text)
    # Fix broken decimal     e.g.  "12 . 03"  → "12.03"
    text = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', text)

    # Strip noise characters
    text = _NOISE_CHARS.sub(' ', text)

    # Extract all numbers (int or float, possibly negative)
    nums = re.findall(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', text)
    return [float(n) for n in nums]


# ─── Extraction from raw patterns ───────────────────────────────

def extract_box_matrix(raw: str) -> Optional[np.ndarray]:
    """
    Parse a □-bracket (Pattern 1) block into an ``np.ndarray``.

    Each line of *raw* is treated as a matrix row.  Box characters
    and other noise are stripped; remaining numbers become columns.
    """
    rows = []
    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
        nums = _parse_numbers(line)
        if nums:
            rows.append(nums)

    if not rows:
        return None

    # Ensure all rows have the same length (pad with 0 if needed)
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append(0.0)

    return np.array(rows, dtype=float)


def extract_table_matrix(raw: str) -> Optional[np.ndarray]:
    """
    Parse a Markdown-table matrix (Pattern 2) into an ``np.ndarray``.

    Strips ``|``, ``=``, ``□`` and separator rows, then parses
    numbers from each remaining row.
    """
    rows = []
    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Skip separator rows  (| --- | --- |)
        if re.match(r'^\|[\s|:\-_]*\|$', line):
            continue
        nums = _parse_numbers(line)
        if nums:
            rows.append(nums)

    if not rows:
        return None

    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append(0.0)

    return np.array(rows, dtype=float)


# ─── LaTeX rendering ────────────────────────────────────────────

def _default_fmt(value: float, decimals: int) -> str:
    """Format a single number for LaTeX output."""
    if value == int(value) and abs(value) < 1e12:
        return str(int(value))
    return f"{value:.{decimals}f}".rstrip('0').rstrip('.')


def matrix_to_latex(
    arr: np.ndarray,
    name: str = '',
    env: str = 'bmatrix',
    decimals: int = 5,
    fmt: Optional[Callable[[float], str]] = None,
) -> str:
    """
    Render a numpy array as a LaTeX ``bmatrix`` (or other env).

    Parameters
    ----------
    arr : np.ndarray
        1-D or 2-D array.
    name : str
        Optional name displayed before the matrix (e.g. ``"X'X"``).
    env : str
        LaTeX environment (``bmatrix``, ``pmatrix``, etc.).
    decimals : int
        Decimal places when *fmt* is not provided.
    fmt : callable, optional
        Custom formatter ``float → str``.  Overrides *decimals*.

    Returns
    -------
    str
        LaTeX source string.
    """
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)

    formatter = fmt if fmt else lambda v: _default_fmt(v, decimals)

    rows_latex = []
    for row in arr:
        cells = ' & '.join(formatter(v) for v in row)
        rows_latex.append(cells)

    body = ' \\\\\n'.join(rows_latex)
    matrix_str = f"\\begin{{{env}}}\n{body}\n\\end{{{env}}}"

    if name:
        return f"{name} = {matrix_str}"
    return matrix_str


# ─── Solving ────────────────────────────────────────────────────

def solve_normal_equations(XtX: np.ndarray, Xty: np.ndarray) -> np.ndarray:
    """
    Solve the normal equations  ``β̂ = (X'X)⁻¹ X'y``.

    Parameters
    ----------
    XtX : np.ndarray
        The ``X'X`` matrix (n×n).
    Xty : np.ndarray
        The ``X'y`` vector (n×1 or n,).

    Returns
    -------
    np.ndarray
        The coefficient vector β̂.
    """
    Xty_flat = Xty.flatten()
    return np.linalg.solve(XtX, Xty_flat)


# ─── Computation + rendering ────────────────────────────────────

def compute_and_render(
    op: str,
    *arrays: np.ndarray,
    name: str = '',
    decimals: int = 5,
) -> Tuple[np.ndarray, str]:
    """
    Execute a linear-algebra operation and return
    ``(result_array, latex_string)``.

    Supported *op* values
    ---------------------
    ``'inv'``        (X'X)⁻¹            — 1 array
    ``'transpose'``  Aᵀ                  — 1 array
    ``'multiply'``   A @ B               — 2 arrays
    ``'solve'``      lstsq / solve(A, b) — 2 arrays (A, b)

    The returned LaTeX shows both the input(s) and the result.
    """
    if op == 'inv':
        A = arrays[0]
        result = np.linalg.inv(A)
        latex = (
            matrix_to_latex(A, name=name or "A", decimals=decimals)
            + "\n\\Rightarrow\n"
            + matrix_to_latex(result, name=f"({name or 'A'})^{{-1}}", decimals=decimals)
        )

    elif op == 'transpose':
        A = arrays[0]
        result = A.T
        latex = (
            matrix_to_latex(A, name=name or "A", decimals=decimals)
            + "\n\\Rightarrow\n"
            + matrix_to_latex(result, name=f"({name or 'A'})^T", decimals=decimals)
        )

    elif op == 'multiply':
        A, B = arrays[0], arrays[1]
        result = A @ B
        res_name = name if name else "AB"
        latex = (
            matrix_to_latex(A, name="A", decimals=decimals)
            + "\n\\cdot\n"
            + matrix_to_latex(B, name="B", decimals=decimals)
            + "\n=\n"
            + matrix_to_latex(result, name=res_name, decimals=decimals)
        )

    elif op == 'solve':
        A, b = arrays[0], arrays[1]
        b_flat = b.flatten()
        result = np.linalg.solve(A, b_flat)
        res_name = name if name else r"\hat{\beta}"
        latex = (
            matrix_to_latex(A, name="A", decimals=decimals)
            + ",\\quad "
            + matrix_to_latex(b.reshape(-1, 1) if b.ndim == 1 else b,
                              name="b", decimals=decimals)
            + "\n\\Rightarrow\n"
            + matrix_to_latex(result.reshape(-1, 1), name=res_name,
                              decimals=decimals)
        )

    else:
        raise ValueError(f"Unknown operation: {op!r}")

    return result, latex


def render_step_by_step(XtX: np.ndarray, Xty: np.ndarray, decimals: int = 5) -> str:
    r"""
    Return complete LaTeX for solving  β̂ = (X'X)⁻¹ X'y
    in four numbered steps.

    Steps
    -----
    1. X'X  = [...]
    2. X'y  = [...]
    3. (X'X)⁻¹ = [...]
    4. β̂ = (X'X)⁻¹ X'y = [...]
    """
    inv_XtX = np.linalg.inv(XtX)
    beta = inv_XtX @ Xty.flatten()

    Xty_col = Xty.reshape(-1, 1) if Xty.ndim == 1 else Xty

    steps = [
        f"\\text{{Step 1: }} X'X &= {matrix_to_latex(XtX, decimals=decimals)}",
        f"\\text{{Step 2: }} X'y &= {matrix_to_latex(Xty_col, decimals=decimals)}",
        f"\\text{{Step 3: }} (X'X)^{{-1}} &= {matrix_to_latex(inv_XtX, decimals=decimals)}",
        (
            f"\\text{{Step 4: }} \\hat{{\\beta}} = (X'X)^{{-1}} X'y &= "
            f"{matrix_to_latex(beta.reshape(-1, 1), decimals=decimals)}"
        ),
    ]

    body = " \\\\\n".join(steps)
    return f"\\begin{{aligned}}\n{body}\n\\end{{aligned}}"
