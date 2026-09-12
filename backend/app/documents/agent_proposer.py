from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AgentProposal:
    name: str
    description: str
    system_prompt: str
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def semantic_text(self) -> str:
        parts = [
            self.name,
            self.description,
            " ".join(self.tags),
        ]
        return "\n".join(
            part for part in parts
            if part
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tags": self.tags,
            "confidence": self.confidence,
        }


class AgentProposer:
    """
    Internal LLM service used when SemanticAgentRouter cannot find
    a suitable existing agent for a document.

    This component does NOT use or modify the Central Handler prompt.

    Supported providers:
        - gigachat
        - local

    Provider selection:
        AGENT_PROPOSER_PROVIDER
        -> HANDLER_PROVIDER
        -> gigachat
    """

    def __init__(
        self,
        models_dir: str | Path | None = None,
    ) -> None:
        self.provider = (
            os.getenv("AGENT_PROPOSER_PROVIDER")
            or os.getenv("HANDLER_PROVIDER")
            or "gigachat"
        ).strip().lower()

        self.models_dir = (
            Path(models_dir)
            if models_dir is not None
            else None
        )

        self._gigachat_client = None

        self._local_tokenizer = None
        self._local_model = None
        self._local_device = None

    def propose(
        self,
        document_text: str,
        existing_agents: Dict[str, Dict[str, Any]],
        document_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentProposal]:

        document_text = document_text.strip()

        if not document_text:
            return None

        prompt = self._build_prompt(
            document_text=document_text,
            existing_agents=existing_agents,
            document_metadata=document_metadata or {},
        )

        if self.provider == "gigachat":
            raw_answer = self._generate_gigachat(prompt)

        elif self.provider == "local":
            raw_answer = self._generate_local(prompt)

        else:
            raise ValueError(
                "Unsupported AgentProposer provider: "
                f"{self.provider}"
            )

        return self._parse_proposal(raw_answer)

    def _build_prompt(
        self,
        *,
        document_text: str,
        existing_agents: Dict[str, Dict[str, Any]],
        document_metadata: Dict[str, Any],
    ) -> str:

        agents_payload = []

        for name, metadata in existing_agents.items():
            agents_payload.append({
                "name": name,
                "description":
                    metadata.get("description", ""),
                "tags":
                    metadata.get("tags", []),
            })

        # Do not send arbitrarily huge documents to the proposal model.
        max_chars = int(
            os.getenv(
                "AGENT_PROPOSER_MAX_CHARS",
                "12000",
            )
        )

        document_excerpt = document_text[:max_chars]

        return f"""
You are an internal component of a multi-agent AI system.

A document could not be confidently assigned to any existing agent.

Your task is to describe ONE useful specialist agent that should own
documents of this semantic domain.

Do not create an agent merely for the individual filename or one narrow
fact. The agent must represent a reusable professional specialization.

Existing agents:
{json.dumps(agents_payload, ensure_ascii=False, indent=2)}

Document metadata:
{json.dumps(document_metadata, ensure_ascii=False, indent=2)}

Document:
--- BEGIN DOCUMENT ---
{document_excerpt}
--- END DOCUMENT ---

Return ONLY one valid JSON object.

Required schema:

{{
  "name": "EnglishAgentName",
  "description": "Short semantic description of the agent specialization",
  "system_prompt": "Instruction defining the specialist's role and domain",
  "tags": ["tag1", "tag2", "tag3"],
  "confidence": 0.0
}}

Rules:

1. name must be a short English identifier ending with Agent.
2. name must describe a reusable domain, not the document filename.
3. description must explain what knowledge/tasks belong to this agent.
4. system_prompt must define the agent as a specialist in that domain.
5. tags must contain 3 to 8 concise semantic tags.
6. confidence must be between 0 and 1.
7. Do not output Markdown.
8. Do not output explanations outside JSON.
""".strip()

    def _generate_gigachat(
        self,
        prompt: str,
    ) -> str:

        if self._gigachat_client is None:
            from gigachat import GigaChat

            model = os.getenv(
                "GIGACHAT_MODEL",
                "GigaChat-2-Pro",
            )

            self._gigachat_client = GigaChat(
                model=model
            )

        model = os.getenv(
            "GIGACHAT_MODEL",
            "GigaChat-2-Pro",
        )

        messages = [
            {
                "role": "system",
                "content":
                    "You are an internal semantic "
                    "agent-profile generator. "
                    "Return valid JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        response = self._gigachat_client.chat({
            "messages": messages,
            "model": model,
        })

        return (
            response.choices[0]
            .message.content
            .strip()
        )

    def _generate_local(
        self,
        prompt: str,
    ) -> str:

        self._ensure_local_model()

        messages = [
            {
                "role": "system",
                "content":
                    "You are an internal semantic "
                    "agent-profile generator. "
                    "Return valid JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        tokenizer = self._local_tokenizer
        model = self._local_model
        device = self._local_device

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
                messages[0]["content"]
                + "\n\n"
                + prompt
                + "\n\nJSON:"
            )

        inputs = tokenizer(
            text,
            return_tensors="pt",
        ).to(device)

        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

        generated_tokens = outputs[0][
            inputs["input_ids"].shape[-1]:
        ]

        return tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()

    def _ensure_local_model(self) -> None:

        if (
            self._local_tokenizer is not None
            and self._local_model is not None
        ):
            return

        import torch

        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
        )

        model_path_env = os.getenv(
            "AGENT_PROPOSER_MODEL_PATH",
            "",
        ).strip()

        if model_path_env:
            model_path = Path(model_path_env)

        else:
            model_name = os.getenv(
                "AGENT_PROPOSER_MODEL_NAME",
                "",
            ).strip()

            if not model_name:
                raise RuntimeError(
                    "Local AgentProposer requires "
                    "AGENT_PROPOSER_MODEL_PATH or "
                    "AGENT_PROPOSER_MODEL_NAME."
                )

            if self.models_dir is None:
                raise RuntimeError(
                    "models_dir is not configured "
                    "for local AgentProposer."
                )

            model_path = (
                self.models_dir
                / model_name
            )

        if not model_path.exists():
            raise FileNotFoundError(
                "AgentProposer local model "
                f"not found: {model_path}"
            )

        device = os.getenv(
            "AGENT_PROPOSER_DEVICE",
            "cpu",
        )

        dtype_name = os.getenv(
            "AGENT_PROPOSER_TORCH_DTYPE",
            "float32",
        )

        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }

        torch_dtype = dtype_map.get(
            dtype_name,
            torch.float32,
        )

        self._local_tokenizer = (
            AutoTokenizer.from_pretrained(
                model_path,
                local_files_only=True,
                trust_remote_code=True,
            )
        )

        self._local_model = (
            AutoModelForCausalLM.from_pretrained(
                model_path,
                local_files_only=True,
                torch_dtype=torch_dtype,
                trust_remote_code=True,
            )
        )

        self._local_model.to(device)
        self._local_model.eval()

        self._local_device = device

    def _parse_proposal(
        self,
        raw_answer: str,
    ) -> AgentProposal:

        cleaned = raw_answer.strip()

        # Tolerate ```json ... ``` even though the model
        # was explicitly asked not to use Markdown.
        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )

            cleaned = re.sub(
                r"\s*```$",
                "",
                cleaned,
            )

        try:
            payload = json.loads(cleaned)

        except json.JSONDecodeError as exc:
            # One recovery attempt: extract the outermost JSON object.
            start = cleaned.find("{")
            end = cleaned.rfind("}")

            if (
                start == -1
                or end == -1
                or end <= start
            ):
                raise ValueError(
                    "AgentProposer returned invalid JSON: "
                    f"{raw_answer}"
                ) from exc

            try:
                payload = json.loads(
                    cleaned[start:end + 1]
                )

            except json.JSONDecodeError as inner_exc:
                raise ValueError(
                    "AgentProposer returned invalid JSON: "
                    f"{raw_answer}"
                ) from inner_exc

        if not isinstance(payload, dict):
            raise ValueError(
                "AgentProposer response must be "
                "a JSON object."
            )

        name = self._normalize_name(
            str(payload.get("name", ""))
        )

        description = str(
            payload.get(
                "description",
                "",
            )
        ).strip()

        system_prompt = str(
            payload.get(
                "system_prompt",
                "",
            )
        ).strip()

        raw_tags = payload.get(
            "tags",
            [],
        )

        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []

        for item in raw_tags:
            value = str(item).strip()

            if (
                value
                and value not in tags
            ):
                tags.append(value)

        tags = tags[:8]

        try:
            confidence = float(
                payload.get(
                    "confidence",
                    1.0,
                )
            )
        except (TypeError, ValueError):
            confidence = 1.0

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        if not name:
            raise ValueError(
                "AgentProposer returned an empty name."
            )

        if not description:
            raise ValueError(
                "AgentProposer returned an empty description."
            )

        if not system_prompt:
            raise ValueError(
                "AgentProposer returned an empty system_prompt."
            )

        if not tags:
            raise ValueError(
                "AgentProposer returned no tags."
            )

        return AgentProposal(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tags=tags,
            confidence=confidence,
        )

    @staticmethod
    def _normalize_name(
        value: str,
    ) -> str:

        value = value.strip()

        # Keep only letters, digits and underscores.
        value = re.sub(
            r"[^A-Za-z0-9_]",
            "",
            value,
        )

        if not value:
            return ""

        if not value.endswith("Agent"):
            value += "Agent"

        return value