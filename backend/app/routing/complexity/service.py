from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Optional

from app.routing.complexity.router import (
    ComplexityDecision,
    ComplexityRouter,
)


_router: Optional[ComplexityRouter] = None
_router_lock = Lock()
_warning_printed = False


def _project_dir() -> Path:
    # .../backend/app/routing/complexity/service.py -> project root
    return Path(__file__).resolve().parents[4]


def _router_path() -> Path:
    configured = os.getenv("COMPLEXITY_ROUTER_PATH", "").strip()
    if configured:
        return Path(configured)

    return _project_dir() / "models" / "complexity_router"


def _enabled() -> bool:
    value = os.getenv(
        "COMPLEXITY_ROUTER_ENABLED",
        "true",
    ).strip().lower()

    return value not in {"0", "false", "no", "off"}


def get_complexity_router() -> Optional[ComplexityRouter]:
    global _router

    if not _enabled():
        return None

    if _router is not None:
        return _router

    with _router_lock:
        if _router is None:
            device = os.getenv(
                "COMPLEXITY_ROUTER_DEVICE",
                "",
            ).strip() or None

            _router = ComplexityRouter(
                model_dir=_router_path(),
                device=device,
            )

    return _router


def classify_complexity(prompt: str) -> ComplexityDecision:
    """
    Safe facade for Agent runtime.

    If the model is absent or fails to load, agent inference continues in
    simple_direct mode instead of breaking the whole request.
    """
    global _warning_printed

    router = get_complexity_router()

    if router is None:
        return ComplexityDecision(
            label=1,
            mode="simple_direct",
            probs={"1": 1.0, "2": 0.0, "3": 0.0},
            confidence=1.0,
            enabled=False,
            reason="router_disabled",
        )

    try:
        return router.predict_one(prompt)
    except Exception as exc:
        if not _warning_printed:
            print(
                "[ComplexityRouter] unavailable, "
                f"falling back to simple_direct: {exc}"
            )
            _warning_printed = True

        return ComplexityDecision(
            label=1,
            mode="simple_direct",
            probs={"1": 1.0, "2": 0.0, "3": 0.0},
            confidence=1.0,
            enabled=False,
            reason=f"fallback: {type(exc).__name__}",
        )
