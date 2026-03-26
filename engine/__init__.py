"""
engine — Deterministic analysis engine for chapter study prompts.

Takes extracted chapter markdown and produces a fully structured,
optimal prompt for any LLM — no AI needed for the analysis itself.

Pipeline:
    chapter_text → StructureAnalyzer → ConceptExtractor → FormulaExtractor
                 → DependencyMapper → DensityAnalyzer → PromptAssembler
                 → final prompt string
"""

from engine.structure_analyzer import StructureAnalyzer
from engine.concept_extractor import ConceptExtractor
from engine.formula_extractor import FormulaExtractor
from engine.dependency_mapper import DependencyMapper
from engine.density_analyzer import DensityAnalyzer
from engine.prompt_assembler import PromptAssembler


class Engine:
    """
    Deterministic analysis engine.

    Runs the full pipeline on a chapter's markdown text and produces
    a structured analysis + an optimal LLM prompt.
    """

    def __init__(self):
        self.structure = StructureAnalyzer()
        self.concepts = ConceptExtractor()
        self.formulas = FormulaExtractor()
        self.dependencies = DependencyMapper()
        self.density = DensityAnalyzer()
        self.assembler = PromptAssembler()

    def analyze(self, chapter_text: str, chapter_meta: dict | None = None) -> dict:
        """
        Run full deterministic analysis on a chapter.

        Args:
            chapter_text: The full markdown text of the chapter.
            chapter_meta: Optional metadata (title, number, book_title, etc.)

        Returns:
            dict with keys:
                - structure: heading tree + sections
                - concepts: extracted key terms + definitions
                - formulas: LaTeX blocks with context
                - dependencies: concept relationship graph
                - density: section type classifications
        """
        meta = chapter_meta or {}

        # Run each analyzer
        structure = self.structure.analyze(chapter_text)
        concepts = self.concepts.extract(chapter_text, structure)
        formulas = self.formulas.extract(chapter_text)
        dependencies = self.dependencies.map(chapter_text, concepts, structure)
        density = self.density.analyze(chapter_text, structure, concepts, formulas)

        return {
            "structure": structure,
            "concepts": concepts,
            "formulas": formulas,
            "dependencies": dependencies,
            "density": density,
        }

    def build_prompt(
        self,
        chapter_text: str,
        chapter_meta: dict | None = None,
        book_meta: dict | None = None,
        mode: str = "deep_dive",
        cross_references: list[dict] | None = None,
    ) -> str:
        """
        Full pipeline: analyze chapter → build optimal prompt.

        Args:
            chapter_text: The full markdown of the chapter.
            chapter_meta: Chapter metadata (title, number, etc.)
            book_meta: Book metadata (title, author, total_chapters, etc.)
            mode: Study mode — "deep_dive", "exam_prep", "quick_review", "socratic"
            cross_references: Related chapters from other books.

        Returns:
            The fully assembled prompt string, ready to send to any LLM.
        """
        analysis = self.analyze(chapter_text, chapter_meta)

        return self.assembler.assemble(
            chapter_text=chapter_text,
            analysis=analysis,
            chapter_meta=chapter_meta or {},
            book_meta=book_meta or {},
            mode=mode,
            cross_references=cross_references or [],
        )

    def map_knowledge(
        self,
        input_book: dict,
        input_chapters: list[dict],
        warehouse_books: list[dict],
        warehouse_chapters_map: dict[str, list[dict]],
    ) -> dict:
        from engine.library_intelligence import IntelligenceEngine
        engine = IntelligenceEngine(
            name_weight=0.2,
            structure_weight=0.3,
            concept_weight=0.5,
        )
        result = engine.match_knowledge(
            input_book=input_book,
            input_chapters=input_chapters,
            warehouse_books=warehouse_books,
            warehouse_chapters_map=warehouse_chapters_map,
        )
        return {
            "input_book_id": result.input_book_id,
            "matches": [
                {
                    "warehouse_book_id": m.warehouse_book_id,
                    "name_score": m.name_score,
                    "structure_score": m.structure_score,
                    "concept_score": m.concept_score,
                    "total_score": m.total_score,
                }
                for m in result.matches
            ],
        }

