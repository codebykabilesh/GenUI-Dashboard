"""Single access point to the mock traffic data, shared by all tools."""

from collections import Counter
from collections.abc import Iterable
from datetime import datetime

from servers.analytics.data import COVERAGE_END, COVERAGE_START, JUNCTIONS, generate_hourly_counts


class MockTrafficRepository:
    coverage_start = COVERAGE_START
    coverage_end = COVERAGE_END

    def __init__(
        self,
        counts: dict[tuple[str, datetime], dict[str, int]] | None = None,
        junctions: dict[str, tuple[str, float]] | None = None,
    ) -> None:
        self._counts = counts if counts is not None else generate_hourly_counts()
        self._junctions = junctions if junctions is not None else JUNCTIONS

    @property
    def junction_ids(self) -> list[str]:
        return sorted(self._junctions)

    def has_junction(self, junction_id: str) -> bool:
        return junction_id in self._junctions

    def junction_name(self, junction_id: str) -> str:
        return self._junctions[junction_id][0]

    def hourly(
        self, start: datetime, end: datetime, junction_ids: Iterable[str]
    ) -> list[tuple[str, datetime, dict[str, int]]]:
        """Hourly buckets whose start is in [start, end), for the given junctions."""
        wanted = set(junction_ids)
        return sorted(
            (jn, hour, by_type)
            for (jn, hour), by_type in self._counts.items()
            if jn in wanted and start <= hour < end
        )

    def type_totals(self, start: datetime, end: datetime, junction_ids: Iterable[str]) -> Counter[str]:
        totals: Counter[str] = Counter()
        for _, _, by_type in self.hourly(start, end, junction_ids):
            totals.update(by_type)
        return totals
