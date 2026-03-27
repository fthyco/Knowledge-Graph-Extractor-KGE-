"""
density_analyzer.py — Classify section types by content density.

Deterministic analysis of each section's content to determine if it's:
- concept-dense (many definitions/terms)
- math-heavy (many formulas)
- example-rich (many examples/case studies)
- implementation-focused (code blocks, algorithms)
- comparison (contrasting approaches)
- introductory (overview, light content)

This tells the prompt assembler HOW to instruct the LLM
for each section — e.g. "explain the math step by step"
vs "summarize the examples".

No AI involved.
"""

from __future__ import annotations

import re


class DensityAnalyzer:
    """Classify each section by its content type and density."""

    # ── Detection patterns ───────────────────────────────────

    # Code blocks: ```...``` or indented 4+ spaces
    CODE_BLOCK_RE = re.compile(r'```[\s\S]*?```|(?:^    .+$\n?)+', re.MULTILINE)

    # Example markers
    EXAMPLE_RE = re.compile(
        r'(?:for\s+example|e\.g\.,?|for\s+instance|'
        r'consider\s+(?:the|a|an)|'
        r'(?:imagine|suppose|say)\s+(?:that|we|you)|'
        r'(?:real-world|practical)\s+example|'
        r'case\s+study|'
        r'(?:Figure|Table|Listing)\s+\d)',
        re.IGNORECASE
    )

    # Comparison markers
    COMPARISON_RE = re.compile(
        r'(?:unlike|compared\s+to|in\s+contrast|'
        r'on\s+the\s+other\s+hand|whereas|while|'
        r'however|alternatively|instead|'
        r'advantage|disadvantage|trade-?off|'
        r'pros?\s+and\s+cons?|'
        r'vs\.?|versus)',
        re.IGNORECASE
    )

    # Algorithm/procedure markers
    ALGORITHM_RE = re.compile(
        r'(?:algorithm|step\s+\d|procedure|'
        r'(?:first|second|third|finally),?\s+(?:we|the|it)|'
        r'pseudo\s*code|implementation|'
        r'function\s+\w+|class\s+\w+|'
        r'def\s+\w+|import\s+)',
        re.IGNORECASE
    )

    # Proof markers
    PROOF_RE = re.compile(
        r'(?:Q\.E\.D\.|\u220e|\u25a0|\bproof\b|'
        r'\btherefore\b|\bhence\b|\bit\s+follows|'
        r'\bwe\s+conclude|\bwe\s+have\s+shown|'
        r'\bsufficiency|\bnecessity|'
        r'\bby\s+(?:induction|contradiction|contrapositive))',
        re.IGNORECASE
    )

    # Problem/exercise markers
    PROBLEM_RE = re.compile(
        r'(?:\bexercise\b|\bproblem\b|\bquestion\b|'
        r'\bfind\s+(?:the|a|an)\b|\bshow\s+that\b|'
        r'\bprove\s+that\b|\bcalculate\b|\bcompute\b|'
        r'\bdetermine\b|\bverify\s+that\b|'
        r'\bhomework|\bassignment)',
        re.IGNORECASE
    )

    # Display math
    DISPLAY_MATH_RE = re.compile(r'\$\$.+?\$\$', re.DOTALL)

    # Inline math
    INLINE_MATH_RE = re.compile(r'(?<!\$)\$[^$\n]+?\$(?!\$)')

    # Definition markers
    DEFINITION_MARKERS = re.compile(
        r'(?:is\s+defined\s+as|refers?\s+to|means?|'
        r'is\s+(?:a|an|the)\s+\w+\s+(?:that|which|where)|'
        r'we\s+call|known\s+as|termed)',
        re.IGNORECASE
    )

    def analyze(self, text: str, structure: dict,
                concepts: list[dict], formulas: list[dict]) -> dict:
        """
        Analyze content density for each section.

        Returns:
            {
                "overall": {
                    "primary_type": "concept-dense",
                    "types": ["concept-dense", "comparison"],
                    "stats": { ... }
                },
                "sections": [
                    {
                        "title": "Hash Indexes",
                        "primary_type": "concept-dense",
                        "types": ["concept-dense", "implementation-focused"],
                        "scores": { ... }
                    },
                    ...
                ]
            }
        """
        # Analyze overall chapter
        overall_stats = self._compute_stats(text)
        overall_types = self._classify(overall_stats)

        # Analyze per section
        section_analyses = []
        for section in structure.get("sections", []):
            section_text = section.get("text", "")
            if not section_text:
                # Reconstruct from the full text using character offsets
                start = section.get("start", 0)
                end = section.get("end", len(text))
                section_text = text[start:end] if start < len(text) else ""

            if len(section_text.split()) < 20:
                continue

            stats = self._compute_stats(section_text)
            types = self._classify(stats)

            section_analyses.append({
                "title": section.get("title", ""),
                "primary_type": types[0] if types else "general",
                "types": types,
                "scores": stats,
            })

            # Recurse into children
            for child in section.get("children", []):
                child_start = child.get("start", 0)
                child_end = child.get("end", len(text))
                child_text = text[child_start:child_end] if child_start < len(text) else ""

                if len(child_text.split()) < 20:
                    continue

                child_stats = self._compute_stats(child_text)
                child_types = self._classify(child_stats)

                section_analyses.append({
                    "title": child.get("title", ""),
                    "primary_type": child_types[0] if child_types else "general",
                    "types": child_types,
                    "scores": child_stats,
                })

        return {
            "overall": {
                "primary_type": overall_types[0] if overall_types else "general",
                "types": overall_types,
                "stats": overall_stats,
            },
            "sections": section_analyses,
        }

    def _compute_stats(self, text: str) -> dict:
        """Compute raw statistics for a text segment."""
        words = text.split()
        word_count = len(words)
        if word_count == 0:
            return self._empty_stats()

        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        para_count = max(len(paragraphs), 1)

        # Count features
        display_math_count = len(self.DISPLAY_MATH_RE.findall(text))
        inline_math_count = len(self.INLINE_MATH_RE.findall(text))
        total_math = display_math_count + inline_math_count

        code_blocks = self.CODE_BLOCK_RE.findall(text)
        code_count = len(code_blocks)

        example_count = len(self.EXAMPLE_RE.findall(text))
        comparison_count = len(self.COMPARISON_RE.findall(text))
        algorithm_count = len(self.ALGORITHM_RE.findall(text))
        definition_count = len(self.DEFINITION_MARKERS.findall(text))

        # Bold terms (concept indicators)
        bold_count = len(re.findall(r'\*\*[^*]+\*\*', text))

        # Lists (bullet/numbered)
        list_count = len(re.findall(r'^[\s]*[-*•]\s+|^\s*\d+\.\s+', text, re.MULTILINE))

        # Proof and problem indicators
        proof_count = len(self.PROOF_RE.findall(text))
        problem_count = len(self.PROBLEM_RE.findall(text))

        # Compute ratios (per paragraph)
        return {
            "word_count": word_count,
            "para_count": para_count,
            "math_per_para": total_math / para_count,
            "display_math_count": display_math_count,
            "inline_math_count": inline_math_count,
            "code_per_para": code_count / para_count,
            "code_count": code_count,
            "example_ratio": example_count / para_count,
            "example_count": example_count,
            "comparison_ratio": comparison_count / para_count,
            "comparison_count": comparison_count,
            "algorithm_ratio": algorithm_count / para_count,
            "definition_ratio": definition_count / para_count,
            "definition_count": definition_count,
            "bold_ratio": bold_count / para_count,
            "bold_count": bold_count,
            "list_ratio": list_count / para_count,
            "list_count": list_count,
            "proof_ratio": proof_count / para_count,
            "proof_count": proof_count,
            "problem_ratio": problem_count / para_count,
            "problem_count": problem_count,
        }

    def _empty_stats(self) -> dict:
        return {k: 0 for k in [
            "word_count", "para_count", "math_per_para",
            "display_math_count", "inline_math_count",
            "code_per_para", "code_count", "example_ratio",
            "example_count", "comparison_ratio", "comparison_count",
            "algorithm_ratio", "definition_ratio", "definition_count",
            "bold_ratio", "bold_count", "list_ratio", "list_count",
            "proof_ratio", "proof_count", "problem_ratio", "problem_count",
        ]}

    def _classify(self, stats: dict) -> list[str]:
        """
        Classify section type based on computed stats.
        Returns a ranked list of applicable types.
        """
        scores = {
            "concept-dense": 0.0,
            "math-heavy": 0.0,
            "example-rich": 0.0,
            "implementation-focused": 0.0,
            "comparison": 0.0,
            "proof-heavy": 0.0,
            "problem-set": 0.0,
            "introductory": 0.0,
        }

        # Math-heavy
        if stats["math_per_para"] >= 1.0:
            scores["math-heavy"] += 3.0
        elif stats["math_per_para"] >= 0.3:
            scores["math-heavy"] += 1.5
        if stats["display_math_count"] >= 3:
            scores["math-heavy"] += 2.0

        # Concept-dense
        if stats["definition_ratio"] >= 0.3:
            scores["concept-dense"] += 2.0
        if stats["bold_ratio"] >= 0.5:
            scores["concept-dense"] += 2.0
        elif stats["bold_ratio"] >= 0.2:
            scores["concept-dense"] += 1.0

        # Example-rich
        if stats["example_ratio"] >= 0.3:
            scores["example-rich"] += 2.0
        elif stats["example_ratio"] >= 0.15:
            scores["example-rich"] += 1.0

        # Implementation-focused
        if stats["code_per_para"] >= 0.3:
            scores["implementation-focused"] += 3.0
        elif stats["code_count"] >= 2:
            scores["implementation-focused"] += 1.5
        if stats["algorithm_ratio"] >= 0.2:
            scores["implementation-focused"] += 1.5

        # Comparison
        if stats["comparison_ratio"] >= 0.3:
            scores["comparison"] += 2.5
        elif stats["comparison_ratio"] >= 0.15:
            scores["comparison"] += 1.0

        # Proof-heavy
        if stats.get("proof_ratio", 0) >= 0.3:
            scores["proof-heavy"] += 3.0
        elif stats.get("proof_ratio", 0) >= 0.15:
            scores["proof-heavy"] += 1.5
        if stats.get("proof_count", 0) >= 5:
            scores["proof-heavy"] += 1.0

        # Problem-set
        if stats.get("problem_ratio", 0) >= 0.3:
            scores["problem-set"] += 3.0
        elif stats.get("problem_ratio", 0) >= 0.15:
            scores["problem-set"] += 1.5
        if stats.get("problem_count", 0) >= 5:
            scores["problem-set"] += 1.5

        # Introductory (low density of everything, short)
        if stats["word_count"] < 300:
            scores["introductory"] += 1.0
        if all(v < 0.1 for k, v in stats.items() if k.endswith("_ratio")):
            scores["introductory"] += 2.0

        # Return types sorted by score, filtering out near-zero
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [t for t, s in ranked if s >= 1.0] or ["general"]
