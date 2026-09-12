from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.documents.processor import DocumentProcessor


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        processed_dir = root / "processed"
        source = root / "example.txt"

        source.write_text(
            "FastAPI backend with PostgreSQL "
            "and JWT authentication.",
            encoding="utf-8",
        )

        processor = DocumentProcessor(
            processed_dir
        )

        doc = processor.process(str(source))
        saved = processor.save_normalized(
            doc
        )

        assert doc.kind == "text"
        assert "FastAPI" in doc.text
        assert Path(saved).exists()

        payload = json.loads(
            Path(saved).read_text(
                encoding="utf-8"
            )
        )
        assert payload["file_name"] == (
            "example.txt"
        )

        print("DocumentProcessor smoke test: OK")


if __name__ == "__main__":
    main()
