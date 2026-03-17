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

app = FastAPI(title="Marker Bridge", version="1.0.0")

# Allow requests from Chrome extensions (moz-extension:// / chrome-extension://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check — lets the extension know the server is alive."""
    return {"status": "ok", "service": "marker-bridge"}


@app.post("/convert")
async def convert(
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
        content = await pdf_file.read()
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


def _run_marker(filepath: str, force_ocr: bool) -> str:
    """Run marker-pdf on the given file and return markdown string."""
    from marker.converters.pdf import PdfConverter
    from marker.config.parser import ConfigParser

    config = {
        "output_format": "markdown",
        "force_ocr": force_ocr,
    }

    config_parser = ConfigParser(config)
    converter = PdfConverter(config=config_parser.generate_config_dict())

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
    uvicorn.run(app, host="0.0.0.0", port=8001)
