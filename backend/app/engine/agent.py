from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.models.model_manager import get_model_manager
from app.routing.complexity.policy import build_reasoning_policy
from app.routing.complexity.service import classify_complexity


class LLMAgent:
    def __init__(
        self,
        metadata: Dict[str, Any],
    ) -> None:
        self.name = metadata["name"]
        self.description = metadata.get(
            "description",
            "",
        )
        self.system_prompt = metadata.get(
            "system_prompt",
            "",
        )
        self.tags: List[str] = list(
            metadata.get("tags", [])
        )

        self.model_path = metadata.get(
            "model_path",
            "",
        )
        self.model_name = metadata.get(
            "model_name",
            "",
        )
        self.model_assignment = metadata.get(
            "model_assignment",
            "",
        )

        generation = metadata.get(
            "generation",
            {},
        )

        self.max_new_tokens = generation.get(
            "max_new_tokens",
            256,
        )
        self.temperature = generation.get(
            "temperature",
            0.7,
        )
        self.do_sample = generation.get(
            "do_sample",
            True,
        )

        self.device = metadata.get(
            "device",
            "auto",
        )
        self.torch_dtype_name = metadata.get(
            "torch_dtype",
            "float16",
        )

        self._runtime = None
        self.tokenizer = None
        self.model = None

    def _ensure_loaded(self) -> None:
        if self._runtime is not None:
            return

        if not self.model_path:
            raise RuntimeError(
                f"Agent '{self.name}' has no local "
                "model configured. No generative model "
                "was discovered for automatic assignment."
            )

        model_path = Path(self.model_path)

        if not model_path.exists():
            raise FileNotFoundError(
                f"Local model for agent "
                f"'{self.name}' was not found: "
                f"{model_path}"
            )

        manager = get_model_manager()

        self._runtime = manager.get_runtime(
            model_path=self.model_path,
            device=self.device,
            torch_dtype=self.torch_dtype_name,
        )

        self.tokenizer = (
            self._runtime.tokenizer
        )
        self.model = self._runtime.model

    def _build_agent_messages(
        self,
        prompt: str,
        reasoning_instruction: str,
    ) -> List[Dict[str, str]]:
        system_parts = []

        if self.system_prompt.strip():
            system_parts.append(
                self.system_prompt.strip()
            )

        if reasoning_instruction.strip():
            system_parts.append(
                reasoning_instruction.strip()
            )

        effective_system_prompt = (
            "\n\n".join(system_parts)
        )

        return [
            {
                "role": "system",
                "content":
                    effective_system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

    def _input_device(self):
        if self.device != "auto":
            return self.device

        return self.model.device

    def run(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._ensure_loaded()

        prompt = (
            payload.get("prompt")
            or payload.get("task")
            or payload.get("query")
            or ""
        )

        decision = classify_complexity(prompt)

        policy = build_reasoning_policy(
            decision,
            base_max_new_tokens=
                self.max_new_tokens,
            base_temperature=
                self.temperature,
            base_do_sample=
                self.do_sample,
        )

        print(
            "[ComplexityRouter]",
            f"agent={self.name}",
            f"raw_mode={decision.mode}",
            f"policy={policy.mode}",
            f"confidence="
            f"{decision.confidence:.4f}",
            f"probs={decision.probs}",
            f"enabled={decision.enabled}",
        )

        messages = (
            self._build_agent_messages(
                prompt,
                policy.instruction,
            )
        )

        if hasattr(
            self.tokenizer,
            "apply_chat_template",
        ):
            text = (
                self.tokenizer
                .apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            )
        else:
            system_text = (
                messages[0]["content"]
            )
            text = (
                f"{system_text}\n\n"
                f"User: {prompt}\n"
                f"Assistant:"
            )

        inputs = self.tokenizer(
            text,
            return_tensors="pt",
        )

        inputs = inputs.to(
            self._input_device()
        )

        generation_kwargs = {
            "max_new_tokens":
                policy.max_new_tokens,
            "do_sample":
                policy.do_sample,
            "pad_token_id": (
                self.tokenizer.pad_token_id
                if (
                    self.tokenizer
                    .pad_token_id
                    is not None
                )
                else
                self.tokenizer.eos_token_id
            ),
        }

        if policy.do_sample:
            generation_kwargs[
                "temperature"
            ] = policy.temperature

        outputs = self.model.generate(
            **inputs,
            **generation_kwargs,
        )

        generated_tokens = outputs[0][
            inputs["input_ids"].shape[-1]:
        ]

        answer = self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()

        return {
            "agent": self.name,
            "status": "ok",
            "type": "llm",
            "role": self.system_prompt,
            "model": {
                "name": self.model_name,
                "path": self.model_path,
                "assignment":
                    self.model_assignment,
                "shared_runtime": True,
            },
            "received_prompt": prompt,
            "reasoning": {
                "classifier_enabled":
                    decision.enabled,
                "raw_label":
                    decision.label,
                "raw_mode":
                    decision.mode,
                "policy":
                    policy.mode,
                "confidence":
                    round(
                        decision.confidence,
                        4,
                    ),
                "probs":
                    decision.probs,
                "reason":
                    decision.reason,
            },
            "result": answer,
        }

    def add_data(
        self,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "status": "ok",
            "agent": self.name,
            "note":
                "LLM memory is not implemented yet",
            "data": data,
        }

    def delete_data(
        self,
        target: str,
    ) -> Dict[str, Any]:
        return {
            "status": "ok",
            "agent": self.name,
            "note":
                "LLM memory is not implemented yet",
            "target": target,
        }

    def edit_data(
        self,
        target: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "status": "ok",
            "agent": self.name,
            "note":
                "LLM memory is not implemented yet",
            "target": target,
            "data": data,
        }

    def load_file(
        self,
        file_path: str,
    ) -> Dict[str, Any]:
        return {
            "status": "ok",
            "agent": self.name,
            "note":
                "RAG loading is not implemented yet",
            "file_path": file_path,
        }
