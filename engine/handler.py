from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Union

from engine.agent_registry import AgentRegistry
from engine.command_store import CommandStore


HandlerOutput = Union[str, List[Dict[str, Any]]]


def build_handler_system_prompt(user_request, registry, retrieve_commands):
    agents_lines = []
    for a in registry["agents"]:
        agents_lines.append("  - " + a["name"] + ": " + a["system_prompt"])
    agents_block = "\n".join(agents_lines)

    top_commands = retrieve_commands(user_request, top_k=3)

    cmd_lines = []
    for c in top_commands:
        cmd_lines.append("  name:          " + c["name"])
        cmd_lines.append("  functionality: " + c["functionality"])
        cmd_lines.append("  example:       " + c["example"])
        cmd_lines.append("  template:      " + json.dumps(c["command"], ensure_ascii=False))
        cmd_lines.append(
            "  usage_example: " +
            json.dumps(
                c.get("usage_example", {}),
                ensure_ascii=False
            )
        )
        cmd_lines.append("")
    commands_block = "\n".join(cmd_lines)

    prompt = (
        "You are the central Handler of a distributed multi-agent system.\n"
        "\n"
        "You are NOT a general chatbot.\n"
        "You operate ONLY within the scope of this multi-agent system.\n"
        "\n"
        "You have TWO allowed response modes:\n"
        "\n"
        "MODE 1 — COMMAND MODE:\n"
        "When the user asks to do something with agents or data — decompose the request\n"
        "into one or more engine commands and output a JSON array.\n"
        "\n"
        "MODE 2 — SYSTEM Q&A MODE:\n"
        "Triggers: any question about agents, commands, system capabilities, how it works.\n"
        "Examples of MODE 2 questions:\n"
        "  - 'what agents are in the system'\n"
        "  - 'what does FinanceAgent do'\n"
        "  - 'list all commands'\n"
        "  - 'what can this system do'\n"
        "  - 'give me the functionality of each agent'\n"
        "\n"
        "In MODE 2 you MUST:\n"
        "  - Answer DIRECTLY in natural language\n"
        "  - Use ONLY information from AVAILABLE AGENTS and AVAILABLE COMMANDS in this prompt\n"
        "  - NEVER generate any JSON\n"
        "  - NEVER call extract, add, or any other command\n"
        "  - End with one suggested follow-up action\n"
        "\n"
        "MODE 2 response format:\n"
        "\n"
        "your answer here\n"
        "\n"
        "\n"
        "CRITICAL: if the user asks ABOUT the system — answer from the prompt, do NOT execute commands.\n"
        "\n"
        "AVAILABLE AGENTS (from registry):\n"
        + agents_block +
        "\n\n"
        "AVAILABLE COMMANDS (retrieved for this request):\n"
        + commands_block +
        "\n\n"
        "YOUR TASK:\n"
        "1. Determine which mode applies to the user request\n"
        "2. MODE 1: decompose into commands, fill templates, output JSON array\n"
        "3. MODE 2: answer the system question briefly, suggest a follow-up action\n"
        "4. Commands must follow usage_example format\n"
        "5. Command sequence reflects execution order\n"
        "\n"
        "OUTPUT FORMAT for MODE 1 (strict JSON array):\n"
        "[\n"
        "  { ...command_1... },\n"
        "  { ...command_2... }\n"
        "]\n"
        "\n"
        "RULES:\n"
        "- Agent names must exactly match AVAILABLE AGENTS\n"
        "- Command actions must exactly match AVAILABLE COMMANDS\n"
        "- Prefer minimal number of commands to fulfill the request\n"
        "- If one command is enough output array with one element\n"
        "- For MODE 1 output ONLY the JSON array, no markdown, no explanation\n"
        "- For MODE 2 keep the answer short and always redirect to a system action\n"
        "- NEVER answer questions unrelated to this system\n"
        "- If the request is completely off-topic respond strictly with:\n"
        "  \n"
    )
    return prompt


