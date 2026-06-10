import json
from pathlib import Path

from engine.agent_executor import AgentExecutor
from engine.agent_registry import AgentRegistry
from engine.command_router import CommandRouter
from engine.command_store import CommandStore
from engine.handler import RuleBasedHandler


BASE_DIR = Path(__file__).resolve().parent
AGENTS_CONFIG = BASE_DIR / "agents.json"
COMMANDS_CONFIG = BASE_DIR / "commands.json"


def build_router() -> CommandRouter:
    registry = AgentRegistry(AGENTS_CONFIG)
    registry.load()

    command_store = CommandStore(COMMANDS_CONFIG)
    command_store.load()

    executor = AgentExecutor(registry)
    handler = RuleBasedHandler(registry, command_store)

    print("Loaded agents:", registry.list_agents())

    return CommandRouter(executor, handler)


def main() -> None:
    router = build_router()

    print("\n--- Direct run by name ---")
    result = router.route_by_agent_name(
        "BackendAgent",
        {"prompt": "Спроектируй REST API для системы задач"}
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- Handler request: list agents ---")
    result = router.handle_user_request("Какие агенты есть в системе?")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- Handler request: create agent ---")
    result = router.handle_user_request("Создай агента SecurityAgent для анализа безопасности и уязвимостей")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- Handler request: delegate task ---")
    result = router.handle_user_request("Проверь безопасность API авторизации")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()