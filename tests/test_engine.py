"""
test_engine.py — Engine Unit Tests (Phase 5.1)
Tests all deterministic extraction pipeline components.
Runs standalone — no pytest required.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.concept_extractor import ConceptExtractor
from engine.dependency_mapper import DependencyMapper
from engine.density_analyzer import DensityAnalyzer
from engine.formula_extractor import FormulaExtractor


def test_concept_extraction_bold_heavy():
    """Book with lots of bold terms — should extract all."""
    ce = ConceptExtractor()
    text = (
        "A **B-Tree** is a self-balancing tree data structure that maintains "
        "sorted data. The **write-ahead log** (WAL) is defined as a log where "
        "all modifications are written before being applied."
    )
    result = ce.extract(text)
    names = [c["name"].lower() for c in result]
    assert any("b-tree" in n for n in names), f"Should find B-Tree, got {names}"
    assert any("write-ahead log" in n or "wal" in n for n in names), \
        f"Should find WAL, got {names}"
    print(f"[BOLD HEAVY] Found {len(result)} concepts — PASSED ✓")


def test_concept_extraction_no_formatting():
    """Book with no bold/italic — should still find concepts via fallback."""
    ce = ConceptExtractor()
    text = (
        "The hash table stores key-value pairs efficiently. A hash table uses "
        "a hash function to compute an index into an array of buckets. "
        "The hash function must distribute keys uniformly across the buckets. "
        "When two keys hash to the same bucket, a collision occurs. The hash "
        "table resolves collisions using chaining or open addressing. "
        "The load factor determines when to resize the hash table."
    )
    result = ce.extract(text)
    assert len(result) > 0, "Should find concepts using fallback mechanisms"
    print(f"[NO FORMATTING] Found {len(result)} concepts — PASSED ✓")


def test_concept_extraction_math_book():
    """Math book with theorems — should detect theorem names."""
    ce = ConceptExtractor()
    text = """
    Definition 3.1: A group (G, *) is a set G together with a binary
    operation * that satisfies closure, associativity, identity, and invertibility.

    Theorem 3.2 (Lagrange's Theorem): If H is a subgroup of a finite
    group G, then the order of H divides the order of G.
    """
    result = ce.extract(text)
    assert len(result) >= 2, f"Should find theorem/definition concepts, got {len(result)}"
    print(f"[MATH BOOK] Found {len(result)} concepts — PASSED ✓")


def test_dependency_comparison_detection():
    """'Unlike X, Y is...' should create compared_with edge."""
    dm = DependencyMapper()
    text = "Unlike a B-Tree, a Hash Table does not store elements in sorted order."
    concepts = [
        {"name": "B-Tree", "definition": "", "importance": "high"},
        {"name": "Hash Table", "definition": "", "importance": "high"},
    ]
    result = dm.map(text, concepts)
    edges = result.get("edges", [])

    has_comparison = any(
        e["type"] == "compared_with"
        for e in edges
    )
    assert has_comparison, f"Should find compared_with edge, got {edges}"
    print(f"[COMPARISON] Found {len(edges)} edges — PASSED ✓")


def test_dependency_mapper_no_crash_empty():
    """Empty text should return empty result, not crash."""
    dm = DependencyMapper()
    result = dm.map("", [])
    assert "edges" in result, "Should return dict with edges key"
    assert result["edges"] == [], f"Should have 0 edges, got {result['edges']}"
    print("[EMPTY TEXT] No crash — PASSED ✓")


def test_density_math_heavy():
    """Text with many $$...$$ should be classified as math-heavy."""
    da = DensityAnalyzer()
    text = (
        "The Fourier transform is given by $$F(\\omega) = \\int_{-\\infty}^"
        "{\\infty} f(t) e^{-i\\omega t} dt$$\n\n"
        "Using the convolution theorem, $$f * g = F^{-1}(F(f) \\cdot F(g))$$\n\n"
        "The inverse transform is $$f(t) = \\frac{1}{2\\pi} \\int F(\\omega) "
        "e^{i\\omega t} d\\omega$$\n\n"
        "We can also express this as $$\\hat{f}(\\xi) = \\int f(x) e^{-2\\pi "
        "i x \\xi} dx$$"
    )
    stats = da._compute_stats(text)
    types = da._classify(stats)
    assert "math-heavy" in types, f"Should detect math-heavy, got {types}"
    print(f"[MATH HEAVY] Types: {types} — PASSED ✓")


def test_density_proof_heavy():
    """Proof sections should be classified as proof-heavy."""
    da = DensityAnalyzer()
    text = """
    Proof: We proceed by induction on n. For the base case n=1,
    the result holds trivially.

    For the inductive step, assume the theorem holds for n=k.
    We must show it holds for n=k+1. Hence the result follows
    by induction. ∎

    Proof of sufficiency: Suppose the condition holds.
    Then by contradiction, we conclude that this leads to a
    contradiction, hence we have shown the result.
    """
    stats = da._compute_stats(text)
    types = da._classify(stats)
    assert "proof-heavy" in types, f"Should detect proof-heavy, got {types}"
    print(f"[PROOF HEAVY] Types: {types} — PASSED ✓")


def test_density_problem_set():
    """Exercise/problem sections should be classified as problem-set."""
    da = DensityAnalyzer()
    text = """
    Exercise 1: Find the eigenvalues of the matrix A = [[2,1],[1,2]].
    Problem 2: Show that every finite group of order p (prime) is cyclic.
    Exercise 3: Calculate the determinant of the 3x3 matrix B.
    Problem 4: Determine whether f(x) = x^2 is uniformly continuous.
    Exercise 5: Compute the integral of sin(x)/x from 0 to infinity.
    Problem 6: Prove that the set of rational numbers is countable.
    """
    stats = da._compute_stats(text)
    types = da._classify(stats)
    assert "problem-set" in types, f"Should detect problem-set, got {types}"
    print(f"[PROBLEM SET] Types: {types} — PASSED ✓")


def test_formula_extraction_display():
    """$$E=mc^2$$ should be extracted as a display formula."""
    fe = FormulaExtractor()
    text = "The energy-mass equivalence is:\n\n$$ E = mc^2 $$\n\nWhich is famous."
    formulas = fe.extract(text)
    has_emc2 = any("E = mc^2" in f.get("latex", "") or "E=mc^2" in f.get("latex", "")
                    for f in formulas)
    assert has_emc2, f"Should extract E=mc^2, got {[f.get('latex','') for f in formulas]}"
    print(f"[FORMULA DISPLAY] Found {len(formulas)} formulas — PASSED ✓")


def test_formula_extraction_inline():
    """$x^2$ should be extracted as inline formula."""
    fe = FormulaExtractor()
    text = "The function $f(x) = x^2$ is a parabola and $g(x) = 2x$ is linear."
    formulas = fe.extract(text)
    assert len(formulas) >= 1, f"Should extract inline formulas, got {len(formulas)}"
    print(f"[FORMULA INLINE] Found {len(formulas)} formulas — PASSED ✓")


# ─── Run all tests ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 5.1 — Engine Unit Tests")
    print("=" * 60 + "\n")

    test_concept_extraction_bold_heavy()
    test_concept_extraction_no_formatting()
    test_concept_extraction_math_book()
    test_dependency_comparison_detection()
    test_dependency_mapper_no_crash_empty()
    test_density_math_heavy()
    test_density_proof_heavy()
    test_density_problem_set()
    test_formula_extraction_display()
    test_formula_extraction_inline()

    print("\n" + "=" * 60)
    print("ALL ENGINE TESTS PASSED ✓")
    print("=" * 60)
