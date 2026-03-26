"""
prompt_assembler.py — Assemble the final optimal LLM prompt.

Takes the full deterministic analysis (structure, concepts, formulas,
dependencies, density) and builds a structured prompt that gives
any LLM everything it needs to produce excellent study material.

The prompt is the PRODUCT — it's designed so that even a weaker model
can produce great output because the hard analytical work is already done.

No AI involved — pure string construction.
"""

from __future__ import annotations

import textwrap
from datetime import datetime


# ══════════════════════════════════════════════════════════════
# Study mode templates
# ══════════════════════════════════════════════════════════════

STUDY_MODES = {
    "deep_dive": {
        "name": "Deep Dive",
        "instruction": textwrap.dedent("""\
            Using the complete chapter text and all the structured analysis above,
            produce a comprehensive study guide that covers EVERY concept, formula,
            and relationship listed.

            Structure your response as follows:

            ## 1. Chapter Overview
            A 3-4 paragraph summary that captures the chapter's main thesis,
            why it matters, and how it connects to the broader subject.

            ## 2. Core Concepts Explained
            For EACH key concept listed above (in order of importance):
            - Explain it in your own words (don't just quote the book)
            - Provide a real-world analogy or concrete example
            - Explain WHY this concept matters
            - Note any common misconceptions

            ## 3. Formulas & Mathematical Reasoning
            For EACH formula listed above:
            - Explain the intuition behind it (what does it mean conceptually?)
            - Walk through each variable and what it represents
            - Show a worked example with concrete numbers
            - Explain when/why you would use this formula

            ## 4. How Concepts Connect
            Using the dependency graph above, explain:
            - How concepts build on each other (follow the dependency order)
            - Key comparisons and trade-offs between approaches
            - What decisions/trade-offs drive the choice between alternatives

            ## 5. Practical Applications
            - 3-5 real-world scenarios where this chapter's content applies
            - For each scenario, identify which concepts are most relevant

            ## 6. Key Takeaways
            - Bullet-point summary of the 5-10 most important ideas
            - One sentence capturing the chapter's essence

            IMPORTANT: Preserve all LaTeX mathematical notation.
            Do not skip any concept from the list above.
        """),
    },

    "exam_prep": {
        "name": "Exam Preparation",
        "instruction": textwrap.dedent("""\
            Using the complete chapter text and all the structured analysis above,
            produce exam-focused study material.

            Structure your response as follows:

            ## 1. Key Definitions (Flashcard Format)
            For EACH key concept listed above:
            **Q:** What is [concept]?
            **A:** [Clear, concise 1-2 sentence definition]

            ## 2. Quick-Reference Formula Sheet
            For EACH formula listed above:
            | Formula | What it computes | When to use it |
            Provide the table.

            ## 3. Conceptual Questions (10-15)
            Multiple-choice or short-answer questions that test understanding.
            For each question:
            - State the question clearly
            - Provide the correct answer
            - Explain WHY it's correct and why other options are wrong

            ## 4. Application Problems (5-8)
            Scenario-based questions that require applying concepts:
            - State the problem
            - Walk through the solution step by step
            - Identify which concept(s) are being tested

            ## 5. Compare & Contrast Questions (3-5)
            Based on the comparisons identified in the dependency graph:
            - "Compare X and Y. When would you choose each?"
            - Provide a model answer for each

            ## 6. Common Exam Traps
            - List 5 subtle points that are commonly tested
            - For each, explain the correct understanding

            IMPORTANT: Preserve all LaTeX mathematical notation.
            Cover ALL concepts from the analysis above.
        """),
    },

    "quick_review": {
        "name": "Quick Review",
        "instruction": textwrap.dedent("""\
            Using the complete chapter text and all the structured analysis above,
            produce a concise review document optimized for quick revision.

            Structure your response as follows:

            ## TL;DR (3 sentences max)
            The absolute essence of this chapter in 3 sentences.

            ## Key Concepts at a Glance
            A bullet-point list of EVERY key concept with a one-line explanation.
            Format: **Concept** — one-line explanation

            ## Formula Cheat Sheet
            List every formula with a one-line description of what it does.

            ## Concept Map (Text)
            Show how the main concepts relate to each other using arrows:
            A → depends on → B
            C ↔ compared with ↔ D

            ## One-Paragraph Takeaway
            A single paragraph that a reader could use to explain this chapter
            to someone who hasn't read it.

            IMPORTANT: Keep it SHORT. This is a quick review, not a deep dive.
            Preserve all LaTeX mathematical notation.
        """),
    },

    "socratic": {
        "name": "Socratic Dialogue",
        "instruction": textwrap.dedent("""\
            Using the complete chapter text and all the structured analysis above,
            create a Socratic dialogue that guides the reader through the material
            step by step.

            Format as a conversation between TEACHER and STUDENT:

            **TEACHER:** [Opens with a thought-provoking question about the main topic]
            **STUDENT:** [Attempts an answer based on intuition]
            **TEACHER:** [Builds on the answer, introduces the first key concept]
            ...

            Rules:
            1. Cover EVERY key concept from the analysis above
            2. Follow the dependency order — introduce prerequisites first
            3. Use the comparisons from the dependency graph as debate points
            4. When a formula appears, have the student work through it step by step
            5. Each exchange should deepen understanding (don't just state facts)
            6. Include "aha moments" where the student connects concepts
            7. End with a synthesis question that ties everything together

            The dialogue should feel like a real tutoring session.
            IMPORTANT: Preserve all LaTeX mathematical notation.
        """),
    },
}


