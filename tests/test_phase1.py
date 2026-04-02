"""
test_phase1.py — Verify Phase 1 changes:
1.1 Dependency Mapper fix
1.2 Error recovery in ingester
1.3 Analysis caching in storage
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_dependency_mapper_comparison_edges():
    """Bug fix: _match_concept_edge should now produce real edges."""
    from engine.dependency_mapper import DependencyMapper

    dm = DependencyMapper()
    concepts = [
        {"name": "LSM-Tree", "importance": "high"},
        {"name": "B-Tree", "importance": "high"},
        {"name": "Hash Index", "importance": "medium"},
    ]

    text = (
        "Unlike **B-Tree** indexes, an LSM-Tree uses a log-structured approach. "
        "Compared to Hash Index, the B-Tree provides range queries."
    )

    result = dm.map(text, concepts)

    print(f"[DEP MAPPER] Edges found: {len(result['edges'])}")
    for e in result["edges"]:
        print(f"  {e['from']} --[{e['type']}]--> {e['to']}")

    print(f"[DEP MAPPER] Clusters: {len(result['concept_clusters'])}")
    for cluster in result["concept_clusters"]:
        print(f"  {cluster}")

    # The old code returned 0 comparison edges from single-term patterns
    # Now it should find at least 1
    comparison_edges = [e for e in result["edges"] if e["type"] == "compared_with"]
    assert len(comparison_edges) >= 1, (
        f"Expected >= 1 comparison edges, got {len(comparison_edges)}. "
        f"Bug fix for _match_concept_edge may not be working."
    )
    print("[DEP MAPPER] PASSED\n")


def test_dependency_mapper_empty_text():
    """Mapper should handle empty text without crashing."""
    from engine.dependency_mapper import DependencyMapper

    dm = DependencyMapper()
    result = dm.map("", [], None)

    assert result["edges"] == []
    assert result["cross_references"] == []
    assert result["concept_clusters"] == []
    print("[DEP MAPPER EMPTY] PASSED\n")


def test_dependency_mapper_vs_pattern():
    """'X vs Y' pattern should still produce edges (this was already working)."""
    from engine.dependency_mapper import DependencyMapper

    dm = DependencyMapper()
    concepts = [
        {"name": "OLTP", "importance": "high"},
        {"name": "OLAP", "importance": "high"},
    ]

    text = "OLTP vs OLAP: two different workload patterns."
    result = dm.map(text, concepts)

    vs_edges = [e for e in result["edges"] if e["type"] == "compared_with"]
    print(f"[VS PATTERN] Edges: {len(vs_edges)}")
    for e in vs_edges:
        print(f"  {e['from']} --[{e['type']}]--> {e['to']}")

    assert len(vs_edges) >= 1, f"Expected >= 1 comparison edge from 'vs' pattern"
    print("[VS PATTERN] PASSED\n")


def test_analysis_caching():
    """Storage analysis cache should save/load correctly."""
    import json
    import tempfile
    import shutil
    from warehouse.storage import Storage
    from warehouse.models import Book

    # Use temp dir for test
    tmp_dir = tempfile.mkdtemp(prefix="test_storage_")
    try:
        storage = Storage(data_dir=tmp_dir)

        # Create parent book first (FK constraint)
        book = Book(id="book123", title="Test Book", filename="test.pdf")
        storage.save_book(book)

        test_analysis = {
            "structure": {"heading_count": 5, "max_depth": 3},
            "concepts": [{"name": "Test Concept", "importance": "high"}],
            "formulas": [],
            "dependencies": {"edges": []},
            "density": {"overall": {"primary_type": "concept-dense"}},
        }

        # Save
        storage.save_analysis("book123", "ch456", test_analysis)

        # Load
        loaded = storage.get_cached_analysis("book123", "ch456")
        assert loaded is not None, "Cached analysis should exist"
        assert loaded["structure"]["heading_count"] == 5
        assert loaded["concepts"][0]["name"] == "Test Concept"

        # Non-existent should return None
        missing = storage.get_cached_analysis("book123", "nonexistent")
        assert missing is None, "Non-existent analysis should return None"

        print("[ANALYSIS CACHE] PASSED\n")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ingester_helper_methods_exist():
    """Verify the refactored helper methods exist on Ingester."""
    from warehouse.ingester import Ingester

    assert hasattr(Ingester, "_extract_markdown"), "Missing _extract_markdown"
    assert hasattr(Ingester, "_analyze_and_save_chapters"), "Missing _analyze_and_save_chapters"
    assert hasattr(Ingester, "_build_knowledge_map"), "Missing _build_knowledge_map"

    print("[INGESTER HELPERS] PASSED\n")


def test_chapter_analysis_error_recovery():
    """Per-chapter analysis should not crash even if one chapter fails."""
    import tempfile
    import shutil
    from warehouse.storage import Storage
    from warehouse.ingester import Ingester
    from warehouse.models import Book, Chapter, _generate_id

    tmp_dir = tempfile.mkdtemp(prefix="test_ingester_")
    try:
        storage = Storage(data_dir=tmp_dir)
        ingester = Ingester(raw_dir=os.path.join(tmp_dir, "raw"), storage=storage)

        # Create parent book first (FK constraint)
        book = Book(id="testbook", title="Test Book", filename="test.pdf")
        storage.save_book(book)

        # Create test chapters — one normal, one that might cause issues
        chapters = [
            Chapter(
                id=_generate_id("test:ch1"),
                book_id="testbook",
                number=1,
                title="Normal Chapter",
                full_text="This is a **normal chapter** about **Data Structures**. "
                          "Data Structures are defined as organized collections of data.",
            ),
            Chapter(
                id=_generate_id("test:ch2"),
                book_id="testbook",
                number=2,
                title="Another Chapter",
                full_text="More content about **algorithms** and their applications.",
            ),
        ]

        # This should not crash  
        ingester._analyze_and_save_chapters(chapters)

        # Verify chapters were saved
        for ch in chapters:
            saved = storage.get_chapter("testbook", ch.id)
            assert saved is not None, f"Chapter {ch.number} should be saved"
            print(f"  Ch {ch.number}: concepts={len(saved.get('concepts', []))}, "
                  f"formulas={len(saved.get('formulas', []))}")

        print("[ERROR RECOVERY] PASSED\n")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ─── Run all tests ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1 — Test Suite")
    print("=" * 60 + "\n")

    test_dependency_mapper_comparison_edges()
    test_dependency_mapper_empty_text()
    test_dependency_mapper_vs_pattern()
    test_analysis_caching()
    test_ingester_helper_methods_exist()
    test_chapter_analysis_error_recovery()

    print("=" * 60)
    print("ALL PHASE 1 TESTS PASSED")
    print("=" * 60)
