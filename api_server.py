from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel

from engine.agent_executor import AgentExecutor
from engine.agent_loader import AgentLoader
from engine.agent_registry import AgentRegistry
from engine.command_router import CommandRouter


BASE_DIR = Path(__file__).resolve().parent
AGENTS_CONFIG = BASE_DIR / "agents.json"


class AgentRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}


class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    tags: list[str] = []


app = FastAPI()

registry = AgentRegistry()
AgentLoader(AGENTS_CONFIG).load_all(registry)

executor = AgentExecutor(registry)
router = CommandRouter(executor)


@app.get("/agents")
def list_agents():
    return {
        "agents": registry.list_agents(),
        "metadata": registry.snapshot()
    }


@app.post("/agents/{agent_name}/run")
def run_agent(agent_name: str, request: AgentRequest):
    return router.route_by_agent_name(
        agent_name,
        {
            "prompt": request.prompt,
            "context": request.context
        }
    )


@app.post("/agents")
def add_agent(request: AgentCreateRequest):
    metadata = request.model_dump()
    registry.register_from_metadata(metadata)

    return {
        "status": "created",
        "agent": request.name
    }


@app.delete("/agents/{agent_name}")
def delete_agent(agent_name: str):
    registry.unregister(agent_name)

    return {
        "status": "deleted",
        "agent": agent_name
    }


@app.post("/agents/select")
def select_agent(request: AgentRequest):
    agent_name = registry.select_agent(request.prompt)

    if agent_name is None:
        return {
            "status": "error",
            "message": "No agents available"
        }

    return router.route_by_agent_name(
        agent_name,
        {
            "prompt": request.prompt,
            "context": request.context
        }
    )