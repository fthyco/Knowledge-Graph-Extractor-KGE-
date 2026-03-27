"""
dependency_mapper.py — Build a concept relationship graph.

Deterministic: scans text for cross-references, comparisons,
prerequisite mentions, and co-occurrences.

Relationship types:
    - "depends_on": concept requires understanding of another
    - "compared_with": two concepts are explicitly compared
    - "part_of": concept is a component of another
    - "related_to": general relationship
    - "see_also": cross-reference to another section/chapter
    - "example_of": concept is an instance of a category

No AI involved — pure text pattern matching.
"""

from __future__ import annotations

import re
from collections import defaultdict


class DependencyMapper:
    """Build concept dependency and relationship graphs."""

    # ── Cross-reference patterns ─────────────────────────────

    # "See Chapter/Section X"
    CROSS_REF_RE = re.compile(
        r'(?:see|refer\s+to|as\s+(?:discussed|described|shown)\s+in)\s+'
        r'(?:Chapter|Section|Part|Figure|Table)\s+'
        r'([\d.]+(?:\s*[-–]\s*[\d.]+)?)',
        re.IGNORECASE
    )

    # "as we saw earlier", "mentioned above"
    BACK_REF_RE = re.compile(
        r'(?:as\s+we\s+(?:saw|discussed|mentioned|noted)|'
        r'mentioned\s+(?:earlier|above|previously)|'
        r'as\s+(?:before|earlier|previously))',
        re.IGNORECASE
    )

    # ── Comparison patterns ──────────────────────────────────

    # "unlike X, Y...", "compared to X", "X vs Y", "in contrast to X"
    COMPARISON_RE = re.compile(
        r'(?:'
        r'(?:unlike|compared\s+(?:to|with)|'
        r'in\s+contrast\s+(?:to|with)|'
        r'(?:similar|equivalent|analogous)\s+to|'
        r'differs?\s+from|'
        r'as\s+opposed\s+to)\s+'
        r'(?:\*\*)?([^,.*]+?)(?:\*\*)?\s*[,.]'
        r'|'
        r'(\S+)\s+(?:vs\.?|versus)\s+(\S+)'
        r')',
        re.IGNORECASE
    )

    # ── Containment patterns ─────────────────────────────────

    # "X includes Y", "X consists of Y", "types of X: Y, Z"
    CONTAINMENT_RE = re.compile(
        r'(?:\*\*)?([^.!?*]{3,40}?)(?:\*\*)?\s+'
        r'(?:includes?|consists?\s+of|comprises?|contains?|'
        r'is\s+(?:composed|made\s+up)\s+of)\s+'
        r'([^.!?]{5,150})',
        re.IGNORECASE
    )

    # "types of X", "kinds of X", "forms of X"
    TYPES_RE = re.compile(
        r'(?:types?|kinds?|forms?|varieties?|categories?)\s+of\s+'
        r'(?:\*\*)?([^.!?*:]{3,40}?)(?:\*\*)?\s*'
        r'(?::|include|are)\s*'
        r'([^.!?]{5,200})',
        re.IGNORECASE
    )

    # ── Example patterns ─────────────────────────────────────

    # "for example, X", "such as X", "e.g., X"
    EXAMPLE_RE = re.compile(
        r'(?:\*\*)?([^.!?*]{3,40}?)(?:\*\*)?\s*'
        r'(?:,?\s*(?:for\s+example|such\s+as|e\.g\.,?|for\s+instance)\s*,?\s*)'
        r'([^.!?]{5,150})',
        re.IGNORECASE
    )

    def map(self, text: str, concepts: list[dict],
            structure: dict | None = None) -> dict:
        """
        Build a dependency/relationship map.

        Args:
            text: Full chapter markdown.
            concepts: Extracted concepts from ConceptExtractor.
            structure: Structure analysis from StructureAnalyzer.

        Returns:
            {
                "edges": [
                    {"from": "A", "to": "B", "type": "compared_with"},
                    ...
                ],
                "cross_references": [
                    {"text": "See Chapter 5", "target": "5"},
                    ...
                ],
                "concept_clusters": [
                    ["LSM-Tree", "SSTable", "Compaction"],
                    ...
                ]
            }
        """
        edges = []
        cross_refs = []

        # Build concept name lookup for matching
        concept_names = [c["name"] for c in concepts]
        concept_names_lower = {n.lower(): n for n in concept_names}

        # 1. Cross-references to other chapters/sections
        for match in self.CROSS_REF_RE.finditer(text):
            cross_refs.append({
                "text": match.group(0),
                "target": match.group(1),
            })

        # 2. Back-references
        for match in self.BACK_REF_RE.finditer(text):
            cross_refs.append({
                "text": match.group(0),
                "target": "earlier_content",
            })

        # 3. Comparisons
        for match in self.COMPARISON_RE.finditer(text):
            if match.group(1):
                term = match.group(1).strip()
                # Get surrounding sentence for context to find the other concept
                ctx_start = max(0, match.start() - 200)
                ctx_end = min(len(text), match.end() + 200)
                context = text[ctx_start:ctx_end]
                edges.extend(
                    self._match_concept_edge(term, context, concept_names_lower, "compared_with")
                )
            elif match.group(2) and match.group(3):
                term_a = match.group(2).strip()
                term_b = match.group(3).strip()
                matched_a = self._find_concept(term_a, concept_names_lower)
                matched_b = self._find_concept(term_b, concept_names_lower)
                if matched_a and matched_b:
                    edges.append({
                        "from": matched_a,
                        "to": matched_b,
                        "type": "compared_with",
                    })

        # 4. Containment
        for match in self.CONTAINMENT_RE.finditer(text):
            parent = match.group(1).strip()
            children_text = match.group(2).strip()
            matched_parent = self._find_concept(parent, concept_names_lower)
            if matched_parent:
                # Try to extract child concepts from the list
                children = self._extract_list_items(children_text)
                for child in children:
                    matched_child = self._find_concept(child, concept_names_lower)
                    if matched_child:
                        edges.append({
                            "from": matched_child,
                            "to": matched_parent,
                            "type": "part_of",
                        })

        # 5. Types/categories
        for match in self.TYPES_RE.finditer(text):
            category = match.group(1).strip()
            items_text = match.group(2).strip()
            matched_cat = self._find_concept(category, concept_names_lower)
            if matched_cat:
                items = self._extract_list_items(items_text)
                for item in items:
                    matched_item = self._find_concept(item, concept_names_lower)
                    if matched_item:
                        edges.append({
                            "from": matched_item,
                            "to": matched_cat,
                            "type": "example_of",
                        })

        # 6. Co-occurrence clusters (concepts in same paragraph)
        clusters = self._find_co_occurrence_clusters(text, concept_names)

        # 7. Heading-based dependencies (concepts under same heading)
        if structure:
            heading_deps = self._heading_dependencies(structure, concept_names_lower)
            edges.extend(heading_deps)

        # Deduplicate edges
        seen_edges = set()
        unique_edges = []
        for edge in edges:
            key = (edge["from"], edge["to"], edge["type"])
            reverse_key = (edge["to"], edge["from"], edge["type"])
            if key not in seen_edges and reverse_key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(edge)

        return {
            "edges": unique_edges,
            "cross_references": cross_refs,
            "concept_clusters": clusters,
        }

    def _find_concept(self, term: str, concept_lookup: dict) -> str | None:
        """Find a concept name that matches the given term."""
        term_lower = term.lower().strip()

        # Exact match
        if term_lower in concept_lookup:
            return concept_lookup[term_lower]

        # Partial match (term is part of a concept name or vice versa)
        for name_lower, name in concept_lookup.items():
            if term_lower in name_lower or name_lower in term_lower:
                return name

        return None

    def _match_concept_edge(self, term: str, context: str,
                            concept_lookup: dict,
                            edge_type: str) -> list[dict]:
        """
        Create edges between a term and other known concepts
        found nearby in the surrounding context text.
        """
        matched = self._find_concept(term, concept_lookup)
        if not matched:
            return []

        # Find other known concepts mentioned in the surrounding context
        edges = []
        context_lower = context.lower()
        for name_lower, name in concept_lookup.items():
            if name_lower == matched.lower():
                continue  # skip self
            if name_lower in context_lower:
                edges.append({
                    "from": matched,
                    "to": name,
                    "type": edge_type,
                })
        return edges

    def _extract_list_items(self, text: str) -> list[str]:
        """Extract individual items from a comma/and separated list."""
        # Split by comma, semicolon, "and", "or"
        items = re.split(r',\s*|\s+and\s+|\s+or\s+|;\s*', text)
        return [item.strip().strip('*').strip() for item in items if item.strip()]

    def _find_co_occurrence_clusters(self, text: str,
                                     concept_names: list[str]) -> list[list[str]]:
        """
        Find clusters of concepts that appear together frequently.
        Split text into paragraphs and find concepts that co-occur.

        Optimized: pre-builds a word-set for each paragraph and uses
        set operations for fast concept lookup instead of O(n) substring
        scanning per concept per paragraph.
        """
        if not concept_names:
            return []

        paragraphs = re.split(r'\n\s*\n', text)
        co_occurrence = defaultdict(set)

        # Pre-compute: for multi-word concepts, we need substring matching.
        # For single-word concepts, we can use set membership (much faster).
        single_word = {}   # lower_name -> original_name
        multi_word = {}    # lower_name -> original_name
        for name in concept_names:
            lower = name.lower()
            if ' ' in lower or '-' in lower:
                multi_word[lower] = name
            else:
                single_word[lower] = name

        for para in paragraphs:
            if len(para.split()) < 5:
                continue  # skip tiny paragraphs

            para_lower = para.lower()

            # Fast path: single-word concepts via set intersection
            para_words = set(re.findall(r'\b\w+\b', para_lower))
            present = [single_word[w] for w in para_words & single_word.keys()]

            # Slower path: multi-word concepts via substring check
            for lower, name in multi_word.items():
                if lower in para_lower:
                    present.append(name)

            # Record co-occurrences (skip if < 2 concepts)
            if len(present) < 2:
                continue
            for i, a in enumerate(present):
                for b in present[i + 1:]:
                    co_occurrence[a].add(b)
                    co_occurrence[b].add(a)

        # Build clusters using simple connected components
        visited = set()
        clusters = []

        for concept in concept_names:
            if concept in visited or concept not in co_occurrence:
                continue
            cluster = set()
            stack = [concept]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                cluster.add(current)
                for neighbor in co_occurrence.get(current, set()):
                    if neighbor not in visited:
                        stack.append(neighbor)

            if len(cluster) >= 2:
                clusters.append(sorted(cluster))

        # Sort clusters by size (largest first), cap at 10
        clusters.sort(key=len, reverse=True)
        return clusters[:10]

    def _heading_dependencies(self, structure: dict,
                              concept_lookup: dict) -> list[dict]:
        """
        Infer dependencies from heading structure.
        Concepts under a parent heading depend on concepts
        introduced in earlier sibling sections.
        """
        edges = []
        sections = structure.get("sections", [])

        for section in sections:
            children = section.get("children", [])
            for i in range(1, len(children)):
                current_title = children[i].get("title", "")
                prev_title = children[i - 1].get("title", "")

                current_concept = self._find_concept(current_title, concept_lookup)
                prev_concept = self._find_concept(prev_title, concept_lookup)

                if current_concept and prev_concept:
                    edges.append({
                        "from": current_concept,
                        "to": prev_concept,
                        "type": "depends_on",
                    })

        return edges
