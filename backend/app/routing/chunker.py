\
from __future__ import annotations

import re
from typing import List


_SENT_RE = re.compile(r"(?<=[.!?…])\s+|\n{2,}")


def split_into_chunks(
    text: str,
    max_chars: int = 300,
    min_chars: int = 25,
) -> List[str]:
    """
    Chunker adapted from agent_router_v3.ipynb.

    - Tries to split on sentence boundaries.
    - Packs sentences into chunks of approximately max_chars.
    - Very short trailing fragments are appended to the previous chunk.
    """
    text = (text or "").strip()

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    sentences = [
        sentence.strip()
        for sentence in _SENT_RE.split(text)
        if sentence.strip()
    ]

    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()

    if current:
        chunks.append(current)

    result: List[str] = []

    for chunk in chunks:
        if result and len(chunk) < min_chars:
            result[-1] += " " + chunk
        else:
            result.append(chunk)

    return result
