"""Confidence: a statement about input completeness and freshness, not about accuracy."""

from app.intelligence.types import Confidence, WeatherSnapshot
from app.schemas.weather import DataProvenance

_NOTE = "This describes how complete the inputs were. It is not a measured accuracy."


def assess_confidence(
    snapshot: WeatherSnapshot | None,
    *,
    critical_missing: list[str],
    secondary_missing: list[str],
) -> tuple[Confidence, str]:
    if snapshot is None or snapshot.provenance == DataProvenance.UNAVAILABLE:
        return Confidence.INSUFFICIENT, f"No verified weather was available. {_NOTE}"

    if critical_missing:
        level = Confidence.LIMITED
        reason = "Key inputs are missing: " + ", ".join(critical_missing) + "."
    elif secondary_missing:
        level = Confidence.MODERATE
        reason = "Some supporting inputs are missing: " + ", ".join(secondary_missing) + "."
    else:
        level = Confidence.GOOD
        reason = "All inputs this assessment uses were provided."

    if snapshot.is_stale:
        level = Confidence.LIMITED
        reason += " The weather data is out of date."
    if snapshot.provenance == DataProvenance.SIMULATED:
        reason += " The weather is simulated."
    return level, f"{reason} {_NOTE}"
