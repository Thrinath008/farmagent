"""Crop profile structure. Adding a crop means adding one validated profile to the registry."""

from dataclasses import dataclass, field
from typing import Literal

SupportLevel = Literal["rules_implemented", "planned"]


@dataclass(frozen=True)
class GrowthStage:
    id: str
    label: str
    irrigation_critical: bool = False
    kc: float | None = None
    temp_max_range_c: tuple[float, float] | None = None
    note: str | None = None


@dataclass(frozen=True)
class ThreatRule:
    id: str
    name: str
    category: Literal["fungal", "insect", "abiotic"]
    temp_min_c: float | None
    temp_max_c: float | None
    humidity_min_pct: float | None
    susceptible_stages: frozenset[str]
    favorable_conditions: str
    monitoring_actions: tuple[str, ...]
    needs_rain: bool = False
    # Forecast rain counts as well as humidity, standing in for "free moisture" on the leaf.
    rain_counts_as_moisture: bool = False
    # Daily-window rules compare each 24 hours' minimum and maximum, as PAU states yellow rust.
    daily_min_range_c: tuple[float, float] | None = None
    daily_max_range_c: tuple[float, float] | None = None
    # False when no verified weather trigger exists: the rule gives monitoring advice only.
    weather_evaluable: bool = True
    regional_note: str | None = None
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CropProfile:
    id: str
    name: str
    support: SupportLevel
    support_note: str
    stages: tuple[GrowthStage, ...] = ()
    stage_aliases: dict[str, str] = field(default_factory=dict)
    threats: tuple[ThreatRule, ...] = ()
    irrigation_considerations: tuple[str, ...] = ()
    weather_sensitivities: tuple[str, ...] = ()
    no_irrigation_stages: frozenset[str] = frozenset()
    first_irrigation_stages: frozenset[str] = frozenset()
    variety_notes: dict[str, str] = field(default_factory=dict)
    source_ids: tuple[str, ...] = ()

    def stage(self, stage_id: str | None) -> GrowthStage | None:
        if not stage_id:
            return None
        key = stage_id.strip().lower().replace(" ", "_").replace("-", "_")
        key = self.stage_aliases.get(key, key)
        return next((s for s in self.stages if s.id == key), None)
