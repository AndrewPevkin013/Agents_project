from __future__ import annotations

import json
from typing import Callable, Dict, Any


def build_handler_system_prompt(
    user_request: str,
    registry: Dict[str, Any],
    retrieve_commands: Callable,
) -> str:

    agents_lines = []

    for a in registry["agents"]:
        agents_lines.append(
            "  - " + a["name"] + ": " + a["system_prompt"]
        )

    agents_block = "\n".join(agents_lines)

    top_commands = retrieve_commands(
        user_request,
        top_k=3
    )

    cmd_lines = []

    for c in top_commands:
        cmd_lines.append(
            "  name:          " + c["name"]
        )
        cmd_lines.append(
            "  functionality: " + c["functionality"]
        )
        cmd_lines.append(
            "  example:       " + c["example"]
        )
        cmd_lines.append(
            "  template:      "
            + json.dumps(
                c["command"],
                ensure_ascii=False
            )
        )
        cmd_lines.append(
            "  usage_example: "
            + json.dumps(
                c["usage_example"],
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