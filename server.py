"""
server.py — FastAPI backend for the PDF Reader & Study Prompt Engine.

Start:
    python server.py

Endpoints:
    /docs                                   — Interactive API docs
    /warehouse/upload                       — Upload a PDF book
    /warehouse/books                        — List all books
    /warehouse/books/{id}                   — Get book details
    /warehouse/books/{id}/chapters          — List chapters
    /warehouse/books/{id}/chapters/{c}      — Get chapter text
    /warehouse/scan                         — Scan raw_source/ for new PDFs
    /engine/modes                           — List study modes
    /engine/analyze/{book}/{ch}             — Analyze a chapter
    /engine/prompt/{book}/{ch}              — Build study prompt
"""

import hashlib
import os
import tempfile
import threading
import time
import traceback

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from warehouse import Warehouse
from engine import Engine
from engine.prompt_assembler import get_available_modes

app = FastAPI(title="PDF Reader", version="3.0.0")

# Initialize the book warehouse and analysis engine
warehouse = Warehouse(raw_dir="raw_source", data_dir="warehouse/data")
engine = Engine()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve web UI static files
_web_dir = os.path.join(os.path.dirname(__file__), "web")
if os.path.isdir(_web_dir):
    app.mount("/web", StaticFiles(directory=_web_dir), name="web")

# ── Background Ingestion Infrastructure ──────────────────

_ingestion_jobs: dict[str, dict] = {}
_ingestion_lock = threading.Lock()


def _update_job(job_id: str, **kwargs):
    """Thread-safe update of a job's progress state."""
    with _ingestion_lock:
        if job_id in _ingestion_jobs:
            _ingestion_jobs[job_id].update(**kwargs)


def _run_ingest_background(job_id: str, pdf_path: str, title: str, cleanup_path: str | None = None):
    """Run the full ingestion pipeline in a background thread."""
    try:
        def on_progress(step, percent, **kw):
            _update_job(job_id, step=step, percent=percent, **kw)

        book = warehouse.ingest(pdf_path, title, progress_callback=on_progress)
        _update_job(job_id, status="done", percent=100, book_id=book["id"],
                    book_title=book.get("title", ""))
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="error", error=str(e))
    finally:
        if cleanup_path and os.path.exists(cleanup_path):
            os.unlink(cleanup_path)


def _run_scan_background(job_id: str):
    """Run the scan pipeline in a background thread."""
    try:
        def on_progress(step, percent, **kw):
            _update_job(job_id, step=step, percent=percent, **kw)

        _update_job(job_id, step="clearing_errors", percent=5)
        cleared = warehouse.clear_errors()

        _update_job(job_id, step="scanning_directory", percent=15)
        new_books = warehouse.scan_raw_source(progress_callback=on_progress)

        _update_job(job_id, status="done", percent=100,
                    count=len(new_books), cleared_errors=cleared,
                    new_books=new_books)
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="error", error=str(e))


# ╔══════════════════════════════════════════════════════════════╗
# ║  HEALTH                                                      ║
# ╚══════════════════════════════════════════════════════════════╝


@app.get("/")
def root():
    """Serve the web UI."""
    index = os.path.join(_web_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return JSONResponse({"message": "PDF Reader API", "docs": "/docs"})


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok", "service": "pdf-reader"}


# ╔══════════════════════════════════════════════════════════════╗
# ║  WAREHOUSE ENDPOINTS — Book Organizer                       ║
# ╚══════════════════════════════════════════════════════════════╝


@app.post("/warehouse/upload")
def warehouse_upload(
    pdf_file: UploadFile = File(...),
    title: str = Form(default=""),
    background: str = Form(default="true"),
):
    """
    Upload a PDF book to the warehouse.

    If background=true (default): starts processing in background,
    returns immediately with a job_id for progress tracking.
    If background=false: blocks until processing completes.
    """
    tmp_path = None
    try:
        content = pdf_file.file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        book_title = title.strip() or pdf_file.filename.replace(".pdf", "").replace("_", " ").title()

        if background.lower() == "false":
            try:
                book = warehouse.ingest(tmp_path, book_title)
                return JSONResponse({"success": True, "book": book})
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        # Background mode
        job_id = hashlib.md5(content[:4096] + book_title.encode()).hexdigest()[:12]

        with _ingestion_lock:
            _ingestion_jobs[job_id] = {
                "status": "started",
                "step": "uploading",
                "percent": 0,
                "book_id": None,
                "error": None,
            }

        thread = threading.Thread(
            target=_run_ingest_background,
            args=(job_id, tmp_path, book_title, tmp_path),
            daemon=True,
        )
        thread.start()

        return JSONResponse({"success": True, "job_id": job_id})

    except Exception as e:
        traceback.print_exc()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=500,
        )


