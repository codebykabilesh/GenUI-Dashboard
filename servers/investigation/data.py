"""Hard-coded MOCK ANPR data. Not connected to any real ANPR system."""

from servers.investigation.models import ANPRRecord, VehicleDetails

MOCK_RECORDS: list[ANPRRecord] = [
    ANPRRecord(detection_id="DET-0001", plate_number="KA01AB1234", vehicle_type="car", confidence=0.97,
               junction_id="JN-001", timestamp="2026-09-30T08:15:22Z", direction="N"),
    ANPRRecord(detection_id="DET-0002", plate_number="KA01AB1234", vehicle_type="car", confidence=0.91,
               junction_id="JN-014", timestamp="2026-09-30T08:42:05Z", direction="E"),
    ANPRRecord(detection_id="DET-0003", plate_number="KA05MN4321", vehicle_type="motorcycle", confidence=0.88,
               junction_id="JN-003", timestamp="2026-09-30T09:03:47Z", direction="S"),
    ANPRRecord(detection_id="DET-0004", plate_number="MH12XY9876", vehicle_type="truck", confidence=0.94,
               junction_id="JN-007", timestamp="2026-10-01T22:10:11Z", direction="W"),
]

MOCK_VEHICLES: list[VehicleDetails] = [
    VehicleDetails(plate_number="KA01AB1234", vehicle_type="car", make="Maruti Suzuki", model="Swift",
                   colour="white", registered_state="Karnataka"),
    VehicleDetails(plate_number="KA05MN4321", vehicle_type="motorcycle", make="Honda", model="Activa",
                   colour="black", registered_state="Karnataka"),
    VehicleDetails(plate_number="MH12XY9876", vehicle_type="truck", make="Tata", model="407",
                   colour="blue", registered_state="Maharashtra"),
]
