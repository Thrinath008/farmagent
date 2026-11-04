"""Wheat rules for Punjab. Sources and limits for each value: docs/agricultural-assumptions.md."""

from app.intelligence.crops.base import CropProfile, GrowthStage, ThreatRule

# PAU's "maximum temperature for higher productivity" ranges, by phase of the crop.
_VEGETATIVE_TMAX = (15.0, 22.0)
_GRAIN_TMAX = (21.0, 28.0)

# Kc from FAO-56 Table 12, winter wheat on non-frozen soils: ini 0.7, mid 1.15, end 0.25-0.4.
# 0.93 and 0.78 are midpoints of the rising and falling limbs of the crop-coefficient curve.
_KC_INITIAL = 0.7
_KC_DEVELOPMENT = 0.93
_KC_MID = 1.15
_KC_LATE = 0.78
_KC_END = 0.4

_STAGES = (
    GrowthStage(
        "germination",
        "Germination and emergence",
        kc=_KC_INITIAL,
        temp_max_range_c=_VEGETATIVE_TMAX,
    ),
    GrowthStage(
        "crown_root_initiation",
        "Crown root initiation",
        irrigation_critical=True,
        kc=_KC_INITIAL,
        temp_max_range_c=_VEGETATIVE_TMAX,
        note="Coincides with the first irrigation in PAU's timetable.",
    ),
    GrowthStage("tillering", "Tillering", kc=_KC_DEVELOPMENT, temp_max_range_c=_VEGETATIVE_TMAX),
    GrowthStage(
        "vegetative",
        "Vegetative (general)",
        kc=_KC_DEVELOPMENT,
        temp_max_range_c=_VEGETATIVE_TMAX,
        note="Use when the exact vegetative stage is not known.",
    ),
    GrowthStage("jointing", "Jointing", kc=_KC_DEVELOPMENT, temp_max_range_c=_VEGETATIVE_TMAX),
    GrowthStage("boot_leaf", "Boot leaf", kc=_KC_MID, temp_max_range_c=_VEGETATIVE_TMAX),
    GrowthStage(
        "heading_flowering",
        "Ear emergence and flowering",
        irrigation_critical=True,
        kc=_KC_MID,
        temp_max_range_c=_GRAIN_TMAX,
    ),
    GrowthStage(
        "grain_filling", "Grain filling (milk and dough)", kc=_KC_LATE, temp_max_range_c=_GRAIN_TMAX
    ),
    GrowthStage("maturity", "Maturity", kc=_KC_END),
)

_AFTER_EMERGENCE = frozenset(
    {
        "crown_root_initiation",
        "tillering",
        "vegetative",
        "jointing",
        "boot_leaf",
        "heading_flowering",
        "grain_filling",
    }
)
_AFTER_ANTHESIS = frozenset({"heading_flowering", "grain_filling"})
_BEFORE_ANTHESIS = frozenset(
    {"germination", "crown_root_initiation", "tillering", "vegetative", "jointing", "boot_leaf"}
)

