"""Single access point to the mock dataset, shared by all tools."""

from collections.abc import Sequence

from servers.investigation.data import MOCK_RECORDS, MOCK_VEHICLES
from servers.investigation.models import ANPRRecord, EvidenceRef, VehicleDetails


class MockRepository:
    def __init__(
        self,
        records: Sequence[ANPRRecord] = MOCK_RECORDS,
        vehicles: Sequence[VehicleDetails] = MOCK_VEHICLES,
    ) -> None:
        self._records = sorted(records, key=lambda r: r.timestamp)
        self._by_id = {r.detection_id: r for r in self._records}
        self._vehicles = {v.plate_number: v for v in vehicles}

    def records_for_plate(self, plate: str) -> list[ANPRRecord]:
        return [r for r in self._records if r.plate_number == plate]

    def vehicle(self, plate: str) -> VehicleDetails | None:
        return self._vehicles.get(plate)

    def detection(self, detection_id: str) -> ANPRRecord | None:
        return self._by_id.get(detection_id)

    def evidence_for(self, detection_id: str) -> list[EvidenceRef]:
        """Evidence references in the evidence store's layout (development data: no media behind them)."""
        record = self._by_id.get(detection_id)
        if record is None:
            return []
        base = (f"s3://chn-anpr-evidence/{record.timestamp:%Y/%m/%d}/{record.junction_id}/"
                f"{record.camera_id}/{detection_id}")
        return [
            EvidenceRef(evidence_id=f"{detection_id}-IMG", kind="vehicle_image",
                        uri=f"{base}/vehicle.jpg", content_type="image/jpeg"),
            EvidenceRef(evidence_id=f"{detection_id}-PLT", kind="plate_crop",
                        uri=f"{base}/plate.jpg", content_type="image/jpeg"),
            EvidenceRef(evidence_id=f"{detection_id}-VID", kind="video_clip",
                        uri=f"{base}/clip.mp4", content_type="video/mp4"),
        ]
