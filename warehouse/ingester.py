"""
ingester.py — PDF → Markdown → Chapter Detection → Storage pipeline.

Takes a raw PDF, converts it to markdown via marker-pdf (no OCR),
detects chapter boundaries, and stores the structured result.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from warehouse.models import Book, Chapter, _generate_id
from warehouse.storage import Storage
from engine.formula_extractor import FormulaExtractor
from engine.structure_analyzer import StructureAnalyzer
from engine.concept_extractor import ConceptExtractor
from engine.metadata_extractor import MetadataExtractor


class Ingester:
    """Pipeline: raw PDF → extracted markdown → detected chapters → stored."""

    # Thread pool for parallel chapter analysis (shared across invocations)
    _analysis_pool = ThreadPoolExecutor(max_workers=4)

    def __init__(self, raw_dir: str, storage: Storage, config_manager: 'ConfigManager' = None):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage
        self.config_manager = config_manager

    def ingest(self, pdf_path: str, title: str | None = None,
               progress_callback=None) -> dict:
        """
        Full ingestion pipeline:
        1. Copy PDF to raw_source/
        2. Extract markdown via marker (no OCR)
        3. Detect chapters
        4. Analyze & store book + chapters (parallel)
        5. Build knowledge map (background)
        6. Return book record

        Args:
            progress_callback: Optional callable(step: str, percent: int, **kw)
                for reporting progress to the UI.
        """
        def _progress(step, percent, **kw):
            if progress_callback:
                progress_callback(step=step, percent=percent, **kw)

        pipeline_start = time.perf_counter()
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Derive title from filename if not provided
        if not title:
            title = pdf_path.stem.replace("_", " ").replace("-", " ").title()

        _progress("uploading", 5, book_title=title)

        # Step 1: Copy to raw_source/ (skip if already there)
        if pdf_path.parent.resolve() == self.raw_dir.resolve():
            stored_path = pdf_path
        else:
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
        _progress("extracting_markdown", 10, book_title=title)
        t0 = time.perf_counter()
        try:
            markdown_text, page_count = self._extract_markdown(str(stored_path))
            book.full_markdown = markdown_text
            book.total_pages = page_count
            book.total_words = len(markdown_text.split())
            self.storage.save_book(book, defer_index=True)
            print(f"[Perf] Markdown extraction: {time.perf_counter() - t0:.1f}s")
            print(f"[Warehouse] Extracted {page_count} pages, {book.total_words} words")
        except Exception as e:
            book.status = "error"
            self.storage.save_book(book)
            raise RuntimeError(f"Markdown extraction failed: {e}") from e

        # Step 3.5: Auto-extract metadata
        t0 = time.perf_counter()
        self._extract_metadata(book, str(stored_path), markdown_text)
        print(f"[Perf] Metadata extraction: {time.perf_counter() - t0:.1f}s")

        # Step 4: Detect chapters
        _progress("detecting_chapters", 50, book_title=title)
        t0 = time.perf_counter()
        chapters = self._detect_chapters(markdown_text, book.id)
        book.total_chapters = len(chapters)
        book.chapter_ids = [ch.id for ch in chapters]
        book.full_markdown = ""  # Release memory
        self.storage.save_book(book, defer_index=True)
        self.storage.flush_index()  # MUST commit book before saving chapters (FK constraint)
        print(f"[Perf] Chapter detection: {time.perf_counter() - t0:.1f}s — {len(chapters)} chapters")

        # Step 5: Analyze & save chapters (parallel)
        _progress("analyzing_chapters", 65, book_title=title)
        t0 = time.perf_counter()
        self._analyze_and_save_chapters(chapters)
        print(f"[Perf] Chapter analysis: {time.perf_counter() - t0:.1f}s")


        # Step 6: Mark as ready
        book.status = "ready"
        self.storage.save_book(book)

        # Step 7: Knowledge map in background
        self._build_knowledge_map_background(book, chapters)

        total = time.perf_counter() - pipeline_start
        print(f"[Perf] ═══ Total ingestion: {total:.1f}s ═══")
        return book.to_dict()

    def scan_directory(self, progress_callback=None) -> list[dict]:
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
                book = self.ingest(str(pdf_file), title, progress_callback=progress_callback)
                results.append(book)
                print(f"[Warehouse] ✓ Ingested: {pdf_file.name}")
            except Exception as e:
                print(f"[Warehouse] ✗ Failed to ingest {pdf_file.name}: {e}")

        return results

    # ── Pipeline Helpers ────────────────────────────────────

    def _extract_metadata(self, book: Book, pdf_path: str, markdown_text: str):
        """
        Auto-extract metadata from PDF properties and content.
        Only fills in fields that are empty (doesn't override user-provided values).
        """
        try:
            import pypdf

            pdf_info = None
            try:
                with open(pdf_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    pdf_info = dict(reader.metadata) if reader.metadata else None
            except Exception:
                pass

            first_pages = markdown_text[:3000] if markdown_text else ""

            extractor = MetadataExtractor()
            meta = extractor.extract(
                pdf_info=pdf_info,
                first_pages_text=first_pages,
                full_text=markdown_text,
                title=book.title,
            )

            if not book.author and meta.get("author"):
                book.author = meta["author"]
            if not book.subject and meta.get("subject"):
                book.subject = meta["subject"]

            found = [f"{k}={v}" for k, v in meta.items() if v]
            if found:
                print(f"[Warehouse] Auto-detected metadata: {', '.join(found)}")

        except Exception as e:
            print(f"[Warehouse] Metadata extraction failed (non-fatal): {e}")

    def _extract_markdown(self, pdf_path: str) -> tuple[str, int]:
        """
        Extract text from PDF.

        Strategy:
        1. Try pypdf first (instant for digital-native PDFs)
        2. If text is too sparse (< threshold words/page), fall back to marker
        """
        text, page_count = self._try_pypdf_extract(pdf_path)

        threshold = self.config_manager.config.pypdf_threshold if self.config_manager else 50

        if text and page_count > 0:
            words_per_page = len(text.split()) / max(page_count, 1)
            if words_per_page >= threshold:
                print(f"[Warehouse] Fast path: pypdf extracted {len(text.split())} words "
                      f"({words_per_page:.0f} w/p) — skipping marker")
                return text, page_count
            else:
                print(f"[Warehouse] Sparse text ({words_per_page:.0f} w/p) — falling back to marker")

        return self._marker_extract(pdf_path)

    def _try_pypdf_extract(self, pdf_path: str) -> tuple[str, int]:
        """Fast extraction using pypdf (works for digital-native PDFs)."""
        # Only check fast path if enabled in config
        fast_path = True
        threshold = 50
        if self.config_manager:
            fast_path = self.config_manager.config.fast_path_enabled
            threshold = self.config_manager.config.pypdf_threshold

        if fast_path:
            try:
                import pypdf
                with open(pdf_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    total_pypdf_pages = len(reader.pages)
                    
                    # Estimate if it's digital native vs scanned image
                    # We check first few pages and require a decent word/page ratio
                    sample_size = min(total_pypdf_pages, 5)
                    sample_words = 0
                    
                    for i in range(sample_size):
                        text = reader.pages[i].extract_text()
                        if text:
                            sample_words += len(text.split())
                    
                    # If average words per page > threshold, we assume it's digital native text
                    # and we skip the heavy marker OCR
                    if sample_words / max(sample_size, 1) >= threshold:
                        pages_text = []
                        for i, page in enumerate(reader.pages):
                            page_text = page.extract_text() or ""
                            if page_text.strip():
                                pages_text.append(f"## Page {i + 1}\n\n{page_text.strip()}")

                        if not pages_text:
                            return "", total_pypdf_pages

                        return "\n\n---\n\n".join(pages_text), total_pypdf_pages
            except Exception as e:
                print(f"[Warehouse] pypdf extraction failed: {e}")
        return "", 0

    def _marker_extract(self, pdf_path: str) -> tuple[str, int]:
        """
        Slow but accurate extraction using marker-pdf.
        Runs layout recognition + text extraction (no OCR).
        """
        from marker.converters.pdf import PdfConverter
        from marker.config.parser import ConfigParser
        from marker.models import create_model_dict

        config = {
            "output_format": "markdown",
            "force_ocr": False,
        }

        config_parser = ConfigParser(config)
        converter = PdfConverter(
            artifact_dict=create_model_dict(),
            config=config_parser.generate_config_dict(),
        )

        rendered = converter(pdf_path)
        markdown_text = rendered.markdown

        # Count pages from PDF
        try:
            import pypdf
            with open(pdf_path, "rb") as f:
                page_count = len(pypdf.PdfReader(f).pages)
        except Exception:
            page_breaks = len(re.findall(r'\n-{3,}\n', markdown_text))
            page_count = max(page_breaks + 1, 1)

        return markdown_text, page_count

    def _analyze_and_save_chapters(self, chapters: list[Chapter]):
        """
        Analyze each chapter (structure, concepts, formulas) and save.
        Uses parallel processing + per-chapter error recovery.
        """
        if not chapters:
            return

        def _analyze_single(ch: Chapter) -> Chapter:
            """Analyze a single chapter — runs in thread pool."""
            try:
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

        futures = {
            self._analysis_pool.submit(_analyze_single, ch): ch
            for ch in chapters
        }

        saved = 0
        for future in as_completed(futures):
            ch = future.result()
            try:
                self.storage.save_chapter(ch, auto_commit=False)
                saved += 1
            except Exception as e:
                print(f"[Warehouse] ✗ save_chapter failed for ch {ch.number} "
                      f"'{ch.title}' (book_id={ch.book_id}): {e}")

        self.storage.flush_index()
        print(f"[Warehouse] Saved {saved}/{len(chapters)} chapters")

    def _build_knowledge_map_background(self, book: Book, chapters: list[Chapter]):
        """Build knowledge map in a background daemon thread."""
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
        """Compare this book against other books in the warehouse."""
        try:
            all_books = self.storage.list_books()
            other_books = [b for b in all_books if b["id"] != book.id]

            if not other_books:
                return

            from engine import Engine
            engine = Engine()

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

    # ── Store raw PDF ───────────────────────────────────────

    def _store_raw_pdf(self, pdf_path: Path) -> Path:
        """Copy PDF to raw_source/ with a unique name."""
        with open(pdf_path, "rb") as f:
            file_hash = hashlib.md5(f.read(8192)).hexdigest()[:8]

        dest_name = f"{file_hash}_{pdf_path.name}"
        dest_path = self.raw_dir / dest_name

        if not dest_path.exists():
            shutil.copy2(pdf_path, dest_path)

        return dest_path

    # ── Chapter Detection ───────────────────────────────────

    def _detect_chapters(self, markdown: str, book_id: str) -> list[Chapter]:
        """
        Detect chapter boundaries in the markdown.

        Strategy (in priority order):
        1. Look for '# Chapter N' or '# Part N' patterns
        2. Look for consistent top-level headings (# Heading)
        3. Fall back to page-break splitting
        """
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

            try:
                ch_num = int(ch_num_str)
            except ValueError:
                ch_num = i + 1

            start_idx = match.start()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            full_text = markdown[start_idx:end_idx].strip()

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
                sub_headings=sub_headings[:20],
            )
            chapters.append(chapter)

        return chapters

    def _detect_from_top_headings(self, markdown: str, book_id: str) -> list[Chapter]:
        """Fall back to splitting by top-level headings (# Heading)."""
        pattern = re.compile(r'^#\s+(.+)$', re.MULTILINE)
        matches = list(pattern.finditer(markdown))

        if len(matches) < 2:
            return []

        skip_titles = {
            "table of contents", "contents", "preface", "foreword",
            "acknowledgments", "bibliography", "references", "index",
            "appendix", "about the author", "glossary",
        }

        chapters = []
        for i, match in enumerate(matches):
            title = match.group(1).strip()

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
        """Last resort: split by page break markers (---)."""
        sections = re.split(r'\n-{3,}\n', markdown)

        significant = [
            (i, s.strip()) for i, s in enumerate(sections)
            if len(s.split()) > 100
        ]

        if not significant:
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
