from __future__ import annotations

from typing import Any, Dict

import json
import urllib.request

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


class LlamaCppHandler(BaseHandler):
    """
    Handler implementation backed by an external llama.cpp server.

    llama.cpp owns the physical model runtime.
    The backend communicates with it through the OpenAI-compatible
    /v1/chat/completions endpoint.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        command_store: CommandStore,
        config: Dict[str, Any],
    ) -> None:
        self.registry = registry
        self.command_store = command_store

        self.base_url = str(
            config.get(
                "base_url",
                "http://host.docker.internal:8081",
            )
        ).rstrip("/")

        self.model = str(
            config.get(
                "model",
                "Qwen3-4B",
            )
        )

        self.max_new_tokens = int(
            config.get(
                "max_new_tokens",
                128,
            )
        )

        self.temperature = float(
            config.get(
                "temperature",
                0.0,
            )
        )

        self.timeout = float(
            config.get(
                "timeout",
                120.0,
            )
        )

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

        # Qwen3 supports /no_think.
        # It is intentionally appended to the user message so the model
        # returns the actual answer instead of spending the response budget
        # on reasoning_content.
        model_request = (
            f"{user_request}\n\n"
            "/no_think"
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": model_request,
                },
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_new_tokens,
            "stream": False,
        }

        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.timeout,
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

        choices = data.get("choices") or []

        if not choices:
            raise RuntimeError(
                "llama.cpp returned no completion choices."
            )

        message = choices[0].get("message") or {}

        answer = str(
            message.get("content") or ""
        ).strip()

        if not answer:
            reasoning = str(
                message.get("reasoning_content") or ""
            ).strip()

            raise RuntimeError(
                "llama.cpp returned an empty answer. "
                f"reasoning_content_present={bool(reasoning)}"
            )

        print(
            "LLAMACPP HANDLER mode:",
            "SYSTEM_QA"
            if explicit_system_qa
            else "LLM_ROUTED",
        )

        print("LLAMACPP HANDLER raw answer:")
        print(answer)

        # Same safety boundary as LocalLLMHandler:
        # an explicit SYSTEM Q&A request must never become an
        # executable engine command.
        if explicit_system_qa:
            return answer

        return parse_handler_output(
            answer,
            allow_embedded_json=True,
        )