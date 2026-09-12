from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Tuple


@dataclass
class ModelRuntime:
    tokenizer: Any
    model: Any
    model_path: str
    device: str
    torch_dtype: str


class ModelManager:
    """
    Shared lazy runtime cache for generative base models.

    Multiple LLMAgent objects that point to the same model_path/device/dtype
    receive the same loaded tokenizer/model instead of loading duplicate copies.
    """

    def __init__(self) -> None:
        self._runtimes: Dict[
            Tuple[str, str, str],
            ModelRuntime,
        ] = {}
        self._lock = Lock()

    @staticmethod
    def _cache_key(
        model_path: str,
        device: str,
        torch_dtype: str,
    ) -> Tuple[str, str, str]:
        resolved = str(
            Path(model_path).expanduser().resolve()
        )
        return (
            resolved,
            device,
            torch_dtype,
        )

    def get_runtime(
        self,
        *,
        model_path: str,
        device: str = "auto",
        torch_dtype: str = "float16",
    ) -> ModelRuntime:
        key = self._cache_key(
            model_path,
            device,
            torch_dtype,
        )

        runtime = self._runtimes.get(key)
        if runtime is not None:
            return runtime

        with self._lock:
            runtime = self._runtimes.get(key)
            if runtime is not None:
                return runtime

            runtime = self._load_runtime(
                model_path=key[0],
                device=device,
                torch_dtype=torch_dtype,
            )
            self._runtimes[key] = runtime
            return runtime

    @staticmethod
    def _load_runtime(
        *,
        model_path: str,
        device: str,
        torch_dtype: str,
    ) -> ModelRuntime:
        path = Path(model_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Local model folder was not found: {path}"
            )

        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
        )

        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        resolved_dtype = dtype_map.get(
            torch_dtype,
            torch.float16,
        )

        print(
            "[ModelManager] loading shared base model:",
            path,
            "device=",
            device,
            "dtype=",
            torch_dtype,
        )

        tokenizer = AutoTokenizer.from_pretrained(
            path,
            local_files_only=True,
            trust_remote_code=True,
        )

        if device == "auto":
            model = AutoModelForCausalLM.from_pretrained(
                path,
                local_files_only=True,
                device_map="auto",
                torch_dtype=resolved_dtype,
                trust_remote_code=True,
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                path,
                local_files_only=True,
                torch_dtype=resolved_dtype,
                trust_remote_code=True,
            )
            model.to(device)

        model.eval()

        runtime = ModelRuntime(
            tokenizer=tokenizer,
            model=model,
            model_path=str(path),
            device=device,
            torch_dtype=torch_dtype,
        )

        print(
            "[ModelManager] ready:",
            path,
        )

        return runtime

    def loaded_models(self) -> list[dict[str, str]]:
        result = []

        for (
            model_path,
            device,
            torch_dtype,
        ), runtime in self._runtimes.items():
            result.append(
                {
                    "model_path": model_path,
                    "device": device,
                    "torch_dtype": torch_dtype,
                }
            )

        return result


_default_manager = ModelManager()


def get_model_manager() -> ModelManager:
    return _default_manager
