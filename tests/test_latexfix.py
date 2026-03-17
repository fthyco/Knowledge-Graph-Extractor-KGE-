"""
test_latexfix.py — Verify the latexfix package works end-to-end.

Key validation:  β̂ ≈ [2.34123, 1.61591, 0.01438]
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import numpy as np
from pathlib import Path


# ─── Synthetic test document ────────────────────────────────────

SAMPLE_MD = r"""
# Lecture 7 — Least Squares

## X'X Matrix

□ 25   219    10232  □
□ 219  3055   133899 □
□ 10232 133899 6725688 □

## X'y Vector

|  | 559.55 |  |
|  | 7374.80 |  |
|  | 337039.59 |  |

This is the **X'y** vector above.

Some inline text with a broken number like - . 00444 or 12 . 03 end.
"""

def test_detection():
    """Test that matrices are detected from the sample document."""
    from latexfix import detect_matrices

    matrices = detect_matrices(SAMPLE_MD)
    print(f"[DETECT] Found {len(matrices)} matrices")
    for m in matrices:
        print(f"  name={m.name!r}  shape={m.shape}  type={m.pattern_type}")
    assert len(matrices) >= 2, f"Expected >=2 matrices, got {len(matrices)}"
    print("[DETECT] PASSED\n")
    return matrices


def test_broken_numbers():
    """Test that Pattern 3 (broken decimals) is fixed."""
    from latexfix.detector import _fix_broken_numbers

    assert _fix_broken_numbers("12 . 03") == "12.03"
    assert _fix_broken_numbers("- . 00444") == "-0.00444"
    assert _fix_broken_numbers("- . 5") == "-0.5"
    assert _fix_broken_numbers("133 899") == "133 899"  # NOT a decimal
    print("[BROKEN_NUMBERS] PASSED\n")


def test_matrix_to_latex():
    """Test LaTeX rendering of a matrix."""
    from latexfix import matrix_to_latex

    arr = np.array([[1, 2], [3, 4]])
    latex = matrix_to_latex(arr, name="A")
    print(f"[LATEX]\n{latex}\n")
    assert "\\begin{bmatrix}" in latex
    assert "A =" in latex
    print("[MATRIX_TO_LATEX] PASSED\n")


def test_compute_and_render():
    """Test compute_and_render for inverse."""
    from latexfix import compute_and_render

    A = np.array([[25, 219, 10232],
                  [219, 3055, 133899],
                  [10232, 133899, 6725688]], dtype=float)
    result, latex = compute_and_render('inv', A, name="X'X")
    print(f"[COMPUTE inv]\n{latex[:200]}...\n")
    assert result.shape == (3, 3), f"Expected (3,3), got {result.shape}"
    # Verify A @ inv(A) ≈ I
    identity_check = A @ result
    assert np.allclose(identity_check, np.eye(3), atol=1e-6), "Inverse check failed"
    print("[COMPUTE_AND_RENDER] PASSED\n")


def test_solve_normal_equations():
    """Test that solve_normal_equations returns the expected β̂."""
    from latexfix import solve_normal_equations

    XtX = np.array([[25, 219, 10232],
                    [219, 3055, 133899],
                    [10232, 133899, 6725688]], dtype=float)
    Xty = np.array([559.55, 7374.80, 337039.59], dtype=float)

    beta = solve_normal_equations(XtX, Xty)
    print(f"[SOLVE] β̂ = {beta}")
    expected = np.array([2.34123, 1.61591, 0.01438])
    assert np.allclose(beta, expected, atol=0.001), \
        f"β̂ mismatch: got {beta}, expected ≈{expected}"
    print("[SOLVE_NORMAL_EQUATIONS] PASSED\n")


def test_render_step_by_step():
    """Test the step-by-step LaTeX generation."""
    from latexfix import render_step_by_step

    XtX = np.array([[25, 219, 10232],
                    [219, 3055, 133899],
                    [10232, 133899, 6725688]], dtype=float)
    Xty = np.array([559.55, 7374.80, 337039.59], dtype=float)

    latex = render_step_by_step(XtX, Xty)
    print(f"[STEP_BY_STEP]\n{latex[:300]}...\n")
    assert "\\begin{aligned}" in latex
    assert "Step 1" in latex
    assert "Step 4" in latex
    print("[RENDER_STEP_BY_STEP] PASSED\n")


def test_pipeline_end_to_end():
    """Test the full LatexFix pipeline on a temp file."""
    from latexfix import LatexFix

    # Write sample to a temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md',
                                     delete=False, encoding='utf-8') as f:
        f.write(SAMPLE_MD)
        tmp_path = f.name

    try:
        lf = LatexFix(tmp_path).run()

        # Report
        print(lf.report())
        assert len(lf.matrices) >= 2

        # Compute inverse
        inv_result = lf.compute("X'X", "inv")
        print(f"\n[PIPELINE inv] shape={inv_result['result'].shape}")
        assert inv_result['result'].shape == (3, 3)

        # Compute solve
        solve_result = lf.compute("X'X", "solve", "X'y")
        beta = solve_result['result']
        print(f"[PIPELINE solve] β̂ = {beta}")
        expected = np.array([2.34123, 1.61591, 0.01438])
        assert np.allclose(beta, expected, atol=0.001), \
            f"β̂ mismatch: got {beta}"

        # Auto-solve
        solutions = lf.auto_solve()
        print(f"[PIPELINE auto_solve] {len(solutions)} solution(s)")
        assert len(solutions) >= 1

        # Save
        out_path = tmp_path.replace('.md', '_fixed.md')
        patched = lf.save(out_path)
        assert '□' not in patched, "Patched output still contains □"
        print(f"[PIPELINE save] wrote {out_path}")

        print("\n[PIPELINE] PASSED\n")
    finally:
        os.unlink(tmp_path)
        fixed = tmp_path.replace('.md', '_fixed.md')
        if os.path.exists(fixed):
            os.unlink(fixed)


# ─── Run all tests ──────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("latexfix — Test Suite")
    print("=" * 60 + "\n")

    test_broken_numbers()
    test_matrix_to_latex()
    test_compute_and_render()
    test_solve_normal_equations()
    test_render_step_by_step()
    test_detection()
    test_pipeline_end_to_end()

    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
