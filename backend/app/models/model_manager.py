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
    Shared lazy runtime cache for local generative base models.

    Handler and LLMAgent instances must request models through this manager
    instead of loading their own physical copies.

    Runtime cache key:

        (resolved_model_path, device, torch_dtype)

    Therefore consumers using the same model/device/dtype receive exactly
    the same tokenizer/model objects.
    """

    def __init__(self) -> None:
        self._runtimes: Dict[
            Tuple[str, str, str],
            ModelRuntime,
        ] = {}

        self._lock = Lock()

    @staticmethod
    def _normalize_device(device: str) -> str:
        value = str(device).strip().lower()

        if not value:
            return "cpu"

        return value

    @staticmethod
    def _normalize_dtype(torch_dtype: str) -> str:
        value = str(torch_dtype).strip().lower()

        allowed = {
            "float32",
            "float16",
            "bfloat16",
        }

        if value not in allowed:
            return "float32"

        return value

    @staticmethod
    def _cache_key(
        model_path: str,
        device: str,
        torch_dtype: str,
    ) -> Tuple[str, str, str]:
        resolved = str(
            Path(model_path)
            .expanduser()
            .resolve()
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
        device: str = "cpu",
        torch_dtype: str = "float32",
    ) -> ModelRuntime:

        normalized_device = self._normalize_device(device)
        normalized_dtype = self._normalize_dtype(torch_dtype)

        key = self._cache_key(
            model_path,
            normalized_device,
            normalized_dtype,
        )

        runtime = self._runtimes.get(key)

        if runtime is not None:
            print(
                "[ModelManager] reusing shared base model:",
                key[0],
                "device=",
                normalized_device,
                "dtype=",
                normalized_dtype,
            )

            return runtime

        with self._lock:
            runtime = self._runtimes.get(key)

            if runtime is not None:
                print(
                    "[ModelManager] reusing shared base model:",
                    key[0],
                    "device=",
                    normalized_device,
                    "dtype=",
                    normalized_dtype,
                )

                return runtime

            runtime = self._load_runtime(
                model_path=key[0],
                device=normalized_device,
                torch_dtype=normalized_dtype,
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

        resolved_dtype = dtype_map[torch_dtype]

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

        load_kwargs = {
            "local_files_only": True,
            "trust_remote_code": True,

            # Transformers 5.x prefers dtype instead of torch_dtype.
            "dtype": resolved_dtype,
        }

        if device == "auto":
            # Kept for compatibility with another deployment profile.
            #
            # For the current CPU deployment HANDLER_DEVICE=cpu should be
            # used, therefore this branch is not entered.
            model = AutoModelForCausalLM.from_pretrained(
                path,
                device_map="auto",
                **load_kwargs,
            )

        else:
            model = AutoModelForCausalLM.from_pretrained(
                path,
                **load_kwargs,
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
            "device=",
            device,
            "dtype=",
            torch_dtype,
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