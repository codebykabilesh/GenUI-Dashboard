from collections.abc import AsyncIterator

from app.core.config import Settings
from app.llm.base import LLMProvider, LLMResponse, StreamEvent
from app.llm.mock import MockLLMProvider
from app.llm.openai_compat import OpenAICompatibleProvider
from app.schemas.common import Message, ToolInfo

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def create_provider(settings: Settings) -> LLMProvider:
    name = settings.llm_provider
    if name == "mock":
        return MockLLMProvider()
    if name in ("groq", "openrouter", "openai_compatible"):
        # (fallback key, fallback model, default base URL) per preset
        presets = {
            "groq": (settings.groq_api_key, settings.groq_model, GROQ_BASE_URL),
            "openrouter": (settings.openrouter_api_key, settings.openrouter_model, OPENROUTER_BASE_URL),
            "openai_compatible": (None, "", ""),
        }
        preset_key, preset_model, preset_url = presets[name]
        key = settings.llm_api_key or preset_key
        model = settings.llm_model or preset_model
        base_url = settings.llm_base_url or preset_url
        missing = [
            label
            for label, value in (("LLM_API_KEY", key), ("LLM_MODEL", model), ("LLM_BASE_URL", base_url))
            if not value
        ]
        if missing:
            raise ValueError(f"LLM_PROVIDER={name} requires: {', '.join(missing)}")
        return OpenAICompatibleProvider(
            name=name,
            base_url=base_url,
            api_key=key.get_secret_value(),  # type: ignore[union-attr]
            model=model,
            timeout=settings.llm_timeout,
        )
    raise ValueError(
        f"Unknown LLM provider '{name}'. Supported: mock, groq, openrouter, openai_compatible"
    )


class LLMGateway:
    """Provider-independent entry point; the orchestrator only talks to this."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def complete(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> LLMResponse:
        return await self._provider.complete(messages, tools, system)

    async def aclose(self) -> None:
        close = getattr(self._provider, "aclose", None)
        if close:
            await close()

    def stream(
        self, messages: list[Message], tools: list[ToolInfo], system: str | None = None
    ) -> AsyncIterator[StreamEvent]:
        return self._provider.stream(messages, tools, system)
