"""
pipeline.py — End-to-end pipeline for detecting, fixing,
computing, and saving corrected LaTeX matrices.
"""

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .detector import DetectedMatrix, detect_matrices, _fix_broken_numbers
from .matrix_extractor import (
    compute_and_render,
    matrix_to_latex,
    solve_normal_equations,
    render_step_by_step,
)
from .renderer import (
    display_all,
    display_latex,
    patch_document,
    render,
    render_all,
    render_with_computation,
)


class LatexFix:
    """
    High-level API for detecting and fixing broken matrices
    in Markdown files extracted from PDF Beamer slides.

    Usage::

        lf = LatexFix("lecture.md").run()
        lf.display()
        result = lf.compute("X'X", "inv")
        lf.save("lecture_fixed.md")
    """

    def __init__(self, filepath: Optional[str] = None) -> None:
        self.filepath = Path(filepath) if filepath else None
        self.raw_text: str = ""
        self.cleaned_text: str = ""
        self.matrices: List[DetectedMatrix] = []
        self._name_index: Dict[str, DetectedMatrix] = {}

    @classmethod
    def from_text(cls, text: str) -> "LatexFix":
        """Initialize pipeline directly from a Markdown string."""
        lf = cls(None)
        lf.raw_text = text
        return lf

    # ─── Core pipeline ──────────────────────────────────────────

    def run(self) -> "LatexFix":
        """Read the file (or use existing text), fix broken numbers, detect & extract matrices."""
        if self.filepath and not self.raw_text:
            self.raw_text = self.filepath.read_text(encoding='utf-8')
        
        self.cleaned_text = _fix_broken_numbers(self.raw_text)
        self.matrices = detect_matrices(self.raw_text)

        # Build name index (case-insensitive, plus canonical forms)
        self._name_index.clear()
        for m in self.matrices:
            if m.name:
                self._name_index[m.name.lower()] = m
                self._name_index[m.name] = m
        return self

    # ─── Display ────────────────────────────────────────────────

    def display(self, decimals: int = 5) -> None:
        """Display all detected matrices (Jupyter or plain text)."""
        display_all(self.matrices, decimals=decimals)

    # ─── Save / Output ──────────────────────────────────────────

    def export_text(self, decimals: int = 5) -> str:
        """Patch the document with computed matrices and return the result string."""
        # Use cleaned_text to include fixes for inline broken decimals
        return patch_document(self.cleaned_text, self.matrices, decimals=decimals)

    def save(self, output_path: Optional[str] = None, decimals: int = 5) -> str:
        """
        Patch the original document and write to *output_path*.
        Returns the patched text.
        """
        patched = self.export_text(decimals=decimals)
        if output_path:
            out = Path(output_path)
        elif self.filepath:
            out = self.filepath.with_name(self.filepath.stem + '_fixed' + self.filepath.suffix)
        else:
            raise ValueError("No output path provided, and no original filepath to derive from.")
            
        out.write_text(patched, encoding='utf-8')
        return patched

    # ─── Report ─────────────────────────────────────────────────

    def report(self) -> str:
        """Return a human-readable summary of detected matrices."""
        lines = [f"Detected {len(self.matrices)} matrix/matrices:\n"]
        for i, m in enumerate(self.matrices, 1):
            lines.append(
                f"  {i}. name={m.name!r}  shape={m.shape}  "
                f"type={m.pattern_type}  chars=[{m.start}:{m.end}]"
            )
        return '\n'.join(lines)

    # ─── Lookup ─────────────────────────────────────────────────

    def get_matrix(self, name: str) -> Optional[DetectedMatrix]:
        """Look up a detected matrix by name (case-insensitive)."""
        return self._name_index.get(name) or self._name_index.get(name.lower())

    # ─── Computation ────────────────────────────────────────────

    def compute(
        self,
        name: str,
        op: str,
        other_name: Optional[str] = None,
    ) -> dict:
        """
        Look up a matrix by *name*, perform *op*, and return a dict::

            {
                'input':  numpy array,
                'result': numpy array,
                'latex':  LaTeX string,
                'name':   result name,
            }

        Examples::

            lf.compute("X'X", "inv")
            lf.compute("X'X", "multiply", "X'y")
            lf.compute("X'X", "solve", "X'y")
        """
        dm = self.get_matrix(name)
        if dm is None:
            raise KeyError(f"Matrix {name!r} not found. Available: "
                           f"{[m.name for m in self.matrices]}")

        arrays = [dm.array]

        if other_name is not None:
            dm2 = self.get_matrix(other_name)
            if dm2 is None:
                raise KeyError(f"Matrix {other_name!r} not found.")
            arrays.append(dm2.array)

        # Determine result name
        if op == 'inv':
            res_name = f"({name})^{{-1}}"
        elif op == 'transpose':
            res_name = f"({name})^T"
        elif op == 'solve':
            res_name = r"\hat{\beta}"
        else:
            res_name = name

        result, latex = compute_and_render(
            op, *arrays, name=name, decimals=5,
        )

        dm.computed = True
        dm.result_array = result

        return {
            'input': dm.array,
            'result': result,
            'latex': latex,
            'name': res_name,
        }

    def auto_solve(self) -> List[dict]:
        """
        Automatically find matrix pairs that can be solved
        (X'X + X'y → β̂) and execute the solutions.

        Returns a list of result dicts (same format as ``compute``).
        """
        results: List[dict] = []

        # Look for X'X + X'y pair
        xtx = self.get_matrix("X'X")
        xty = self.get_matrix("X'y")

        if xtx is not None and xty is not None:
            # 1. Inverse of X'X
            try:
                inv_result = self.compute("X'X", "inv")
                results.append(inv_result)
            except Exception:
                pass

            # 2. Solve for β̂
            try:
                solve_result = self.compute("X'X", "solve", "X'y")
                results.append(solve_result)
            except Exception:
                pass

        # Generic: invert any square matrix that hasn't been computed yet
        for m in self.matrices:
            if m.array is not None and not m.computed:
                if m.array.ndim == 2 and m.array.shape[0] == m.array.shape[1]:
                    try:
                        inv_result = self.compute(m.name, "inv")
                        results.append(inv_result)
                    except Exception:
                        pass

        return results
