# PDF Reader & Study Prompt Engine

A local-first system that ingests PDF textbooks, organizes them into a structured library by chapters, and runs a fully **deterministic analysis engine** to generate optimized study prompts for any Large Language Model.

All processing happens **100% locally** on your machine. No API calls. No cloud dependencies. No recurring costs.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/Storage-SQLite_WAL-003B57?logo=sqlite&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Component Breakdown](#component-breakdown)
  - [Server](#1-server-serverpy)
  - [Warehouse](#2-warehouse-warehouse)
  - [Deterministic Engine](#3-deterministic-analysis-engine-engine)
  - [Library Intelligence](#4-library-intelligence)
  - [Web UI](#5-web-ui-web)
- [Why Not Just Send the PDF to ChatGPT?](#why-not-just-send-the-pdf-to-chatgpt)
- [Study Modes](#study-modes)
- [API Reference](#api-reference)
- [Setup & Installation](#setup--installation)
- [How to Use](#how-to-use)
- [Project Structure](#project-structure)
- [Performance](#performance)
- [Testing](#testing)

---

## Why This Exists

If you've ever tried to study from a textbook PDF using an LLM, you've hit these walls:

| Problem | What happens |
|---|---|
| **Lost structure** | The LLM gets a wall of text with no chapter boundaries |
| **Hallucination** | The model invents definitions instead of quoting the author's |
| **Token waste** | Sending a 500-page book costs a fortune in tokens -- *every single time you ask a question* |
| **No memory** | The LLM can't cross-reference your other textbooks. It forgets page 50 by page 200 |

This project solves all of them by building a **deterministic intelligence layer** between your PDFs and the LLM:

1. **Precision Extraction** -- Extracts text from PDFs using `marker-pdf` for layout detection or `pypdf` for digital-native content.
2. **Semantic Chunking** -- Intelligently splits books into logical chapters using heading patterns, Table of Contents detection, and page-break analysis.
3. **Deterministic Pre-computation** -- Extracts every formula, variable definition, concept, and dependency graph **before** the LLM touches anything.
4. **Prompt Assembly** -- Combines extracted text and deterministic metadata into highly structured prompts that eliminate hallucination and reduce token costs by orders of magnitude.
5. **Library Intelligence** -- Cross-references books against each other using TF-IDF cosine similarity to build a persistent knowledge graph.

---

## Key Features

### Intelligent PDF Ingestion
- Dual-path extraction: fast `pypdf` for digital-native PDFs, `marker-pdf` for scanned content
- Configurable word-per-page threshold to auto-select the extraction strategy
- Automatic metadata extraction (author, subject, edition, year, language) from PDF properties and content heuristics
- Background ingestion with real-time SSE progress streaming to the web UI

### Library Management
- SQLite-backed storage with WAL mode for concurrent access
- Automatic chapter detection using a 3-tier heuristic strategy (explicit chapters, top-level headings, page breaks)
- Study status tracking per chapter (`not_started` / `in_progress` / `completed`)
- Configurable control unit (fast-path toggle, PyPDF threshold, export directory)
- Bulk library import by scanning a `raw_source/` directory

### Deterministic Analysis Engine (6-Stage Pipeline)
- **StructureAnalyzer** -- Builds a hierarchical heading tree with word counts
- **ConceptExtractor** -- Identifies key terms, acronyms, and bold/italic definitions with importance ranking. Falls back to TF-IDF frequency analysis and theorem/definition block detection when formatting is absent
- **FormulaExtractor** -- Isolates every `$...$` and `$$...$$` block and captures surrounding variable definitions
- **DependencyMapper** -- Finds relationship markers ("depends on", "in contrast to", "generalizes") and builds a directed concept graph with clusters
- **DensityAnalyzer** -- Classifies each section as `math-heavy`, `proof-heavy`, `problem-set`, `example-heavy`, `code-heavy`, or `concept-dense`
- **LibraryIntelligence** -- Cross-references new books against your existing library using TF-IDF cosine similarity

### 4 Study Modes
- **Deep Dive** -- Comprehensive breakdown of every concept and formula
- **Exam Prep** -- Flashcards, practice problems, common traps
- **Quick Review** -- Condensed cheat-sheet summary
- **Socratic Dialogue** -- Interactive teacher-student conversation format

### Web UI
- Full library dashboard with sidebar book browser and chapter selection
- Real-time ingestion pipeline overlay with activity log and elapsed timer
- Mode selection and one-click prompt generation
- Copy-to-clipboard and download support for generated prompts
- Warehouse control unit for configuration management
- Premium dark theme built with Inter + JetBrains Mono typography

---

## System Architecture

```
PDF File
  |
  +-- Ingester ------> pypdf fast path (digital-native, >= threshold w/p)
  |                    OR marker-pdf (scanned / sparse content)
  |
  +-- Metadata ------> Auto-extract author, subject, edition, year, language
  |
  +-- Chapter Detection (3 strategies)
  |     +-- Explicit "Chapter N" / "Part N" headings
  |     +-- Top-level # headings (filtering TOC, preface, index)
  |     +-- Page-break fallback (--- separators)
  |
  +-- Per-Chapter Analysis (parallel, ThreadPoolExecutor)
  |     +-- StructureAnalyzer --> heading tree
  |     +-- ConceptExtractor  --> key terms + definitions
  |     +-- FormulaExtractor  --> LaTeX blocks + variable context
  |
  +-- Storage ----------> SQLite WAL (books, chapters, prompts, analysis)
  |
  +-- Library Intelligence (background thread)
  |     +-- TF-IDF + SequenceMatcher cross-referencing
  |
  +-- Prompt Assembly --> Structured prompt for any LLM
```

### Request Flow

```
Browser (Web UI)
  |
  +--[HTTP]--> FastAPI Server (localhost:8001)
                |
                +-- /warehouse/*  --> Warehouse facade --> Ingester + Storage
                +-- /engine/*     --> Engine pipeline  --> PromptAssembler
                +-- /             --> Serves web UI (index.html)
```

---

## Component Breakdown

### 1. Server (`server.py`)

The FastAPI backend that exposes all endpoints for the web UI.

**Key capabilities:**
- **Background Ingestion** (`POST /warehouse/upload`): Non-blocking PDF processing with SSE progress streaming. The server stays responsive while processing large books.
- **Library Scanning** (`POST /warehouse/scan`): Auto-discovers PDFs in the `raw_source/` folder and ingests any new ones.
- **Engine Analysis** (`POST /engine/analyze/{book}/{ch}`): Runs the 6-stage deterministic pipeline on a chapter.
- **Prompt Building** (`POST /engine/prompt/{book}/{ch}`): Full pipeline to structured prompt, with SQLite caching.
- **Control Unit** (`GET/PATCH /warehouse/config`): Read and update runtime configuration (fast path, thresholds, export directory).
- Serves the web UI as static files from the `web/` directory.

---

### 2. Warehouse (`warehouse/`)

The warehouse handles ingestion, structuring, and persistent storage of your document library.

| Module | Purpose |
|---|---|
| `__init__.py` | `Warehouse` facade class -- top-level API for ingestion, book/chapter access, search, and maintenance |
| `ingester.py` | Full pipeline orchestrator: PDF extraction (dual-path), metadata extraction, chapter detection, parallel analysis, background knowledge mapping |
| `models.py` | Data models: `Book` and `Chapter` dataclasses with `to_dict()` / `from_dict()` serialization and deterministic ID generation |
| `storage.py` | SQLite-backed persistence with WAL mode. Schema: `books`, `chapters`, `markdown`, `prompts`, `analysis`. Thread-local connections, batched writes, auto-migration from legacy JSON |
| `config.py` | `ConfigManager` with JSON-persisted `WarehouseConfig` (fast_path_enabled, pypdf_threshold, export_dir) |

**Ingestion Pipeline:**
1. Copy PDF to `raw_source/` with hash-based naming
2. Create book record (status: `processing`)
3. Extract markdown -- try `pypdf` fast path first; if words per page is below threshold, fall back to `marker-pdf`
4. Auto-extract metadata (author, subject, edition, year, language) from PDF properties and content analysis
5. Detect chapter boundaries using 3-tier heuristic strategy
6. Analyze each chapter in parallel via `ThreadPoolExecutor` (structure, concepts, formulas)
7. Mark book as `ready`
8. Build Library Intelligence knowledge map in background daemon thread

---

### 3. Deterministic Analysis Engine (`engine/`)

Instead of making an LLM read the whole chapter and guess, the engine pre-extracts everything deterministically -- **no AI needed for the analysis itself**.

| Stage | Module | What it does |
|---|---|---|
| 1 | `structure_analyzer.py` | Converts headings into a hierarchical tree with word counts per section |
| 2 | `concept_extractor.py` | Identifies key terms via bold/italic patterns, `Definition:` / `Theorem:` blocks, and TF-IDF frequency fallback. Ranks by importance (`high`/`medium`/`low`) based on frequency and formatting |
| 3 | `formula_extractor.py` | Finds all `$...$` and `$$...$$` blocks. Traverses surrounding text to find variable definitions (e.g., "where $m$ is mass") and attaches context |
| 4 | `dependency_mapper.py` | Scans for relationship keywords ("depends on", "in contrast to", "unlike X", "X vs Y") and builds a directed concept graph with clusters |
| 5 | `density_analyzer.py` | Classifies each section: `math-heavy`, `proof-heavy`, `problem-set`, `example-heavy`, `code-heavy`, `concept-dense`. Tells the LLM *how* to explain each section |
| 6 | `prompt_assembler.py` | Combines everything into a structured prompt with headers, concept lists, formula sheets, dependency graphs, and mode-specific instructions |

Additional modules:
- `metadata_extractor.py` -- Heuristic-based extraction of author, subject, edition, year, and language from PDF metadata and first-page text
- `library_intelligence.py` -- Cross-book similarity matching (see below)

---

### 4. Library Intelligence

When you add a new book, the Intelligence Engine compares it against every book already in your warehouse -- **fully offline, fully deterministic**.

**Three similarity dimensions:**

| Dimension | Algorithm | What it measures |
|---|---|---|
| Name Similarity | `SequenceMatcher` | How similar the book titles are (character-level) |
| Structure Similarity | `SequenceMatcher` | How similar the ordered chapter title sequences are |
| Concept Overlap | TF-IDF Cosine Similarity | How many extracted concepts are shared (weighted by rarity) |

**Weighted scoring:** `total = 0.2 x name + 0.3 x structure + 0.5 x concept`

The concept score is weighted highest because two books can have completely different titles and chapter orders but cover the same material. The engine builds IDF across your entire library corpus, so rare shared concepts score much higher than common ones.

---

### 5. Web UI (`web/`)

A self-contained browser-based interface served by the FastAPI backend at the root URL.

| File | Purpose |
|---|---|
| `index.html` | Application shell: sidebar, chapter list, prompt view, upload overlay, control unit overlay |
| `app.js` | Full client-side controller: library browsing, SSE progress tracking, mode selection, prompt generation, copy/download, study status management |
| `styles.css` | Premium dark theme with CSS custom properties, glassmorphism overlays, smooth transitions, and JetBrains Mono for code/prompt display |

**UI Features:**
- Sidebar book browser with chapter count badges
- Pipeline progress overlay with step-by-step indicators and live activity log
- 4 study mode selector (Deep Dive, Exam Prep, Quick Review, Socratic)
- Prompt output panel with word/token count, copy-to-clipboard, and file download
- Control Unit settings panel (fast ingestion toggle, PyPDF threshold, export directory, danger zone)

---

## Why Not Just Send the PDF to ChatGPT?

Most people's instinct is to drag the PDF into ChatGPT and ask questions. **This approach has fundamental flaws:**

### 1. Cost & Token Efficiency
| | Direct PDF approach | This system |
|---|---|---|
| **Per question** | Re-send the whole book every time (~500K tokens) | Send only the pre-built prompt (~5K tokens) |
| **Processing cost** | Paid API call every single time | One-time free local processing |
| **Speed** | Minutes per query on large books | Instant (prompts are cached in SQLite) |

### 2. Zero Hallucination
| | Direct PDF approach | This system |
|---|---|---|
| **Definitions** | LLM might paraphrase or invent definitions | Engine extracts the *exact* definition from the text |
| **Formulas** | LLM might "recall" a wrong formula from training | Engine extracts the *exact* LaTeX from the book |
| **Variables** | LLM might guess what symbols mean | Engine finds "where $X$ is the design matrix" and attaches it to the formula |

### 3. Long-Term Memory & Cross-Referencing
| | Direct PDF approach | This system |
|---|---|---|
| **Context limit** | Can't process 50 books simultaneously | Entire library is indexed and cross-referenced |
| **Lost in the middle** | Forgets content in the middle of long documents | Chapter-level chunking ensures nothing is lost |
| **Cross-referencing** | Cannot compare books | TF-IDF engine detects concept overlap across your entire library |

### 4. Reproducibility
The engine is **100% deterministic**. Given the same PDF, it produces the exact same analysis every time. No randomness, no temperature settings, no model drift.

---

## Study Modes

| Mode | Best for | What the LLM produces |
|---|---|---|
| **Deep Dive** | First pass through dense material | Chapter overview, every concept explained with analogies, formula walkthroughs with worked examples, concept connections, practical applications, key takeaways |
| **Exam Prep** | Test preparation | Flashcard-format definitions, formula reference sheet, 10-15 conceptual questions, 5-8 application problems, compare & contrast, common exam traps |
| **Quick Review** | Revision before class | 3-sentence TL;DR, bullet-point concept list, formula cheat sheet, concept map, one-paragraph summary |
| **Socratic** | Deep understanding | Teacher-student dialogue that follows concept dependencies, works through formulas step-by-step, builds to synthesis questions |

---

## API Reference

All endpoints are served by the FastAPI backend at `http://localhost:8001`. Interactive docs at `/docs`.

### Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serve the web UI (or API info if web/ is missing) |
| `GET` | `/health` | Health check |

### Warehouse (Library Management)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/warehouse/upload` | Upload & ingest a PDF (background by default) |
| `GET` | `/warehouse/progress/{job_id}` | SSE stream for real-time ingestion progress |
| `GET` | `/warehouse/job/{job_id}` | Polling fallback for job status |
| `GET` | `/warehouse/books` | List all books |
| `GET` | `/warehouse/books/{id}` | Get book metadata |
| `GET` | `/warehouse/books/{id}/chapters` | List chapters (metadata only) |
| `GET` | `/warehouse/books/{id}/chapters/{ch}` | Get chapter with full text |
| `DELETE` | `/warehouse/books/{id}` | Delete a book (cascading) |
| `POST` | `/warehouse/scan` | Scan `raw_source/` for new PDFs |
| `PATCH` | `/warehouse/books/{id}/chapters/{ch}/status` | Update study status |
| `POST` | `/warehouse/clear-errors` | Remove all errored books |
| `POST` | `/warehouse/clear-all` | Delete entire library |
| `GET` | `/warehouse/config` | Get current configuration |
| `PATCH` | `/warehouse/config` | Update configuration (fast_path, threshold, export_dir) |

### Engine (Analysis & Prompts)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/engine/modes` | List available study modes |
| `POST` | `/engine/analyze/{book}/{ch}` | Run 6-stage deterministic analysis (cached) |
| `POST` | `/engine/prompt/{book}/{ch}` | Build optimized study prompt (cached). Exports to configured directory |

---

## Setup & Installation

### Prerequisites
- **Python 3.11+**
- **GPU recommended** for `marker-pdf` (works on CPU too, just slower)

### 1. Clone and set up a virtual environment

```bash
git clone <repo-url> pdf_reader
cd pdf_reader
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
```

### 2. Install dependencies

```bash
pip install marker-pdf fastapi uvicorn python-multipart pypdf
```

### 3. Start the server

```bash
python server.py
```

You'll see:
```
Starting PDF Reader on http://localhost:8001
API Docs: http://localhost:8001/docs
```

### 4. Open the web UI

Navigate to `http://localhost:8001` in your browser.

---

## How to Use

### Upload a Book
1. Open `http://localhost:8001` in your browser
2. Click **Upload PDF** in the sidebar
3. The backend automatically:
   - Extracts text (fast pypdf path or marker-pdf fallback)
   - Detects author, subject, and other metadata
   - Splits the book into chapters
   - Extracts formulas, concepts, and dependencies per chapter
   - Cross-references against your existing library
4. Watch the live pipeline progress overlay

### Generate a Study Prompt
1. Select a book from the sidebar
2. Click **Study** on any chapter
3. Choose a study mode: **Deep Dive**, **Exam Prep**, **Quick Review**, or **Socratic**
4. Click **Generate Study Prompt**
5. **Copy** the prompt and paste it into ChatGPT, Claude, Gemini, or any LLM

### Bulk Library Import
1. Place PDF files in the `raw_source/` folder
2. Click **Scan Library** in the sidebar
3. All new PDFs are automatically ingested with progress tracking

### Track Study Progress
- Click the status indicator next to any chapter to cycle through `not_started` / `in_progress` / `completed`
- Status persists across sessions in the SQLite database

### Configure Settings
- Click **Control Unit** in the sidebar footer
- Toggle fast ingestion (PyPDF path), adjust word threshold, set export directory
- **Danger Zone:** clear error logs or wipe the entire library

---

## Project Structure

```
pdf_reader/
+-- server.py               # FastAPI backend (all endpoints)
+-- README.md                # This file
+-- .gitignore               # Git ignore rules
|
+-- engine/                  # Deterministic analysis engine
|   +-- __init__.py          # Engine orchestrator class
|   +-- structure_analyzer.py    # Heading tree builder
|   +-- concept_extractor.py     # Key term + definition extractor
|   +-- formula_extractor.py     # LaTeX formula extractor with context
|   +-- dependency_mapper.py     # Concept relationship graph builder
|   +-- density_analyzer.py      # Section type classifier
|   +-- metadata_extractor.py    # PDF metadata extractor (author, subject, language)
|   +-- library_intelligence.py  # TF-IDF cross-book matching
|   +-- prompt_assembler.py      # Final prompt builder (4 study modes)
|   +-- README.md                # Engine-specific documentation
|
+-- warehouse/               # Library management system
|   +-- __init__.py          # Warehouse facade
|   +-- ingester.py          # Full PDF-to-chapters pipeline
|   +-- models.py            # Book + Chapter dataclasses
|   +-- storage.py           # SQLite storage (WAL, cached, indexed)
|   +-- config.py            # ConfigManager (fast_path, threshold, export_dir)
|
+-- web/                     # Browser-based UI
|   +-- index.html           # Application shell
|   +-- app.js               # Client-side controller
|   +-- styles.css           # Premium dark theme
|
+-- tests/                   # Test suite
|   +-- test_engine.py           # Engine pipeline tests
|   +-- test_library_intelligence.py  # Cross-book matching tests
|   +-- test_performance.py      # Performance benchmarks
|   +-- test_phase1.py           # Phase 1 integration tests
|   +-- test_phase3.py           # Phase 3 integration tests
|
+-- raw_source/              # PDF storage directory (git-ignored)
+-- warehouse/data/          # SQLite database + config (git-ignored)
```

---

## Performance

The system is optimized for processing large, multi-hundred-page textbooks:

| Optimization | Impact |
|---|---|
| **Dual-path extraction** | Digital-native PDFs use the fast `pypdf` path (instant); only sparse/scanned PDFs trigger `marker-pdf` |
| **Configurable threshold** | Words-per-page threshold (default: 50) controls when to skip heavy extraction |
| **Parallel chapter analysis** | `ThreadPoolExecutor(4)` analyzes structure, concepts, and formulas concurrently |
| **SQLite WAL mode** | Concurrent reads during background processing; 8MB cache; foreign key cascading |
| **Background knowledge mapping** | Library Intelligence runs in a daemon thread -- ingestion returns instantly |
| **Prompt caching** | Generated prompts are cached per (book, chapter, mode) -- subsequent calls are instant |
| **Analysis caching** | Engine analysis results are cached per (book, chapter) |
| **Batched storage writes** | `auto_commit=False` mode defers commits for bulk chapter saves; `flush_index()` commits once |
| **Memory cleanup** | Full markdown released from book object after chapter detection to free memory |

---

## Testing

Run individual test modules (no pytest required):

```bash
python tests/test_engine.py                # Engine pipeline (10 tests)
python tests/test_phase1.py                # Phase 1 integration (6 tests)
python tests/test_phase3.py                # Phase 3 integration (9 tests)
python tests/test_performance.py           # Performance benchmarks (3 tests)
python tests/test_library_intelligence.py  # Cross-book matching (1 test)
```

All tests run standalone with no external dependencies beyond the project itself.

---

## License

MIT

---

*Built to eliminate the gap between raw PDFs and perfect LLM study sessions -- because generating knowledge shouldn't cost you a fortune in API calls.*