@app.get("/warehouse/progress/{job_id}")
def warehouse_progress(job_id: str):
    """SSE endpoint — stream real-time progress updates for a background job."""
    import json

    def event_stream():
        last_state_str = None
        while True:
            with _ingestion_lock:
                state = _ingestion_jobs.get(job_id)
            if state is None:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break

            state_str = json.dumps(state, default=str)
            if state_str != last_state_str:
                yield f"data: {state_str}\n\n"
                last_state_str = state_str

                if state["status"] in ("done", "error"):
                    with _ingestion_lock:
                        _ingestion_jobs.pop(job_id, None)
                    break

            time.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/warehouse/job/{job_id}")
def warehouse_job_status(job_id: str):
    """Polling fallback — get current status of a background job."""
    with _ingestion_lock:
        state = _ingestion_jobs.get(job_id)
    if state is None:
        return JSONResponse({"success": False, "error": "Job not found"}, status_code=404)
    return JSONResponse({"success": True, **state})


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


@app.post("/warehouse/scan")
def warehouse_scan(background: str = "true"):
    """Scan raw_source/ for new PDFs and ingest them."""
    try:
        if background.lower() == "false":
            cleared = warehouse.clear_errors()
            new_books = warehouse.scan_raw_source()
            return JSONResponse({
                "success": True,
                "new_books": new_books,
                "count": len(new_books),
                "cleared_errors": cleared,
            })

        job_id = f"scan_{int(time.time())}"

        with _ingestion_lock:
            _ingestion_jobs[job_id] = {
                "status": "started",
                "step": "preparing_scan",
                "percent": 0,
                "error": None,
            }

        thread = threading.Thread(
            target=_run_scan_background,
            args=(job_id,),
            daemon=True,
        )
        thread.start()

        return JSONResponse({"success": True, "job_id": job_id})

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


@app.get("/warehouse/config")
def warehouse_get_config():
    """Get the current configuration variables for the warehouse control unit."""
    try:
        config_data = warehouse.config_manager.config.to_dict()
        return JSONResponse({"success": True, "config": config_data})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.patch("/warehouse/config")
def warehouse_update_config(
    fast_path_enabled: str = Form(default=None),
    pypdf_threshold: str = Form(default=None),
    export_dir: str = Form(default=None)
):
    """Update configuration variables via the control unit."""
    try:
        updates = {}
        if fast_path_enabled is not None:
            updates["fast_path_enabled"] = fast_path_enabled.lower() == "true"
        if pypdf_threshold is not None:
            updates["pypdf_threshold"] = int(pypdf_threshold)
        if export_dir is not None:
            updates["export_dir"] = export_dir

        if updates:
            warehouse.config_manager.update(updates)

        return JSONResponse({"success": True, "config": warehouse.config_manager.config.to_dict()})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.patch("/warehouse/books/{book_id}/chapters/{chapter_id}/status")
def warehouse_update_chapter_status(book_id: str, chapter_id: str, status: str = Form(...)):
    """Update study status of a chapter."""
    try:
        if status not in ("not_started", "in_progress", "completed"):
            return JSONResponse({"success": False, "error": "Invalid status"}, status_code=400)

        chapter = warehouse.get_chapter(book_id, chapter_id)
        if not chapter:
            return JSONResponse({"success": False, "error": "Chapter not found"}, status_code=404)

        chapter["study_status"] = status

        from warehouse.models import Chapter
        ch_model = Chapter.from_dict(chapter)
        warehouse.storage.save_chapter(ch_model)

        return JSONResponse({"success": True, "status": status})
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
    Returns cached results if available.
    """
    try:
        cached = warehouse.storage.get_cached_analysis(book_id, chapter_id)
        if cached:
            return JSONResponse({
                "success": True,
                "book_id": book_id,
                "chapter_id": chapter_id,
                "analysis": cached,
                "cached": True,
            })

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

        warehouse.storage.save_analysis(book_id, chapter_id, analysis)

        return JSONResponse({
            "success": True,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "analysis": analysis,
            "cached": False,
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
    Returns the complete prompt ready to paste into any LLM.
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

        book = warehouse.get_book(book_id) or {}

        # Check cache
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

        prompt = engine.build_prompt(
            chapter_text=chapter_text,
            chapter_meta=chapter,
            book_meta=book,
            mode=mode,
        )

        warehouse.storage.save_prompt(book_id, chapter_id, mode, prompt)

        # Also write the final final output to the configured export dir
        try:
            export_path = os.path.join(warehouse.config_manager.config.export_dir, book.get("title", "Unknown Book"))
            os.makedirs(export_path, exist_ok=True)
            filename = f"Ch_{chapter.get('number', '00')}_{mode}.txt"
            with open(os.path.join(export_path, filename), "w", encoding="utf-8") as f:
                f.write(prompt)
        except Exception as ex:
            print(f"[Engine] Failed to write prompt to export directory: {ex}")

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


# ╔══════════════════════════════════════════════════════════════╗
# ║  MAIN                                                       ║
# ╚══════════════════════════════════════════════════════════════╝


if __name__ == "__main__":
    import uvicorn
    print("Starting PDF Reader on http://localhost:8001")
    print("API Docs: http://localhost:8001/docs")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8001)
