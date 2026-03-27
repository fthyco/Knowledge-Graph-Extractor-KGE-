"""
test_performance.py — Performance Benchmarks (Phase 5.2)
Ensures engine components scale well with large inputs.
Runs standalone — no pytest required.
"""
import sys
import os
import time
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.concept_extractor import ConceptExtractor
from warehouse.storage import Storage


def test_concept_extraction_performance():
    """ConceptExtractor should handle ~60K words in < 3 seconds."""
    ce = ConceptExtractor()
    # ~12 words per repeat × 5000 copies = ~60K words
    base = (
        "The **algorithm** processes data linearly. "
        "It focuses on the **B-Tree** structure for caching.\n"
    )
    large_text = base * 5000

    start = time.time()
    result = ce.extract(large_text)
    duration = time.time() - start

    print(f"[CONCEPT PERF] {len(result)} concepts in {duration:.2f}s for ~60K words")
    assert duration < 3.0, f"Too slow: {duration:.2f}s (limit: 3.0s)"
    print("[CONCEPT PERF] PASSED ✓\n")


def test_storage_index_cache_performance():
    """SQLite list_books: 50 repeated reads should be < 500ms."""
    tmp = tempfile.mkdtemp(prefix="pdf_test_")
    try:
        storage = Storage(tmp)

        # Insert 200 books via SQLite
        from warehouse.models import Book
        for i in range(200):
            book = Book(
                id=f"bk_{i}",
                title=f"Book Title {i}",
                filename=f"book_{i}.pdf",
                total_chapters=15,
                chapter_ids=[f"ch_{i}_{c}" for c in range(15)],
            )
            storage.save_book(book, defer_index=True)
        storage.flush_index()

        # 50 repeated reads
        start = time.time()
        for _ in range(50):
            idx = storage.list_books()
        duration = time.time() - start

        print(f"[SQLITE PERF] 50 list_books() in {duration*1000:.1f}ms ({len(idx)} books)")
        assert duration < 0.5, f"Too slow: {duration*1000:.1f}ms (limit: 500ms)"
        print("[SQLITE PERF] PASSED ✓\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_density_analyzer_performance():
    """DensityAnalyzer should handle large text quickly."""
    from engine.density_analyzer import DensityAnalyzer

    da = DensityAnalyzer()
    # ~50K words of mixed content
    base = (
        "Proof: We proceed by induction. $$E=mc^2$$ and by theorem 1, "
        "the result follows. Exercise 1: compute the answer.\n"
    )
    large_text = base * 3000

    start = time.time()
    stats = da._compute_stats(large_text)
    types = da._classify(stats)
    duration = time.time() - start

    print(f"[DENSITY PERF] Types: {types} in {duration:.2f}s")
    assert duration < 2.0, f"Too slow: {duration:.2f}s (limit: 2.0s)"
    print("[DENSITY PERF] PASSED ✓\n")


# ─── Run all ────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 5.2 — Performance Benchmarks")
    print("=" * 60 + "\n")

    test_concept_extraction_performance()
    test_storage_index_cache_performance()
    test_density_analyzer_performance()

    print("=" * 60)
    print("ALL PERFORMANCE TESTS PASSED ✓")
    print("=" * 60)
