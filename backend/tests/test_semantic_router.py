from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.engine.agent_registry import AgentRegistry
from app.routing.semantic_router import SemanticAgentRouter


def build_registry(tmp: Path) -> AgentRegistry:
    config = {
        "agents": [
            {
                "name": "SecurityAgent",
                "type": "llm",
                "description": (
                    "Information security, vulnerabilities, "
                    "authentication, access control and security audit"
                ),
                "system_prompt": "",
                "tags": [
                    "security",
                    "vulnerability",
                    "authentication",
                    "JWT",
                    "MFA",
                    "pentest",
                ],
                "model_name": "",
                "model_path": "",
            },
            {
                "name": "BackendAgent",
                "type": "llm",
                "description": (
                    "Backend development, server architecture, "
                    "REST API, databases and network services"
                ),
                "system_prompt": "",
                "tags": [
                    "backend",
                    "API",
                    "server",
                    "PostgreSQL",
                    "FastAPI",
                    "networking",
                ],
                "model_name": "",
                "model_path": "",
            },
        ]
    }

    config_path = tmp / "agents.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    registry = AgentRegistry(
        config_path=config_path,
        models_dir=tmp / "models",
    )

    registry.load()
    return registry


def main() -> None:
    with TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        registry = build_registry(tmp)

        router = SemanticAgentRouter(
            registry,
            low=0.45,
            high=0.58,
            margin=0.05,
            rerank_min=0.30,
            learn=False,
        )

        cases = [
            (
                "The REST API is implemented in FastAPI. "
                "PostgreSQL stores application data and Nginx "
                "works as a reverse proxy.",
                "BackendAgent",
            ),
            (
                "Security audit found an authentication bypass, "
                "weak JWT validation and missing MFA for administrators.",
                "SecurityAgent",
            ),
            (
                "Рецепт борща: свёкла, капуста, картофель, "
                "морковь и два часа варки.",
                None,
            ),
        ]

        failed = 0

        for text, expected in cases:
            decision = router.route(text)

            print()
            print("=" * 80)
            print("TEXT:", text)
            print("EXPECTED:", expected)
            print("GOT:", decision.agent)
            print("STAGE:", decision.stage)
            print("REASON:", decision.reason)
            print(
                "SIMILARITIES:",
                {
                    key: round(value, 3)
                    for key, value
                    in decision.similarities.items()
                },
            )

            if decision.rerank_scores:
                print(
                    "RERANK:",
                    {
                        key: round(value, 3)
                        for key, value
                        in decision.rerank_scores.items()
                    },
                )

            if decision.agent != expected:
                failed += 1
                print("RESULT: FAIL")
            else:
                print("RESULT: OK")

        print()
        print(
            f"Passed {len(cases) - failed}/{len(cases)}"
        )

        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
