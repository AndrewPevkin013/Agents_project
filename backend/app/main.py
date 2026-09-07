from pathlib import Path
from typing import Any, Dict, List
from fastapi import FastAPI
from fastapi import UploadFile, File, Form
import shutil
from dotenv import load_dotenv
import json
from pydantic import BaseModel
from app.engine.agent_executor import AgentExecutor
from app.engine.agent_registry import AgentRegistry
from app.engine.command_router import CommandRouter
from app.engine.command_store import CommandStore
from app.handlers.factory import create_handler
from fastapi import Depends

from app.auth.dependencies import get_current_user


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(
    PROJECT_DIR / ".env"
)
CONFIG_DIR = BACKEND_DIR / "config"

AGENTS_CONFIG = CONFIG_DIR / "agents.json"
COMMANDS_CONFIG = CONFIG_DIR / "commands.json"
CORE_CONFIG = CONFIG_DIR / "core_config.json"

MODELS_DIR = PROJECT_DIR / "models"

UPLOADS_DIR = BACKEND_DIR / "server_storage" / "uploads"
LOGS_DIR = BACKEND_DIR / "logs"

UPLOADS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOGS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

core_config = json.loads(
    CORE_CONFIG.read_text(
        encoding="utf-8"
    )
)


class AgentRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}
class AgentCreateRequest(BaseModel):
    name: str
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
handler = create_handler(
    registry=registry,
    command_store=command_store,
    config=core_config,
    models_dir=MODELS_DIR,
)
executor = AgentExecutor(registry)
router = CommandRouter(executor, handler)

@app.get("/")
def root():
    return {
        "service": "multi-agent-backend",
        "status": "ok",
    }

@app.get("/agents")
def list_agents(
    user: dict = Depends(get_current_user),
):
    return {
        "agents": registry.list_agents(),
        "metadata": registry.snapshot(),
    }


@app.post("/agents")
def add_agent(
    request: AgentCreateRequest,
    user: dict = Depends(get_current_user),
):
    metadata = request.model_dump()
    registry.upsert_from_metadata(metadata)

    return {
        "status": "ok",
        "created": request.name,
        "metadata": registry.get_metadata(request.name),
    }


@app.delete("/agents/{agent_name}")
def delete_agent(
    agent_name: str,
    user: dict = Depends(get_current_user),
):
    registry.unregister(agent_name)

    return {
        "status": "ok",
        "deleted": agent_name,
    }


@app.post("/agents/{agent_name}/run")
def run_agent(
    agent_name: str,
    request: AgentRequest,
    user: dict = Depends(get_current_user),
):
    return router.route_by_agent_name(
        agent_name,
        {
            "prompt": request.prompt,
            "context": request.context,
        },
    )


@app.post("/handler")
def ask_handler(
    request: HandlerRequest,
    user: dict = Depends(get_current_user),
):
    return router.handle_user_request(
        request.request
    )


@app.post("/documents/route")
def route_document(
    request: DocumentRouteRequest,
    user: dict = Depends(get_current_user),
):
    return router.route({
        "action": "route_document",
        "file_path": request.file_path,
        "document_text": request.document_text,
        "threshold": request.threshold,
    })


@app.post("/logger/resolve")
def resolve_logger(
    user: dict = Depends(get_current_user),
):
    return router.route({
        "action": "resolve_logger_conflicts"
    })


@app.get("/logs/state")
def logs_state(
    user: dict = Depends(get_current_user),
):
    return router.route({
        "action": "save_system_state"
    })


@app.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    document_text: str = Form(""),
    threshold: int = Form(1),
    user: dict = Depends(get_current_user),
):
    safe_name = Path(file.filename).name
    saved_path = UPLOADS_DIR / safe_name

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return router.route({
        "action": "route_document",
        "file_path": str(saved_path),
        "document_text": document_text,
        "threshold": threshold,
    })


@app.get("/logs/metrics")
def logs_metrics(
    user: dict = Depends(get_current_user),
):
    return executor.metrics_logger.build_summary()
