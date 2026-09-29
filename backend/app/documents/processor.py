from __future__ import annotations

import json
from pathlib import Path

from app.documents.drawing_analyzer import DrawingAnalyzer
from app.documents.models import ProcessedDocument


TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".py", ".csv",
    ".log", ".yaml", ".yml", ".xml",
}


class DocumentProcessor:
    """
    Normalize heterogeneous uploads into ProcessedDocument.

    Dispatch is deterministic and does not depend on Handler/LLM reasoning:
      text/code/config -> text pipeline
      image/drawing/scan -> DrawingAnalyzer -> vision pipeline
      PDF -> DrawingAnalyzer -> per-page vision pipeline
      unknown binary -> explicit unsupported ProcessedDocument
    """

    def __init__(self, processed_dir: str | Path) -> None:
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.drawing_analyzer = DrawingAnalyzer(self.processed_dir / "drawings")

    @staticmethod
    def _text_document(path: Path, document_text: str = "") -> ProcessedDocument:
        text = document_text.strip()
        if not text:
            text = path.read_text(encoding="utf-8", errors="ignore")

        return ProcessedDocument(
            source_path=str(path),
            file_name=path.name,
            kind="text",
            text=text,
            metadata={
                "extension": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "processing_pipeline": "text",
            },
        )

    @staticmethod
    def _pdf_text_document(
        path: Path,
    ) -> ProcessedDocument | None:
        import fitz

        pages = []
        page_texts = []

        with fitz.open(path) as pdf:
            for page_index, page in enumerate(
                pdf,
                start=1,
            ):
                text = page.get_text("text").strip()

                pages.append({
                    "page": page_index,
                    "text": text,
                })

                if text:
                    page_texts.append(
                        f"[PDF page {page_index}]\n{text}"
                    )

        text = "\n\n".join(page_texts).strip()

        if not text:
            return None

        return ProcessedDocument(
            source_path=str(path),
            file_name=path.name,
            kind="text_pdf",
            text=text,
            pages=pages,
            metadata={
                "extension": ".pdf",
                "size_bytes": path.stat().st_size,
                "page_count": len(pages),
                "processing_pipeline": "pdf_text",
                "source_kind": "text_pdf",
                "extraction_supported": True,
            },
        )

    @staticmethod
    def _docx_text_document(
        path: Path,
    ) -> ProcessedDocument:
        from docx import Document

        doc = Document(path)

        blocks: list[str] = []

        # Paragraphs
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if text:
                blocks.append(text)

        # Tables
        for table_index, table in enumerate(doc.tables, start=1):
            rows: list[str] = []

            for row in table.rows:
                cells = [
                    cell.text.strip().replace("\n", " ")
                    for cell in row.cells
                ]

                if any(cells):
                    rows.append(" | ".join(cells))

            if rows:
                blocks.append(
                    f"[DOCX table {table_index}]\n"
                    + "\n".join(rows)
                )

        text = "\n\n".join(blocks).strip()

        return ProcessedDocument(
            source_path=str(path),
            file_name=path.name,
            kind="text_docx",
            text=text,
            metadata={
                "extension": ".docx",
                "size_bytes": path.stat().st_size,
                "paragraph_count": len(doc.paragraphs),
                "table_count": len(doc.tables),
                "processing_pipeline": "docx_text",
                "source_kind": "text_docx",
                "extraction_supported": True,
            },
        )

    

    def process(self, file_path: str, document_text: str = "") -> ProcessedDocument:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        suffix = path.suffix.lower()

        if suffix in TEXT_EXTENSIONS:
            return self._text_document(
                path,
                document_text,
            )

        if suffix == ".docx":
            return self._docx_text_document(
                path
            )

        if suffix == ".pdf":
            pdf_document = self._pdf_text_document(
                path
            )

            if pdf_document is not None:
                return pdf_document

        # IMPORTANT: visual routing is deterministic.
        # Handler/LLM does not choose the processing pipeline.
        if self.drawing_analyzer.supports(path):
            return self.drawing_analyzer.analyze(
                path
            )

        fallback_text = (
            document_text.strip()
            if document_text.strip()
            else (
                f"Uploaded file: {path.name}. "
                f"Content extraction is not implemented for format "
                f"{suffix or '<no extension>'}."
            )
        )

        return ProcessedDocument(
            source_path=str(path),
            file_name=path.name,
            kind="unsupported",
            text=fallback_text,
            metadata={
                "extension": suffix,
                "size_bytes": path.stat().st_size,
                "extraction_supported": False,
                "processing_pipeline": "unsupported",
            },
        )

    def save_normalized(self, document: ProcessedDocument) -> str:
        safe_name = Path(document.file_name).stem.replace(" ", "_")
        output = self.processed_dir / f"{safe_name}.normalized.json"
        output.write_text(
            json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(output)
