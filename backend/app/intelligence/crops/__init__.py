"""Crop registry. A crop stays "planned", and gets no assessments, until its rules exist."""

from app.intelligence.crops.base import CropProfile, GrowthStage, ThreatRule
from app.intelligence.crops.wheat import WHEAT

_PLANNED_NOTE = (
    "Crop-specific rules for {name} are not implemented yet, so FarmAgent does not assess it. You "
    "can still record it on your farm and see the weather."
)


def _planned(crop_id: str, name: str) -> CropProfile:
    return CropProfile(
        id=crop_id,
        name=name,
        support="planned",
        support_note=_PLANNED_NOTE.format(name=name.lower()),
    )


CROPS: dict[str, CropProfile] = {
    profile.id: profile
    for profile in (
        WHEAT,
        _planned("rice", "Rice"),
        _planned("maize", "Maize"),
        _planned("cotton", "Cotton"),
        _planned("sugarcane", "Sugarcane"),
        _planned("pulses", "Pulses"),
        _planned("vegetables", "Vegetables"),
    )
}


def get_crop(crop_id: str | None) -> CropProfile | None:
    if not crop_id:
        return None
    return CROPS.get(crop_id.strip().lower())


__all__ = ["CROPS", "CropProfile", "GrowthStage", "ThreatRule", "get_crop"]
