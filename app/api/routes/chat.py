from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_orchestrator, get_sessions
from app.orchestrator.orchestrator import Orchestrator
from app.schemas.api import ChatRequest, ChatResponse, SessionResponse
from app.sessions.manager import SessionManager

router = APIRouter(prefix="/api/v1")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest, orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)]
) -> ChatResponse:
    return await orchestrator.chat(body.message, body.session_id)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str, sessions: Annotated[SessionManager, Depends(get_sessions)]
) -> SessionResponse:
    s = await sessions.get(session_id)
    return SessionResponse(session_id=s.id, created_at=s.created_at, messages=s.messages)
