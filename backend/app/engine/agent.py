from __future__ import annotations

import json
import urllib.request
import os
from pathlib import Path
from typing import Any, Dict, List

from app.rag.memory import AgentMemory
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

        self.max_new_tokens = int(
            generation.get(
                "max_new_tokens",
                256,
            )
        )

        self.temperature = float(
            generation.get(
                "temperature",
                0.7,
            )
        )

        self.do_sample = bool(
            generation.get(
                "do_sample",
                True,
            )
        )

        # ---------------------------------------------------------
        # Shared runtime configuration
        # ---------------------------------------------------------
        #
        # Agents and Handler must use the same device/dtype pair
        # when they use the same physical base model. Otherwise
        # ModelManager correctly treats them as different runtimes
        # and loads another physical copy.
        #
        # Priority:
        #
        # agent metadata
        #     ↓
        # AGENT_* environment
        #     ↓
        # HANDLER_* environment
        #     ↓
        # CPU-safe defaults
        #

        self.device = str(
            metadata.get(
                "device",
                os.getenv(
                    "AGENT_DEVICE",
                    os.getenv(
                        "HANDLER_DEVICE",
                        "cpu",
                    ),
                ),
            )
        ).lower()

        self.torch_dtype_name = str(
            metadata.get(
                "torch_dtype",
                os.getenv(
                    "AGENT_TORCH_DTYPE",
                    os.getenv(
                        "HANDLER_TORCH_DTYPE",
                        "float32",
                    ),
                ),
            )
        ).lower()

        self._runtime = None

        self.tokenizer = None
        self.model = None

        self.inference_provider = str(
            os.getenv(
                "AGENT_INFERENCE_PROVIDER",
                "transformers",
            )
        ).strip().lower()

        self.llamacpp_base_url = str(
            os.getenv(
                "LLAMACPP_BASE_URL",
                "http://host.docker.internal:8081",
            )
        ).rstrip("/")

        self.llamacpp_model = str(
            os.getenv(
                "LLAMACPP_MODEL",
                "Qwen3-4B",
            )
        )

        self.llamacpp_timeout = float(
            os.getenv(
                "LLAMACPP_TIMEOUT",
                "120",
            )
        )

        self.memory = AgentMemory(
            agent_name=self.name
        )

    def _ensure_loaded(self) -> None:

        if self.inference_provider == "llamacpp":
            return

        if self._runtime is not None:
            return

        if not self.model_path:
            raise RuntimeError(
                f"Agent '{self.name}' has no local "
                "model configured. No generative model "
                "was discovered for automatic assignment."
            )

        model_path = Path(
            self.model_path
        )

        if not model_path.exists():
            raise FileNotFoundError(
                f"Local model for agent "
                f"'{self.name}' was not found: "
                f"{model_path}"
            )

        manager = get_model_manager()

        print(
            f"[LLMAgent] requesting runtime: "
            f"agent={self.name} "
            f"model={self.model_path} "
            f"device={self.device} "
            f"dtype={self.torch_dtype_name}"
        )

        self._runtime = manager.get_runtime(
            model_path=self.model_path,
            device=self.device,
            torch_dtype=self.torch_dtype_name,
        )

        self.tokenizer = (
            self._runtime.tokenizer
        )

        self.model = (
            self._runtime.model
        )

    def _build_agent_messages(
        self,
        prompt: str,
        reasoning_instruction: str,
        rag_context: str = "",
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

        if rag_context.strip():
            system_parts.append(
                "DOCUMENT KNOWLEDGE:\n"
                "Use the following retrieved document excerpts as the "
                "authoritative source for document-specific facts.\n"
                "Do not invent facts that are absent from these excerpts.\n"
                "If the excerpts do not contain enough information to answer "
                "the question, explicitly state that the available documents "
                "do not provide that information.\n"
                "Answer in the language used by the user.\n\n"
                f"{rag_context}"
            )

        effective_system_prompt = (
            "\n\n".join(
                system_parts
            )
        )

        return [
            {
                "role": "system",
                "content": effective_system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

    def _input_device(self):
        """
        Determine the device where model input embeddings live.

        Using the actual embedding device is more robust than returning
        the configured device string and also remains compatible with a
        future device_map deployment.
        """

        return (
            self.model
            .get_input_embeddings()
            .weight
            .device
        )

    @staticmethod
    def _build_source_metadata(
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        document_processing = metadata.get(
            "document_processing",
            {},
        )

        processing_metadata = document_processing.get(
            "metadata",
            {},
        )

        return {
            "kind": document_processing.get(
                "kind",
                "",
            ),
            "extension": processing_metadata.get(
                "extension",
                "",
            ),
            "source_kind": processing_metadata.get(
                "source_kind",
                "",
            ),
            "processing_pipeline": processing_metadata.get(
                "processing_pipeline",
                "",
            ),
        }

    

    def _build_rag_context(
        self,
        prompt: str,
        *,
        top_k: int = 5,
        rerank_top_k: int = 3,
    ) -> tuple[str, List[Dict[str, Any]]]:

        retrieved = self.memory.retrieve(
            prompt,
            top_k=top_k,
            rerank_top_k=rerank_top_k,
        )

        if not retrieved:
            return "", []

        context_parts = []
        sources = []

        for index, item in enumerate(retrieved, start=1):
            context_parts.append(
                f"[SOURCE {index}]\n"
                f"{item.text}"
            )

            source_path = Path(item.source_path)

            sources.append({
                "source_number": index,
                "document_id": item.document_id,
                "chunk_index": item.chunk_index,
                "file_name": source_path.name,
                "text": item.text,
                "similarity": item.similarity,
                "rerank_score": item.rerank_score,
                "metadata": self._build_source_metadata(
                    item.metadata
                ),
            })

        return "\n\n".join(context_parts), sources

    def _generate_llamacpp(
        self,
        messages: List[Dict[str, str]],
        *,
        max_new_tokens: int,
        temperature: float,
        do_sample: bool,
    ) -> str:
        request_messages = [
            dict(message)
            for message in messages
        ]

        # Qwen3: disable reasoning tokens for fast interactive responses.
        request_messages[-1]["content"] = (
            request_messages[-1]["content"].rstrip()
            + "\n\n/no_think"
        )

        payload = {
            "model": self.llamacpp_model,
            "messages": request_messages,
            "max_tokens": max_new_tokens,
            "temperature": (
                temperature
                if do_sample
                else 0.0
            ),
            "stream": False,
        }

        request = urllib.request.Request(
            f"{self.llamacpp_base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=self.llamacpp_timeout,
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
                "llama.cpp returned an empty agent answer. "
                f"reasoning_content_present={bool(reasoning)}"
            )

        return answer


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

        rag_enabled = bool(
            payload.get("rag_enabled", True)
        )

        rag_context = ""
        sources: List[Dict[str, Any]] = []

        if rag_enabled and prompt.strip():
            rag_context, sources = self._build_rag_context(
                prompt,
                top_k=int(
                    payload.get("rag_top_k", 5)
                ),
                rerank_top_k=int(
                    payload.get("rag_rerank_top_k", 3)
                ),
            )

        decision = classify_complexity(
            prompt
        )

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
            f"confidence={decision.confidence:.4f}",
            f"probs={decision.probs}",
            f"enabled={decision.enabled}",
        )

        messages = (
            self._build_agent_messages(
                prompt,
                policy.instruction,
                rag_context,
            )
        )

        if self.inference_provider == "llamacpp":
            answer = self._generate_llamacpp(
                messages,
                max_new_tokens=policy.max_new_tokens,
                temperature=policy.temperature,
                do_sample=policy.do_sample,
            )

        else:
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

            input_device = (
                self._input_device()
            )

            inputs = {
                key: value.to(
                    input_device
                )
                for key, value
                in inputs.items()
            }

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

            answer = (
                self.tokenizer.decode(
                    generated_tokens,
                    skip_special_tokens=True,
                )
                .strip()
            )

        return {
            "agent": self.name,
            "status": "ok",
            "type": "llm",
            "role": self.system_prompt,

            "model": {
                "name": (
                    self.llamacpp_model
                    if self.inference_provider == "llamacpp"
                    else self.model_name
                ),

                "path": (
                    ""
                    if self.inference_provider == "llamacpp"
                    else self.model_path
                ),

                "assignment":
                    self.model_assignment,

                "provider":
                    self.inference_provider,

                "shared_runtime":
                    True,

                "device": (
                    "llama.cpp-server"
                    if self.inference_provider == "llamacpp"
                    else self.device
                ),

                "torch_dtype": (
                    ""
                    if self.inference_provider == "llamacpp"
                    else self.torch_dtype_name
                ),
            },

            "received_prompt":
                prompt,

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

            "rag": {
                "enabled": rag_enabled,
                "used": bool(sources),
                "sources_count": len(sources),
                "sources": sources,
            },

            "result":
                answer,
        }

    def add_data(
        self,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:

        data_type = data.get("type", "")

        if data_type != "loaded_document":
            return {
                "status": "ignored",
                "agent": self.name,
                "reason": (
                    f"Unsupported memory data type: "
                    f"{data_type}"
                ),
            }

        document_id = str(
            data.get("id", "")
        ).strip()

        chunks = data.get(
            "chunks",
            [],
        )

        if not document_id:
            raise ValueError(
                "Loaded document has no document id"
            )

        if not isinstance(chunks, list):
            raise TypeError(
                "Loaded document chunks must be a list"
            )

        result = self.memory.add_document(
            document_id=document_id,
            chunks=chunks,
            source_path=str(
                data.get("file_path", "")
            ),
            saved_path=str(
                data.get("saved_path", "")
            ),
            metadata={
                "document_processing":
                    data.get(
                        "document_processing",
                        {},
                    ),
            },
        )

        return {
            "status": "ok",
            "agent": self.name,
            "memory": result,
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