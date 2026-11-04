"""Crop calendar: stage lookup and PAU's sowing-date irrigation timetable for wheat.

PAU states its schedule as weeks after the previous irrigation, not as named stages by day after
sowing. No verified Punjab table of stages by day exists in our sources, so the engine does not
guess the growth stage from the sowing date: the farmer selects it.
"""

from datetime import date, timedelta

from pydantic import BaseModel

from app.intelligence.crops import CropProfile, get_crop
from app.intelligence.types import IrrigationSchedule, IrrigationWindow

_SOURCE_ID = "pau_pop_rabi_2025"
_VARIATION_DAYS = 3  # "can be varied by 2 or 3 days on either side"

# Weeks after the previous irrigation, for irrigations 2 to 4, by sowing window.
_TIMETABLE: list[tuple[tuple[int, int], tuple[int, int], list[tuple[int, int]]]] = [
    ((10, 1), (11, 21), [(5, 6), (5, 6), (4, 4)]),
    ((11, 22), (12, 20), [(5, 6), (3, 4), (2, 2)]),
    ((12, 21), (1, 15), [(4, 4), (3, 3), (2, 2)]),
]


def days_after_sowing(sowing_date: date, on_date: date) -> int:
    return (on_date - sowing_date).days


def _rabi_order(day: date) -> tuple[int, int]:
    """Sort key placing January after December within one rabi season."""
    return (day.month + 12 if day.month < 8 else day.month, day.day)


def _weeks_table(sowing_date: date) -> list[tuple[int, int]] | None:
    key = _rabi_order(sowing_date)
    for start, end, weeks in _TIMETABLE:
        low = (start[0] + 12 if start[0] < 8 else start[0], start[1])
        high = (end[0] + 12 if end[0] < 8 else end[0], end[1])
        if low <= key <= high:
            return weeks
    return None


def _season_end(sowing_date: date) -> date:
    """PAU: irrigate to the end of March, or to 10 April for wheat sown after 5 December."""
    year = sowing_date.year if sowing_date.month < 8 else sowing_date.year + 1
    late_sown = _rabi_order(sowing_date) > _rabi_order(date(sowing_date.year, 12, 5))
    return date(year, 4, 10) if late_sown else date(year, 3, 31)


def wheat_irrigation_schedule(sowing_date: date, on_date: date) -> IrrigationSchedule | None:
    """Apply PAU's timetable. Returns None for sowing dates outside the published windows."""
    weeks_table = _weeks_table(sowing_date)
    if weeks_table is None:
        return None

    first_day = 21 if sowing_date.month == 10 else 28
    center = sowing_date + timedelta(days=first_day)
    windows = [
        IrrigationWindow(
            number=1,
            start_date=center - timedelta(days=_VARIATION_DAYS),
            end_date=center + timedelta(days=_VARIATION_DAYS),
            basis=f"{first_day // 7} weeks after sowing (a relatively light irrigation)",
        )
    ]
    for number, (low, high) in enumerate(weeks_table, start=2):
        start = center + timedelta(weeks=low)
        end = center + timedelta(weeks=high)
        center = start + (end - start) / 2
        if low == high:
            start -= timedelta(days=_VARIATION_DAYS)
            end += timedelta(days=_VARIATION_DAYS)
        span = f"{low}" if low == high else f"{low}-{high}"
        windows.append(
            IrrigationWindow(
                number=number,
                start_date=start,
                end_date=end,
                basis=f"{span} weeks after irrigation {number - 1}",
            )
        )

    return IrrigationSchedule(
        sowing_date=sowing_date,
        days_after_sowing=days_after_sowing(sowing_date, on_date),
        windows=windows,
        last_irrigation_by=_season_end(sowing_date),
        in_window=next((w for w in windows if w.start_date <= on_date <= w.end_date), None),
        next_window=next((w for w in windows if w.start_date > on_date), None),
        source_id=_SOURCE_ID,
    )


def rain_interval_extension_days(rain_mm: float, on_date: date) -> float:
    """PAU: each 1 cm of rain adds 5 days to the next interval to end January, then 2 days."""
    per_cm = 5 if on_date.month in (8, 9, 10, 11, 12, 1) else 2
    return round(rain_mm / 10 * per_cm, 1)


class StageInformation(BaseModel):
    id: str
    label: str
    irrigation_critical: bool
    crop_coefficient: float | None = None
    note: str | None = None


def stage_information(profile: CropProfile, stage_id: str | None) -> StageInformation | None:
    stage = profile.stage(stage_id)
    if stage is None:
        return None
    return StageInformation(
        id=stage.id,
        label=stage.label,
        irrigation_critical=stage.irrigation_critical,
        crop_coefficient=stage.kc,
        note=stage.note,
    )


def schedule_for_crop(
    crop_id: str, sowing_date: date | None, on_date: date
) -> IrrigationSchedule | None:
    profile = get_crop(crop_id)
    if profile is None or profile.id != "wheat" or sowing_date is None:
        return None
    return wheat_irrigation_schedule(sowing_date, on_date)
