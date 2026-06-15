import json
from pathlib import Path

from engine.agent_executor import AgentExecutor
from engine.agent_registry import AgentRegistry
from engine.command_router import CommandRouter
from engine.command_store import CommandStore
from engine.handler import create_handler


BASE_DIR = Path(__file__).resolve().parent

AGENTS_CONFIG = BASE_DIR / "agents.json"
COMMANDS_CONFIG = BASE_DIR / "commands.json"
CORE_CONFIG = BASE_DIR / "core_config.json"
MODELS_DIR = BASE_DIR / "Models"


def build_router(use_llm_handler: bool = True) -> CommandRouter:
    registry = AgentRegistry(
        config_path=AGENTS_CONFIG,
        models_dir=MODELS_DIR
    )
    registry.load()

    command_store = CommandStore(COMMANDS_CONFIG)
    command_store.load()

    executor = AgentExecutor(registry)

    handler = create_handler(
        registry=registry,
        command_store=command_store,
        core_config_path=CORE_CONFIG,
        use_llm=use_llm_handler
    )

    print("Loaded agents:", registry.list_agents())
    print("Handler:", type(handler).__name__)

    return CommandRouter(executor, handler)


def main() -> None:
    router = build_router(use_llm_handler=False)

    print("\n--- Direct run by name ---")
    result = router.route_by_agent_name(
        "BackendAgent",
        {"prompt": "Спроектируй REST API для системы задач"}
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- Handler request: create mock agent ---")
    result = router.handle_user_request(
        "Создай агента SecurityAgent для анализа безопасности"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()