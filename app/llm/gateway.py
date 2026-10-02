from app.core.config import Settings
from app.llm.base import LLMProvider, LLMResponse
from app.llm.mock import MockLLMProvider
from app.llm.openai_compat import OpenAICompatibleProvider
from app.schemas.common import Message, ToolInfo

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def create_provider(settings: Settings) -> LLMProvider:
    name = settings.llm_provider
    if name == "mock":
        return MockLLMProvider()
    if name in ("openrouter", "openai_compatible"):
        key = settings.llm_api_key or (settings.openrouter_api_key if name == "openrouter" else None)
        model = settings.llm_model or (settings.openrouter_model if name == "openrouter" else "")
        base_url = settings.llm_base_url or (OPENROUTER_BASE_URL if name == "openrouter" else "")
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
        f"Unknown LLM provider '{name}'. Supported: mock, openrouter, openai_compatible"
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
