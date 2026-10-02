import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseModel):
    """One MCP server: either remote (`url`) or local stdio (`command`)."""

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def _one_transport(self) -> "MCPServerConfig":
        if bool(self.url) == bool(self.command):
            raise ValueError(f"server '{self.name}': set exactly one of 'url' or 'command'")
        return self

    def to_client_config(self) -> dict[str, Any]:
        """Single-server MCPConfig dict understood by fastmcp.Client."""
        if self.url:
            entry: dict[str, Any] = {"url": self.url}
            if self.headers:
                entry["headers"] = self.headers
        else:
            entry = {"command": self.command, "args": self.args}
            if self.env:
                entry["env"] = self.env
        return {"mcpServers": {self.name: entry}}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "GenUI MCP Runtime"
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    llm_provider: str = "mock"  # mock | openrouter | openai_compatible
    llm_model: str = ""
    llm_api_key: SecretStr | None = None
    llm_base_url: str = ""
    llm_timeout: float = 60.0
    # Legacy variable names, used as fallback by the "openrouter" provider.
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = ""
    max_tool_rounds: int = 8

    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    mcp_servers_file: str = ""
    mcp_connect_timeout: float = 10.0
    mcp_call_timeout: float = 30.0

    def load_servers(self) -> list[MCPServerConfig]:
        """Servers from MCP_SERVERS_FILE if set, else MCP_SERVERS."""
        if self.mcp_servers_file:
            raw = json.loads(Path(self.mcp_servers_file).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw = raw.get("servers", [])
            return [MCPServerConfig.model_validate(s) for s in raw]
        return self.mcp_servers


@lru_cache
def get_settings() -> Settings:
    return Settings()
