from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from app.documents.models import ProcessedDocument


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


class DrawingAnalyzer:
    """
    Adapter around the drawing-indexer supplied by the project team.

    The original script remains mostly unchanged in app/vision/drawing_pipeline.py.
    This adapter converts its file-oriented CLI workflow into:
        one uploaded file -> one ProcessedDocument

    PDF pages are analyzed individually and then aggregated into one logical
    document for agent routing. Per-page RAG records remain available in
    ProcessedDocument.pages and as JSON artifacts.
    """

    def __init__(
        self,
        output_dir: str | Path,
        *,
        min_conf: float | None = None,
        ocr_backend: str | None = None,
        scan_mode: str | None = None,
        enable_clip: bool | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.min_conf = (
            float(
                os.getenv(
                    "DRAWING_OCR_MIN_CONF",
                    "50",
                )
            )
            if min_conf is None
            else float(min_conf)
        )

        self.ocr_backend = (
            ocr_backend
            or os.getenv(
                "DRAWING_OCR_BACKEND",
                "rapidocr",
            )
        )

        self.scan_mode = (
            scan_mode
            or os.getenv(
                "DRAWING_SCAN_MODE",
                "auto",
            )
        )

        if enable_clip is None:
            enable_clip = (
                os.getenv(
                    "DRAWING_CLIP_ENABLED",
                    "false",
                )
                .strip()
                .lower()
                in {"1", "true", "yes", "on"}
            )

        self.enable_clip = enable_clip
        self._clip_tagger = None
        self._clip_attempted = False

    @staticmethod
    def supports(path: str | Path) -> bool:
        suffix = Path(path).suffix.lower()
        return (
            suffix in IMAGE_EXTENSIONS
            or suffix == ".pdf"
        )

    def _pipeline(self):
        # Lazy import: OpenCV/OCR do not initialize merely because FastAPI starts.
        from app.vision import drawing_pipeline
        return drawing_pipeline

    def _get_clip_tagger(self):
        if not self.enable_clip:
            return None

        if self._clip_attempted:
            return self._clip_tagger

        self._clip_attempted = True

        try:
            from app.vision.clip_tags import ClipTagger

            self._clip_tagger = ClipTagger()
        except Exception as exc:
            print(
                "[DrawingAnalyzer] CLIP unavailable, "
                f"continuing without it: {exc}"
            )
            self._clip_tagger = None

        return self._clip_tagger

    def _artifact_dir(
        self,
        source: Path,
    ) -> Path:
        safe_stem = (
            source.stem
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )
        target = self.output_dir / safe_stem
        target.mkdir(
            parents=True,
            exist_ok=True,
        )
        return target

    def _analyze_one(
        self,
        *,
        name: str,
        source_path: Path,
        artifact_dir: Path,
        image_array=None,
    ) -> Dict[str, Any]:
        pipeline = self._pipeline()

        report = pipeline.analyze(
            source_path,
            self.min_conf,
            self.ocr_backend,
            self.scan_mode,
            image_array,
        )

        report.file = name

        clip_result = None
        clip_tagger = self._get_clip_tagger()

        # CLIP needs an actual image path. PDF pages are materialized below.
        clip_path = source_path

        if image_array is not None:
            import cv2

            clip_path = (
                artifact_dir
                / f"{Path(name).stem}_page.png"
            )
            cv2.imwrite(
                str(clip_path),
                image_array,
            )

        if clip_tagger is not None:
            try:
                clip_result = clip_tagger(clip_path)
            except Exception as exc:
                print(
                    "[DrawingAnalyzer] CLIP failed for "
                    f"{name}: {exc}"
                )

        rag = pipeline.rag_document(
            report,
            vlm=None,
            clip=clip_result,
        )

        report_path = (
            artifact_dir
            / f"{Path(name).stem}.report.json"
        )
        rag_path = (
            artifact_dir
            / f"{Path(name).stem}.rag.json"
        )
        md_path = (
            artifact_dir
            / f"{Path(name).stem}.md"
        )
        annotated_path = (
            artifact_dir
            / f"{Path(name).stem}_annotated.png"
        )

        report_path.write_text(
            report.to_json(),
            encoding="utf-8",
        )
        rag_path.write_text(
            json.dumps(
                rag,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        md_path.write_text(
            pipeline.describe(report),
            encoding="utf-8",
        )

        try:
            pipeline.annotate(
                clip_path,
                report,
                annotated_path,
            )
        except Exception as exc:
            print(
                "[DrawingAnalyzer] annotation failed "
                f"for {name}: {exc}"
            )

        diagram = (
            rag.get("metadata", {}).get("diagram")
            or report.diagram
            or {}
        )

        return {
            "name": name,
            "text": rag.get("text", ""),
            "tags": list(rag.get("tags", [])),
            "metadata": dict(
                rag.get("metadata", {})
            ),
            "diagram": diagram,
            "artifacts": {
                "report_json":
                    str(report_path),
                "rag_json":
                    str(rag_path),
                "markdown":
                    str(md_path),
                "annotated_image":
                    (
                        str(annotated_path)
                        if annotated_path.exists()
                        else ""
                    ),
                "page_image":
                    (
                        str(clip_path)
                        if image_array is not None
                        else ""
                    ),
            },
        }

    @staticmethod
    def _aggregate_pages(
        pages: List[Dict[str, Any]],
    ) -> tuple[
        str,
        List[str],
        Dict[str, Any],
        Dict[str, Any],
    ]:
        texts: List[str] = []
        tags: List[str] = []
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        for index, page in enumerate(
            pages,
            start=1,
        ):
            page_text = str(
                page.get("text", "")
            ).strip()

            if page_text:
                texts.append(
                    f"[PDF page {index}]\n"
                    + page_text
                )

            for tag in page.get("tags", []):
                if tag not in tags:
                    tags.append(tag)

            diagram = page.get("diagram", {})
            for node in diagram.get(
                "nodes",
                [],
            ):
                item = dict(node)
                item["page"] = index
                nodes.append(item)

            for edge in diagram.get(
                "edges",
                [],
            ):
                item = dict(edge)
                item["page"] = index
                edges.append(item)

        metadata = {
            "page_count": len(pages),
            "pages": [
                {
                    "page": i,
                    "name": page.get("name", ""),
                    "metadata":
                        page.get("metadata", {}),
                }
                for i, page in enumerate(
                    pages,
                    start=1,
                )
            ],
        }

        diagram = {
            "nodes": nodes,
            "edges": edges,
        }

        return (
            "\n\n".join(texts),
            tags,
            metadata,
            diagram,
        )

    def analyze(
        self,
        file_path: str | Path,
    ) -> ProcessedDocument:
        source = Path(file_path)

        if not source.exists():
            raise FileNotFoundError(
                f"Drawing file not found: {source}"
            )

        if not self.supports(source):
            raise ValueError(
                f"Unsupported drawing format: "
                f"{source.suffix}"
            )

        artifact_dir = self._artifact_dir(
            source
        )

        if source.suffix.lower() == ".pdf":
            pipeline = self._pipeline()
            pages: List[Dict[str, Any]] = []

            generated_pages = pipeline.pdf_pages(
                source
            )

            if generated_pages is None:
                raise RuntimeError(
                    "PDF processing requires pymupdf"
                )

            for page_name, image_array in generated_pages:
                pages.append(
                    self._analyze_one(
                        name=f"{page_name}.pdf",
                        source_path=source,
                        artifact_dir=artifact_dir,
                        image_array=image_array,
                    )
                )

            if not pages:
                raise RuntimeError(
                    f"PDF contains no processable "
                    f"pages: {source}"
                )

            (
                text,
                tags,
                metadata,
                diagram,
            ) = self._aggregate_pages(pages)

            aggregate_path = (
                artifact_dir
                / f"{source.stem}.processed.json"
            )

            document = ProcessedDocument(
                source_path=str(source),
                file_name=source.name,
                kind="drawing_pdf",
                text=text,
                tags=tags,
                metadata=metadata,
                diagram=diagram,
                pages=pages,
                artifacts={
                    "processed_json":
                        str(aggregate_path),
                    "artifact_dir":
                        str(artifact_dir),
                },
            )

            aggregate_path.write_text(
                json.dumps(
                    document.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            return document

        page = self._analyze_one(
            name=source.name,
            source_path=source,
            artifact_dir=artifact_dir,
        )

        processed_path = (
            artifact_dir
            / f"{source.stem}.processed.json"
        )

        document = ProcessedDocument(
            source_path=str(source),
            file_name=source.name,
            kind="drawing_image",
            text=page["text"],
            tags=page["tags"],
            metadata=page["metadata"],
            diagram=page["diagram"],
            pages=[],
            artifacts={
                **page["artifacts"],
                "processed_json":
                    str(processed_path),
                "artifact_dir":
                    str(artifact_dir),
            },
        )

        processed_path.write_text(
            json.dumps(
                document.to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return document
