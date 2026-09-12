from __future__ import annotations

from dataclasses import dataclass

from app.routing.complexity.router import ComplexityDecision


@dataclass(frozen=True)
class ReasoningPolicy:
    mode: str
    max_new_tokens: int
    temperature: float
    do_sample: bool
    instruction: str


def build_reasoning_policy(
    decision: ComplexityDecision,
    *,
    base_max_new_tokens: int,
    base_temperature: float,
    base_do_sample: bool,
) -> ReasoningPolicy:
    """
    Version 1 policy.

    This does NOT expose chain-of-thought to the user and does not implement a
    literal multi-branch Tree-of-Thought search. It changes the inference budget
    and adds an internal task instruction while the model still returns only a
    final answer.
    """

    if decision.mode == "chain_of_thought":
        return ReasoningPolicy(
            mode="deliberate",
            max_new_tokens=max(base_max_new_tokens, 512),
            temperature=min(base_temperature, 0.5),
            do_sample=base_do_sample,
            instruction=(
                "Analyze the task carefully before answering. "
                "Check important assumptions and return only the final answer; "
                "do not reveal private intermediate reasoning."
            ),
        )

    if decision.mode == "tree_of_thought":
        return ReasoningPolicy(
            mode="deep",
            max_new_tokens=max(base_max_new_tokens, 768),
            temperature=min(base_temperature, 0.4),
            do_sample=base_do_sample,
            instruction=(
                "Treat this as a complex task. Internally consider multiple "
                "plausible approaches, compare their trade-offs, verify the "
                "result, and return only the final answer without exposing "
                "private intermediate reasoning."
            ),
        )

    return ReasoningPolicy(
        mode="direct",
        max_new_tokens=base_max_new_tokens,
        temperature=base_temperature,
        do_sample=base_do_sample,
        instruction="",
    )
