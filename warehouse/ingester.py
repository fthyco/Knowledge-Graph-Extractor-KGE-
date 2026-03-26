"""
ingester.py — PDF → Marker → Chapter Detection → Storage pipeline.

Takes a raw PDF, processes it through the marker pipeline,
detects chapter boundaries, and stores the structured result.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

from warehouse.models import Book, Chapter, _generate_id
from warehouse.storage import Storage
from latexfix.pipeline import LatexFix
from engine.formula_extractor import FormulaExtractor
from engine.structure_analyzer import StructureAnalyzer
from engine.concept_extractor import ConceptExtractor


class Ingester:
    """Pipeline: raw PDF → extracted markdown → detected chapters → stored."""

    def __init__(self, raw_dir: str, storage: Storage):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage

    def ingest(self, pdf_path: str, title: str | None = None) -> dict:
        """
        Full ingestion pipeline:
        1. Copy PDF to raw_source/
        2. Extract markdown via marker
        3. Detect chapters
        4. Store book + chapters
        5. Return book record
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Derive title from filename if not provided
        if not title:
            title = pdf_path.stem.replace("_", " ").replace("-", " ").title()

        # Step 1: Copy to raw_source/
        stored_path = self._store_raw_pdf(pdf_path)
        print(f"[Warehouse] Stored PDF: {stored_path}")

        # Step 2: Create book record
        book = Book.create(
            title=title,
            filename=pdf_path.name,
            pdf_path=str(stored_path),
        )
        book.status = "processing"
        self.storage.save_book(book)
        print(f"[Warehouse] Created book: {book.id} — {book.title}")

        # Step 3: Extract markdown
        try:
            markdown_text, page_count = self._extract_markdown(str(stored_path))
            # Run LatexFix to patch broken math and matrices
            markdown_text = LatexFix.from_text(markdown_text).run().export_text()
            
            book.full_markdown = markdown_text
            book.total_pages = page_count
            book.total_words = len(markdown_text.split())
            print(f"[Warehouse] Extracted {page_count} pages, {book.total_words} words")
        except Exception as e:
            book.status = "error"
            self.storage.save_book(book)
            raise RuntimeError(f"Markdown extraction/processing failed: {e}") from e

        # Step 4: Detect chapters
        chapters = self._detect_chapters(markdown_text, book.id)
        book.total_chapters = len(chapters)
        book.chapter_ids = [ch.id for ch in chapters]
        print(f"[Warehouse] Detected {len(chapters)} chapters")

        # Step 5: Extract formulas, concepts, and structure. Save everything
        formula_extractor = FormulaExtractor()
        structure_analyzer = StructureAnalyzer()
        concept_extractor = ConceptExtractor()

        for ch in chapters:
            structure = structure_analyzer.analyze(ch.full_text)
            ch.concepts = [
                c for c in concept_extractor.extract(ch.full_text, structure)
                if c.get("importance") in ("high", "medium")
            ]
            ch.formulas = formula_extractor.extract(ch.full_text)
            self.storage.save_chapter(ch)

        book.status = "ready"
        
        # Only run if warehouse has other books
        all_books = self.storage.list_books()
        other_books = [b for b in all_books if b["id"] != book.id]

        if other_books:
            from engine import Engine
            engine = Engine()

            # Build chapters map for warehouse books
            warehouse_chapters_map = {}
            for wb in other_books:
                wb_chapters = []
                for ch_id in wb.get("chapter_ids", []):
                    ch_dict = self.storage.get_chapter(wb["id"], ch_id)
                    if ch_dict:
                        wb_chapters.append(ch_dict)
                warehouse_chapters_map[wb["id"]] = wb_chapters

            input_chapters_dicts = [ch.to_dict() for ch in chapters]
            knowledge_map = engine.map_knowledge(
                input_book=book.to_dict(),
                input_chapters=input_chapters_dicts,
                warehouse_books=other_books,
                warehouse_chapters_map=warehouse_chapters_map,
            )
            book.similar_books = knowledge_map["matches"]

        self.storage.save_book(book)

        return book.to_dict()

    def scan_directory(self) -> list[dict]:
        """
        Scan raw_source/ for PDFs not yet in the warehouse.
        Process each one and return the list of new books.
        """
        existing = self.storage.list_books()
        existing_files = {b.get("raw_pdf_path", "") for b in existing}

        results = []
        for pdf_file in sorted(self.raw_dir.glob("*.pdf")):
            # Skip if already ingested
            rel_path = str(pdf_file)
            if rel_path in existing_files or any(pdf_file.name in f for f in existing_files):
                print(f"[Warehouse] Skipping (already ingested): {pdf_file.name}")
                continue

            try:
                title = pdf_file.stem.replace("_", " ").replace("-", " ").title()
                book = self.ingest_local(pdf_file, title)
                results.append(book)
                print(f"[Warehouse] ✓ Ingested: {pdf_file.name}")
            except Exception as e:
                print(f"[Warehouse] ✗ Failed to ingest {pdf_file.name}: {e}")

        return results

    def ingest_local(self, pdf_path: Path, title: str | None = None) -> dict:
        """
        Ingest a PDF that's ALREADY in raw_source/ (no copy needed).
        1. Create book record
        2. Extract markdown via marker
        3. Detect chapters
        4. Store everything
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if not title:
            title = pdf_path.stem.replace("_", " ").replace("-", " ").title()

        # Create book record
        book = Book.create(
            title=title,
            filename=pdf_path.name,
            pdf_path=str(pdf_path),
        )
        book.status = "processing"
        self.storage.save_book(book)
        print(f"[Warehouse] Created book: {book.id} — {book.title}")

        # Extract markdown
        try:
            markdown_text, page_count = self._extract_markdown(str(pdf_path))
            # Run LatexFix to patch broken math and matrices
            markdown_text = LatexFix.from_text(markdown_text).run().export_text()
            
            book.full_markdown = markdown_text
            book.total_pages = page_count
            book.total_words = len(markdown_text.split())
            print(f"[Warehouse] Extracted {page_count} pages, {book.total_words} words")
        except Exception as e:
            book.status = "error"
            self.storage.save_book(book)
            raise RuntimeError(f"Markdown extraction/processing failed: {e}") from e

        # Detect chapters
        chapters = self._detect_chapters(markdown_text, book.id)
        book.total_chapters = len(chapters)
        book.chapter_ids = [ch.id for ch in chapters]
        print(f"[Warehouse] Detected {len(chapters)} chapters")

        # Save everything
        formula_extractor = FormulaExtractor()
        structure_analyzer = StructureAnalyzer()
        concept_extractor = ConceptExtractor()

        for ch in chapters:
            structure = structure_analyzer.analyze(ch.full_text)
            ch.concepts = [
                c for c in concept_extractor.extract(ch.full_text, structure)
                if c.get("importance") in ("high", "medium")
            ]
            ch.formulas = formula_extractor.extract(ch.full_text)
            self.storage.save_chapter(ch)

        book.status = "ready"
        
        # Only run if warehouse has other books
        all_books = self.storage.list_books()
        other_books = [b for b in all_books if b["id"] != book.id]

        if other_books:
            from engine import Engine
            engine = Engine()

            # Build chapters map for warehouse books
            warehouse_chapters_map = {}
            for wb in other_books:
                wb_chapters = []
                for ch_id in wb.get("chapter_ids", []):
                    ch_dict = self.storage.get_chapter(wb["id"], ch_id)
                    if ch_dict:
                        wb_chapters.append(ch_dict)
                warehouse_chapters_map[wb["id"]] = wb_chapters

            input_chapters_dicts = [ch.to_dict() for ch in chapters]
            knowledge_map = engine.map_knowledge(
                input_book=book.to_dict(),
                input_chapters=input_chapters_dicts,
                warehouse_books=other_books,
                warehouse_chapters_map=warehouse_chapters_map,
            )
            book.similar_books = knowledge_map["matches"]

        self.storage.save_book(book)

        return book.to_dict()

    # ── Step 1: Store raw PDF ───────────────────────────────

    def _store_raw_pdf(self, pdf_path: Path) -> Path:
        """Copy PDF to raw_source/ with a unique name."""
        # Use hash prefix to avoid collisions
        with open(pdf_path, "rb") as f:
            file_hash = hashlib.md5(f.read(8192)).hexdigest()[:8]

        dest_name = f"{file_hash}_{pdf_path.name}"
        dest_path = self.raw_dir / dest_name

        if not dest_path.exists():
            shutil.copy2(pdf_path, dest_path)

        return dest_path

    # ── Step 2: Extract markdown ────────────────────────────

    def _get_optimal_chunk_size(self) -> int:
        """Calculate safe chunk size based on available RAM."""
        import psutil

        available_gb = psutil.virtual_memory().available / (1024 ** 3)
        print(f"[Warehouse] Available RAM: {available_gb:.1f} GB")

        # Each page needs ~50MB processing headroom (image + model tensors)
        # Keep 2GB buffer for OS + server
        usable_gb = max(0, available_gb - 2.0)
        chunk = int((usable_gb * 1024) / 50)

        # Hard bounds: never below 10, never above 80
        return max(10, min(chunk, 80))

    def _extract_markdown(self, pdf_path: str) -> tuple[str, int]:
        """Extract markdown from PDF using marker-pdf."""
        import gc
        import pypdf

        # Reduce memory footprint of surya models to prevent cv2 OutOfMemoryError
        os.environ["LAYOUT_BATCH_SIZE"] = "2"
        os.environ["DETECTOR_BATCH_SIZE"] = "2"
        os.environ["RECOGNITION_BATCH_SIZE"] = "4"

        from marker.converters.pdf import PdfConverter
        from marker.config.parser import ConfigParser
        from marker.models import create_model_dict

        # Count total pages first
        with open(pdf_path, "rb") as f:
            total_pages = len(pypdf.PdfReader(f).pages)

        config_base = {
            "output_format": "markdown",
            "force_ocr": False,
            "pdftext_workers": 1,
            "batch_multiplier": 1,
        }

        CHUNK_SIZE = self._get_optimal_chunk_size()
        all_markdown_parts = []

        model_dict = create_model_dict()  # Load models only once

        for start in range(0, total_pages, CHUNK_SIZE):
            end = min(start + CHUNK_SIZE, total_pages)
            print(f"[Warehouse] Processing pages {start+1}–{end} of {total_pages}...")

            config = {**config_base, "page_range": f"{start}-{end - 1}"}
            config_parser = ConfigParser(config)
            converter = PdfConverter(
                artifact_dict=model_dict,
                config=config_parser.generate_config_dict()
            )

            try:
                rendered = converter(pdf_path)
                all_markdown_parts.append(rendered.markdown)
            except Exception as e:
                print(f"[Warehouse] Warning: chunk {start}–{end} failed: {e}")
                continue
            finally:
                del converter
                gc.collect()

        if not all_markdown_parts:
            raise RuntimeError("All chunks failed during markdown extraction")

        full_markdown = "\n\n".join(all_markdown_parts)

        # Estimate page count from page break markers
        page_breaks = len(re.findall(r'\n-{3,}\n', full_markdown))
        page_count = max(page_breaks + 1, total_pages)

        return full_markdown, page_count

    # ── Step 3: Detect chapters ─────────────────────────────

    def _detect_chapters(self, markdown: str, book_id: str) -> list[Chapter]:
        """
        Detect chapter boundaries in the markdown.

        Strategy (in priority order):
        1. Look for TOC (Table of Contents) and parse it
        2. Look for '# Chapter N' or '# Part N' patterns
        3. Look for consistent top-level headings (# Heading)
        4. Fall back to page-break splitting
        """
        # Try each strategy in order
        chapters = self._detect_from_chapter_headings(markdown, book_id)
        if not chapters:
            chapters = self._detect_from_top_headings(markdown, book_id)
        if not chapters:
            chapters = self._detect_from_page_breaks(markdown, book_id)

        return chapters

    def _detect_from_chapter_headings(self, markdown: str, book_id: str) -> list[Chapter]:
        """
        Look for explicit chapter markers:
        - # Chapter 1: Title
        - # Part I: Title
        - # 1. Title
        - # 1 Title
        """
        pattern = re.compile(
            r'^(#{1,2})\s+'
            r'(?:'
            r'(?:Chapter|CHAPTER|Part|PART)\s+(\d+|[IVXLC]+)'
            r'[\s:.—–-]*'
            r'(.+?)'
            r'|'
            r'(\d+)\.\s+(.+?)'
            r'|'
            r'(\d+)\s+(.+?)'
            r')\s*$',
            re.MULTILINE
        )

        matches = list(pattern.finditer(markdown))
        if len(matches) < 2:
            return []

        chapters = []
        for i, match in enumerate(matches):
            heading_level = len(match.group(1))

            # Extract chapter number and title from whichever group matched
            if match.group(2):
                ch_num_str = match.group(2)
                ch_title = match.group(3).strip()
            elif match.group(4):
                ch_num_str = match.group(4)
                ch_title = match.group(5).strip()
            elif match.group(6):
                ch_num_str = match.group(6)
                ch_title = match.group(7).strip()
            else:
                continue

            # Convert Roman numerals or parse int
            try:
                ch_num = int(ch_num_str)
            except ValueError:
                ch_num = i + 1

            # Calculate text range
            start_idx = match.start()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            full_text = markdown[start_idx:end_idx].strip()

            # Extract sub-headings within this chapter
            sub_headings = re.findall(
                r'^#{2,3}\s+(.+)$',
                full_text,
                re.MULTILINE
            )

            ch_id = _generate_id(f"{book_id}:ch{ch_num}:{ch_title}")
            chapter = Chapter(
                id=ch_id,
                book_id=book_id,
                number=ch_num,
                title=ch_title,
                level=heading_level,
                start_index=start_idx,
                end_index=end_idx,
                word_count=len(full_text.split()),
                full_text=full_text,
                sub_headings=sub_headings[:20],  # cap at 20
            )
            chapters.append(chapter)

        return chapters

    def _detect_from_top_headings(self, markdown: str, book_id: str) -> list[Chapter]:
        """
        Fall back to splitting by top-level headings (# Heading).
        Useful for books that don't use 'Chapter N' format.
        """
        pattern = re.compile(r'^#\s+(.+)$', re.MULTILINE)
        matches = list(pattern.finditer(markdown))

        if len(matches) < 2:
            return []

        chapters = []
        for i, match in enumerate(matches):
            title = match.group(1).strip()

            # Skip TOC, preface, index, bibliography
            skip_titles = [
                "table of contents", "contents", "preface", "foreword",
                "acknowledgments", "bibliography", "references", "index",
                "appendix", "about the author", "glossary",
            ]
            if title.lower() in skip_titles:
                continue

            start_idx = match.start()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            full_text = markdown[start_idx:end_idx].strip()

            sub_headings = re.findall(r'^#{2,3}\s+(.+)$', full_text, re.MULTILINE)

            ch_id = _generate_id(f"{book_id}:h:{title}")
            chapter = Chapter(
                id=ch_id,
                book_id=book_id,
                number=len(chapters) + 1,
                title=title,
                level=1,
                start_index=start_idx,
                end_index=end_idx,
                word_count=len(full_text.split()),
                full_text=full_text,
                sub_headings=sub_headings[:20],
            )
            chapters.append(chapter)

        return chapters

    def _detect_from_page_breaks(self, markdown: str, book_id: str) -> list[Chapter]:
        """
        Last resort: split by page break markers (---) and treat
        each significant section as a chapter.
        """
        sections = re.split(r'\n-{3,}\n', markdown)

        # Filter out very small sections (likely headers/footers)
        significant = [
            (i, s.strip()) for i, s in enumerate(sections)
            if len(s.split()) > 100
        ]

        if not significant:
            # If nothing is significant, treat entire document as one chapter
            ch_id = _generate_id(f"{book_id}:full")
            return [Chapter(
                id=ch_id,
                book_id=book_id,
                number=1,
                title="Full Document",
                level=1,
                start_index=0,
                end_index=len(markdown),
                word_count=len(markdown.split()),
                full_text=markdown,
            )]

        chapters = []
        for idx, (orig_idx, text) in enumerate(significant):
            # Try to extract a title from the first line
            first_line = text.split("\n")[0].strip()
            title = re.sub(r'^#+\s*', '', first_line)[:80] or f"Section {idx + 1}"

            sub_headings = re.findall(r'^#{2,3}\s+(.+)$', text, re.MULTILINE)

            ch_id = _generate_id(f"{book_id}:sec{idx + 1}:{title}")
            chapter = Chapter(
                id=ch_id,
                book_id=book_id,
                number=idx + 1,
                title=title,
                level=1,
                start_index=0,
                end_index=len(text),
                word_count=len(text.split()),
                full_text=text,
                sub_headings=sub_headings[:20],
            )
            chapters.append(chapter)

        return chapters
