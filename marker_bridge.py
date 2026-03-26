"""
marker_bridge.py — Lightweight FastAPI bridge to marker-pdf.
Accepts PDF uploads and returns per-page markdown with LaTeX math.

Start:
    pip install marker-pdf fastapi uvicorn python-multipart
    python marker_bridge.py
"""

import io
import os
import tempfile
import traceback

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from latexfix import LatexFix
from warehouse import Warehouse
from engine import Engine
from engine.prompt_assembler import get_available_modes

app = FastAPI(title="Marker Bridge", version="2.0.0")

# Initialize the book warehouse and analysis engine
warehouse = Warehouse(raw_dir="raw_source", data_dir="warehouse/data")
engine = Engine()

# Allow requests from Chrome extensions (moz-extension:// / chrome-extension://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check — lets the extension know the server is alive."""
    return {"status": "ok", "service": "marker-bridge"}


@app.post("/convert")
def convert(
    pdf_file: UploadFile = File(...),
    pages: str = Form(default=""),
    force_ocr: bool = Form(default=True),
):
    """
    Convert a PDF (or specific pages) to Markdown via marker-pdf.

    - **pdf_file**: The PDF file (multipart upload)
    - **pages**: Comma-separated 1-based page numbers to return.
                 If empty, all pages are returned.
    - **force_ocr**: Force OCR on all lines (needed for inline math → LaTeX).
    """
    tmp_path = None
    try:
        # Save uploaded PDF to a temp file (marker needs a file path)
        content = pdf_file.file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Parse requested page numbers
        requested_pages = set()
        if pages.strip():
            for p in pages.split(","):
                p = p.strip()
                if p.isdigit():
                    requested_pages.add(int(p))

        # Run marker conversion
        markdown_text = _run_marker(tmp_path, force_ocr)

        # Apply latexfix to detect and compute LaTeX matrices
        try:
            lf = LatexFix.from_text(markdown_text).run()
            lf.auto_solve()
            markdown_text = lf.export_text()
        except Exception as lf_err:
            print(f"Warning: latexfix failed, returning original markdown. Error: {lf_err}")
            traceback.print_exc()

        # Split into per-page sections if marker inserted page breaks
        page_sections = _split_by_pages(markdown_text)

        # Filter to requested pages if specified
        if requested_pages:
            filtered = {}
            for pg_num, pg_md in page_sections.items():
                if pg_num in requested_pages:
                    filtered[str(pg_num)] = pg_md
        else:
            filtered = {str(k): v for k, v in page_sections.items()}

        return JSONResponse({
            "success": True,
            "markdown": markdown_text,
            "pages": filtered,
            "total_pages": len(page_sections),
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/latexfix")
def apply_latexfix(markdown: str = Form(...)):
    """
    Apply latexfix to a full markdown string and return the computed/fixed markdown.
    """
    try:
        lf = LatexFix.from_text(markdown).run()
        lf.auto_solve()
        fixed_markdown = lf.export_text()
        return JSONResponse({"success": True, "markdown": fixed_markdown})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ╔══════════════════════════════════════════════════════════════╗
# ║  WAREHOUSE ENDPOINTS — Book Organizer                       ║
# ╚══════════════════════════════════════════════════════════════╝


@app.post("/warehouse/upload")
def warehouse_upload(
    pdf_file: UploadFile = File(...),
    title: str = Form(default=""),
):
    """
    Upload a PDF book to the warehouse.
    Extracts markdown, detects chapters, stores everything.
    """
    tmp_path = None
    try:
        content = pdf_file.file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        book_title = title.strip() or pdf_file.filename.replace(".pdf", "").replace("_", " ").title()
        book = warehouse.ingest(tmp_path, book_title)

        return JSONResponse({
            "success": True,
            "book": book,
        })
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/warehouse/books")
def warehouse_list_books():
    """List all books in the warehouse."""
    books = warehouse.list_books()
    return JSONResponse({"success": True, "books": books})


@app.get("/warehouse/books/{book_id}")
def warehouse_get_book(book_id: str):
    """Get a single book's metadata."""
    book = warehouse.get_book(book_id)
    if not book:
        return JSONResponse(
            {"success": False, "error": "Book not found"},
            status_code=404,
        )
    return JSONResponse({"success": True, "book": book})


@app.get("/warehouse/books/{book_id}/chapters")
def warehouse_get_chapters(book_id: str):
    """Get all chapters for a book (metadata only, no full text)."""
    chapters = warehouse.get_chapters(book_id)
    return JSONResponse({"success": True, "chapters": chapters})


@app.get("/warehouse/books/{book_id}/chapters/{chapter_id}")
def warehouse_get_chapter(book_id: str, chapter_id: str):
    """Get a single chapter with full text."""
    chapter = warehouse.get_chapter(book_id, chapter_id)
    if not chapter:
        return JSONResponse(
            {"success": False, "error": "Chapter not found"},
            status_code=404,
        )
    return JSONResponse({"success": True, "chapter": chapter})


@app.delete("/warehouse/books/{book_id}")
def warehouse_delete_book(book_id: str):
    """Delete a book from the warehouse."""
    deleted = warehouse.delete_book(book_id)
    if not deleted:
        return JSONResponse(
            {"success": False, "error": "Book not found"},
            status_code=404,
        )
    return JSONResponse({"success": True})


@app.get("/warehouse/books/{book_id}/knowledge-map")
def warehouse_get_knowledge_map(book_id: str):
    """Retrieve the pre-computed Library Intelligence data for the book."""
    book = warehouse.get_book(book_id)
    if not book:
        return JSONResponse(
            {"success": False, "error": "Book not found"},
            status_code=404,
        )
    return JSONResponse({
        "success": True, 
        "knowledge_map": {
            "input_book_id": book_id,
            "matches": book.get("similar_books", [])
        }
    })


@app.get("/warehouse/search")
def warehouse_search(q: str = ""):
    """Search books by title."""
    results = warehouse.search_books(q)
    return JSONResponse({"success": True, "books": results})


@app.post("/warehouse/scan")
def warehouse_scan():
    """
    Scan raw_source/ for new PDFs and ingest them.
    Use this when PDFs are placed directly in the raw_source/ folder.
    """
    try:
        # First clear any errored books
        cleared = warehouse.clear_errors()
        if cleared:
            print(f"[Warehouse] Cleared {cleared} errored books")

        # Scan and ingest new PDFs
        new_books = warehouse.scan_raw_source()
        return JSONResponse({
            "success": True,
            "new_books": new_books,
            "count": len(new_books),
            "cleared_errors": cleared,
        })
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@app.post("/warehouse/clear-errors")
def warehouse_clear_errors():
    """Remove all books with status 'error'."""
    cleared = warehouse.clear_errors()
    return JSONResponse({"success": True, "cleared": cleared})


@app.post("/warehouse/clear-all")
def warehouse_clear_all():
    """Remove all books from the library."""
    try:
        cleared = warehouse.clear_all_books()
        return JSONResponse({"success": True, "cleared": cleared})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ╔══════════════════════════════════════════════════════════════╗
# ║  ENGINE ENDPOINTS — Deterministic Analysis & Prompt Builder ║
# ╚══════════════════════════════════════════════════════════════╝


@app.get("/engine/modes")
def engine_list_modes():
    """List available study modes."""
    return JSONResponse({"success": True, "modes": get_available_modes()})


@app.post("/engine/analyze/{book_id}/{chapter_id}")
def engine_analyze(book_id: str, chapter_id: str):
    """
    Run the deterministic engine on a chapter.
    Extracts structure, concepts, formulas, dependencies, density.
    """
    try:
        chapter = warehouse.get_chapter(book_id, chapter_id)
        if not chapter:
            return JSONResponse(
                {"success": False, "error": "Chapter not found"},
                status_code=404,
            )

        chapter_text = chapter.get("full_text", "")
        if not chapter_text:
            return JSONResponse(
                {"success": False, "error": "Chapter has no text"},
                status_code=400,
            )

        analysis = engine.analyze(chapter_text, chapter)

        return JSONResponse({
            "success": True,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "analysis": analysis,
        })
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@app.post("/engine/prompt/{book_id}/{chapter_id}")
def engine_build_prompt(
    book_id: str,
    chapter_id: str,
    mode: str = Form(default="deep_dive"),
):
    """
    Build an optimal study prompt for a chapter.

    Runs the full engine pipeline:
    chapter text → structure → concepts → formulas → dependencies
    → density → prompt assembly

    Returns the complete prompt ready to paste into any LLM.
    """
    try:
        # Load chapter
        chapter = warehouse.get_chapter(book_id, chapter_id)
        if not chapter:
            return JSONResponse(
                {"success": False, "error": "Chapter not found"},
                status_code=404,
            )

        chapter_text = chapter.get("full_text", "")
        if not chapter_text:
            return JSONResponse(
                {"success": False, "error": "Chapter has no text"},
                status_code=400,
            )

        # Load book metadata
        book = warehouse.get_book(book_id) or {}

        # Check for cached prompt
        cached = warehouse.storage.get_cached_prompt(book_id, chapter_id, mode)
        if cached:
            return JSONResponse({
                "success": True,
                "prompt": cached,
                "cached": True,
                "mode": mode,
                "word_count": len(cached.split()),
                "est_tokens": len(cached) // 4,
            })

        # Build cross-references from other books in the library
        cross_refs = _find_cross_references(book_id, chapter, warehouse)

        # Run engine
        prompt = engine.build_prompt(
            chapter_text=chapter_text,
            chapter_meta=chapter,
            book_meta=book,
            mode=mode,
            cross_references=cross_refs,
        )

        # Cache the result
        warehouse.storage.save_prompt(book_id, chapter_id, mode, prompt)

        return JSONResponse({
            "success": True,
            "prompt": prompt,
            "cached": False,
            "mode": mode,
            "word_count": len(prompt.split()),
            "est_tokens": len(prompt) // 4,
        })
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


def _find_cross_references(book_id: str, chapter: dict,
                           warehouse_inst) -> list[dict]:
    """
    Find related books and chapters using the pre-computed Intelligence Engine matches.
    """
    book = warehouse_inst.get_book(book_id)
    if not book:
        return []

    similar = book.get("similar_books", [])
    if not similar:
        return []

    cross_refs = []
    # Filter and sort the pre-computed knowledge map
    top_matches = sorted(similar, key=lambda x: x.get("total_score", 0), reverse=True)[:5]

    for match in top_matches:
        # Skip weak correlations
        if match.get("total_score", 0) < 0.2:
            continue
            
        w_id = match.get("warehouse_book_id")
        w_book = warehouse_inst.get_book(w_id)
        if not w_book:
            continue
            
        cross_refs.append({
            "book_title": w_book.get("title", ""),
            "chapter_title": "Related via Library Intelligence",
            "relevance": f"Score: {match.get('total_score')} (Concepts: {match.get('concept_score')})",
        })

    return cross_refs


# ╔══════════════════════════════════════════════════════════════╗
# ║  HELPERS                                                    ║
# ╚══════════════════════════════════════════════════════════════╝


def _run_marker(filepath: str, force_ocr: bool) -> str:
    """Run marker-pdf on the given file and return markdown string."""
    from marker.converters.pdf import PdfConverter
    from marker.config.parser import ConfigParser
    from marker.models import create_model_dict

    config = {
        "output_format": "markdown",
        "force_ocr": force_ocr,
    }

    config_parser = ConfigParser(config)
    converter = PdfConverter(
        artifact_dict=create_model_dict(),
        config=config_parser.generate_config_dict()
    )

    rendered = converter(filepath)
    return rendered.markdown


def _split_by_pages(markdown: str) -> dict:
    """
    Best-effort split of marker output into per-page sections.
    Marker doesn't always insert explicit page breaks, so we use
    horizontal rules (---) or page-break comments as delimiters.
    If no delimiters found, the entire text is page 1.
    """
    import re

    # Try splitting on horizontal rules or page-break markers
    # Marker sometimes inserts "---" between pages
    parts = re.split(r'\n-{3,}\n', markdown)

    if len(parts) <= 1:
        # No clear page breaks — return everything as page 1
        return {1: markdown.strip()}

    result = {}
    for i, part in enumerate(parts, start=1):
        stripped = part.strip()
        if stripped:
            result[i] = stripped

    return result


if __name__ == "__main__":
    import uvicorn
    print("Starting Marker Bridge on http://localhost:8001")
    print("Docs available at http://localhost:8001/docs")
    print()
    print("Warehouse endpoints:")
    print("  POST   /warehouse/upload                — Upload a PDF book")
    print("  GET    /warehouse/books                  — List all books")
    print("  GET    /warehouse/books/{id}             — Get book details")
    print("  GET    /warehouse/books/{id}/chapters    — List chapters")
    print("  GET    /warehouse/books/{id}/chapters/{c}— Get chapter text")
    print("  DELETE /warehouse/books/{id}             — Delete a book")
    print("  GET    /warehouse/search?q=...           — Search books")
    print()
    print("Engine endpoints:")
    print("  GET    /engine/modes                     — List study modes")
    print("  POST   /engine/analyze/{book}/{ch}       — Analyze a chapter")
    print("  POST   /engine/prompt/{book}/{ch}        — Build study prompt")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8001)


