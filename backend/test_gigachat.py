import json
from pathlib import Path

from dotenv import load_dotenv

from app.engine.agent_registry import AgentRegistry
from app.engine.command_store import CommandStore
from app.handlers.gigachat import GigaChatHandler


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

ENV_FILE = PROJECT_DIR / ".env"

print("BACKEND_DIR:", BACKEND_DIR)
print("PROJECT_DIR:", PROJECT_DIR)
print("ENV_FILE:", ENV_FILE)
print("ENV EXISTS:", ENV_FILE.exists())

load_dotenv(ENV_FILE, override=True)

registry = AgentRegistry(
    config_path=BACKEND_DIR / "config" / "agents.json",
    models_dir=PROJECT_DIR / "models",
)
registry.load()

command_store = CommandStore(
    BACKEND_DIR / "config" / "commands.json"
)
command_store.load()

handler = GigaChatHandler(
    registry=registry,
    command_store=command_store,
    config={
        "model": "GigaChat-2-Pro"
    },
)

print("HANDLER:", type(handler).__name__)

tests = [
    "Какие агенты есть в системе?",
    "Какие команды доступны в системе?",
    "Попроси BackendAgent спроектировать REST API для сервиса задач."
]

for request in tests:
    print("\n" + "=" * 80)
    print("USER:")
    print(request)

    result = handler.handle(request)

    print("\nHANDLER RESULT:")
    print(json.dumps(result, ensure_ascii=False, indent=2) if not isinstance(result, str) else result)