class RuleBasedHandler:
    def __init__(self, registry: AgentRegistry, command_store: CommandStore) -> None:
        self.registry = registry
        self.command_store = command_store

    def build_system_prompt(self, user_request: str) -> str:
        return build_handler_system_prompt(
            user_request,
            self.registry.as_prompt_registry(),
            self.command_store.retrieve
        )

    def handle(self, user_request: str) -> HandlerOutput:
        text = user_request.strip()
        lower = text.lower()

        if any(x in lower for x in ["какие агенты", "список агентов", "list agents", "what agents"]):
            return "Доступные агенты: " + ", ".join(self.registry.list_agents()) + ". Можно создать или запустить агента."

        if any(x in lower for x in ["какие команды", "список команд", "list commands", "what commands"]):
            return "Доступные команды: " + ", ".join(c["name"] for c in self.command_store.list_commands()) + ". Можно выполнить команду через Handler."

        if any(x in lower for x in ["отмени", "cancel"]):
            return [{"action": "cancel", "reason": text}]

        if any(x in lower for x in ["разреши конфликты", "logger", "логгер", "resolve conflicts"]):
            return [{"action": "resolve_logger_conflicts"}]

        if any(x in lower for x in ["загрузи документ", "route document", "load document", "подходящего агента"]):
            return [{"action": "route_document", "file_path": self._extract_file_path(text), "threshold": 1}]

        if ("создай" in lower and "агент" in lower) or ("create" in lower and "agent" in lower):
            name = self._extract_agent_name(text) or "NewAgent"
            model_name = self._extract_model_name(text)

            command = {
                "action": "create_agent",
                "agent": name,
                "type": "llm" if model_name else "mock",
                "description": f"Agent created from request: {text}",
                "system_prompt": f"Ты агент {name}. Твоя роль сформирована из запроса пользователя: {text}",
                "tags": self._guess_tags(text),
            }

            if model_name:
                command["model_name"] = model_name

            return [command]

        if any(x in lower for x in ["удали агента", "delete agent", "remove agent"]):
            name = self._extract_agent_name(text) or self.registry.select_agent(text) or ""
            return [{"action": "delete_agent", "agent": name}]

        selected = self.registry.select_agent(text)

        if selected is None:
            return "В системе нет доступных агентов. Можно создать нового агента."

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
    def _extract_model_name(text: str) -> str | None:
        known_models = [
            "Qwen2.5-3B-Instruct",
            "Qwen2.5-7B-Instruct",
            "Qwen2.5-14B-Instruct",
            "Mistral-7B",
        ]

        for model in known_models:
            if model.lower() in text.lower():
                return model

        return None

    @staticmethod
    def _extract_file_path(text: str) -> str:
        match = re.search(
            r"([A-Za-z]:[\\/][^\s]+|[\w./\\-]+\.(?:txt|md|json|pdf|csv|py))",
            text
        )
        return match.group(1) if match else ""

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
            "analysis": ["analysis", "summary"],
            "аналит": ["analysis", "summary"],
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
        core_config_path: str | Path
    ) -> None:
        self.registry = registry
        self.command_store = command_store
        self.core_config_path = Path(core_config_path)

        config = json.loads(self.core_config_path.read_text(encoding="utf-8"))
        core_model = config["core_model"]

        self.model_path = core_model["model_path"]
        self.device = core_model.get("device", "cpu")
        self.dtype_name = core_model.get("torch_dtype", "float32")

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

        torch_dtype = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }.get(self.dtype_name, torch.float32)

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
        return build_handler_system_prompt(
            user_request,
            self.registry.as_prompt_registry(),
            self.command_store.retrieve
        )

    def handle(self, user_request: str) -> HandlerOutput:
        self._ensure_loaded()

        system_prompt = self.build_system_prompt(user_request)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request}
        ]

        if hasattr(self.tokenizer, "apply_chat_template"):
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        else:
            text = f"{system_prompt}\n\nUser request:\n{user_request}\n\nAnswer:"

        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)

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

        return self._parse_handler_output(answer)

    @staticmethod
    def _parse_handler_output(text: str) -> HandlerOutput:
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return [parsed]
            if isinstance(parsed, list):
                return parsed
            return text
        except json.JSONDecodeError:
            pass

        for pattern in [r"\[.*\]", r"\{.*\}"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return [parsed]
                if isinstance(parsed, list):
                    return parsed

        return text


def create_handler(
    registry: AgentRegistry,
    command_store: CommandStore,
    core_config_path: str | Path,
    use_llm: bool = True
):
    if use_llm and Path(core_config_path).exists():
        return LLMHandler(registry, command_store, core_config_path)

    return RuleBasedHandler(registry, command_store)