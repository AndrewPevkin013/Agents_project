from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore
from app.handlers.base import BaseHandler, HandlerOutput
from app.handlers.output_parser import parse_handler_output
from app.handlers.prompt import build_handler_system_prompt


class LocalLLMHandler(BaseHandler):
    def __init__(
        self,
        registry: AgentRegistry,
        command_store: CommandStore,
        config: Dict[str, Any],
        models_dir: str | Path,
    ) -> None:

        self.registry = registry
        self.command_store = command_store

        self.models_dir = Path(models_dir)

        self.model_name = config["model_name"]

        self.model_path = (
            self.models_dir
            / self.model_name
        )

        self.device = config.get(
            "device",
            "cpu"
        )

        self.dtype_name = config.get(
            "torch_dtype",
            "float32"
        )

        generation = config.get(
            "generation",
            {}
        )

        self.max_new_tokens = generation.get(
            "max_new_tokens",
            256
        )

        self.temperature = generation.get(
            "temperature",
            0.2
        )

        self.do_sample = generation.get(
            "do_sample",
            False
        )

        self.tokenizer = None
        self.model = None

    def _ensure_loaded(self) -> None:
        if (
            self.tokenizer is not None
            and self.model is not None
        ):
            return

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Local Handler model not found: "
                f"{self.model_path}"
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

        torch_dtype = dtype_map.get(
            self.dtype_name,
            torch.float32
        )

        print(
            "Loading local Handler model:",
            self.model_path
        )

        print(
            "Handler device:",
            self.device
        )

        self.tokenizer = (
            AutoTokenizer.from_pretrained(
                self.model_path,
                local_files_only=True,
                trust_remote_code=True,
            )
        )

        self.model = (
            AutoModelForCausalLM.from_pretrained(
                self.model_path,
                local_files_only=True,
                torch_dtype=torch_dtype,
                trust_remote_code=True,
            )
        )

        self.model.to(self.device)
        self.model.eval()

    def _build_system_prompt(
        self,
        user_request: str,
    ) -> str:

        return build_handler_system_prompt(
            user_request,
            self.registry.as_prompt_registry(),
            self.command_store.retrieve,
        )

    def handle(
        self,
        user_request: str,
    ) -> HandlerOutput:

        self._ensure_loaded()

        system_prompt = (
            self._build_system_prompt(
                user_request
            )
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_request,
            },
        ]

        if hasattr(
            self.tokenizer,
            "apply_chat_template"
        ):
            text = (
                self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            )
        else:
            text = (
                f"{system_prompt}\n\n"
                f"User request:\n"
                f"{user_request}\n\n"
                f"Answer:"
            )

        inputs = self.tokenizer(
            text,
            return_tensors="pt"
        ).to(self.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            do_sample=self.do_sample,
            pad_token_id=self.tokenizer.eos_token_id,
        )

        generated_tokens = outputs[0][
            inputs["input_ids"].shape[-1]:
        ]

        answer = self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True
        ).strip()

        print("LOCAL HANDLER raw answer:")
        print(answer)

        return parse_handler_output(answer)