from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from engine.agent_executor import AgentExecutor
from engine.agent_registry import AgentRegistry
from engine.command_router import CommandRouter
from engine.command_store import CommandStore
from engine.handler import RuleBasedHandler


BASE_DIR = Path(__file__).resolve().parent
AGENTS_CONFIG = BASE_DIR / "agents.json"
COMMANDS_CONFIG = BASE_DIR / "commands.json"


class AgentRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}


class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    tags: List[str] = []


class HandlerRequest(BaseModel):
    request: str


app = FastAPI(title="Multi-Agent MVP")


registry = AgentRegistry(AGENTS_CONFIG)
registry.load()

command_store = CommandStore(COMMANDS_CONFIG)
command_store.load()

executor = AgentExecutor(registry)
handler = RuleBasedHandler(registry, command_store)
router = CommandRouter(executor, handler)


@app.get("/", response_class=HTMLResponse)
def ui():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Multi-Agent MVP</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; max-width: 1000px; }
    input, textarea { width: 100%; padding: 8px; margin: 4px 0 12px; }
    button { padding: 8px 12px; margin: 4px 0; cursor: pointer; }
    pre { background: #f4f4f4; padding: 12px; white-space: pre-wrap; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  </style>
</head>
<body>
  <h1>Multi-Agent MVP</h1>

  <button onclick="listAgents()">Обновить список агентов</button>
  <pre id="agents"></pre>

  <div class="row">
    <section>
      <h2>Добавить агента</h2>
      <input id="agentName" placeholder="SecurityAgent"/>
      <input id="agentTags" placeholder="security, vulnerabilities"/>
      <textarea id="agentPrompt" rows="4" placeholder="Ты security-агент..."></textarea>
      <button onclick="addAgent()">Добавить</button>
    </section>

    <section>
      <h2>Запустить агента</h2>
      <input id="runAgentName" placeholder="BackendAgent"/>
      <textarea id="runPrompt" rows="4" placeholder="Сделай архитектуру API"></textarea>
      <button onclick="runAgent()">Запустить</button>
    </section>
  </div>

  <h2>Главный Handler</h2>
  <textarea id="handlerRequest" rows="4" placeholder="Создай агента SecurityAgent..."></textarea>
  <button onclick="handlerAsk()">Отправить Handler-у</button>

  <h2>Ответ</h2>
  <pre id="result"></pre>

<script>
async function listAgents() {
  const r = await fetch('/agents');
  document.getElementById('agents').textContent = JSON.stringify(await r.json(), null, 2);
}

async function addAgent() {
  const name = document.getElementById('agentName').value;
  const tags = document.getElementById('agentTags').value.split(',').map(x => x.trim()).filter(Boolean);
  const system_prompt = document.getElementById('agentPrompt').value;
  const r = await fetch('/agents', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, tags, system_prompt, description: system_prompt})
  });
  document.getElementById('result').textContent = JSON.stringify(await r.json(), null, 2);
  listAgents();
}

async function runAgent() {
  const name = document.getElementById('runAgentName').value;
  const prompt = document.getElementById('runPrompt').value;
  const r = await fetch(`/agents/${name}/run`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt})
  });
  document.getElementById('result').textContent = JSON.stringify(await r.json(), null, 2);
}

async function handlerAsk() {
  const request = document.getElementById('handlerRequest').value;
  const r = await fetch('/handler', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({request})
  });
  document.getElementById('result').textContent = JSON.stringify(await r.json(), null, 2);
}

listAgents();
</script>
</body>
</html>
"""


@app.get("/agents")
def list_agents():
    return {
        "agents": registry.list_agents(),
        "metadata": registry.snapshot()
    }


@app.post("/agents")
def add_agent(request: AgentCreateRequest):
    metadata = request.model_dump()
    registry.upsert_from_metadata(metadata)
    return {
        "status": "ok",
        "created": request.name,
        "metadata": registry.get_metadata(request.name)
    }


@app.delete("/agents/{agent_name}")
def delete_agent(agent_name: str):
    registry.unregister(agent_name)
    return {
        "status": "ok",
        "deleted": agent_name
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


@app.post("/handler")
def ask_handler(request: HandlerRequest):
    return router.handle_user_request(request.request)


@app.get("/link/add/{agent_name}")
def link_add_agent(agent_name: str, role: str = "", tags: str = ""):
    tag_list = [x.strip() for x in tags.split(",") if x.strip()]
    metadata = {
        "name": agent_name,
        "description": role,
        "system_prompt": role or f"Ты агент {agent_name}.",
        "tags": tag_list,
    }
    registry.upsert_from_metadata(metadata)
    return {
        "status": "ok",
        "created": agent_name,
        "metadata": registry.get_metadata(agent_name)
    }


@app.get("/link/run/{agent_name}")
def link_run_agent(agent_name: str, prompt: str = ""):
    return router.route_by_agent_name(agent_name, {"prompt": prompt})


@app.get("/link/delete/{agent_name}")
def link_delete_agent(agent_name: str):
    registry.unregister(agent_name)
    return {
        "status": "ok",
        "deleted": agent_name
    }


@app.get("/link/handler")
def link_handler(request: str):
    return router.handle_user_request(request)