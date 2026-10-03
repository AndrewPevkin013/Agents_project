from fastapi import APIRouter

from app.api.v1.conversations import router as conversations_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(conversations_router)