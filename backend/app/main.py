from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from app.api.errors import application_error_handler
from app.api.v1.router import api_router
from app.auth.dependencies import get_current_user
from app.core.exceptions import ApplicationError
from app.engine.agent_executor import AgentExecutor
from app.engine.agent_registry import AgentRegistry
from app.engine.command_router import CommandRouter
from app.engine.command_store import CommandStore
from app.handlers.factory import create_handler
from app.runtime import ApplicationRuntime


# Paths and configuration
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(PROJECT_DIR / ".env")

CONFIG_DIR = BACKEND_DIR / "config"

AGENTS_CONFIG = CONFIG_DIR / "agents.json"
COMMANDS_CONFIG = CONFIG_DIR / "commands.json"
CORE_CONFIG = CONFIG_DIR / "core_config.json"

MODELS_DIR = PROJECT_DIR / "models"

UPLOADS_DIR = BACKEND_DIR / "server_storage" / "uploads"
LOGS_DIR = BACKEND_DIR / "logs"


# Legacy API schemas
#
# These remain here temporarily.
# They can later be moved into app/schemas.
class AgentRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    rag_enabled: bool = True
    rag_top_k: int = 5
    rag_rerank_top_k: int = 3


class AgentCreateRequest(BaseModel):
    name: str
    model_name: str = ""
    description: str = ""
    system_prompt: str = ""
    tags: List[str] = Field(default_factory=list)


class HandlerRequest(BaseModel):
    request: str


class DocumentRouteRequest(BaseModel):
    file_path: str
    document_text: str = ""
    threshold: int = 1


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    rerank_top_k: int = 3


# Runtime construction
def load_core_config() -> dict[str, Any]:
    return json.loads(
        CORE_CONFIG.read_text(encoding="utf-8")
    )


def prepare_runtime_directories() -> None:
    UPLOADS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def create_runtime() -> ApplicationRuntime:
    """
    Construct application runtime components.

    This function must only be called during application startup,
    not while importing app.main.
    """

    prepare_runtime_directories()

    core_config = load_core_config()

    registry = AgentRegistry(
        config_path=AGENTS_CONFIG,
        models_dir=MODELS_DIR,
    )
    registry.load()

    command_store = CommandStore(COMMANDS_CONFIG)
    command_store.load()

    handler = create_handler(
        registry=registry,
        command_store=command_store,
        config=core_config,
        models_dir=MODELS_DIR,
    )

    executor = AgentExecutor(registry)

    router = CommandRouter(
        executor,
        handler,
    )

    return ApplicationRuntime(
        registry=registry,
        command_store=command_store,
        executor=executor,
        router=router,
    )


# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start and stop runtime infrastructure together with FastAPI.

    Importing app.main must not initialize AgentRegistry,
    AgentMemory, Handler, Executor, or CommandRouter.
    """

    app.state.runtime = create_runtime()

    try:
        yield
    finally:
        app.state.runtime = None


# Application factory
def create_app() -> FastAPI:
    application = FastAPI(
        title="Multi-Agent MVP",
        lifespan=lifespan,
    )

    application.add_exception_handler(
        ApplicationError,
        application_error_handler,
    )

    application.include_router(api_router)

    return application


app = create_app()

# Dependencies
def get_runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(
        request.app.state,
        "runtime",
        None,
    )

    if runtime is None:
        raise RuntimeError(
            "Application runtime is not initialized"
        )

    return runtime


# Basic API
@app.get("/")
def root():
    return {
        "service": "multi-agent-backend",
        "status": "ok",
    }


# Legacy Agent API
#
# These endpoints are kept operational during the architecture migration.
# They now receive runtime dependencies through FastAPI instead of using
# module-level global objects.
@app.get("/agents")
def list_agents(
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return {
        "agents": runtime.registry.list_agents(),
        "metadata": runtime.registry.snapshot(),
    }


@app.post("/agents")
def add_agent(
    request: AgentCreateRequest,
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    metadata = request.model_dump()

    runtime.registry.upsert_from_metadata(metadata)

    return {
        "status": "ok",
        "created": request.name,
        "metadata": runtime.registry.get_metadata(request.name),
    }


@app.delete("/agents/{agent_name}")
def delete_agent(
    agent_name: str,
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    runtime.registry.unregister(agent_name)

    return {
        "status": "ok",
        "deleted": agent_name,
    }


@app.post("/agents/{agent_name}/run")
def run_agent(
    agent_name: str,
    request: AgentRequest,
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.router.route_by_agent_name(
        agent_name,
        request.model_dump(),
    )


@app.post("/agents/{agent_name}/retrieve")
def retrieve_agent_memory(
    agent_name: str,
    request: RetrieveRequest,
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.executor.execute(
        {
            "action": "retrieve",
            "agent": agent_name,
            "query": request.query,
            "top_k": request.top_k,
            "rerank_top_k": request.rerank_top_k,
        }
    )


# Legacy Handler API
@app.post("/handler")
def ask_handler(
    request: HandlerRequest,
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.router.handle_user_request(
        request.request
    )

# Legacy Document API
@app.post("/documents/route")
def route_document(
    request: DocumentRouteRequest,
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.router.route(
        {
            "action": "route_document",
            "file_path": request.file_path,
            "document_text": request.document_text,
            "threshold": request.threshold,
        }
    )


@app.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    document_text: str = Form(""),
    threshold: int = Form(1),
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    safe_name = Path(file.filename or "upload").name
    saved_path = UPLOADS_DIR / safe_name

    with saved_path.open("wb") as buffer:
        shutil.copyfileobj(
            file.file,
            buffer,
        )

    return runtime.router.route(
        {
            "action": "route_document",
            "file_path": str(saved_path),
            "document_text": document_text,
            "threshold": threshold,
        }
    )


# Legacy logging API
@app.post("/logger/resolve")
def resolve_logger(
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.router.route(
        {
            "action": "resolve_logger_conflicts",
        }
    )


@app.get("/logs/state")
def logs_state(
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.router.route(
        {
            "action": "save_system_state",
        }
    )


@app.get("/logs/metrics")
def logs_metrics(
    user: dict = Depends(get_current_user),
    runtime: ApplicationRuntime = Depends(get_runtime),
):
    return runtime.executor.metrics_logger.build_summary()