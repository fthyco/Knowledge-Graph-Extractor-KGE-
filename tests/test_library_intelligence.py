import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.library_intelligence import IntelligenceEngine, BookMatch, KnowledgeMap

class TestLibraryIntelligence(unittest.TestCase):
    def setUp(self):
        self.engine = IntelligenceEngine(name_weight=0.3, structure_weight=0.3, concept_weight=0.4)
        
        # Mock Book 1 (Input Book - e.g. a new Linear Algebra textbook)
        self.input_book = {
            "id": "book_1",
            "title": "Introduction to Linear Algebra"
        }
        self.input_chapters = [
            {"number": 1, "title": "Vectors and Matrices", "concepts": [{"name": "Vector"}, {"name": "Matrix"}, {"name": "Dot Product"}]},
            {"number": 2, "title": "Solving Linear Equations", "concepts": [{"name": "Gaussian Elimination"}, {"name": "Pivot"}]}
        ]
        
        # Mock Book 2 (Warehouse Book - Very Similar)
        self.warehouse_book_1 = {
            "id": "book_2",
            "title": "Linear Algebra Basics"
        }
        self.warehouse_chapters_1 = [
            {"number": 1, "title": "Vectors and Matrices", "concepts": [{"name": "Vector"}, {"name": "Matrix"}, {"name": "Cross Product"}]},
            {"number": 2, "title": "Systems of Linear Equations", "concepts": [{"name": "Gaussian Elimination"}, {"name": "Matrix Inverse"}]}
        ]
        
        # Mock Book 3 (Warehouse Book - Unrelated)
        self.warehouse_book_2 = {
            "id": "book_3",
            "title": "History of the Roman Empire"
        }
        self.warehouse_chapters_2 = [
            {"number": 1, "title": "The Republic", "concepts": [{"name": "Senate"}, {"name": "Consul"}]},
            {"number": 2, "title": "The Empire", "concepts": [{"name": "Emperor"}, {"name": "Legion"}]}
        ]
        
        self.warehouse_books = [self.warehouse_book_1, self.warehouse_book_2]
        self.warehouse_chapters_map = {
            "book_2": self.warehouse_chapters_1,
            "book_3": self.warehouse_chapters_2
        }

    def test_match_knowledge(self):
        result = self.engine.match_knowledge(
            input_book=self.input_book,
            input_chapters=self.input_chapters,
            warehouse_books=self.warehouse_books,
            warehouse_chapters_map=self.warehouse_chapters_map
        )
        
        self.assertIsInstance(result, KnowledgeMap)
        self.assertEqual(result.input_book_id, "book_1")
        self.assertEqual(len(result.matches), 2)
        
        # The expected matches should be sorted by total_score descending
        top_match = result.matches[0]
        bottom_match = result.matches[1]
        
        # The first match should be the Linear Algebra book, not the Roman Empire book
        self.assertEqual(top_match.warehouse_book_id, "book_2")
        self.assertEqual(bottom_match.warehouse_book_id, "book_3")
        
        # Linear Algebra Basics should score relatively high (e.g. title overlap, exact chapter 1 match)
        self.assertGreater(top_match.name_score, 0.4)
        self.assertGreater(top_match.structure_score, 0.4)
        self.assertGreater(top_match.concept_score, 0.4)
        self.assertGreater(top_match.total_score, 0.4)
        
        # History of the Roman Empire should score low since there are no meaningful overlaps
        # Note: character-level comparison gives ~0.28 due to common English letters
        self.assertLess(bottom_match.name_score, 0.35)
        self.assertLess(bottom_match.concept_score, 0.01)
        self.assertLess(bottom_match.total_score, 0.15)

if __name__ == '__main__':
    unittest.main()