_THREATS = (
    ThreatRule(
        id="yellow_rust",
        name="Yellow (stripe) rust",
        category="fungal",
        temp_min_c=None,
        temp_max_c=None,
        humidity_min_pct=85,
        daily_min_range_c=(7, 13),
        daily_max_range_c=(15, 24),
        susceptible_stages=_AFTER_EMERGENCE,
        favorable_conditions=(
            "Night minimum of 7-13 °C with 85-100% humidity, and a day maximum of 15-24 °C."
        ),
        monitoring_actions=(
            "Walk the field from the second week of December, especially after irrigation or rain.",
            "Look for the first patches of yellow, powdery stripes on leaves.",
            "If you find a patch, confirm it with your extension officer before any treatment.",
        ),
        regional_note=(
            "PAU reports that it appears first in Punjab's sub-mountainous areas, and that rain with "
            "wind in February-March can worsen its spread."
        ),
        source_ids=("pau_pop_rabi_2025",),
    ),
    ThreatRule(
        id="brown_rust",
        name="Brown (leaf) rust",
        category="fungal",
        temp_min_c=20,
        temp_max_c=25,
        humidity_min_pct=85,
        rain_counts_as_moisture=True,
        susceptible_stages=_AFTER_EMERGENCE,
        favorable_conditions="20-25 °C with free moisture on the leaf from rain or dew.",
        monitoring_actions=(
            "Check lower and middle leaves for small round orange-brown pustules.",
            "Confirm anything you find with your extension officer before any treatment.",
        ),
        source_ids=("niphm_vikaspedia",),
    ),
    ThreatRule(
        id="powdery_mildew",
        name="Powdery mildew",
        category="fungal",
        temp_min_c=18,
        temp_max_c=23,
        humidity_min_pct=85,
        susceptible_stages=_AFTER_EMERGENCE,
        favorable_conditions="High humidity, not necessarily rain, with temperatures around 20-21 °C.",
        monitoring_actions=(
            "Check dense, shaded parts of the field for white powdery growth on leaves.",
            "Confirm anything you find with your extension officer before any treatment.",
        ),
        source_ids=("niphm_vikaspedia",),
    ),
    ThreatRule(
        id="karnal_bunt",
        name="Karnal bunt",
        category="fungal",
        temp_min_c=8,
        temp_max_c=20,
        humidity_min_pct=80,
        needs_rain=True,
        susceptible_stages=frozenset({"heading_flowering"}),
        favorable_conditions=(
            "8-20 °C with high humidity, light rain and cloud at ear emergence and flowering."
        ),
        monitoring_actions=(
            "Note rainy, cloudy spells during ear emergence and flowering.",
            "Karnal bunt only shows in the grain, so inspect grain samples at harvest.",
        ),
        regional_note=(
            "PAU authors link high-incidence years in Punjab to February-March rain and humidity at "
            "flowering, and note the disease is difficult to predict."
        ),
        source_ids=("eppo_karnal_bunt", "bala_2020_karnal_bunt"),
    ),
    ThreatRule(
        id="spot_blotch",
        name="Foliar blight (spot blotch)",
        category="fungal",
        temp_min_c=18,
        temp_max_c=32,
        humidity_min_pct=90,
        susceptible_stages=_AFTER_EMERGENCE,
        favorable_conditions=(
            "18-32 °C with humidity near 95% and more than 12-18 hours of leaf wetness."
        ),
        monitoring_actions=(
            "Look for brown oval spots with yellow margins, especially after flowering.",
            "Confirm anything you find with your extension officer before any treatment.",
        ),
        regional_note="Reported as mainly a problem of the warmer North Eastern Plains Zone.",
        source_ids=("chowdhury_2013_spot_blotch",),
    ),
    ThreatRule(
        id="aphids",
        name="Aphids",
        category="insect",
        temp_min_c=None,
        temp_max_c=None,
        humidity_min_pct=None,
        weather_evaluable=False,
        susceptible_stages=frozenset({"heading_flowering", "grain_filling"}),
        favorable_conditions=(
            "No verified weather trigger for Punjab, so this cannot be judged from the forecast."
        ),
        monitoring_actions=(
            "At ear-head stage, check 10 random ear heads in each of 4 quarters of one acre.",
            "PAU's threshold is 5 aphids per ear head. Aphids usually appear on field borders first.",
            "Ask your extension officer about control if the threshold is crossed.",
        ),
        source_ids=("pau_pop_rabi_2025",),
    ),
    ThreatRule(
        id="terminal_heat",
        name="Terminal heat stress",
        category="abiotic",
        temp_min_c=30,
        temp_max_c=None,
        humidity_min_pct=None,
        susceptible_stages=_AFTER_ANTHESIS,
        favorable_conditions="Temperatures above 30 °C after flowering and during grain development.",
        monitoring_actions=(
            "Avoid moisture stress at this stage. PAU continues irrigation to the end of March for "
            "timely sown wheat, depending on rain, and to 10 April for wheat sown after 5 December.",
            "Do not irrigate on windy days, to avoid lodging.",
        ),
        source_ids=("singh_2023_terminal_heat", "pau_pop_rabi_2025"),
    ),
    ThreatRule(
        id="vegetative_heat",
        name="Early-season heat stress",
        category="abiotic",
        temp_min_c=30,
        temp_max_c=None,
        humidity_min_pct=None,
        susceptible_stages=_BEFORE_ANTHESIS,
        favorable_conditions=(
            "PAU reports poor tillering and early heading when the vegetative-stage maximum runs "
            "above 15-22 °C. FarmAgent flags this only from 30 °C."
        ),
        monitoring_actions=(
            "Check soil moisture more often during hot, dry spells.",
            "Record the dates of the spell, since they help explain later tillering and heading.",
        ),
        source_ids=("pau_pop_rabi_2025",),
    ),
)

WHEAT = CropProfile(
    id="wheat",
    name="Wheat",
    support="rules_implemented",
    support_note=(
        "Rules are implemented for wheat from published Punjab guidance. They have not been "
        "validated in field trials."
    ),
    stages=_STAGES,
    stage_aliases={
        "cri": "crown_root_initiation",
        "crown_root": "crown_root_initiation",
        "emergence": "germination",
        "sowing": "germination",
        "boot": "boot_leaf",
        "booting": "boot_leaf",
        "heading": "heading_flowering",
        "flowering": "heading_flowering",
        "anthesis": "heading_flowering",
        "ear_emergence": "heading_flowering",
        "milk": "grain_filling",
        "dough": "grain_filling",
        "grain_development": "grain_filling",
        "ripening": "maturity",
        "harvest": "maturity",
    },
    threats=_THREATS,
    irrigation_considerations=(
        "PAU's first irrigation is relatively light: 3 weeks after sowing for October-sown wheat, "
        "and 4 weeks for wheat sown later.",
        "On light soils, advance the first irrigation. On heavy paddy soils, delay it by one week.",
        "For each 1 cm of rain, PAU lengthens the interval to the next irrigation by 5 days up to "
        "the end of January, and by 2 days after that.",
        "Do not irrigate on windy days, to avoid lodging.",
        "Avoid excessive irrigation. Wheat does not suit waterlogged soils.",
    ),
    weather_sensitivities=(
        "PAU gives higher productivity when the maximum stays within 15-22 °C in the vegetative "
        "stage and 21-28 °C during grain development, and the minimum within 4-11 °C and 7-13 °C.",
        "Higher vegetative-stage temperatures cause poor tillering and early heading.",
        "Rising temperatures after flowering cause premature ripening and lower grain weight.",
        "Rain and humidity at flowering favour Karnal bunt.",
    ),
    no_irrigation_stages=frozenset({"maturity"}),
    first_irrigation_stages=frozenset({"germination", "crown_root_initiation"}),
    variety_notes={
        "pbw 1 chapati": (
            "PAU advises reducing one irrigation for PBW 1 Chapati on medium-textured soils, to "
            "prevent lodging."
        ),
    },
    source_ids=(
        "pau_pop_rabi_2025",
        "fao56_ch6",
        "fao56_ch7",
        "fao56_ch8",
        "fao56_hargreaves",
        "tnau_irrigation",
    ),
)
