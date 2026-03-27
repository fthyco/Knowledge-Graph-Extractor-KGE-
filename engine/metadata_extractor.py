"""
metadata_extractor.py — Auto-extract book metadata from PDF properties + content.

Extracts:
- Author name (from PDF metadata, or first-page patterns)
- Subject/field (from title heuristics, content analysis)
- Edition/year (from title or copyright page)
- Language (from character distribution)

No AI involved — pure heuristics + PDF metadata.
"""

from __future__ import annotations

import re
from collections import Counter


class MetadataExtractor:
    """Extract book metadata from PDF info dict and first-page text."""

    # Common academic/field keywords for subject detection
    SUBJECT_KEYWORDS = {
        "mathematics": ["theorem", "proof", "lemma", "algebra", "calculus",
                        "topology", "geometry", "equation", "matrix", "integral",
                        "manifold", "eigenvalue"],
        "computer science": ["algorithm", "data structure", "complexity",
                             "programming", "software", "database", "compiler",
                             "operating system", "machine learning",
                             "distributed system", "concurrency", "hash table",
                             "binary tree", "linked list", "API"],
        "physics": ["mechanics", "quantum", "thermodynamics", "electromagnetism",
                    "relativity", "particle physics", "wave function",
                    "kinetic energy", "potential energy", "newton"],
        "statistics": ["probability", "distribution", "hypothesis",
                       "regression", "variance", "bayesian", "sampling",
                       "confidence interval", "p-value", "random variable"],
        "engineering": ["circuit design", "signal processing", "control theory",
                        "structural analysis", "fluid dynamics", "mechanical engineering",
                        "electrical engineering", "civil engineering"],
        "biology": ["cell", "protein", "gene", "organism", "evolution",
                    "ecology", "molecular", "dna", "rna", "metabolism"],
        "chemistry": ["reaction", "compound", "molecule", "organic chemistry",
                      "inorganic", "periodic table", "chemical bond",
                      "solution", "acid"],
        "economics": ["market", "supply and demand", "equilibrium",
                      "fiscal", "monetary", "inflation", "gdp", "utility",
                      "microeconomics", "macroeconomics"],
    }

    # Edition patterns
    EDITION_RE = re.compile(
        r'(\d+)(?:st|nd|rd|th)\s+edition',
        re.IGNORECASE,
    )

    # Year patterns (reasonable range for textbooks)
    YEAR_RE = re.compile(r'\b(19[5-9]\d|20[0-3]\d)\b')

    # Author patterns in first-page text
    AUTHOR_PATTERNS = [
        # "by Author Name"
        re.compile(r'\bby\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+){1,3})', re.MULTILINE),
        # "Author Name\n" at top (standalone name line)
        re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+){1,2})\s*$', re.MULTILINE),
    ]

    # Copyright line
    COPYRIGHT_RE = re.compile(
        r'[©Ⓒ]\s*(?:Copyright\s+)?(\d{4})\s+(?:by\s+)?([^.\n]{5,60})',
        re.IGNORECASE,
    )

    def extract(
        self,
        pdf_info: dict | None = None,
        first_pages_text: str = "",
        full_text: str = "",
        title: str = "",
    ) -> dict:
        """
        Extract metadata from available sources.

        Args:
            pdf_info: PDF metadata dict (from pypdf.PdfReader.metadata)
            first_pages_text: Text of the first 2-3 pages (title page, copyright)
            full_text: Full book markdown (for subject detection)
            title: Book title (for subject heuristics)

        Returns:
            {
                "author": "Martin Kleppmann",
                "subject": "computer science",
                "edition": "2nd",
                "year": "2017",
                "language": "en",
            }
        """
        result = {
            "author": "",
            "subject": "",
            "edition": "",
            "year": "",
            "language": "en",
        }

        # 1. Try PDF metadata first (most reliable)
        if pdf_info:
            result["author"] = self._clean_pdf_string(pdf_info.get("/Author", ""))
            subject = self._clean_pdf_string(pdf_info.get("/Subject", ""))
            if subject:
                result["subject"] = subject

        # 2. Extract from first pages text
        if first_pages_text:
            if not result["author"]:
                result["author"] = self._extract_author(first_pages_text)

            # Edition
            edition_match = self.EDITION_RE.search(first_pages_text)
            if edition_match:
                n = edition_match.group(1)
                suffixes = {"1": "st", "2": "nd", "3": "rd"}
                suffix = suffixes.get(n, "th")
                result["edition"] = f"{n}{suffix}"

            # Year from copyright
            copyright_match = self.COPYRIGHT_RE.search(first_pages_text)
            if copyright_match:
                result["year"] = copyright_match.group(1)
                if not result["author"]:
                    result["author"] = copyright_match.group(2).strip()
            elif not result["year"]:
                # Try year from any context
                years = self.YEAR_RE.findall(first_pages_text[:2000])
                if years:
                    result["year"] = max(years)  # Most recent year

        # 3. Detect subject from content
        if not result["subject"]:
            result["subject"] = self._detect_subject(title, full_text)

        # 4. Detect language
        if full_text:
            result["language"] = self._detect_language(full_text[:5000])

        # Clean up
        result["author"] = result["author"].strip()
        result["subject"] = result["subject"].strip()

        return result

    def _clean_pdf_string(self, value) -> str:
        """Clean a PDF metadata string (may be bytes or weird encoding)."""
        if not value:
            return ""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8").strip()
            except UnicodeDecodeError:
                return value.decode("latin-1", errors="ignore").strip()
        return str(value).strip()

    def _extract_author(self, text: str) -> str:
        """Try to find author name in first-page text."""
        for pattern in self.AUTHOR_PATTERNS:
            match = pattern.search(text[:1000])
            if match:
                name = match.group(1).strip()
                # Filter out common false positives
                if name.lower() not in {"the", "this", "chapter", "part",
                                        "section", "table", "figure",
                                        "new york", "press", "university"}:
                    return name
        return ""

    def _detect_subject(self, title: str, text: str) -> str:
        """Detect the book's subject/field from title and content keywords."""
        # Combine title (weighted higher) and first 10k chars of text
        search_text = (title.lower() + " ") * 5 + (text[:10000].lower() if text else "")

        scores: dict[str, int] = {}
        for subject, keywords in self.SUBJECT_KEYWORDS.items():
            score = sum(search_text.count(kw) for kw in keywords)
            if score > 0:
                scores[subject] = score

        if scores:
            return max(scores, key=scores.get)
        return ""

    def _detect_language(self, text: str) -> str:
        """Simple language detection from character distribution."""
        if not text:
            return "en"

        # Remove math, code blocks, and markdown formatting
        clean = re.sub(r'\$\$.*?\$\$|\$.*?\$|```.*?```', '', text, flags=re.DOTALL)
        clean = re.sub(r'[#*_\[\](){}|>]', '', clean)

        # Count character ranges
        arabic_count = len(re.findall(r'[\u0600-\u06FF]', clean))
        cjk_count = len(re.findall(r'[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]', clean))
        cyrillic_count = len(re.findall(r'[\u0400-\u04FF]', clean))
        latin_count = len(re.findall(r'[a-zA-Z]', clean))

        total = arabic_count + cjk_count + cyrillic_count + latin_count
        if total == 0:
            return "en"

        if arabic_count / total > 0.3:
            return "ar"
        if cjk_count / total > 0.3:
            return "zh"  # or ja/ko — simplified detection
        if cyrillic_count / total > 0.3:
            return "ru"

        return "en"
