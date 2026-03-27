"""
test_phase3.py — Verify Phase 3 changes:
3.1 Concept Extractor fallbacks
3.2 Density Analyzer new types
3.3 Metadata Extractor
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_concept_fallback_tfidf():
    """Fallback: extract concepts from plain text without bold or definitions."""
    from engine.concept_extractor import ConceptExtractor

    ce = ConceptExtractor()

    # Text with NO bold, no definitions, no headings — just repeated terms
    text = """
    The hash table stores key-value pairs efficiently. A hash table uses
    a hash function to compute an index into an array of buckets.
    The hash function must distribute keys uniformly across the buckets.
    When two keys hash to the same bucket, a collision occurs. The hash
    table resolves collisions using chaining or open addressing.
    The load factor determines when to resize the hash table.
    """

    result = ce.extract(text)
    names = [c["name"].lower() for c in result]

    print(f"[TFIDF FALLBACK] Found {len(result)} concepts:")
    for c in result[:8]:
        print(f"  {c['name']} ({c['importance']}) via {c.get('sources', [])}")

    assert len(result) >= 1, "Should find at least 1 concept from frequency analysis"
    print("[TFIDF FALLBACK] PASSED ✓\n")


def test_concept_fallback_theorem_blocks():
    """Fallback: detect Theorem/Definition blocks."""
    from engine.concept_extractor import ConceptExtractor

    ce = ConceptExtractor()

    text = """
    Definition 3.1: A group (G, *) is a set G together with a binary
    operation * that satisfies closure, associativity, identity, and
    invertibility.

    Theorem 3.2 (Lagrange's Theorem): If H is a subgroup of a finite
    group G, then the order of H divides the order of G.

    Lemma 3.3: Every subgroup of a cyclic group is cyclic.
    """

    result = ce.extract(text)
    names = [c["name"].lower() for c in result]

    print(f"[THEOREM BLOCKS] Found {len(result)} concepts:")
    for c in result:
        print(f"  {c['name']} ({c['importance']}) - def: {c.get('definition', '')[:50]}")

    # Should find concepts from theorem blocks
    has_lagrange = any("lagrange" in n for n in names)
    print(f"  Found Lagrange: {has_lagrange}")

    assert len(result) >= 2, "Should find concepts from theorem/definition blocks"
    print("[THEOREM BLOCKS] PASSED ✓\n")


def test_concept_primary_still_works():
    """Primary extraction (bold, definitions) should still work."""
    from engine.concept_extractor import ConceptExtractor

    ce = ConceptExtractor()

    text = """
    A **B-Tree** is a self-balancing tree data structure that maintains
    sorted data. The **write-ahead log** (WAL) is defined as a log where
    all modifications are written before being applied. Unlike the B-Tree,
    an **LSM-Tree** uses a log-structured merge approach.
    """

    result = ce.extract(text)
    names = [c["name"].lower() for c in result]

    assert any("b-tree" in n for n in names), "Should find B-Tree from bold"
    assert any("lsm-tree" in n or "lsm" in n for n in names), "Should find LSM-Tree"
    print(f"[PRIMARY EXTRACTION] Found {len(result)} concepts - PASSED ✓\n")


def test_density_proof_heavy():
    """Density analyzer should detect proof-heavy sections."""
    from engine.density_analyzer import DensityAnalyzer

    da = DensityAnalyzer()

    text = """
    Proof: We proceed by induction on n. For the base case n=1,
    the result holds trivially.

    For the inductive step, assume the theorem holds for n=k.
    We must show it holds for n=k+1. By the induction hypothesis,
    we have that f(k) = g(k). Therefore,

    f(k+1) = f(k) + h(k) = g(k) + h(k) = g(k+1).

    Hence the result follows by induction. ∎

    Proof of sufficiency: Suppose the condition holds.
    Then by contradiction, assume the negation.
    We conclude that this leads to a contradiction, hence
    we have shown the result.
    """

    stats = da._compute_stats(text)
    types = da._classify(stats)

    print(f"[PROOF-HEAVY] Types: {types}")
    print(f"  proof_ratio={stats['proof_ratio']:.2f}, proof_count={stats['proof_count']}")

    assert "proof-heavy" in types, f"Should detect proof-heavy, got {types}"
    print("[PROOF-HEAVY] PASSED ✓\n")


def test_density_problem_set():
    """Density analyzer should detect problem/exercise sections."""
    from engine.density_analyzer import DensityAnalyzer

    da = DensityAnalyzer()

    text = """
    Exercise 1: Find the eigenvalues of the matrix A = [[2,1],[1,2]].

    Problem 2: Show that every finite group of order p (prime) is cyclic.

    Exercise 3: Calculate the determinant of the 3x3 matrix B.

    Problem 4: Determine whether the function f(x) = x^2 is uniformly
    continuous on [0, infinity).

    Exercise 5: Compute the integral of sin(x)/x from 0 to infinity.

    Problem 6: Prove that the set of rational numbers is countable.
    """

    stats = da._compute_stats(text)
    types = da._classify(stats)

    print(f"[PROBLEM-SET] Types: {types}")
    print(f"  problem_ratio={stats['problem_ratio']:.2f}, problem_count={stats['problem_count']}")

    assert "problem-set" in types, f"Should detect problem-set, got {types}"
    print("[PROBLEM-SET] PASSED ✓\n")


def test_density_backward_compat():
    """Existing types should still be detected correctly."""
    from engine.density_analyzer import DensityAnalyzer

    da = DensityAnalyzer()

    # Math-heavy text
    text = """
    The Fourier transform is given by $$F(\\omega) = \\int_{-\\infty}^{\\infty} f(t) e^{-i\\omega t} dt$$

    Using the convolution theorem, $$f * g = F^{-1}(F(f) \\cdot F(g))$$

    The inverse transform is $$f(t) = \\frac{1}{2\\pi} \\int_{-\\infty}^{\\infty} F(\\omega) e^{i\\omega t} d\\omega$$

    We can also express this as $$\\hat{f}(\\xi) = \\int f(x) e^{-2\\pi i x \\xi} dx$$
    """

    stats = da._compute_stats(text)
    types = da._classify(stats)

    print(f"[BACKWARD COMPAT] Math text types: {types}")
    assert "math-heavy" in types, f"Should still detect math-heavy, got {types}"
    print("[BACKWARD COMPAT] PASSED ✓\n")


def test_metadata_subject_detection():
    """MetadataExtractor should detect subject from content."""
    from engine.metadata_extractor import MetadataExtractor

    me = MetadataExtractor()

    # Computer science book
    result = me.extract(
        title="Designing Data-Intensive Applications",
        full_text="This book covers database algorithms, data structures, "
                  "distributed systems, and software architecture."
    )
    print(f"[SUBJECT CS] Detected: {result['subject']}")
    assert result["subject"] in ("computer science",), f"Expected CS, got {result['subject']}"

    # Math book
    result2 = me.extract(
        title="Introduction to Linear Algebra",
        full_text="Theorem 1: Every matrix has a unique row echelon form. "
                  "Proof by induction. Integral calculus. Topology of manifolds."
    )
    print(f"[SUBJECT MATH] Detected: {result2['subject']}")
    assert result2["subject"] == "mathematics", f"Expected math, got {result2['subject']}"
    print("[SUBJECT DETECTION] PASSED ✓\n")


def test_metadata_author_extraction():
    """Author extraction from first-page text."""
    from engine.metadata_extractor import MetadataExtractor

    me = MetadataExtractor()

    result = me.extract(
        first_pages_text="Designing Data-Intensive Applications\n\nby Martin Kleppmann\n\n"
                         "O'Reilly Media\n© 2017 Martin Kleppmann"
    )
    print(f"[AUTHOR] Detected: '{result['author']}'")
    assert "Kleppmann" in result["author"], f"Should find Kleppmann, got '{result['author']}'"

    # Year
    assert result["year"] == "2017", f"Expected 2017, got '{result['year']}'"
    print(f"[YEAR] Detected: {result['year']}")
    print("[AUTHOR EXTRACTION] PASSED ✓\n")


def test_metadata_language():
    """Language detection."""
    from engine.metadata_extractor import MetadataExtractor

    me = MetadataExtractor()

    # English
    result = me.extract(full_text="This is a standard English text about algorithms and data.")
    assert result["language"] == "en"

    # Arabic
    result2 = me.extract(full_text="هذا نص عربي عن الخوارزميات وهياكل البيانات والبرمجة")
    assert result2["language"] == "ar", f"Expected ar, got {result2['language']}"

    print("[LANGUAGE DETECTION] PASSED ✓\n")


# ─── Run all tests ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3 — Test Suite")
    print("=" * 60 + "\n")

    test_concept_fallback_tfidf()
    test_concept_fallback_theorem_blocks()
    test_concept_primary_still_works()
    test_density_proof_heavy()
    test_density_problem_set()
    test_density_backward_compat()
    test_metadata_subject_detection()
    test_metadata_author_extraction()
    test_metadata_language()

    print("=" * 60)
    print("ALL PHASE 3 TESTS PASSED ✓")
    print("=" * 60)
