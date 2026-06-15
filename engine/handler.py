from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from engine.agent_registry import AgentRegistry
from engine.command_store import CommandStore


class RuleBasedHandler:
    def __init__(self, registry: AgentRegistry, command_store: CommandStore) -> None:
        self.registry = registry
        self.command_store = command_store

    def build_system_prompt(self, user_request: str) -> str:
        agents = self.registry.snapshot()
        commands = self.command_store.retrieve(user_request, top_k=3)

        agents_block = "\n".join(
            f"- {name}: {meta.get('system_prompt', '')}"
            for name, meta in agents.items()
        )

        commands_block = "\n".join(
            f"- {c['name']}: {c.get('functionality', '')}"
            for c in commands
        )

        return (
            "You are the central Handler of a distributed multi-agent system.\n"
            "AVAILABLE AGENTS:\n"
            f"{agents_block}\n\n"
            "AVAILABLE COMMANDS:\n"
            f"{commands_block}\n"
        )

    def handle(self, user_request: str) -> List[Dict[str, Any]]:
        text = user_request.strip()
        lower = text.lower()

        if any(x in lower for x in ["какие агенты", "список агентов", "list agents", "what agents"]):
            return [{"action": "list_agents"}]

        if "создай" in lower and "агент" in lower:
            name = self._extract_agent_name(text) or "NewAgent"
            return [{
                "action": "create_agent",
                "agent": name,
                "description": f"Agent created from request: {text}",
                "system_prompt": f"Ты агент {name}. Твоя роль сформирована из запроса пользователя: {text}",
                "tags": self._guess_tags(text),
            }]

        if "create" in lower and "agent" in lower:
            name = self._extract_agent_name(text) or "NewAgent"
            return [{
                "action": "create_agent",
                "agent": name,
                "description": f"Agent created from request: {text}",
                "system_prompt": f"You are {name}. Your role was created from user request: {text}",
                "tags": self._guess_tags(text),
            }]

        if any(x in lower for x in ["удали агента", "delete agent", "remove agent"]):
            name = self._extract_agent_name(text)
            if not name:
                selected = self.registry.select_agent(text)
                name = selected or ""
            return [{"action": "delete_agent", "agent": name}]

        selected = self.registry.select_agent(text)
        if selected is None:
            return [{"action": "list_agents"}]

        return [{
            "action": "extract",
            "agents": [selected],
            "prompts": {selected: text}
        }]

    @staticmethod
    def _extract_agent_name(text: str) -> str | None:
        for token in text.replace(",", " ").replace(".", " ").split():
            cleaned = token.strip()
            if cleaned.endswith("Agent") and cleaned[0].isupper():
                return cleaned
        return None

    @staticmethod
    def _guess_tags(text: str) -> List[str]:
        lower = text.lower()

        mapping = {
            "backend": ["backend", "api", "server"],
            "api": ["backend", "api"],
            "бэкенд": ["backend", "api", "server"],
            "devops": ["devops", "docker", "deploy"],
            "docker": ["devops", "docker"],
            "деплой": ["devops", "deploy"],
            "test": ["testing", "qa"],
            "qa": ["testing", "qa"],
            "тест": ["testing", "qa"],
            "security": ["security"],
            "безопас": ["security"],
            "frontend": ["frontend", "ui"],
            "ui": ["frontend", "ui"],
        }

        tags = []
        for key, values in mapping.items():
            if key in lower:
                tags.extend(values)

        return sorted(set(tags))

class LLMHandler:
    def __init__(
        self,
        registry: AgentRegistry,
        command_store: CommandStore,
        core_config_path: str | Path,
    ) -> None:
        self.registry = registry
        self.command_store = command_store

        self.core_config_path = Path(core_config_path)
        with self.core_config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)

        core_model = config["core_model"]

        self.model_path = core_model["model_path"]
        self.device = core_model.get("device", "cpu")
        self.dtype_name = core_model.get("torch_dtype", "float32")
        self.system_prompt = core_model.get("system_prompt", "")

        generation = core_model.get("generation", {})
        self.max_new_tokens = generation.get("max_new_tokens", 256)
        self.temperature = generation.get("temperature", 0.2)
        self.do_sample = generation.get("do_sample", False)

        self.tokenizer = None
        self.model = None

    def _ensure_loaded(self) -> None:
        if self.tokenizer is not None and self.model is not None:
            return

        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch

        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }

        torch_dtype = dtype_map.get(self.dtype_name, torch.float32)

        print(f"Loading CORE model: {self.model_path}")
        print(f"CORE device: {self.device}, dtype: {self.dtype_name}")

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            local_files_only=True,
            trust_remote_code=True
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            local_files_only=True,
            torch_dtype=torch_dtype,
            trust_remote_code=True
        )

        self.model.to(self.device)
        self.model.eval()

    def build_system_prompt(self, user_request: str) -> str:
        agents = self.registry.snapshot()
        commands = self.command_store.retrieve(user_request, top_k=10)

        agents_block = json.dumps(agents, ensure_ascii=False, indent=2)
        commands_block = json.dumps(commands, ensure_ascii=False, indent=2)

        return f"""
{self.system_prompt}

Твоя задача — вернуть ТОЛЬКО JSON-массив команд.
Не пиши пояснения.
Не используй markdown.
Не оборачивай JSON в ```.

Доступные агенты:
{agents_block}

Доступные команды:
{commands_block}

Если пользователь просит создать агента на модели, верни команду create_agent.

Пример создания LLM-агента:
[
  {{
    "action": "create_agent",
    "agent": "AnalystAgent",
    "type": "llm",
    "model_name": "Qwen2.5-3B-Instruct",
    "description": "Analyst agent",
    "system_prompt": "Ты аналитический агент. Анализируй задачи и отвечай кратко.",
    "tags": ["analysis", "summary"]
  }}
]

Пример запуска агента:
[
  {{
    "action": "extract",
    "agents": ["AnalystAgent"],
    "prompts": {{
      "AnalystAgent": "Объясни архитектуру проекта"
    }}
  }}
]

Запрос пользователя:
{user_request}
""".strip()

    def handle(self, user_request: str) -> List[Dict[str, Any]]:
        self._ensure_loaded()

        system_prompt = self.build_system_prompt(user_request)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request}
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
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
            pad_token_id=self.tokenizer.eos_token_id
        )

        answer = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[-1]:],
            skip_special_tokens=True
        ).strip()

        print("CORE raw answer:")
        print(answer)

        return self._parse_commands(answer)

    @staticmethod
    def _parse_commands(text: str) -> List[Dict[str, Any]]:
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return [parsed]
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return [parsed]

        raise ValueError(
            "LLMHandler could not parse JSON commands from model output:\n"
            + text
        )

def create_handler(
    registry: AgentRegistry,
    command_store: CommandStore,
    core_config_path: str | Path,
    use_llm: bool = True,
):
    if use_llm and Path(core_config_path).exists():
        return LLMHandler(registry, command_store, core_config_path)

    return RuleBasedHandler(registry, command_store)