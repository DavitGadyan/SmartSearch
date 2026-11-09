from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.schemas.agent import ChatRequest, ChatResponse
from app.services import agent_service
from app.services.runtime import runtime

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status")
async def status():
    return {
        "provider": "claude" if settings.anthropic_api_key else "rule_based",
        "model": settings.agent_model if settings.anthropic_api_key else None,
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    if runtime.catalog is None:
        raise HTTPException(503, "catalog not loaded")
    if body.messages[-1].role != "user":
        raise HTTPException(422, "last message must be from the user")
    return await agent_service.chat(db, body.user_id, body.session_id, body.messages, body.cart)
