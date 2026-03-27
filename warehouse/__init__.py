"""
warehouse — Book storage, ingestion, and chapter analysis.

Usage:
    from warehouse import Warehouse
    wh = Warehouse()
    book = wh.ingest("path/to/book.pdf")
    chapters = wh.get_chapters(book.id)
"""

from warehouse.models import Book, Chapter
from warehouse.storage import Storage
from warehouse.ingester import Ingester
from warehouse.config import ConfigManager


class Warehouse:
    """Top-level API for the book warehouse."""

    def __init__(self, raw_dir: str = "raw_source", data_dir: str = "warehouse/data"):
        self.config_manager = ConfigManager(f"{data_dir}/config.json")
        self.storage = Storage(data_dir)
        self.ingester = Ingester(raw_dir, self.storage, self.config_manager)

    # ── Books ───────────────────────────────────────────────
    def list_books(self) -> list[dict]:
        """Return all books in the warehouse."""
        return self.storage.list_books()

    def get_book(self, book_id: str) -> dict | None:
        """Get a single book by ID."""
        return self.storage.get_book(book_id)

    def delete_book(self, book_id: str) -> bool:
        """Remove a book and all its chapters from the warehouse."""
        return self.storage.delete_book(book_id)

    def clear_all_books(self) -> int:
        """Remove all books from the warehouse."""
        return self.storage.clear_all_books()

    # ── Ingestion ───────────────────────────────────────────
    def ingest(self, pdf_path: str, title: str | None = None,
               progress_callback=None) -> dict:
        """
        Ingest a PDF book:
        1. Copy PDF to raw_source/
        2. Extract markdown via marker
        3. Detect chapters
        4. Store everything

        Returns the book record.
        """
        return self.ingester.ingest(pdf_path, title, progress_callback=progress_callback)

    # ── Chapters ────────────────────────────────────────────
    def get_chapters(self, book_id: str) -> list[dict]:
        """Get all chapters for a book."""
        return self.storage.get_chapters(book_id)

    def get_chapter(self, book_id: str, chapter_id: str) -> dict | None:
        """Get a single chapter with full text."""
        return self.storage.get_chapter(book_id, chapter_id)

    # ── Search ──────────────────────────────────────────────
    def search_books(self, query: str) -> list[dict]:
        """Search books by title (simple substring match)."""
        return [
            b for b in self.storage.list_books()
            if query.lower() in b["title"].lower()
        ]

    # ── Scan raw_source/ ───────────────────────────────────
    def scan_raw_source(self, progress_callback=None) -> list[dict]:
        """
        Scan raw_source/ for PDFs that aren't yet in the warehouse.
        Ingest each one. Returns list of newly ingested books.
        """
        return self.ingester.scan_directory(progress_callback=progress_callback)

    # ── Maintenance ────────────────────────────────────────
    def clear_errors(self) -> int:
        """Remove all books with status 'error'."""
        all_books = self.storage.list_books()
        errors = [b for b in all_books if b.get("status") == "error"]
        for book in errors:
            self.storage.delete_book(book["id"])
        return len(errors)

