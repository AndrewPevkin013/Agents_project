from pathlib import Path
from typing import Any, Dict, List
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
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

class AgentRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}
class AgentCreateRequest(BaseModel):
    name: str
    type: str = "mock"
    model_name: str = ""
    description: str = ""
    system_prompt: str = ""
    tags: List[str] = []
class HandlerRequest(BaseModel):
    request: str
class DocumentRouteRequest(BaseModel):
    file_path: str
    document_text: str = ""
    threshold: int = 1

app = FastAPI(title="Multi-Agent MVP")
registry = AgentRegistry(config_path=AGENTS_CONFIG, models_dir=MODELS_DIR)
registry.load()
command_store = CommandStore(COMMANDS_CONFIG); command_store.load()
executor = AgentExecutor(registry)
handler = create_handler(registry=registry, command_store=command_store, core_config_path=CORE_CONFIG, use_llm=True)
router = CommandRouter(executor, handler)

@app.get("/", response_class=HTMLResponse)
def ui():
    return """
<!doctype html><html><head><meta charset='utf-8'/><title>Multi-Agent MVP</title>
<style>body{font-family:Arial,sans-serif;margin:32px;max-width:1200px}input,textarea,select{width:100%;padding:8px;margin:4px 0 12px}button{padding:8px 12px;margin:4px 0;cursor:pointer}pre{background:#f4f4f4;padding:12px;white-space:pre-wrap}.row{display:grid;grid-template-columns:1fr 1fr;gap:24px}</style></head><body>
<h1>Multi-Agent MVP</h1><button onclick='listAgents()'>Обновить список агентов</button><pre id='agents'></pre>
<div class='row'><section><h2>Добавить агента вручную</h2><input id='agentName' placeholder='AnalystAgent'/><select id='agentType'><option value='mock'>mock</option><option value='llm'>llm</option></select><input id='modelName' placeholder='Qwen2.5-3B-Instruct'/><input id='agentTags' placeholder='analysis, summary'/><textarea id='agentPrompt' rows='4' placeholder='Ты аналитический агент...'></textarea><button onclick='addAgent()'>Добавить</button></section>
<section><h2>Запустить агента</h2><input id='runAgentName' placeholder='BackendAgent'/><textarea id='runPrompt' rows='4' placeholder='Сделай архитектуру API'></textarea><button onclick='runAgent()'>Запустить</button></section></div>
<h2>Главный Handler</h2><textarea id='handlerRequest' rows='4' placeholder='Создай агента AnalystAgent на модели Qwen2.5-3B-Instruct. Роль: аналитический агент...'></textarea><button onclick='handlerAsk()'>Отправить Handler-у</button>
<h2>Document Router</h2><input id='docPath' placeholder='docs/api_report.txt'/><textarea id='docText' rows='3' placeholder='Текст документа, если файла нет локально'></textarea><button onclick='routeDocument()'>Загрузить документ в подходящего агента</button>
<h2>Logger / самоорганизация</h2><button onclick='resolveLogger()'>Разрешить конфликты Logger</button><h2>Ответ</h2><pre id='result'></pre>
<script>
async function listAgents(){const r=await fetch('/agents');document.getElementById('agents').textContent=JSON.stringify(await r.json(),null,2)}
async function addAgent(){const name=document.getElementById('agentName').value;const type=document.getElementById('agentType').value;const model_name=document.getElementById('modelName').value;const tags=document.getElementById('agentTags').value.split(',').map(x=>x.trim()).filter(Boolean);const system_prompt=document.getElementById('agentPrompt').value;const r=await fetch('/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,type,model_name,tags,system_prompt,description:system_prompt})});document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2);listAgents()}
async function runAgent(){const name=document.getElementById('runAgentName').value;const prompt=document.getElementById('runPrompt').value;const r=await fetch(`/agents/${name}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2)}
async function handlerAsk(){const request=document.getElementById('handlerRequest').value;const r=await fetch('/handler',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request})});document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2);listAgents()}
async function routeDocument(){const file_path=document.getElementById('docPath').value;const document_text=document.getElementById('docText').value;const r=await fetch('/documents/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_path,document_text})});document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2);listAgents()}
async function resolveLogger(){const r=await fetch('/logger/resolve',{method:'POST'});document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2);listAgents()}
listAgents();</script></body></html>"""

@app.get("/agents")
def list_agents(): return {"agents": registry.list_agents(), "metadata": registry.snapshot()}
@app.post("/agents")
def add_agent(request: AgentCreateRequest):
    metadata = request.model_dump(); registry.upsert_from_metadata(metadata)
    return {"status":"ok","created":request.name,"metadata":registry.get_metadata(request.name)}
@app.delete("/agents/{agent_name}")
def delete_agent(agent_name: str): registry.unregister(agent_name); return {"status":"ok","deleted":agent_name}
@app.post("/agents/{agent_name}/run")
def run_agent(agent_name: str, request: AgentRequest): return router.route_by_agent_name(agent_name,{"prompt":request.prompt,"context":request.context})
@app.post("/handler")
def ask_handler(request: HandlerRequest): return router.handle_user_request(request.request)
@app.post("/documents/route")
def route_document(request: DocumentRouteRequest): return router.route({"action":"route_document","file_path":request.file_path,"document_text":request.document_text,"threshold":request.threshold})
@app.post("/logger/resolve")
def resolve_logger(): return router.route({"action":"resolve_logger_conflicts"})
@app.get("/link/add/{agent_name}")
def link_add_agent(agent_name: str, role: str = "", tags: str = "", type: str = "mock", model: str = ""):
    metadata={"name":agent_name,"type":type,"description":role,"system_prompt":role or f"Ты агент {agent_name}.","tags":[x.strip() for x in tags.split(',') if x.strip()],"model_name":model}
    registry.upsert_from_metadata(metadata); return {"status":"ok","created":agent_name,"metadata":registry.get_metadata(agent_name)}
@app.get("/link/edit/{agent_name}")
def link_edit_agent(agent_name: str, role: str = "", tags: str = "", type: str = "", model: str = ""):
    return router.route({"action":"edit_agent","agent":agent_name,"description":role,"system_prompt":role,"tags":[x.strip() for x in tags.split(',') if x.strip()],"type":type,"model_name":model})
@app.get("/link/run/{agent_name}")
def link_run_agent(agent_name: str, prompt: str = ""): return router.route_by_agent_name(agent_name,{"prompt":prompt})
@app.get("/link/delete/{agent_name}")
def link_delete_agent(agent_name: str): registry.unregister(agent_name); return {"status":"ok","deleted":agent_name}
@app.get("/link/handler")
def link_handler(request: str): return router.handle_user_request(request)
@app.get("/link/route_document")
def link_route_document(file_path: str, document_text: str = "", threshold: int = 1): return router.route({"action":"route_document","file_path":file_path,"document_text":document_text,"threshold":threshold})
@app.get("/link/logger/resolve")
def link_logger_resolve(): return router.route({"action":"resolve_logger_conflicts"})
