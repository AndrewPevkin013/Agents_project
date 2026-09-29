from __future__ import annotations

import json
import re
from typing import Any

from app.handlers.base import HandlerOutput


def _normalize_commands(value: Any) -> HandlerOutput | None:
    """
    Convert valid JSON command output to the Handler command representation.

    A command response must be either:
      - one JSON object;
      - a JSON array containing JSON objects.

    Other JSON values are treated as natural-language output.
    """

    if isinstance(value, dict):
        return [value]

    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return value

    return None


def parse_handler_output(
    text: str,
    *,
    allow_embedded_json: bool = True,
) -> HandlerOutput:
    """
    Parse Handler output.

    Natural-language responses remain strings.

    COMMAND MODE normally produces a strict JSON array. For compatibility
    with smaller local models, embedded JSON extraction can optionally be
    enabled.

    SYSTEM Q&A should NOT call this parser at all: LocalLLMHandler returns
    the generated text directly for deterministic SYSTEM Q&A requests.
    """

    text = text.strip()

    if not text:
        return ""

    # Preferred path: the complete response is valid JSON.
    try:
        parsed = json.loads(text)
        commands = _normalize_commands(parsed)

        if commands is not None:
            return commands

        return text

    except json.JSONDecodeError:
        pass

    if not allow_embedded_json:
        return text

    # Compatibility fallback for local models which occasionally add
    # explanatory text around an otherwise valid command array/object.
    #
    # This fallback is used only for requests which are allowed to enter
    # COMMAND MODE.
    for pattern in (
        r"\[.*\]",
        r"\{.*\}",
    ):
        match = re.search(
            pattern,
            text,
            re.DOTALL,
        )

        if not match:
            continue

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue

        commands = _normalize_commands(parsed)

        if commands is not None:
            return commands

    return text