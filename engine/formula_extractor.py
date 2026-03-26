"""
formula_extractor.py — Extract LaTeX formulas with surrounding context.

Deterministic: finds all $...$ and $$...$$ blocks, then captures
the context around each formula (setup sentences, variable definitions).

No AI involved.
"""

from __future__ import annotations

import re


class FormulaExtractor:
    """Extract LaTeX formulas and their context from chapter text."""

    # Display math: $$...$$
    DISPLAY_MATH_RE = re.compile(
        r'\$\$(.+?)\$\$',
        re.DOTALL
    )

    # Inline math: $...$  (not preceded/followed by $)
    INLINE_MATH_RE = re.compile(
        r'(?<!\$)\$([^$\n]+?)\$(?!\$)'
    )

    # Variable definition patterns: "where X is...", "let X =", "X denotes"
    VARIABLE_DEF_RE = re.compile(
        r'(?:where|let|here|and)\s+'
        r'[\$]?([A-Za-z\\][^$\s]*?)[\$]?\s+'
        r'(?:is|=|denotes?|represents?|equals?)\s+'
        r'([^.!?\n]{5,100})',
        re.IGNORECASE
    )

    # "for all X", "for each X"
    QUANTIFIER_RE = re.compile(
        r'(?:for\s+(?:all|each|every|any))\s+'
        r'[\$]?([A-Za-z\\][^$\s]*?)[\$]?\s*(?:[,.]|\s+(?:in|from|where))',
        re.IGNORECASE
    )

    def extract(self, text: str) -> list[dict]:
        """
        Extract all formulas from the text.

        Returns list of formula dicts:
            {
                "latex": "$$E = mc^2$$",
                "type": "display" | "inline",
                "context_before": "Einstein showed that...",
                "context_after": "where m is mass...",
                "variables": [{"symbol": "m", "meaning": "mass"}, ...],
                "position": 1234,  # char offset
            }
        """
        formulas = []

        # Extract display math (higher priority)
        for match in self.DISPLAY_MATH_RE.finditer(text):
            latex = match.group(1).strip()
            if self._is_meaningful(latex):
                formula = self._build_formula(
                    text, match, latex, "display"
                )
                formulas.append(formula)

        # Extract inline math (only significant ones)
        display_ranges = {(m.start(), m.end()) for m in self.DISPLAY_MATH_RE.finditer(text)}
        for match in self.INLINE_MATH_RE.finditer(text):
            # Skip if inside a display math range
            if any(s <= match.start() < e for s, e in display_ranges):
                continue

            latex = match.group(1).strip()
            if self._is_significant_inline(latex):
                formula = self._build_formula(
                    text, match, latex, "inline"
                )
                formulas.append(formula)

        # Deduplicate by latex content
        seen = set()
        unique = []
        for f in formulas:
            normalized = re.sub(r'\s+', '', f["latex"])
            if normalized not in seen:
                seen.add(normalized)
                unique.append(f)

        return unique

    def _is_meaningful(self, latex: str) -> bool:
        """Check if a latex string is meaningful (not just a single letter/number)."""
        stripped = latex.strip()
        if len(stripped) < 2:
            return False
        # Single variable or number
        if re.match(r'^\\?[a-zA-Z]$', stripped):
            return False
        if re.match(r'^\d+$', stripped):
            return False
        return True

    def _is_significant_inline(self, latex: str) -> bool:
        """Check if an inline formula is significant enough to extract."""
        stripped = latex.strip()
        # Must have at least an operator, subscript, superscript, or function
        if len(stripped) < 3:
            return False
        significant_patterns = [
            r'[=<>+\-*/]',       # operators
            r'[_^]',             # sub/superscript
            r'\\[a-z]+',         # LaTeX commands
            r'\{.*\}',           # braces
            r'\\frac',           # fractions
            r'\\sum|\\prod',     # big operators
            r'\\int',            # integrals
            r'\\sqrt',           # square root
        ]
        return any(re.search(p, stripped) for p in significant_patterns)

    def _build_formula(self, text: str, match: re.Match,
                       latex: str, formula_type: str) -> dict:
        """Build a formula dict with context and variable definitions."""
        pos = match.start()

        # Get context before (2 sentences back)
        context_before = self._get_context_before(text, pos)

        # Get context after (1 sentence forward)
        context_after = self._get_context_after(text, match.end())

        # Find variable definitions nearby
        variables = self._find_variables(text, pos, match.end())

        return {
            "latex": f"$${latex}$$" if formula_type == "display" else f"${latex}$",
            "type": formula_type,
            "context_before": context_before,
            "context_after": context_after,
            "variables": variables,
            "position": pos,
        }

    def _get_context_before(self, text: str, pos: int, max_chars: int = 400) -> str:
        """Get the context (sentences) before a formula."""
        start = max(0, pos - max_chars)
        chunk = text[start:pos].strip()

        # Split into sentences and take last 2
        sentences = re.split(r'(?<=[.!?])\s+', chunk)
        context = ' '.join(sentences[-2:]) if len(sentences) >= 2 else chunk
        return context.strip()

    def _get_context_after(self, text: str, end_pos: int, max_chars: int = 300) -> str:
        """Get the context (sentence) after a formula."""
        chunk = text[end_pos:end_pos + max_chars].strip()

        # Take the first sentence
        sentence_match = re.match(r'^(.+?[.!?])\s', chunk)
        if sentence_match:
            return sentence_match.group(1).strip()
        return chunk[:200].strip()

    def _find_variables(self, text: str, start: int, end: int) -> list[dict]:
        """Find variable definitions near a formula."""
        # Look in a window around the formula
        window_start = max(0, start - 200)
        window_end = min(len(text), end + 400)
        window = text[window_start:window_end]

        variables = []

        # "where X is Y" patterns
        for match in self.VARIABLE_DEF_RE.finditer(window):
            variables.append({
                "symbol": match.group(1).strip(),
                "meaning": match.group(2).strip(),
            })

        # "for all X" patterns
        for match in self.QUANTIFIER_RE.finditer(window):
            variables.append({
                "symbol": match.group(1).strip(),
                "meaning": f"quantified variable",
            })

        return variables
