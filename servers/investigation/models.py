import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_DETECTION_ID = re.compile(r"^DET-\d{4,8}$")


def normalize_plate(value: str) -> str:
    return "".join(ch for ch in value if ch not in " -").upper()


def validate_plate(value: str) -> str:
    plate = normalize_plate(value.strip())
    if not (4 <= len(plate) <= 12) or not plate.isalnum() or not plate.isascii():
        raise ValueError("registration number must be 4-12 letters/digits (spaces and hyphens allowed)")
    return plate


def validate_detection_id(value: str) -> str:
    did = value.strip().upper()
    if not _DETECTION_ID.match(did):
        raise ValueError("detection id must look like DET-0001")
    return did


class SearchVehicleInput(BaseModel):
    registration_number: str = Field(description="Vehicle registration number, e.g. KA01AB1234")

    @field_validator("registration_number")
    @classmethod
    def _validate(cls, v: str) -> str:
        return validate_plate(v)


class DetectionIdInput(BaseModel):
    detection_id: str = Field(description="Unique detection ID, e.g. DET-0001")

    @field_validator("detection_id")
    @classmethod
    def _validate(cls, v: str) -> str:
        return validate_detection_id(v)


class ANPRRecord(BaseModel):
    detection_id: str
    plate_number: str
    vehicle_type: str
    confidence: float = Field(ge=0, le=1)
    junction_id: str
    timestamp: datetime
    direction: Literal["N", "S", "E", "W", "NE", "NW", "SE", "SW"]


class VehicleDetails(BaseModel):
    plate_number: str
    vehicle_type: str
    make: str
    model: str
    colour: str
    registered_state: str


class EvidenceRef(BaseModel):
    evidence_id: str
    kind: Literal["vehicle_image", "plate_crop", "video_clip"]
    uri: str
    content_type: str


class _MockResult(BaseModel):
    """Envelope shared by every tool result."""

    found: bool
    message: str
    mock_data: bool = True


class SearchVehicleResult(_MockResult):
    query: str
    records: list[ANPRRecord] = Field(default_factory=list)


class VehicleDetailsResult(_MockResult):
    query: str
    vehicle: VehicleDetails | None = None


class VehicleHistoryResult(_MockResult):
    query: str
    total: int = 0
    records: list[ANPRRecord] = Field(default_factory=list)


class DetectionResult(_MockResult):
    detection_id: str
    record: ANPRRecord | None = None


class DetectionEvidenceResult(_MockResult):
    detection_id: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
