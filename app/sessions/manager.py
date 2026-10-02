import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.errors import SessionNotFoundError
from app.schemas.common import Message


@dataclass
class Session:
    id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[Message] = field(default_factory=list)


class SessionManager:
    """In-memory sessions. Swap for a persistent store behind the same interface."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> Session:
        async with self._lock:
            session = Session(id=uuid.uuid4().hex)
            self._sessions[session.id] = session
            return session

    async def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{session_id}' not found")
        return session

    async def get_or_create(self, session_id: str | None) -> Session:
        return await self.get(session_id) if session_id else await self.create()

    async def append(self, session_id: str, *messages: Message) -> None:
        (await self.get(session_id)).messages.extend(messages)
