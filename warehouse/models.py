"""
models.py — Data models for the book warehouse.

Every book and chapter is stored as a plain dict (JSON-serializable).
These dataclasses define the schema and provide construction helpers.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, asdict


def _generate_id(seed: str) -> str:
    """Generate a short deterministic ID from a seed string."""
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


@dataclass
class Chapter:
    """A chapter or major section within a book."""
    id: str
    book_id: str
    number: int                          # chapter number (1-based)
    title: str
    level: int = 1                       # 1=chapter, 2=section, 3=subsection
    start_index: int = 0                 # char offset in full markdown
    end_index: int = 0
    word_count: int = 0
    full_text: str = ""                  # the full markdown of this chapter
    sub_headings: list[str] = field(default_factory=list)
    concepts: list[dict] = field(default_factory=list)
    formulas: list[dict] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # chapter IDs this depends on
    study_status: str = "not_started"    # not_started | in_progress | completed

    def to_dict(self) -> dict:
        d = asdict(self)
        # Don't store full_text in the index (it's stored separately)
        d.pop("full_text", None)
        return d

    def to_full_dict(self) -> dict:
        """Include full_text — used when saving chapter content."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Chapter:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Book:
    """A book in the warehouse."""
    id: str
    title: str
    filename: str                        # original PDF filename
    author: str = ""
    subject: str = ""
    total_chapters: int = 0
    total_words: int = 0
    total_pages: int = 0
    upload_date: float = field(default_factory=time.time)
    raw_pdf_path: str = ""               # path to stored PDF in raw_source/
    full_markdown: str = ""              # complete extracted markdown
    chapter_ids: list[str] = field(default_factory=list)
    similar_books: list[dict] = field(default_factory=list)
    status: str = "processing"           # processing | ready | error

    def to_dict(self) -> dict:
        d = asdict(self)
        # Don't store full_markdown in index (too large)
        d.pop("full_markdown", None)
        return d

    def to_full_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Book:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def create(cls, title: str, filename: str, pdf_path: str) -> Book:
        """Create a new Book with a generated ID."""
        book_id = _generate_id(f"{title}:{filename}:{time.time()}")
        return cls(
            id=book_id,
            title=title,
            filename=filename,
            raw_pdf_path=pdf_path,
        )
