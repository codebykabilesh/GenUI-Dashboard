"""Prefab generative-UI MCP server.

Exposes `generate_prefab_ui` and `search_prefab_components`: the LLM writes Prefab
Python, which is validated in a sandbox and rendered by the host as an MCP App.
"""

import logging
import os

from fastmcp import FastMCP
from fastmcp.apps.generative import GenerativeUI

mcp = FastMCP("prefab")
mcp.add_provider(GenerativeUI())


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("PREFAB_HOST", "127.0.0.1")
    port = int(os.getenv("PREFAB_PORT", "8102"))
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
