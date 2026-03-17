"""
latexfix — Detect, fix, and re-render broken LaTeX matrices
from Markdown files extracted from PDF Beamer slides.
"""

from .pipeline import LatexFix
from .detector import detect_matrices, DetectedMatrix
from .matrix_extractor import (
    solve_normal_equations,
    matrix_to_latex,
    compute_and_render,
    render_step_by_step,
)
from .renderer import (
    render,
    render_all,
    patch_document,
    render_with_computation,
)

__all__ = [
    "LatexFix",
    "detect_matrices",
    "DetectedMatrix",
    "solve_normal_equations",
    "matrix_to_latex",
    "compute_and_render",
    "render_step_by_step",
    "render",
    "render_all",
    "patch_document",
    "render_with_computation",
]
