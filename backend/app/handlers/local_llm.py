from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore

from app.handlers.base import (
    BaseHandler,
    HandlerOutput,
)

from app.handlers.output_parser import parse_handler_output

from app.handlers.prompt import (
    build_handler_system_prompt,
    is_explicit_system_qa,
)

from app.models.model_manager import get_model_manager


class LocalLLMHandler(BaseHandler):
    """
    Local LLM implementation of the central Handler.

    The Handler does NOT own a physical model instance.

    It requests a shared runtime from ModelManager so the same local base
    model can later be reused by LLMAgent instances.
    """

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
        self.model_path = self.models_dir / self.model_name

        self.device = str(
            config.get(
                "device",
                "cpu",
            )
        ).lower()

        self.dtype_name = str(
            config.get(
                "torch_dtype",
                "float32",
            )
        ).lower()

        generation = config.get(
            "generation",
            {},
        )

        self.max_new_tokens = int(
            generation.get(
                "max_new_tokens",
                256,
            )
        )

        self.temperature = float(
            generation.get(
                "temperature",
                0.2,
            )
        )

        self.do_sample = bool(
            generation.get(
                "do_sample",
                False,
            )
        )

        self._runtime = None

    def _ensure_loaded(self) -> None:
        if self._runtime is not None:
            return

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Local Handler model not found: {self.model_path}"
            )

        print(
            "Loading local Handler model through ModelManager:",
            self.model_path,
        )

        print(
            "Handler device:",
            self.device,
        )

        print(
            "Handler dtype:",
            self.dtype_name,
        )

        manager = get_model_manager()

        self._runtime = manager.get_runtime(
            model_path=str(self.model_path),
            device=self.device,
            torch_dtype=self.dtype_name,
        )

    @property
    def tokenizer(self):
        self._ensure_loaded()
        return self._runtime.tokenizer

    @property
    def model(self):
        self._ensure_loaded()
        return self._runtime.model

    def _build_system_prompt(
        self,
        user_request: str,
    ) -> str:

        return build_handler_system_prompt(
            user_request,
            self.registry.as_prompt_registry(),
            self.command_store.retrieve,
        )

    def _input_device(self):
        return (
            self.model
            .get_input_embeddings()
            .weight
            .device
        )

    def handle(
        self,
        user_request: str,
    ) -> HandlerOutput:

        self._ensure_loaded()

        # Guard only obvious questions about the multi-agent system.
        #
        # This does not replace LLM routing. It prevents a small local model
        # from accidentally turning an obvious SYSTEM Q&A request into an
        # executable command.
        explicit_system_qa = is_explicit_system_qa(
            user_request
        )

        system_prompt = self._build_system_prompt(
            user_request
        )

        if explicit_system_qa:
            system_prompt += (
                "\n\n"
                "IMPORTANT FOR THIS REQUEST:\n"
                "This request has already been classified by the backend "
                "as MODE 2 — SYSTEM Q&A MODE.\n"
                "Answer ONLY in natural language.\n"
                "Do NOT output JSON.\n"
                "Do NOT execute or propose an engine command as JSON.\n"
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

        tokenizer = self.tokenizer
        model = self.model

        if hasattr(
            tokenizer,
            "apply_chat_template",
        ):
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        else:
            text = (
                f"{system_prompt}\n\n"
                f"User request:\n"
                f"{user_request}\n\n"
                f"Answer:"
            )

        inputs = tokenizer(
            text,
            return_tensors="pt",
        )

        input_device = self._input_device()

        inputs = {
            key: value.to(input_device)
            for key, value in inputs.items()
        }

        generation_kwargs: Dict[str, Any] = {
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.do_sample,
            "pad_token_id": tokenizer.eos_token_id,
        }

        if self.do_sample:
            generation_kwargs["temperature"] = (
                self.temperature
            )

        outputs = model.generate(
            **inputs,
            **generation_kwargs,
        )

        generated_tokens = outputs[0][
            inputs["input_ids"].shape[-1]:
        ]

        answer = tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()

        print(
            "LOCAL HANDLER mode:",
            "SYSTEM_QA"
            if explicit_system_qa
            else "LLM_ROUTED",
        )

        print(
            "LOCAL HANDLER raw answer:"
        )

        print(answer)

        # Critical safety boundary:
        #
        # an obvious system question can NEVER become an executable
        # Handler command merely because the LLM happened to emit JSON.
        if explicit_system_qa:
            return answer

        return parse_handler_output(
            answer,
            allow_embedded_json=True,
        )