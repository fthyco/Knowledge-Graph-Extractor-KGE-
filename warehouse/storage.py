"""
storage.py — SQLite-based persistent storage for the warehouse.

Single-file database (warehouse.db) replaces the old JSON-file approach.
Benefits:
  - Single query replaces 20+ file reads for get_chapters()
  - Atomic transactions for data integrity
  - WAL mode for concurrent read access
  - ~10x faster for typical list/get operations

Schema:
    books       — book metadata (one row per book)
    chapters    — chapter metadata + analysis (one row per chapter)
    markdown    — full markdown text for books (separate for efficiency)
    prompts     — cached generated prompts
    analysis    — cached engine analysis results
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from warehouse.models import Book, Chapter


class Storage:
    """SQLite-backed storage layer for books and chapters."""

    SCHEMA_VERSION = 1

    def __init__(self, data_dir: str = "warehouse/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "warehouse.db"

        # Thread-local connections (SQLite objects can't cross threads)
        self._local = threading.local()
        self._init_db()

        # Migrate from old JSON format if needed
        self._maybe_migrate_json()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                filename    TEXT NOT NULL DEFAULT '',
                author      TEXT NOT NULL DEFAULT '',
                subject     TEXT NOT NULL DEFAULT '',
                total_chapters INTEGER NOT NULL DEFAULT 0,
                total_words INTEGER NOT NULL DEFAULT 0,
                total_pages INTEGER NOT NULL DEFAULT 0,
                upload_date REAL NOT NULL DEFAULT 0,
                raw_pdf_path TEXT NOT NULL DEFAULT '',
                chapter_ids TEXT NOT NULL DEFAULT '[]',
                similar_books TEXT NOT NULL DEFAULT '[]',
                status      TEXT NOT NULL DEFAULT 'processing'
            );

            CREATE TABLE IF NOT EXISTS chapters (
                id          TEXT PRIMARY KEY,
                book_id     TEXT NOT NULL,
                number      INTEGER NOT NULL DEFAULT 0,
                title       TEXT NOT NULL DEFAULT '',
                level       INTEGER NOT NULL DEFAULT 1,
                start_index INTEGER NOT NULL DEFAULT 0,
                end_index   INTEGER NOT NULL DEFAULT 0,
                word_count  INTEGER NOT NULL DEFAULT 0,
                full_text   TEXT NOT NULL DEFAULT '',
                sub_headings TEXT NOT NULL DEFAULT '[]',
                concepts    TEXT NOT NULL DEFAULT '[]',
                formulas    TEXT NOT NULL DEFAULT '[]',
                dependencies TEXT NOT NULL DEFAULT '[]',
                section_types TEXT NOT NULL DEFAULT '{}',
                study_status TEXT NOT NULL DEFAULT 'not_started',
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS markdown (
                book_id     TEXT PRIMARY KEY,
                content     TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS prompts (
                book_id     TEXT NOT NULL,
                chapter_id  TEXT NOT NULL,
                mode        TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (book_id, chapter_id, mode),
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS analysis (
                book_id     TEXT NOT NULL,
                chapter_id  TEXT NOT NULL,
                data        TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (book_id, chapter_id),
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id);
            CREATE INDEX IF NOT EXISTS idx_prompts_lookup ON prompts(book_id, chapter_id);
        """)
        conn.commit()

    # ── JSON Migration ─────────────────────────────────────

    def _maybe_migrate_json(self):
        """Auto-migrate from old JSON-file format if data exists."""
        old_index = self.data_dir / "index.json"
        old_books_dir = self.data_dir / "books"

        if not old_index.exists():
            return

        # Check if already migrated (books table has data)
        row = self._conn.execute("SELECT COUNT(*) FROM books").fetchone()
        if row[0] > 0:
            # Already have data in SQLite, rename old files as backup
            backup_index = self.data_dir / "index.json.bak"
            if not backup_index.exists():
                old_index.rename(backup_index)
            return

        print("[Storage] Migrating from JSON files to SQLite...")
        try:
            import json as _json

            with open(old_index, "r", encoding="utf-8") as f:
                books_list = _json.load(f)

            migrated = 0
            for book_data in books_list:
                book_id = book_data.get("id")
                if not book_id:
                    continue

                # Save book metadata
                book = Book.from_dict(book_data)
                self.save_book(book)

                # Migrate markdown
                md_path = old_books_dir / book_id / "markdown.md"
                if md_path.exists():
                    with open(md_path, "r", encoding="utf-8") as f:
                        md_text = f.read()
                    self._conn.execute(
                        "INSERT OR REPLACE INTO markdown (book_id, content) VALUES (?, ?)",
                        (book_id, md_text)
                    )

                # Migrate chapters
                chapters_dir = old_books_dir / book_id / "chapters"
                if chapters_dir.exists():
                    for ch_json in sorted(chapters_dir.glob("*.json")):
                        with open(ch_json, "r", encoding="utf-8") as f:
                            ch_data = _json.load(f)

                        # Check for separate .md file
                        ch_md = chapters_dir / f"{ch_json.stem}.md"
                        if ch_md.exists():
                            with open(ch_md, "r", encoding="utf-8") as f:
                                ch_data["full_text"] = f.read()

                        chapter = Chapter.from_dict(ch_data)
                        self.save_chapter(chapter)

                # Migrate prompts
                prompts_dir = old_books_dir / book_id / "prompts"
                if prompts_dir.exists():
                    for p_file in prompts_dir.glob("*.md"):
                        parts = p_file.stem.rsplit("_", 1)
                        if len(parts) == 2:
                            ch_id, mode = parts
                            with open(p_file, "r", encoding="utf-8") as f:
                                self.save_prompt(book_id, ch_id, mode, f.read())

                # Migrate analysis
                analysis_dir = old_books_dir / book_id / "analysis"
                if analysis_dir.exists():
                    for a_file in analysis_dir.glob("*.json"):
                        ch_id = a_file.stem
                        with open(a_file, "r", encoding="utf-8") as f:
                            self.save_analysis(book_id, ch_id, _json.load(f))

                migrated += 1

            self._conn.commit()
            print(f"[Storage] ✓ Migrated {migrated} books to SQLite")

            # Rename old index (keep as backup)
            old_index.rename(self.data_dir / "index.json.bak")

        except Exception as e:
            print(f"[Storage] ⚠ Migration failed: {e}")
            # Don't delete old data on failure

    # ── Books ───────────────────────────────────────────────

    def list_books(self) -> list[dict]:
        """Return all books (metadata only, no full_markdown)."""
        rows = self._conn.execute(
            "SELECT * FROM books ORDER BY upload_date DESC"
        ).fetchall()
        return [self._row_to_book_dict(r) for r in rows]

    def get_book(self, book_id: str) -> dict | None:
        """Get book metadata by ID."""
        row = self._conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_book_dict(row)

    def get_book_markdown(self, book_id: str) -> str | None:
        """Get the full markdown text for a book."""
        row = self._conn.execute(
            "SELECT content FROM markdown WHERE book_id = ?", (book_id,)
        ).fetchone()
        return row["content"] if row else None

    def save_book(self, book: Book, defer_index: bool = False):
        """
        Save a book to storage.

        The defer_index parameter is kept for API compatibility but is
        effectively a no-op in SQLite mode (writes are always atomic).
        """
        self._conn.execute("""
            INSERT OR REPLACE INTO books
            (id, title, filename, author, subject, total_chapters,
             total_words, total_pages, upload_date, raw_pdf_path,
             chapter_ids, similar_books, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            book.id, book.title, book.filename, book.author, book.subject,
            book.total_chapters, book.total_words, book.total_pages,
            book.upload_date, book.raw_pdf_path,
            json.dumps(book.chapter_ids, ensure_ascii=False),
            json.dumps(book.similar_books, ensure_ascii=False),
            book.status,
        ))

        # Save full markdown separately
        if book.full_markdown:
            self._conn.execute(
                "INSERT OR REPLACE INTO markdown (book_id, content) VALUES (?, ?)",
                (book.id, book.full_markdown)
            )

        if not defer_index:
            self._conn.commit()

    def flush_index(self):
        """Commit any pending writes to the database."""
        self._conn.commit()

    def delete_book(self, book_id: str) -> bool:
        """Delete a book and all its data (cascading)."""
        row = self._conn.execute(
            "SELECT id FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        if not row:
            return False

        self._conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        # CASCADE handles chapters, markdown, prompts, analysis
        self._conn.commit()

        # Also remove old file-based data if it exists
        old_dir = self.data_dir / "books" / book_id
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)

        return True

    def clear_all_books(self) -> int:
        """Delete all books and their data."""
        row = self._conn.execute("SELECT COUNT(*) FROM books").fetchone()
        count = row[0]

        self._conn.executescript("""
            DELETE FROM analysis;
            DELETE FROM prompts;
            DELETE FROM chapters;
            DELETE FROM markdown;
            DELETE FROM books;
        """)
        self._conn.commit()

        # Clean up old file-based data
        old_books_dir = self.data_dir / "books"
        if old_books_dir.exists():
            shutil.rmtree(old_books_dir, ignore_errors=True)

        return count

    # ── Chapters ────────────────────────────────────────────

    def get_chapters(self, book_id: str) -> list[dict]:
        """Get all chapter metadata for a book (without full_text for listing)."""
        rows = self._conn.execute(
            "SELECT id, book_id, number, title, level, start_index, end_index, "
            "word_count, sub_headings, concepts, formulas, dependencies, "
            "section_types, study_status "
            "FROM chapters WHERE book_id = ? ORDER BY number",
            (book_id,)
        ).fetchall()
        return [self._row_to_chapter_dict(r, include_text=False) for r in rows]

    def get_chapter(self, book_id: str, chapter_id: str) -> dict | None:
        """Get a single chapter with its full text."""
        row = self._conn.execute(
            "SELECT * FROM chapters WHERE book_id = ? AND id = ?",
            (book_id, chapter_id)
        ).fetchone()
        if not row:
            return None
        return self._row_to_chapter_dict(row, include_text=True)

    def save_chapter(self, chapter: Chapter):
        """Save a chapter (metadata + text) in a single INSERT."""
        self._conn.execute("""
            INSERT OR REPLACE INTO chapters
            (id, book_id, number, title, level, start_index, end_index,
             word_count, full_text, sub_headings, concepts, formulas,
             dependencies, section_types, study_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chapter.id, chapter.book_id, chapter.number, chapter.title,
            chapter.level, chapter.start_index, chapter.end_index,
            chapter.word_count, chapter.full_text,
            json.dumps(chapter.sub_headings, ensure_ascii=False),
            json.dumps(chapter.concepts, ensure_ascii=False),
            json.dumps(chapter.formulas, ensure_ascii=False),
            json.dumps(chapter.dependencies, ensure_ascii=False),
            json.dumps(chapter.section_types, ensure_ascii=False),
            chapter.study_status,
        ))
        self._conn.commit()

    # ── Prompts (cached) ───────────────────────────────────

    def get_cached_prompt(self, book_id: str, chapter_id: str, mode: str) -> str | None:
        """Get a previously generated prompt if cached."""
        row = self._conn.execute(
            "SELECT content FROM prompts WHERE book_id = ? AND chapter_id = ? AND mode = ?",
            (book_id, chapter_id, mode)
        ).fetchone()
        return row["content"] if row else None

    def save_prompt(self, book_id: str, chapter_id: str, mode: str, prompt: str):
        """Cache a generated prompt."""
        self._conn.execute(
            "INSERT OR REPLACE INTO prompts (book_id, chapter_id, mode, content) "
            "VALUES (?, ?, ?, ?)",
            (book_id, chapter_id, mode, prompt)
        )
        self._conn.commit()

    # ── Analysis (cached) ─────────────────────────────────

    def get_cached_analysis(self, book_id: str, chapter_id: str) -> dict | None:
        """Get previously computed engine analysis results."""
        row = self._conn.execute(
            "SELECT data FROM analysis WHERE book_id = ? AND chapter_id = ?",
            (book_id, chapter_id)
        ).fetchone()
        if not row:
            return None
        return json.loads(row["data"])

    def save_analysis(self, book_id: str, chapter_id: str, analysis: dict):
        """Cache engine analysis results for a chapter."""
        self._conn.execute(
            "INSERT OR REPLACE INTO analysis (book_id, chapter_id, data) "
            "VALUES (?, ?, ?)",
            (book_id, chapter_id, json.dumps(analysis, ensure_ascii=False))
        )
        self._conn.commit()

    # ── Row Conversion Helpers ─────────────────────────────

    def _row_to_book_dict(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a book dict."""
        d = dict(row)
        # Parse JSON columns
        d["chapter_ids"] = json.loads(d.get("chapter_ids", "[]"))
        d["similar_books"] = json.loads(d.get("similar_books", "[]"))
        return d

    def _row_to_chapter_dict(self, row: sqlite3.Row, include_text: bool = False) -> dict:
        """Convert a database row to a chapter dict."""
        d = dict(row)
        # Parse JSON columns
        d["sub_headings"] = json.loads(d.get("sub_headings", "[]"))
        d["concepts"] = json.loads(d.get("concepts", "[]"))
        d["formulas"] = json.loads(d.get("formulas", "[]"))
        d["dependencies"] = json.loads(d.get("dependencies", "[]"))
        d["section_types"] = json.loads(d.get("section_types", "{}"))

        if not include_text:
            d.pop("full_text", None)

        return d
