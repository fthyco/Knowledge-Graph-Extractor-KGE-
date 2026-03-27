"""
page_classifier.py — Pre-classify PDF pages for smart OCR routing.

Uses pypdf to quickly extract text from each page and classify it:
  - DIGITAL: Has extractable text (≥ threshold words) → no OCR needed
  - SCANNED: Little/no extractable text → needs full OCR
  - SKIP: Nearly empty page with no images → can be skipped entirely

This pre-scan takes milliseconds even for 500+ page PDFs,
and allows the marker pipeline to apply OCR selectively.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pypdf


@dataclass
class PageClassification:
    """Result of page classification for a PDF."""

    total_pages: int = 0
    digital_pages: list[int] = field(default_factory=list)  # 0-indexed
    ocr_pages: list[int] = field(default_factory=list)      # 0-indexed
    skip_pages: list[int] = field(default_factory=list)      # 0-indexed
    scan_time_ms: float = 0.0

    @property
    def summary(self) -> str:
        return (
            f"{len(self.digital_pages)} digital, "
            f"{len(self.ocr_pages)} scanned, "
            f"{len(self.skip_pages)} skipped "
            f"(of {self.total_pages} total, {self.scan_time_ms:.0f}ms)"
        )


class PageClassifier:
    """Classify PDF pages to determine OCR requirements."""

    # Pages with >= this many extractable words are considered digital
    DIGITAL_THRESHOLD = 50

    # Pages with < this many words AND minimal content are skipped
    SKIP_THRESHOLD = 5

    @classmethod
    def classify(
        cls,
        pdf_path: str | Path,
        digital_threshold: int | None = None,
        skip_threshold: int | None = None,
    ) -> PageClassification:
        """
        Classify all pages in a PDF.

        Uses pypdf text extraction (fast, no ML models) to detect
        which pages have selectable text vs. scanned images.

        Args:
            pdf_path: Path to the PDF file
            digital_threshold: Min words for a page to be considered digital
            skip_threshold: Max words for a page to be skipped

        Returns:
            PageClassification with categorized page indices
        """
        if digital_threshold is None:
            digital_threshold = cls.DIGITAL_THRESHOLD
        if skip_threshold is None:
            skip_threshold = cls.SKIP_THRESHOLD

        t0 = time.perf_counter()
        result = PageClassification()

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            result.total_pages = len(reader.pages)

            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                    word_count = len(text.split())

                    if word_count >= digital_threshold:
                        result.digital_pages.append(i)
                    elif word_count <= skip_threshold:
                        # Check if page has meaningful content (images)
                        has_images = cls._page_has_images(page)
                        if has_images:
                            # Has images but no text → scanned
                            result.ocr_pages.append(i)
                        else:
                            # No text, no images → skip
                            result.skip_pages.append(i)
                    else:
                        # Between skip and digital threshold →
                        # has some text but not enough, needs OCR for completeness
                        result.ocr_pages.append(i)

                except Exception:
                    # If we can't read the page, assume it needs OCR
                    result.ocr_pages.append(i)

        result.scan_time_ms = (time.perf_counter() - t0) * 1000
        return result

    @staticmethod
    def _page_has_images(page: pypdf.PageObject) -> bool:
        """Check if a page contains image resources (indicating scanned content)."""
        try:
            resources = page.get("/Resources")
            if resources is None:
                return False

            xobject = resources.get("/XObject")
            if xobject is None:
                return False

            # Resolve indirect reference
            resolved = xobject.get_object() if hasattr(xobject, "get_object") else xobject
            if isinstance(resolved, dict):
                for obj in resolved.values():
                    try:
                        resolved_obj = (
                            obj.get_object() if hasattr(obj, "get_object") else obj
                        )
                        if isinstance(resolved_obj, dict):
                            subtype = resolved_obj.get("/Subtype")
                            if subtype == "/Image":
                                return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False

    @staticmethod
    def group_contiguous(pages: list[int]) -> list[tuple[int, int]]:
        """
        Group sorted page indices into contiguous (start, end) ranges.

        Example: [0,1,2,5,6,10] → [(0,2), (5,6), (10,10)]
        """
        if not pages:
            return []

        sorted_pages = sorted(pages)
        ranges = []
        start = sorted_pages[0]
        end = sorted_pages[0]

        for p in sorted_pages[1:]:
            if p == end + 1:
                end = p
            else:
                ranges.append((start, end))
                start = p
                end = p

        ranges.append((start, end))
        return ranges
