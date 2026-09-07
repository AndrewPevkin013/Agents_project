from __future__ import annotations

import json
import re

from app.handlers.base import HandlerOutput


def parse_handler_output(text: str) -> HandlerOutput:
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

    for pattern in (
        r"\[.*\]",
        r"\{.*\}",
    ):
        match = re.search(
            pattern,
            text,
            re.DOTALL
        )

        if not match:
            continue

        try:
            parsed = json.loads(
                match.group(0)
            )

            if isinstance(parsed, dict):
                return [parsed]

            if isinstance(parsed, list):
                return parsed

        except json.JSONDecodeError:
            continue

    return text