"""
ingester.py — PDF → Marker → Chapter Detection → Storage pipeline.

Takes a raw PDF, processes it through the marker pipeline,
detects chapter boundaries, and stores the structured result.

Performance-optimized:
  - Singleton marker models (loaded once, reused across all books)
  - Parallel chapter analysis via ThreadPoolExecutor
  - Memory cleanup after chapter detection
  - Batched storage writes
  - Background knowledge map building
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from warehouse.models import Book, Chapter, _generate_id
from warehouse.storage import Storage
from latexfix.pipeline import LatexFix
from engine.formula_extractor import FormulaExtractor
from engine.structure_analyzer import StructureAnalyzer
from engine.concept_extractor import ConceptExtractor
from engine.metadata_extractor import MetadataExtractor


# ── Singleton Marker Models ─────────────────────────────────
# Loaded once on first use, reused for all subsequent conversions.
# This avoids the ~5-15 second model loading overhead per book.

_marker_models = None
_marker_models_lock = threading.Lock()


def _get_marker_models():
    """Get or create the singleton marker model dict."""
    global _marker_models
    if _marker_models is not None:
        return _marker_models

    with _marker_models_lock:
        # Double-check after acquiring lock
        if _marker_models is not None:
            return _marker_models

        print("[Perf] Loading marker models (one-time)...")
        t0 = time.perf_counter()
        from marker.models import create_model_dict
        _marker_models = create_model_dict()
        print(f"[Perf] Marker models loaded in {time.perf_counter() - t0:.1f}s")
        return _marker_models


class Ingester:
    """Pipeline: raw PDF → extracted markdown → detected chapters → stored."""

    # Thread pool for parallel chapter analysis (shared across invocations)
    _analysis_pool = ThreadPoolExecutor(max_workers=4)

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
        4. Analyze & store book + chapters (parallel, per-chapter error recovery)
        5. Build knowledge map (background)
        6. Return book record
        """
        pipeline_start = time.perf_counter()
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
        self.storage.save_book(book, defer_index=True)
        print(f"[Warehouse] Created book: {book.id} — {book.title}")

        # Step 3: Extract markdown
        t0 = time.perf_counter()
        markdown_text, page_count = self._extract_markdown_safe(book, str(stored_path))
        print(f"[Perf] Markdown extraction: {time.perf_counter() - t0:.1f}s")

        # Step 3.5: Auto-extract metadata from PDF + content
        t0 = time.perf_counter()
        self._extract_metadata(book, str(stored_path), markdown_text)
        print(f"[Perf] Metadata extraction: {time.perf_counter() - t0:.1f}s")

        # Step 4: Detect chapters
        t0 = time.perf_counter()
        chapters = self._detect_chapters(markdown_text, book.id)
        book.total_chapters = len(chapters)
        book.chapter_ids = [ch.id for ch in chapters]
        print(f"[Perf] Chapter detection: {time.perf_counter() - t0:.1f}s — {len(chapters)} chapters")

        # Memory cleanup: release full markdown from book object
        # It's already saved to disk by _extract_markdown_safe
        book.full_markdown = ""

        # Step 5: Analyze & save chapters (parallel, per-chapter error recovery)
        t0 = time.perf_counter()
        self._analyze_and_save_chapters(chapters)
        print(f"[Perf] Chapter analysis: {time.perf_counter() - t0:.1f}s")

        # Step 6: Mark as ready and save (flush index now)
        book.status = "ready"
        self.storage.save_book(book)

        # Step 7: Knowledge map in background (non-blocking)
        self._build_knowledge_map_background(book, chapters)

        total = time.perf_counter() - pipeline_start
        print(f"[Perf] ═══ Total ingestion: {total:.1f}s ═══")
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
        4. Analyze & store (parallel, per-chapter error recovery)
        5. Build knowledge map (background)
        """
        pipeline_start = time.perf_counter()

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
        self.storage.save_book(book, defer_index=True)
        print(f"[Warehouse] Created book: {book.id} — {book.title}")

        # Extract markdown
        t0 = time.perf_counter()
        markdown_text, page_count = self._extract_markdown_safe(book, str(pdf_path))
        print(f"[Perf] Markdown extraction: {time.perf_counter() - t0:.1f}s")

        # Auto-extract metadata
        t0 = time.perf_counter()
        self._extract_metadata(book, str(pdf_path), markdown_text)
        print(f"[Perf] Metadata extraction: {time.perf_counter() - t0:.1f}s")

        # Detect chapters
        t0 = time.perf_counter()
        chapters = self._detect_chapters(markdown_text, book.id)
        book.total_chapters = len(chapters)
        book.chapter_ids = [ch.id for ch in chapters]
        print(f"[Perf] Chapter detection: {time.perf_counter() - t0:.1f}s — {len(chapters)} chapters")

        # Memory cleanup
        book.full_markdown = ""

        # Analyze & save chapters (parallel)
        t0 = time.perf_counter()
        self._analyze_and_save_chapters(chapters)
        print(f"[Perf] Chapter analysis: {time.perf_counter() - t0:.1f}s")

        # Mark ready and flush
        book.status = "ready"
        self.storage.save_book(book)

        # Knowledge map in background
        self._build_knowledge_map_background(book, chapters)

        total = time.perf_counter() - pipeline_start
        print(f"[Perf] ═══ Total ingestion: {total:.1f}s ═══")
        return book.to_dict()

    # ── Shared pipeline helpers ─────────────────────────────

    def _extract_metadata(self, book: Book, pdf_path: str, markdown_text: str):
        """
        Auto-extract metadata from PDF properties and content.
        Only fills in fields that are empty (doesn't override user-provided values).
        """
        try:
            import pypdf

            # Read PDF info dict
            pdf_info = None
            try:
                with open(pdf_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    pdf_info = dict(reader.metadata) if reader.metadata else None
            except Exception:
                pass

            # Get first ~3000 chars as "first pages" text
            first_pages = markdown_text[:3000] if markdown_text else ""

            extractor = MetadataExtractor()
            meta = extractor.extract(
                pdf_info=pdf_info,
                first_pages_text=first_pages,
                full_text=markdown_text,
                title=book.title,
            )

            # Only fill empty fields
            if not book.author and meta.get("author"):
                book.author = meta["author"]
            if not book.subject and meta.get("subject"):
                book.subject = meta["subject"]

            # Log what we found
            found = [f"{k}={v}" for k, v in meta.items() if v]
            if found:
                print(f"[Warehouse] Auto-detected metadata: {', '.join(found)}")

        except Exception as e:
            print(f"[Warehouse] Metadata extraction failed (non-fatal): {e}")

    def _extract_markdown_safe(self, book: Book, pdf_path: str) -> tuple[str, int]:
        """
        Extract markdown with error handling.
        On success: updates book metadata and saves intermediate state.
        On failure: sets book status to 'error' and raises.
        """
        try:
            markdown_text, page_count = self._extract_markdown(pdf_path)
            # Run LatexFix to patch broken math and matrices
            try:
                markdown_text = LatexFix.from_text(markdown_text).run().export_text()
            except Exception as lf_err:
                print(f"[Warehouse] LatexFix failed, using raw markdown: {lf_err}")

            book.full_markdown = markdown_text
            book.total_pages = page_count
            book.total_words = len(markdown_text.split())
            # Save markdown to disk but defer index update
            self.storage.save_book(book, defer_index=True)
            print(f"[Warehouse] Extracted {page_count} pages, {book.total_words} words")
            return markdown_text, page_count
        except Exception as e:
            book.status = "error"
            self.storage.save_book(book)
            raise RuntimeError(f"Markdown extraction failed: {e}") from e

    def _analyze_and_save_chapters(self, chapters: list[Chapter]):
        """
        Analyze each chapter (structure, concepts, formulas) and save.
        Uses parallel processing for speed + per-chapter error recovery.
        """
        if not chapters:
            return

        def _analyze_single(ch: Chapter) -> Chapter:
            """Analyze a single chapter — runs in thread pool."""
            try:
                # Each thread gets its own analyzer instances (they're stateless)
                structure_analyzer = StructureAnalyzer()
                concept_extractor = ConceptExtractor()
                formula_extractor = FormulaExtractor()

                structure = structure_analyzer.analyze(ch.full_text)
                ch.concepts = [
                    c for c in concept_extractor.extract(ch.full_text, structure)
                    if c.get("importance") in ("high", "medium")
                ]
                ch.formulas = formula_extractor.extract(ch.full_text)
            except Exception as e:
                print(f"[Warehouse] ⚠ Analysis failed for ch {ch.number} "
                      f"'{ch.title}': {e}")
            return ch

        # Submit all chapters to thread pool
        futures = {
            self._analysis_pool.submit(_analyze_single, ch): ch
            for ch in chapters
        }

        # Collect results and save as they complete
        for future in as_completed(futures):
            ch = future.result()
            self.storage.save_chapter(ch)

    def _build_knowledge_map_background(self, book: Book, chapters: list[Chapter]):
        """
        Build knowledge map in a background daemon thread.
        This way the ingestion returns immediately while the map builds.
        """
        def _build():
            try:
                t0 = time.perf_counter()
                self._build_knowledge_map(book, chapters)
                self.storage.save_book(book)
                print(f"[Perf] Knowledge map: {time.perf_counter() - t0:.1f}s (background)")
            except Exception as e:
                print(f"[Warehouse] ⚠ Background knowledge map failed: {e}")

        thread = threading.Thread(target=_build, daemon=True)
        thread.start()

    def _build_knowledge_map(self, book: Book, chapters: list[Chapter]):
        """
        Compare this book against other books in the warehouse.
        Safely skips if no other books or if comparison fails.

        Optimized: uses summary cache to avoid loading all chapter files.
        """
        try:
            all_books = self.storage.list_books()
            other_books = [b for b in all_books if b["id"] != book.id]

            if not other_books:
                return

            from engine import Engine
            engine = Engine()

            # Use get_chapters() which returns metadata WITHOUT full_text
            # This avoids loading large .md files for every chapter
            warehouse_chapters_map = {}
            for wb in other_books:
                wb_chapters = self.storage.get_chapters(wb["id"])
                warehouse_chapters_map[wb["id"]] = wb_chapters

            input_chapters_dicts = [ch.to_dict() for ch in chapters]
            knowledge_map = engine.map_knowledge(
                input_book=book.to_dict(),
                input_chapters=input_chapters_dicts,
                warehouse_books=other_books,
                warehouse_chapters_map=warehouse_chapters_map,
            )
            book.similar_books = knowledge_map["matches"]
        except Exception as e:
            print(f"[Warehouse] ⚠ Knowledge map failed (non-fatal): {e}")
            # Non-fatal — book is still usable without knowledge map

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
        """
        Extract markdown from PDF using marker-pdf.

        Memory-optimized: writes chunks to temp files instead of
        holding all in memory, and clears GPU cache between chunks.
        Uses singleton marker models for speed.
        """
        import gc
        import pypdf

        # Reduce memory footprint of surya models to prevent cv2 OutOfMemoryError
        os.environ["LAYOUT_BATCH_SIZE"] = "2"
        os.environ["DETECTOR_BATCH_SIZE"] = "2"
        os.environ["RECOGNITION_BATCH_SIZE"] = "4"

        from marker.converters.pdf import PdfConverter
        from marker.config.parser import ConfigParser

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
        total_chunks = max(1, (total_pages + CHUNK_SIZE - 1) // CHUNK_SIZE)

        # Write chunks to temp dir to avoid holding all in memory
        import tempfile
        chunks_dir = Path(tempfile.mkdtemp(prefix="pdf_chunks_"))
        chunk_count = 0

        # Use singleton models — loaded once, reused forever
        model_dict = _get_marker_models()

        for i, start in enumerate(range(0, total_pages, CHUNK_SIZE)):
            end = min(start + CHUNK_SIZE, total_pages)
            print(f"[Warehouse] Processing chunk {i+1}/{total_chunks} "
                  f"(pages {start+1}\u2013{end} of {total_pages})...")

            config = {**config_base, "page_range": f"{start}-{end - 1}"}
            config_parser = ConfigParser(config)
            converter = PdfConverter(
                artifact_dict=model_dict,
                config=config_parser.generate_config_dict()
            )

            try:
                rendered = converter(pdf_path)
                # Write to disk immediately instead of accumulating in list
                chunk_path = chunks_dir / f"chunk_{i:04d}.md"
                chunk_path.write_text(rendered.markdown, encoding="utf-8")
                chunk_count += 1
                del rendered
            except Exception as e:
                print(f"[Warehouse] Warning: chunk {start}\u2013{end} failed: {e}")
                continue
            finally:
                del converter
                gc.collect()
                # Clear CUDA cache if GPU is available
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass

        if chunk_count == 0:
            shutil.rmtree(chunks_dir, ignore_errors=True)
            raise RuntimeError("All chunks failed during markdown extraction")

        # Reassemble from disk
        full_markdown = "\n\n".join(
            f.read_text(encoding="utf-8")
            for f in sorted(chunks_dir.glob("*.md"))
        )
        shutil.rmtree(chunks_dir, ignore_errors=True)

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
