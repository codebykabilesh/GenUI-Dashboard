"""Tool logic (service layer), independent of the MCP server wiring."""

import logging

from pydantic import ValidationError

from servers.investigation.models import (
    DetectionEvidenceResult,
    DetectionIdInput,
    DetectionResult,
    SearchVehicleInput,
    SearchVehicleResult,
    VehicleDetailsResult,
    VehicleHistoryResult,
)
from servers.investigation.repository import MockRepository

logger = logging.getLogger(__name__)

_default_repo = MockRepository()


class InvalidInputError(ValueError):
    """Raised when a tool argument fails validation."""


InvalidRegistrationError = InvalidInputError  # earlier name


def _plate(registration_number: str) -> str:
    try:
        return SearchVehicleInput(registration_number=registration_number).registration_number
    except ValidationError as exc:
        msg = exc.errors()[0]["msg"].removeprefix("Value error, ")
        logger.warning("rejected registration number %r: %s", registration_number, msg)
        raise InvalidInputError(msg) from exc


def _detection_id(detection_id: str) -> str:
    try:
        return DetectionIdInput(detection_id=detection_id).detection_id
    except ValidationError as exc:
        msg = exc.errors()[0]["msg"].removeprefix("Value error, ")
        logger.warning("rejected detection id %r: %s", detection_id, msg)
        raise InvalidInputError(msg) from exc


def search_vehicle(
    registration_number: str, repo: MockRepository = _default_repo
) -> SearchVehicleResult:
    plate = _plate(registration_number)
    matches = repo.records_for_plate(plate)
    logger.info("search_vehicle plate=%s matches=%d", plate, len(matches))
    if not matches:
        return SearchVehicleResult(
            query=plate,
            found=False,
            message=f"No vehicle found with registration number {plate} in the (mock) ANPR records.",
        )
    return SearchVehicleResult(
        query=plate,
        found=True,
        message=f"Found {len(matches)} record(s) for {plate} (mock data).",
        records=matches,
    )


def get_vehicle_details(
    registration_number: str, repo: MockRepository = _default_repo
) -> VehicleDetailsResult:
    plate = _plate(registration_number)
    vehicle = repo.vehicle(plate)
    logger.info("get_vehicle_details plate=%s found=%s", plate, vehicle is not None)
    if vehicle is None:
        return VehicleDetailsResult(
            query=plate, found=False, message=f"No vehicle metadata found for {plate} (mock data)."
        )
    return VehicleDetailsResult(
        query=plate, found=True, message=f"Vehicle metadata for {plate} (mock data).", vehicle=vehicle
    )


def get_vehicle_history(
    registration_number: str, repo: MockRepository = _default_repo
) -> VehicleHistoryResult:
    plate = _plate(registration_number)
    records = repo.records_for_plate(plate)
    logger.info("get_vehicle_history plate=%s records=%d", plate, len(records))
    if not records:
        return VehicleHistoryResult(
            query=plate, found=False, message=f"No detection history found for {plate} (mock data)."
        )
    return VehicleHistoryResult(
        query=plate,
        found=True,
        message=f"{len(records)} detection(s) for {plate}, oldest first (mock data).",
        total=len(records),
        records=records,
    )


def get_detection_by_id(detection_id: str, repo: MockRepository = _default_repo) -> DetectionResult:
    did = _detection_id(detection_id)
    record = repo.detection(did)
    logger.info("get_detection_by_id id=%s found=%s", did, record is not None)
    if record is None:
        return DetectionResult(
            detection_id=did, found=False, message=f"No detection found with ID {did} (mock data)."
        )
    return DetectionResult(
        detection_id=did, found=True, message=f"Detection {did} (mock data).", record=record
    )


def get_detection_evidence(
    detection_id: str, repo: MockRepository = _default_repo
) -> DetectionEvidenceResult:
    did = _detection_id(detection_id)
    evidence = repo.evidence_for(did)
    logger.info("get_detection_evidence id=%s items=%d", did, len(evidence))
    if not evidence:
        return DetectionEvidenceResult(
            detection_id=did, found=False, message=f"No evidence found for detection {did} (mock data)."
        )
    return DetectionEvidenceResult(
        detection_id=did,
        found=True,
        message=f"{len(evidence)} mock evidence reference(s) for {did}; URIs are placeholders.",
        evidence=evidence,
    )
