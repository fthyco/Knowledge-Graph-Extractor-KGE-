"""
storage.py — JSON-file-based persistent storage for the warehouse.

Directory structure:
    data/
    ├── index.json              # list of all books (metadata only)
    ├── books/
    │   ├── {book_id}/
    │   │   ├── book.json       # full book metadata
    │   │   ├── markdown.md     # complete extracted markdown
    │   │   ├── chapters/
    │   │   │   ├── {ch_id}.json    # chapter metadata + analysis
    │   │   │   └── {ch_id}.md      # chapter full text
    │   │   └── prompts/
    │   │       └── {ch_id}_{mode}.md  # generated prompts (cached)
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Optional

from warehouse.models import Book, Chapter


class Storage:
    """File-based storage layer for books and chapters."""

    def __init__(self, data_dir: str = "warehouse/data"):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / "index.json"
        self.books_dir = self.data_dir / "books"
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create directory structure if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.books_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index([])

    # ── Index ───────────────────────────────────────────────

    def _read_index(self) -> list[dict]:
        with open(self.index_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_index(self, index: list[dict]):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    # ── Books ───────────────────────────────────────────────

    def list_books(self) -> list[dict]:
        """Return all books (metadata only, no full_markdown)."""
        return self._read_index()

    def get_book(self, book_id: str) -> dict | None:
        """Get book metadata by ID."""
        book_dir = self.books_dir / book_id
        book_path = book_dir / "book.json"
        if not book_path.exists():
            return None
        with open(book_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_book_markdown(self, book_id: str) -> str | None:
        """Get the full markdown text for a book."""
        md_path = self.books_dir / book_id / "markdown.md"
        if not md_path.exists():
            return None
        with open(md_path, "r", encoding="utf-8") as f:
            return f.read()

    def save_book(self, book: Book):
        """Save a book to storage."""
        book_dir = self.books_dir / book.id
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / "chapters").mkdir(exist_ok=True)
        (book_dir / "prompts").mkdir(exist_ok=True)

        # Save book metadata (without full_markdown)
        with open(book_dir / "book.json", "w", encoding="utf-8") as f:
            json.dump(book.to_dict(), f, indent=2, ensure_ascii=False)

        # Save full markdown separately
        if book.full_markdown:
            with open(book_dir / "markdown.md", "w", encoding="utf-8") as f:
                f.write(book.full_markdown)

        # Update index
        index = self._read_index()
        # Remove existing entry if present
        index = [b for b in index if b["id"] != book.id]
        index.append(book.to_dict())
        self._write_index(index)

    def delete_book(self, book_id: str) -> bool:
        """Delete a book and all its data."""
        book_dir = self.books_dir / book_id
        if not book_dir.exists():
            return False

        shutil.rmtree(book_dir)

        # Update index
        index = self._read_index()
        index = [b for b in index if b["id"] != book_id]
        self._write_index(index)
        return True

    def clear_all_books(self) -> int:
        """Delete all books and their data."""
        if not self.books_dir.exists():
            return 0
        
        count = 0
        for item in self.books_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                count += 1
                
        self._write_index([])
        return count

    # ── Chapters ────────────────────────────────────────────

    def get_chapters(self, book_id: str) -> list[dict]:
        """Get all chapter metadata for a book (without full text)."""
        chapters_dir = self.books_dir / book_id / "chapters"
        if not chapters_dir.exists():
            return []

        chapters = []
        for ch_file in sorted(chapters_dir.glob("*.json")):
            with open(ch_file, "r", encoding="utf-8") as f:
                chapters.append(json.load(f))

        return sorted(chapters, key=lambda c: c.get("number", 0))

    def get_chapter(self, book_id: str, chapter_id: str) -> dict | None:
        """Get a single chapter with its full text."""
        chapters_dir = self.books_dir / book_id / "chapters"
        ch_meta_path = chapters_dir / f"{chapter_id}.json"
        ch_text_path = chapters_dir / f"{chapter_id}.md"

        if not ch_meta_path.exists():
            return None

        with open(ch_meta_path, "r", encoding="utf-8") as f:
            chapter = json.load(f)

        # Attach full text if available
        if ch_text_path.exists():
            with open(ch_text_path, "r", encoding="utf-8") as f:
                chapter["full_text"] = f.read()

        return chapter

    def save_chapter(self, chapter: Chapter):
        """Save a chapter (metadata + text)."""
        chapters_dir = self.books_dir / chapter.book_id / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata (without full_text)
        with open(chapters_dir / f"{chapter.id}.json", "w", encoding="utf-8") as f:
            json.dump(chapter.to_dict(), f, indent=2, ensure_ascii=False)

        # Save full text separately
        if chapter.full_text:
            with open(chapters_dir / f"{chapter.id}.md", "w", encoding="utf-8") as f:
                f.write(chapter.full_text)

    # ── Prompts (cached) ───────────────────────────────────

    def get_cached_prompt(self, book_id: str, chapter_id: str, mode: str) -> str | None:
        """Get a previously generated prompt if cached."""
        prompt_path = self.books_dir / book_id / "prompts" / f"{chapter_id}_{mode}.md"
        if not prompt_path.exists():
            return None
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def save_prompt(self, book_id: str, chapter_id: str, mode: str, prompt: str):
        """Cache a generated prompt."""
        prompts_dir = self.books_dir / book_id / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        with open(prompts_dir / f"{chapter_id}_{mode}.md", "w", encoding="utf-8") as f:
            f.write(prompt)
