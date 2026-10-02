import logging
import os
from collections.abc import Callable
from typing import TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from servers.investigation import tools
from servers.investigation.models import (
    DetectionEvidenceResult,
    DetectionResult,
    SearchVehicleResult,
    VehicleDetailsResult,
    VehicleHistoryResult,
)

logger = logging.getLogger("investigation")

T = TypeVar("T")

mcp = FastMCP(
    "investigation",
    instructions="Investigation tools over MOCK ANPR data (no real ANPR system is connected).",
)


def _guarded(fn: Callable[[str], T], arg: str, what: str) -> T:
    """Run a tool function, mapping failures to clean MCP tool errors."""
    try:
        return fn(arg)
    except tools.InvalidInputError as exc:
        raise ToolError(f"Invalid input: {exc}") from exc
    except Exception:
        logger.exception("%s failed", what)
        raise ToolError(f"Internal error in {what}") from None


@mcp.tool()
def search_vehicle(registration_number: str) -> SearchVehicleResult:
    """Search ANPR sightings of a vehicle by registration number (mock data)."""
    return _guarded(tools.search_vehicle, registration_number, "search_vehicle")


@mcp.tool()
def get_vehicle_details(registration_number: str) -> VehicleDetailsResult:
    """Get vehicle metadata (make, model, colour, registered state) by registration number (mock data)."""
    return _guarded(tools.get_vehicle_details, registration_number, "get_vehicle_details")


@mcp.tool()
def get_vehicle_history(registration_number: str) -> VehicleHistoryResult:
    """Get all detection records for a vehicle, oldest first (mock data)."""
    return _guarded(tools.get_vehicle_history, registration_number, "get_vehicle_history")


@mcp.tool()
def get_detection_evidence(detection_id: str) -> DetectionEvidenceResult:
    """Get authorized mock evidence references (image, plate crop, clip) for a detection ID."""
    return _guarded(tools.get_detection_evidence, detection_id, "get_detection_evidence")


@mcp.tool()
def get_detection_by_id(detection_id: str) -> DetectionResult:
    """Get a single detection record by its unique ID, e.g. DET-0001 (mock data)."""
    return _guarded(tools.get_detection_by_id, detection_id, "get_detection_by_id")


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("INVESTIGATION_HOST", "127.0.0.1")
    port = int(os.getenv("INVESTIGATION_PORT", "8101"))
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