class PromptAssembler:
    """Assemble the final optimal prompt from analysis results."""

    def assemble(
        self,
        chapter_text: str,
        analysis: dict,
        chapter_meta: dict,
        book_meta: dict,
        mode: str = "deep_dive",
        cross_references: list[dict] | None = None,
    ) -> str:
        """
        Assemble the complete prompt.

        Args:
            chapter_text: Full markdown of the chapter.
            analysis: Output from Engine.analyze().
            chapter_meta: Chapter metadata (title, number, etc.)
            book_meta: Book metadata (title, author, total_chapters, etc.)
            mode: Study mode key from STUDY_MODES.
            cross_references: Related chapters from other books.

        Returns:
            The fully assembled prompt string.
        """
        cross_references = cross_references or []
        study_mode = STUDY_MODES.get(mode, STUDY_MODES["deep_dive"])

        parts = []

        # ── Header ──────────────────────────────────────────
        parts.append(self._build_header(chapter_meta, book_meta, study_mode))

        # ── Chapter Structure ───────────────────────────────
        parts.append(self._build_structure_section(analysis["structure"], analysis["density"]))

        # ── Key Concepts ────────────────────────────────────
        parts.append(self._build_concepts_section(analysis["concepts"]))

        # ── Formulas ────────────────────────────────────────
        if analysis["formulas"]:
            parts.append(self._build_formulas_section(analysis["formulas"]))

        # ── Dependency Graph ────────────────────────────────
        parts.append(self._build_dependencies_section(analysis["dependencies"]))

        # ── Cross-References ────────────────────────────────
        if cross_references:
            parts.append(self._build_cross_references(cross_references))

        # ── Full Chapter Text ───────────────────────────────
        parts.append(self._build_chapter_text_section(chapter_text))

        # ── Study Instructions ──────────────────────────────
        parts.append(self._build_instructions(study_mode))

        return "\n\n".join(parts)

    # ── Section Builders ─────────────────────────────────────

    def _build_header(self, chapter_meta: dict, book_meta: dict,
                      study_mode: dict) -> str:
        """Build the context header."""
        ch_title = chapter_meta.get("title", "Unknown Chapter")
        ch_number = chapter_meta.get("number", "?")
        book_title = book_meta.get("title", "Unknown Book")
        book_author = book_meta.get("author", "")
        total_chapters = book_meta.get("total_chapters", "?")

        lines = [
            f"# Study Prompt: Chapter {ch_number} — \"{ch_title}\"",
            f"",
            f"**Book:** {book_title}",
        ]

        if book_author:
            lines.append(f"**Author:** {book_author}")

        lines.extend([
            f"**Chapter:** {ch_number} of {total_chapters}",
            f"**Study Mode:** {study_mode['name']}",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ])

        # Adjacent chapters for context
        prev_ch = chapter_meta.get("prev_chapter")
        next_ch = chapter_meta.get("next_chapter")
        if prev_ch:
            lines.append(f"**Previous:** {prev_ch}")
        if next_ch:
            lines.append(f"**Next:** {next_ch}")

        return "\n".join(lines)

    def _build_structure_section(self, structure: dict, density: dict) -> str:
        """Build the chapter structure map."""
        lines = [
            "---",
            "## Chapter Structure",
            "",
        ]

        heading_count = structure.get("heading_count", 0)
        max_depth = structure.get("max_depth", 1)
        lines.append(f"*{heading_count} sections, max depth {max_depth}*")
        lines.append("")

        # Build tree view with density annotations
        density_map = {}
        for section in density.get("sections", []):
            density_map[section["title"]] = section["primary_type"]

        for section in structure.get("sections", []):
            self._render_section_tree(section, lines, density_map, indent=0)

        return "\n".join(lines)

    def _render_section_tree(self, section: dict, lines: list,
                             density_map: dict, indent: int):
        """Recursively render a section tree."""
        prefix = "  " * indent + ("├─ " if indent > 0 else "")
        title = section.get("title", "")
        word_count = section.get("word_count", 0)
        density_type = density_map.get(title, "")
        annotation = f" [{density_type}]" if density_type else ""

        lines.append(f"{prefix}**{title}** ({word_count} words){annotation}")

        for child in section.get("children", []):
            self._render_section_tree(child, lines, density_map, indent + 1)

    def _build_concepts_section(self, concepts: list[dict]) -> str:
        """Build the key concepts section."""
        if not concepts:
            return "## Key Concepts\n\n*No key concepts detected.*"

        # Group by importance
        high = [c for c in concepts if c.get("importance") == "high"]
        medium = [c for c in concepts if c.get("importance") == "medium"]
        low = [c for c in concepts if c.get("importance") == "low"]

        lines = [
            "---",
            f"## {len(concepts)} Key Concepts Identified",
            "",
        ]

        if high:
            lines.append("### Critical Concepts (must understand)")
            for i, c in enumerate(high, 1):
                definition = f" — {c['definition']}" if c.get("definition") else ""
                mentions = c.get("mentions", 0)
                lines.append(f"{i}. **{c['name']}**{definition} *(mentioned {mentions}×)*")
            lines.append("")

        if medium:
            lines.append("### Important Concepts")
            for i, c in enumerate(medium, len(high) + 1):
                definition = f" — {c['definition']}" if c.get("definition") else ""
                lines.append(f"{i}. **{c['name']}**{definition}")
            lines.append("")

        if low:
            lines.append("### Supporting Concepts")
            for i, c in enumerate(low, len(high) + len(medium) + 1):
                definition = f" — {c['definition']}" if c.get("definition") else ""
                lines.append(f"{i}. {c['name']}{definition}")
            lines.append("")

        return "\n".join(lines)

    def _build_formulas_section(self, formulas: list[dict]) -> str:
        """Build the formulas section with context."""
        lines = [
            "---",
            f"## {len(formulas)} Formulas",
            "",
        ]

        for i, f in enumerate(formulas, 1):
            lines.append(f"### Formula {i}")
            lines.append(f"{f['latex']}")
            lines.append("")

            if f.get("context_before"):
                lines.append(f"**Context:** {f['context_before'][:200]}")

            if f.get("variables"):
                var_strs = [f"`{v['symbol']}` = {v['meaning']}" for v in f["variables"]]
                lines.append(f"**Variables:** {', '.join(var_strs)}")

            lines.append("")

        return "\n".join(lines)

    def _build_dependencies_section(self, dependencies: dict) -> str:
        """Build the concept dependency graph section."""
        lines = [
            "---",
            "## Concept Dependency Graph",
            "",
        ]

        edges = dependencies.get("edges", [])
        cross_refs = dependencies.get("cross_references", [])
        clusters = dependencies.get("concept_clusters", [])

        if edges:
            lines.append("### Relationships")
            for edge in edges:
                type_label = edge["type"].replace("_", " ")
                lines.append(f"- {edge['from']} →[{type_label}]→ {edge['to']}")
            lines.append("")

        if clusters:
            lines.append("### Concept Clusters (frequently co-occur)")
            for i, cluster in enumerate(clusters, 1):
                lines.append(f"{i}. {', '.join(cluster)}")
            lines.append("")

        if cross_refs:
            lines.append("### External References")
            for ref in cross_refs:
                lines.append(f"- {ref['text']}")
            lines.append("")

        if not edges and not clusters and not cross_refs:
            lines.append("*No explicit dependencies detected.*")
            lines.append("")

        return "\n".join(lines)

    def _build_cross_references(self, cross_references: list[dict]) -> str:
        """Build cross-references to other books in the library."""
        lines = [
            "---",
            "## Related Content From Your Library",
            "",
        ]

        for ref in cross_references:
            book = ref.get("book_title", "Unknown")
            chapter = ref.get("chapter_title", "Unknown")
            relevance = ref.get("relevance", "related")
            lines.append(f"- **{book}** → {chapter} *({relevance})*")

        lines.append("")
        return "\n".join(lines)

    def _build_chapter_text_section(self, chapter_text: str) -> str:
        """Build the full chapter text section."""
        # Estimate token count (rough: ~4 chars per token)
        est_tokens = len(chapter_text) // 4

        lines = [
            "---",
            "## Full Chapter Text",
            f"*({len(chapter_text.split())} words, ~{est_tokens:,} tokens)*",
            "",
            "<chapter>",
            chapter_text,
            "</chapter>",
        ]

        return "\n".join(lines)

    def _build_instructions(self, study_mode: dict) -> str:
        """Build the final study mode instructions."""
        lines = [
            "---",
            f"## Instructions — {study_mode['name']} Mode",
            "",
            study_mode["instruction"],
        ]

        return "\n".join(lines)


def get_available_modes() -> dict:
    """Return available study modes and their descriptions."""
    return {
        key: {"name": mode["name"], "instruction_preview": mode["instruction"][:200]}
        for key, mode in STUDY_MODES.items()
    }
