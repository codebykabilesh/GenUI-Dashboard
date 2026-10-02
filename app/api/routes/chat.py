import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
    sessions: Annotated[SessionManager, Depends(get_sessions)],
) -> StreamingResponse:
    """Server-Sent Events: session, delta, tool_call, tool_result, done | error."""
    if body.session_id:
        await sessions.get(body.session_id)  # proper 404 before the stream starts

    async def events() -> AsyncIterator[str]:
        async for event, data in orchestrator.chat_stream(body.message, body.session_id):
            yield _sse(event, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
