from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List


_FILE_HINT_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\n\r]+|[^\s]+\.(?:txt|md|json|py|csv|log|yaml|yml|xml|"
    r"png|jpe?g|bmp|tiff?|webp|pdf))",
    re.IGNORECASE,
)

_VISUAL_WORDS = (
    "image", "picture", "photo", "drawing", "diagram", "scan", "blueprint",
    "изображ", "картин", "фото", "чертеж", "чертёж", "схем", "скан",
)

_CREATE_WORDS = (
    "create agent", "new agent", "создай агента", "создать агента", "новый агент",
)


def _merge_commands(primary: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for item in [*primary, *extra]:
        name = str(item.get("name", ""))
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(item)
    return result


def _ensure_named_command(
    commands: List[Dict[str, Any]],
    command_name: str,
    retrieve_commands: Callable,
    retrieval_query: str,
) -> List[Dict[str, Any]]:
    if any(c.get("name") == command_name for c in commands):
        return commands

    candidates = retrieve_commands(retrieval_query, top_k=8)
    selected = [c for c in candidates if c.get("name") == command_name]
    return _merge_commands(commands, selected)


def build_handler_system_prompt(
    user_request: str,
    registry: Dict[str, Any],
    retrieve_commands: Callable,
) -> str:
    agents_lines = []
    for agent in registry.get("agents", []):
        agents_lines.append(
            "  - " + str(agent.get("name", "")) + ": " + str(agent.get("system_prompt", ""))
        )

    agents_block = "\n".join(agents_lines) or "  (no agents registered)"

    top_commands = list(retrieve_commands(user_request, top_k=3))
    lower = user_request.lower()

    # The command retriever is semantic and may miss route_document for short file paths
    # or words such as "drawing". Make this capability deterministic.
    if _FILE_HINT_RE.search(user_request) or any(word in lower for word in _VISUAL_WORDS):
        top_commands = _ensure_named_command(
            top_commands,
            "route_document",
            retrieve_commands,
            "route process upload document file image picture drawing diagram scan blueprint pdf",
        )

    # Likewise, make create_agent available when the user explicitly asks for a new role.
    if any(word in lower for word in _CREATE_WORDS):
        top_commands = _ensure_named_command(
            top_commands,
            "create_agent",
            retrieve_commands,
            "create new specialized agent role",
        )

    cmd_lines = []
    for command in top_commands:
        cmd_lines.append("  name:          " + command["name"])
        cmd_lines.append("  functionality: " + command["functionality"])
        cmd_lines.append("  example:       " + command["example"])
        cmd_lines.append(
            "  template:      "
            + json.dumps(command["command"], ensure_ascii=False)
        )
        cmd_lines.append(
            "  usage_example: "
            + json.dumps(command["usage_example"], ensure_ascii=False)
        )
        cmd_lines.append("")

    commands_block = "\n".join(cmd_lines)

    return (
        "You are the central Handler of a distributed multi-agent system.\n"
        "\n"
        "You are NOT a general chatbot.\n"
        "You operate ONLY within the scope of this multi-agent system.\n"
        "\n"
        "You have TWO allowed response modes:\n"
        "\n"
        "MODE 1 — COMMAND MODE:\n"
        "When the user asks to perform an action with agents, data, or files, decompose the request\n"
        "into one or more engine commands and output a strict JSON array.\n"
        "\n"
        "MODE 2 — SYSTEM Q&A MODE:\n"
        "Triggers: questions about agents, commands, system capabilities, or how the system works.\n"
        "In MODE 2 you MUST answer directly in natural language, using only AVAILABLE AGENTS and\n"
        "AVAILABLE COMMANDS from this prompt. Never output JSON or execute a command in MODE 2.\n"
        "End with one suggested follow-up system action.\n"
        "\n"
        "FILE AND VISUAL ROUTING POLICY:\n"
        "- Any referenced document or file that needs automatic processing/routing uses route_document.\n"
        "- Images, photos, drawings, diagrams, scans, blueprints, and PDF files MUST use route_document.\n"
        "- Do NOT attempt to interpret image pixels yourself. route_document invokes the backend\n"
        "  DocumentProcessor; visual files then enter the dedicated drawing/vision pipeline.\n"
        "- Use load only when the user explicitly names an existing destination agent.\n"
        "- A file path is server-side. Never invent a file path that the user did not provide.\n"
        "\n"
        "MODEL ASSIGNMENT POLICY:\n"
        "- Handler chooses semantic roles, NOT physical LLM files.\n"
        "- When creating an agent, NEVER invent or choose model_name/model_path/device/dtype.\n"
        "- The backend ModelRegistry automatically assigns an available base model according to server policy.\n"
        "- Therefore create_agent should contain semantic fields only: agent, description, system_prompt, tags.\n"
        "\n"
        "PLACEHOLDER POLICY:\n"
        "- Values surrounded by <...> in usage examples are explanatory placeholders only.\n"
        "- NEVER emit angle-bracket placeholders in the final JSON. Replace them with real values from\n"
        "  the user request or AVAILABLE AGENTS.\n"
        "\n"
        "AVAILABLE AGENTS (from registry):\n"
        + agents_block
        + "\n\n"
        "AVAILABLE COMMANDS (retrieved for this request):\n"
        + commands_block
        + "\n"
        "YOUR TASK:\n"
        "1. Determine which mode applies.\n"
        "2. MODE 1: decompose into commands, fill templates, output a JSON array.\n"
        "3. MODE 2: answer the system question briefly and suggest a follow-up action.\n"
        "4. Command sequence must reflect execution order.\n"
        "\n"
        "OUTPUT FORMAT for MODE 1 (strict JSON array):\n"
        "[\n"
        "  { ...command_1... },\n"
        "  { ...command_2... }\n"
        "]\n"
        "\n"
        "RULES:\n"
        "- References to EXISTING agents must exactly match names in AVAILABLE AGENTS.\n"
        "- create_agent may introduce a new meaningful agent name that is not yet in AVAILABLE AGENTS.\n"
        "- Command actions must exactly match AVAILABLE COMMANDS.\n"
        "- Prefer the minimal number of commands that fulfills the request.\n"
        "- If one command is enough, output an array with one element.\n"
        "- For MODE 1 output ONLY the JSON array: no markdown and no explanation.\n"
        "- For MODE 2 never execute commands.\n"
        "- NEVER answer unrelated general-knowledge questions.\n"
    )
