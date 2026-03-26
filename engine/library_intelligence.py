"""
library_intelligence.py — Independent Knowledge Graph & Pattern Recognition Engine

Computes similarities between an input book and the existing warehouse library
using purely offline, deterministic algorithms (SequenceMatcher, TF-IDF Cosine Similarity).
"""

from __future__ import annotations

import difflib
import math
from collections import Counter
from dataclasses import dataclass
from typing import List, Dict

# Assuming models.py provides these or duck-typed versions
@dataclass
class BookMatch:
    warehouse_book_id: str
    name_score: float
    structure_score: float
    concept_score: float
    total_score: float


@dataclass
class KnowledgeMap:
    input_book_id: str
    matches: List[BookMatch]


class IntelligenceEngine:
    """
    Offline engine for matching a book against a library of books
    to recognize patterns and map knowledge dependencies.
    """

    def __init__(self, name_weight: float = 0.3, structure_weight: float = 0.3, concept_weight: float = 0.4):
        self.name_weight = name_weight
        self.structure_weight = structure_weight
        self.concept_weight = concept_weight

    def match_knowledge(
        self,
        input_book: dict,
        input_chapters: List[dict],
        warehouse_books: List[dict],
        warehouse_chapters_map: Dict[str, List[dict]]
    ) -> KnowledgeMap:
        """
        Match an input book against a warehouse of books.
        
        Args:
            input_book: Dict representation of the input Book.
            input_chapters: List of dict representations of the Input Chapters.
            warehouse_books: List of dict representations of warehouse Books.
            warehouse_chapters_map: Dict mapping warehouse Book ID -> List of Chapter dicts.
            
        Returns:
            KnowledgeMap sorted by descending total_score.
        """
        input_title = input_book.get("title", "")
        input_chapter_titles = self._extract_chapter_titles(input_chapters)
        input_concepts = self._extract_concepts(input_chapters)

        # Pre-compute target concepts for TF-IDF building (Document Corpus)
        # To compute IDF, we need all documents' concepts.
        all_book_concepts: Dict[str, List[str]] = {}
        for w_book in warehouse_books:
            w_id = w_book["id"]
            w_chapters = warehouse_chapters_map.get(w_id, [])
            all_book_concepts[w_id] = self._extract_concepts(w_chapters)

        corpus = list(all_book_concepts.values()) + [input_concepts]
        df_counts, num_docs = self._build_document_frequencies(corpus)

        matches = []
        for w_book in warehouse_books:
            if w_book["id"] == input_book.get("id"):
                continue  # Skip self-matching if input_book is already in warehouse list
                
            w_id = w_book["id"]
            w_title = w_book.get("title", "")
            w_chapters = warehouse_chapters_map.get(w_id, [])
            w_chapter_titles = self._extract_chapter_titles(w_chapters)
            w_concepts = all_book_concepts[w_id]

            # 1. Book Name Similarity (SequenceMatcher)
            name_score = self._compute_sequence_similarity([input_title.lower()], [w_title.lower()])

            # 2. Chapter Sequence Similarity (SequenceMatcher on ordered title list)
            structure_score = self._compute_sequence_similarity(
                [t.lower() for t in input_chapter_titles],
                [t.lower() for t in w_chapter_titles]
            )

            # 3. Concept Overlap (TF-IDF Cosine Similarity)
            concept_score = self._compute_tfidf_cosine_similarity(
                input_concepts, w_concepts, df_counts, num_docs
            )

            # 4. Total Weighted Score
            total_score = (
                self.name_weight * name_score +
                self.structure_weight * structure_score +
                self.concept_weight * concept_score
            )

            matches.append(BookMatch(
                warehouse_book_id=w_id,
                name_score=round(name_score, 4),
                structure_score=round(structure_score, 4),
                concept_score=round(concept_score, 4),
                total_score=round(total_score, 4)
            ))

        # Sort descending by total_score
        matches.sort(key=lambda m: m.total_score, reverse=True)

        return KnowledgeMap(
            input_book_id=input_book.get("id", "unknown"),
            matches=matches
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_chapter_titles(self, chapters: List[dict]) -> List[str]:
        # Ensure chapters are sorted by number to maintain sequence order
        sorted_chapters = sorted(chapters, key=lambda c: c.get("number", 0))
        return [c.get("title", "").strip() for c in sorted_chapters]

    def _extract_concepts(self, chapters: List[dict]) -> List[str]:
        """Extract all concept names lowered from all chapters."""
        concepts = []
        for ch in chapters:
            ch_concepts = ch.get("concepts", [])
            for c_dict in ch_concepts:
                name = c_dict.get("name", "")
                if name:
                    concepts.append(name.strip().lower())
        return concepts

    def _compute_sequence_similarity(self, seq_a: List[str], seq_b: List[str]) -> float:
        """Calculate SequenceMatcher ratio between two lists of strings."""
        if not seq_a and not seq_b:
            return 1.0
        if not seq_a or not seq_b:
            return 0.0
            
        matcher = difflib.SequenceMatcher(None, seq_a, seq_b)
        return matcher.ratio()

    def _build_document_frequencies(self, corpus: List[List[str]]) -> tuple[Dict[str, int], int]:
        df = Counter()
        for doc in corpus:
            unique_terms = set(doc)
            for term in unique_terms:
                df[term] += 1
        return df, len(corpus)

    def _get_tf(self, doc: List[str]) -> Dict[str, float]:
        tf = Counter(doc)
        total_terms = len(doc)
        if total_terms == 0:
            return {}
        return {term: count / total_terms for term, count in tf.items()}

    def _get_tfidf(self, tf_dict: Dict[str, float], df_counts: Dict[str, int], num_docs: int) -> Dict[str, float]:
        tfidf = {}
        for term, tf_val in tf_dict.items():
            # Scikit-learn smooth idf formula
            idf = math.log((1 + num_docs) / (1 + df_counts.get(term, 0))) + 1
            tfidf[term] = tf_val * idf
        return tfidf

    def _compute_tfidf_cosine_similarity(
        self,
        doc_a: List[str],
        doc_b: List[str],
        df_counts: Dict[str, int],
        num_docs: int
    ) -> float:
        """Compute cosine similarity between two documents using TF-IDF."""
        if not doc_a or not doc_b:
            return 0.0

        tf_a = self._get_tf(doc_a)
        tf_b = self._get_tf(doc_b)

        tfidf_a = self._get_tfidf(tf_a, df_counts, num_docs)
        tfidf_b = self._get_tfidf(tf_b, df_counts, num_docs)

        # Dot product
        intersection = set(tfidf_a.keys()) & set(tfidf_b.keys())
        dot_product = sum(tfidf_a[term] * tfidf_b[term] for term in intersection)

        # Magnitudes
        mag_a = math.sqrt(sum(val ** 2 for val in tfidf_a.values()))
        mag_b = math.sqrt(sum(val ** 2 for val in tfidf_b.values()))

        if mag_a == 0 or mag_b == 0:
            return 0.0

        return dot_product / (mag_a * mag_b)
