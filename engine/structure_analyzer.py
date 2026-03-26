"""
structure_analyzer.py — Parse heading hierarchy from chapter markdown.

Deterministic: uses regex to find markdown headings and build a tree.
No AI involved.

Output:
    {
        "sections": [
            {
                "level": 2,
                "title": "Hash Indexes",
                "start": 450,
                "end": 1200,
                "text": "...",
                "children": [...]
            }
        ],
        "heading_count": 12,
        "max_depth": 3,
        "flat_headings": ["Hash Indexes", "SSTables", ...]
    }
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Section:
    """A section in the heading tree."""
    level: int
    title: str
    start: int          # char offset
    end: int = 0
    text: str = ""      # full text of this section (between this heading and the next)
    children: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "word_count": len(self.text.split()),
            "children": [c.to_dict() for c in self.children],
        }


class StructureAnalyzer:
    """Parse markdown headings into a structured tree."""

    # Match markdown headings: ## Title or ## 3.1 Title
    HEADING_RE = re.compile(
        r'^(#{1,6})\s+(.+)$',
        re.MULTILINE
    )

    def analyze(self, text: str) -> dict:
        """
        Parse the heading structure of a chapter.

        Returns:
            dict with "sections" (tree), "heading_count", "max_depth",
            and "flat_headings" (ordered list of all heading titles).
        """
        matches = list(self.HEADING_RE.finditer(text))

        if not matches:
            # No headings found — treat entire text as one section
            return {
                "sections": [{
                    "level": 1,
                    "title": "(No headings detected)",
                    "start": 0,
                    "end": len(text),
                    "word_count": len(text.split()),
                    "children": [],
                }],
                "heading_count": 0,
                "max_depth": 1,
                "flat_headings": [],
            }

        # Build flat list of sections with text ranges
        raw_sections: list[Section] = []
        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()

            raw_sections.append(Section(
                level=level,
                title=title,
                start=start,
                end=end,
                text=section_text,
            ))

        # Build tree from flat list
        tree = self._build_tree(raw_sections)

        # Collect flat heading list
        flat_headings = [s.title for s in raw_sections]
        max_depth = max(s.level for s in raw_sections) if raw_sections else 1

        return {
            "sections": [s.to_dict() for s in tree],
            "heading_count": len(raw_sections),
            "max_depth": max_depth,
            "flat_headings": flat_headings,
        }

    def _build_tree(self, sections: list[Section]) -> list[Section]:
        """
        Convert a flat list of sections into a nested tree
        based on heading levels.
        """
        if not sections:
            return []

        root: list[Section] = []
        stack: list[Section] = []

        for section in sections:
            # Pop stack until we find a parent with a lower level
            while stack and stack[-1].level >= section.level:
                stack.pop()

            if stack:
                # This section is a child of the top of the stack
                stack[-1].children.append(section)
            else:
                # This is a top-level section
                root.append(section)

            stack.append(section)

        return root
