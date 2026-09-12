from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ComplexityDecision:
    label: int
    mode: str
    probs: Dict[str, float]
    confidence: float
    enabled: bool = True
    reason: str = ""


class ComplexityRouter:
    """
    Local request-complexity classifier.

    Expected directory layout:

    complexity_router/
    ├── config.json
    ├── head.pt
    └── encoder/
        ├── config.json
        ├── tokenizer.json
        ├── tokenizer_config.json
        ├── model.safetensors
        └── ...

    The implementation intentionally mirrors the inference code supplied with
    the trained model: multilingual-e5 encoder -> mean pooling -> MLP head.
    """

    def __init__(
        self,
        model_dir: str | Path,
        device: Optional[str] = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.device_name = device

        self.cfg = None
        self.tokenizer = None
        self.encoder = None
        self.head = None
        self.device = None

        self._load_lock = Lock()

    @property
    def is_loaded(self) -> bool:
        return (
            self.cfg is not None
            and self.tokenizer is not None
            and self.encoder is not None
            and self.head is not None
        )

    def _validate_layout(self) -> None:
        required = [
            self.model_dir / "config.json",
            self.model_dir / "head.pt",
            self.model_dir / "encoder",
        ]

        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Complexity router files are missing: " + ", ".join(missing)
            )

    def _ensure_loaded(self) -> None:
        if self.is_loaded:
            return

        with self._load_lock:
            if self.is_loaded:
                return

            self._validate_layout()

            import torch
            import torch.nn as nn
            from transformers import AutoModel, AutoTokenizer

            with (self.model_dir / "config.json").open(
                "r",
                encoding="utf-8",
            ) as fh:
                self.cfg = json.load(fh)

            self.device = torch.device(
                self.device_name
                or ("cuda" if torch.cuda.is_available() else "cpu")
            )

            encoder_dir = self.model_dir / "encoder"

            self.tokenizer = AutoTokenizer.from_pretrained(
                encoder_dir,
                local_files_only=True,
            )

            self.encoder = AutoModel.from_pretrained(
                encoder_dir,
                local_files_only=True,
            )
            self.encoder.to(self.device)
            self.encoder.eval()

            head_cfg = self.cfg["head"]
            self.head = nn.Sequential(
                nn.Linear(self.cfg["hidden"], head_cfg["hid"]),
                nn.GELU(),
                nn.Dropout(head_cfg["dropout"]),
                nn.Linear(head_cfg["hid"], head_cfg["n_classes"]),
            )

            raw_state = torch.load(
                self.model_dir / "head.pt",
                map_location="cpu",
            )

            if isinstance(raw_state, dict) and "state_dict" in raw_state:
                raw_state = raw_state["state_dict"]

            normalized_state = {
                key.replace("net.", ""): value
                for key, value in raw_state.items()
            }

            self.head.load_state_dict(normalized_state)
            self.head.to(self.device)
            self.head.eval()

            print(
                "[ComplexityRouter] loaded:",
                self.model_dir,
                "device=",
                self.device,
            )

    def predict(self, queries: str | Iterable[str]) -> List[ComplexityDecision]:
        self._ensure_loaded()

        import torch

        if isinstance(queries, str):
            query_list = [queries]
        else:
            query_list = list(queries)

        if not query_list:
            return []

        prefixed = [
            self.cfg["query_prefix"] + query
            for query in query_list
        ]

        encoded = self.tokenizer(
            prefixed,
            padding=True,
            truncation=True,
            max_length=self.cfg["max_len"],
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            hidden = self.encoder(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).float()

            pooled = (
                (hidden * mask).sum(dim=1)
                / mask.sum(dim=1).clamp(min=1e-6)
            )

            probs_tensor = torch.softmax(
                self.head(pooled),
                dim=-1,
            ).cpu()

        decisions: List[ComplexityDecision] = []

        for query, probs in zip(query_list, probs_tensor):
            index = int(probs.argmax())
            label = index + 1
            mode = self.cfg["labels"][str(label)]

            probs_dict = {
                str(i + 1): round(float(probs[i]), 4)
                for i in range(len(probs))
            }

            decisions.append(
                ComplexityDecision(
                    label=label,
                    mode=mode,
                    probs=probs_dict,
                    confidence=float(probs[index]),
                )
            )

        return decisions

    def predict_one(self, query: str) -> ComplexityDecision:
        if not query.strip():
            return ComplexityDecision(
                label=1,
                mode="simple_direct",
                probs={"1": 1.0, "2": 0.0, "3": 0.0},
                confidence=1.0,
                enabled=True,
                reason="empty_query",
            )

        return self.predict(query)[0]
