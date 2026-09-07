import json
from pathlib import Path
from backend.app.engine.agent_executor import AgentExecutor
from backend.app.engine.agent_registry import AgentRegistry
from backend.app.engine.command_router import CommandRouter
from backend.app.engine.command_store import CommandStore
from backend.app.engine.handler import create_handler

BASE_DIR = Path(__file__).resolve().parent
AGENTS_CONFIG = BASE_DIR / "agents.json"
COMMANDS_CONFIG = BASE_DIR / "commands.json"
CORE_CONFIG = BASE_DIR / "core_config.json"
MODELS_DIR = BASE_DIR / "Models"

def build_router(use_llm_handler: bool = False) -> CommandRouter:
    registry = AgentRegistry(AGENTS_CONFIG, MODELS_DIR); registry.load()
    command_store = CommandStore(COMMANDS_CONFIG); command_store.load()
    executor = AgentExecutor(registry)
    handler = create_handler(registry, command_store, CORE_CONFIG, use_llm=use_llm_handler)
    print("Loaded agents:", registry.list_agents()); print("Handler:", type(handler).__name__)
    return CommandRouter(executor, handler)

def main() -> None:
    router = build_router(use_llm_handler=False)
    for title, action in [
        ("Direct run by name", lambda: router.route_by_agent_name("BackendAgent", {"prompt":"Спроектируй REST API для системы задач"})),
        ("Handler system Q&A", lambda: router.handle_user_request("Какие агенты есть в системе?")),
        ("Handler create agent", lambda: router.handle_user_request("Создай агента SecurityAgent для анализа безопасности и уязвимостей")),
        ("Document routing", lambda: router.route({"action":"route_document","file_path":"docs/api_report.txt","document_text":"REST API authentication database endpoints","threshold":1})),
        ("Logger conflict resolution", lambda: router.route({"action":"resolve_logger_conflicts"})),
    ]:
        print(f"\n--- {title} ---")
        print(json.dumps(action(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
