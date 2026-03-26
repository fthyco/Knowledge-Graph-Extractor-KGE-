"""
concept_extractor.py — Extract key concepts, definitions, and terms.

Deterministic extraction using pattern matching:
1. Bold/italic terms: **write-ahead log**, *compaction*
2. Definition patterns: "X is defined as Y", "X refers to Y"
3. Technical terms: capitalized multi-word phrases, acronyms
4. Heading terms: words from section headings
5. Parenthetical definitions: "append-only (never modified)"
6. Enumerated definitions: "1. Term — definition"

No AI involved — pure regex + heuristics.
"""

from __future__ import annotations

import re
from collections import Counter


class ConceptExtractor:
    """Extract key concepts and definitions from chapter text."""

    # ── Patterns ─────────────────────────────────────────────

    # **bold text** or __bold text__
    BOLD_RE = re.compile(r'\*\*(.+?)\*\*|__(.+?)__')

    # *italic text* or _italic text_ (single)
    ITALIC_RE = re.compile(r'(?<!\*)\*([^*]+?)\*(?!\*)|(?<!_)_([^_]+?)_(?!_)')

    # "X is defined as Y" / "X is Y" / "X refers to Y" / "X means Y"
    DEFINITION_RE = re.compile(
        r'(?:^|\.\s+)'                          # sentence start
        r'(?:An?\s+)?'                           # optional article
        r'["\u201c]?([A-Z][^.!?]{2,60}?)["\u201d]?'  # term (capitalized)
        r'\s+(?:is\s+(?:defined\s+as|a|an|the)|'
        r'refers?\s+to|means?|represents?)'       # definition verb
        r'\s+([^.!?]{10,200})'                   # definition text
        r'[.!?]',
        re.MULTILINE
    )

    # Parenthetical definitions: "term (explanation)"
    PARENTHETICAL_RE = re.compile(
        r'(\b[A-Z][a-z]+(?:\s+[A-Za-z]+){0,3})\s+'
        r'\(([^)]{10,150})\)'
    )

    # Acronyms: "ETL", "OLAP", "LSM", "SSTable"
    ACRONYM_RE = re.compile(
        r'\b([A-Z]{2,6})\b'
    )

    # Acronym with expansion: "ETL (Extract, Transform, Load)"
    ACRONYM_EXPANSION_RE = re.compile(
        r'\b([A-Z]{2,6})\s+\(([A-Z][^)]{5,80})\)'
    )

    # Technical compound terms: "write-ahead log", "log-structured"
    HYPHENATED_RE = re.compile(
        r'\b([a-z]+-[a-z]+(?:-[a-z]+)?)\b'
    )

    # Numbered/bulleted definition lists: "- **Term**: definition" or "1. **Term** — def"
    LIST_DEFINITION_RE = re.compile(
        r'(?:^[-*•]\s+|\d+\.\s+)'               # list marker
        r'(?:\*\*(.+?)\*\*|__(.+?)__)'           # bold term
        r'\s*[:\u2014\u2013\-]+\s*'              # separator
        r'(.+?)$',                                # definition
        re.MULTILINE
    )

    # Common noise words to filter out
    NOISE_WORDS = {
        "the", "and", "for", "that", "this", "with", "from", "are",
        "was", "were", "been", "have", "has", "had", "will", "would",
        "could", "should", "may", "might", "can", "not", "but", "also",
        "which", "when", "where", "who", "what", "how", "why", "all",
        "each", "every", "some", "any", "most", "more", "less", "very",
        "just", "only", "then", "than", "into", "over", "such", "other",
        "figure", "table", "chapter", "section", "page", "example",
        "note", "see", "also", "however", "therefore", "thus", "hence",
    }

    def extract(self, text: str, structure: dict | None = None) -> list[dict]:
        """
        Extract key concepts from chapter text.

        Returns a list of concept dicts:
            {
                "name": "Write-Ahead Log",
                "definition": "A log where all modifications are written before...",
                "source": "bold",  # how it was detected
                "importance": "high",  # high/medium/low
                "mentions": 5,  # how many times it appears
            }
        """
        concepts: dict[str, dict] = {}

        # 1. Extract from bold text (highest signal)
        self._extract_bold(text, concepts)

        # 2. Extract from definition patterns
        self._extract_definitions(text, concepts)

        # 3. Extract from parenthetical definitions
        self._extract_parentheticals(text, concepts)

        # 4. Extract acronyms with expansions
        self._extract_acronyms(text, concepts)

        # 5. Extract from list-style definitions
        self._extract_list_definitions(text, concepts)

        # 6. Extract from headings (if structure provided)
        if structure:
            self._extract_from_headings(structure, concepts)

        # 7. Extract hyphenated technical terms
        self._extract_hyphenated(text, concepts)

        # 8. Count mentions for importance ranking
        self._count_mentions(text, concepts)

        # 9. Rank importance
        self._rank_importance(concepts)

        # Sort by importance then mentions
        importance_order = {"high": 0, "medium": 1, "low": 2}
        result = sorted(
            concepts.values(),
            key=lambda c: (importance_order.get(c["importance"], 2), -c.get("mentions", 0))
        )

        return result

    def _normalize_name(self, name: str) -> str:
        """Normalize a concept name for deduplication."""
        return name.strip().lower()

    def _is_noise(self, name: str) -> bool:
        """Check if a term is noise (too common or too short)."""
        normalized = self._normalize_name(name)
        if len(normalized) < 3:
            return True
        if normalized in self.NOISE_WORDS:
            return True
        # Filter out pure numbers or single common words
        if re.match(r'^\d+$', normalized):
            return True
        return False

    def _add_concept(self, concepts: dict, name: str, definition: str = "",
                     source: str = "unknown"):
        """Add or update a concept in the collection."""
        name = name.strip()
        if self._is_noise(name):
            return

        key = self._normalize_name(name)
        if key in concepts:
            # Update with better definition if available
            if definition and not concepts[key].get("definition"):
                concepts[key]["definition"] = definition.strip()
            concepts[key]["sources"].add(source)
        else:
            concepts[key] = {
                "name": name,
                "definition": definition.strip() if definition else "",
                "sources": {source},
                "importance": "medium",
                "mentions": 0,
            }

    def _extract_bold(self, text: str, concepts: dict):
        """Extract concepts from bold text."""
        for match in self.BOLD_RE.finditer(text):
            term = match.group(1) or match.group(2)
            if term and not self._is_noise(term) and len(term) < 60:
                # Try to find definition nearby (next sentence)
                end_pos = match.end()
                nearby = text[end_pos:end_pos + 300]
                definition = ""

                # Look for ": definition" or "— definition" right after
                def_match = re.match(r'\s*[:\u2014\u2013\-]+\s*(.+?)(?:\.|$)', nearby)
                if def_match:
                    definition = def_match.group(1)

                self._add_concept(concepts, term, definition, "bold")

    def _extract_definitions(self, text: str, concepts: dict):
        """Extract from 'X is defined as Y' patterns."""
        for match in self.DEFINITION_RE.finditer(text):
            term = match.group(1).strip()
            definition = match.group(2).strip()
            if not self._is_noise(term):
                self._add_concept(concepts, term, definition, "definition")

    def _extract_parentheticals(self, text: str, concepts: dict):
        """Extract from 'Term (explanation)' patterns."""
        for match in self.PARENTHETICAL_RE.finditer(text):
            term = match.group(1).strip()
            explanation = match.group(2).strip()
            if not self._is_noise(term) and not explanation[0].isdigit():
                self._add_concept(concepts, term, explanation, "parenthetical")

    def _extract_acronyms(self, text: str, concepts: dict):
        """Extract acronyms and their expansions."""
        # First, get expanded acronyms
        for match in self.ACRONYM_EXPANSION_RE.finditer(text):
            acronym = match.group(1)
            expansion = match.group(2)
            self._add_concept(concepts, acronym, expansion, "acronym")

        # Then standalone acronyms (only if they appear 2+ times)
        acronym_counts = Counter(m.group(1) for m in self.ACRONYM_RE.finditer(text))
        for acronym, count in acronym_counts.items():
            if count >= 2 and acronym not in {"IT", "OR", "IF", "IS", "AS", "IN", "ON", "TO"}:
                key = self._normalize_name(acronym)
                if key not in concepts:
                    self._add_concept(concepts, acronym, "", "acronym")

    def _extract_list_definitions(self, text: str, concepts: dict):
        """Extract from list-style definitions."""
        for match in self.LIST_DEFINITION_RE.finditer(text):
            term = (match.group(1) or match.group(2)).strip()
            definition = match.group(3).strip()
            if not self._is_noise(term):
                self._add_concept(concepts, term, definition, "list_definition")

    def _extract_from_headings(self, structure: dict, concepts: dict):
        """Extract concepts from section headings."""
        for heading in structure.get("flat_headings", []):
            # Clean heading: remove numbering like "3.1" or "Chapter 5:"
            cleaned = re.sub(r'^[\d.]+\s*', '', heading)
            cleaned = re.sub(r'^(?:Chapter|Part|Section)\s+\d+\s*[:.\-]*\s*', '', cleaned, flags=re.I)
            cleaned = cleaned.strip()

            if cleaned and not self._is_noise(cleaned):
                self._add_concept(concepts, cleaned, "", "heading")

    def _extract_hyphenated(self, text: str, concepts: dict):
        """Extract hyphenated technical terms."""
        term_counts = Counter(m.group(1) for m in self.HYPHENATED_RE.finditer(text))
        for term, count in term_counts.items():
            if count >= 2 and not self._is_noise(term):
                self._add_concept(concepts, term, "", "hyphenated")

    def _count_mentions(self, text: str, concepts: dict):
        """Count how many times each concept appears in the text."""
        text_lower = text.lower()
        for key, concept in concepts.items():
            name_lower = concept["name"].lower()
            concept["mentions"] = text_lower.count(name_lower)

    def _rank_importance(self, concepts: dict):
        """
        Rank concept importance based on signals:
        - Multiple sources → higher importance
        - Definition available → higher importance
        - Many mentions → higher importance
        - From heading → higher importance
        """
        for key, concept in concepts.items():
            score = 0

            # Source signals
            sources = concept.get("sources", set())
            if "heading" in sources:
                score += 3
            if "bold" in sources:
                score += 2
            if "definition" in sources or "list_definition" in sources:
                score += 2
            if "acronym" in sources:
                score += 1

            # Definition available
            if concept.get("definition"):
                score += 1

            # Mention frequency
            mentions = concept.get("mentions", 0)
            if mentions >= 10:
                score += 2
            elif mentions >= 5:
                score += 1

            # Multiple sources = strong signal
            if len(sources) >= 3:
                score += 2
            elif len(sources) >= 2:
                score += 1

            # Classify
            if score >= 5:
                concept["importance"] = "high"
            elif score >= 3:
                concept["importance"] = "medium"
            else:
                concept["importance"] = "low"

            # Convert sources set to list for JSON serialization
            concept["sources"] = list(sources)
