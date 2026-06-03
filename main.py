import json
from pathlib import Path

from engine.agent_executor import AgentExecutor
from engine.agent_loader import AgentLoader
from engine.agent_registry import AgentRegistry
from engine.command_router import CommandRouter
from parser import Parser


BASE_DIR = Path(__file__).resolve().parent
AGENTS_DIR = BASE_DIR / "agents"
COMMANDS_DIR = BASE_DIR / "parsed_command"


def build_router() -> CommandRouter:
    registry = AgentRegistry()
    AgentLoader(AGENTS_DIR).load_all(registry)

    print("Loaded agents:", registry.list_agents())

    executor = AgentExecutor(registry)
    return CommandRouter(executor)


def demo_manual_json_command(router: CommandRouter) -> None:
    command = {
        "type": "agent_call",
        "agent": "AnalystAgent",
        "payload": {
            "task": "Analyze parser and engine integration",
            "context": {
                "parser": "friend_json_parser",
                "engine": "plugin_agent_engine"
            }
        }
    }

    result = router.route(command)
    print("\nManual command result:")
    print(json.dumps(result, ensure_ascii=False, indent=4))


def demo_friend_parser(router: CommandRouter) -> None:
    raw_llm_output = """
    Some garbage before JSON.

    {
        "type": "agent_call",
        "agent": "RetrieverAgent",
        "payload": {
            "query": "What does parser do?"
        }
    }

    Text between commands.

    {
        "type": "agent_call",
        "agent": "AnalystAgent",
        "payload": {
            "task": "Make a short conclusion about the current architecture",
            "context": {
                "agents": ["AnalystAgent", "RetrieverAgent"]
            }
        }
    }
    """

    parser = Parser(output_dir=str(COMMANDS_DIR))
    count = parser.parse(raw_llm_output)
    print(f"\nParser saved {count} JSON commands")

    results = router.route_directory(COMMANDS_DIR)
    print("\nParsed command results:")
    print(json.dumps(results, ensure_ascii=False, indent=4))


def demo_angle_command(router: CommandRouter) -> None:
    command = CommandRouter.from_angle_command(
        "<AnalystAgent, Explain how the agent engine works>"
    )
    result = router.route(command)

    print("\nAngle command result:")
    print(json.dumps(result, ensure_ascii=False, indent=4))


if __name__ == "__main__":
    router = build_router()
    demo_manual_json_command(router)
    demo_friend_parser(router)
    demo_angle_command(router)
