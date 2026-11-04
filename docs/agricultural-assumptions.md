# Agricultural rules, sources and assumptions

This document lists every agricultural rule in FarmAgent, where it came from, and what it cannot do.

**Read this first.** FarmAgent's rules come from published guidance plus design choices of its own.
They have **not** been calibrated or validated in field trials. Status and risk labels are rule-based
statements, not measurements or predictions. Confidence describes how complete the inputs were; it
is not a measured accuracy.

Code: `backend/app/intelligence/`. Crop data: `crops/wheat.py`. Citations: `sources.py`.

## How to read the rule tables

Each rule has one of three bases:

- **Sourced**: the value is stated in the cited document.
- **Derived**: calculated or inferred from a sourced value. The inference is described.
- **Design heuristic**: a threshold chosen for this software. No source states it. These are the
  first things to review with an agronomist.

## Crop support

| Crop | Support | Meaning |
|---|---|---|
| Wheat | Rules implemented | Irrigation and weather-risk rules below, drawn from Punjab guidance |
| Rice, maize, cotton, sugarcane, pulses, vegetables | Planned | Can be recorded on a farm. Assessments return "insufficient information", and FarmAgent says crop-specific rules are not available |

The wheat rules are written for **Punjab, India**. Elsewhere they are at best indicative. FarmAgent
does not currently warn when a farm lies outside Punjab, so this limit is the farmer's and the
deployer's to know.

## Sources

Verification key:

- **Read in full**: the document was downloaded and its text read during development.
- **Read by summary**: loaded through a tool that returns a summary rather than raw text. Treat the
  values as needing a check against the original.

| ID in code | Document | Publisher | Verification |
|---|---|---|---|
| `pau_pop_rabi_2025` | [Package of Practices for Crops of Punjab, Rabi 2025-26](https://www.pau.edu/content/ccil/pf/pp_rabi.pdf), Vol. 42 No. 2, wheat chapter pp. 1-22 | Punjab Agricultural University (PAU), Ludhiana | Read in full |
| `fao56_ch6` | [FAO-56 Chapter 6](https://www.fao.org/3/x0490e/x0490e0b.htm): single crop coefficient, Table 12 | FAO | Read in full |
| `fao56_ch7` | [FAO-56 Chapter 7](https://www.fao.org/3/x0490e/x0490e0c.htm): soil water characteristics, Table 19 | FAO | Read by summary |
| `fao56_ch8` | [FAO-56 Chapter 8](https://www.fao.org/3/x0490e/x0490e0e.htm): rooting depth and depletion, Table 22 | FAO | Read by summary |
| `fao56_hargreaves` | [FAO-56 meteorological data page](https://www.fao.org/3/x0490e/x0490e07.htm): Hargreaves, Eq. 52 | FAO | Read in full |
| `niphm_vikaspedia` | [IPM Strategies for Wheat: Diseases and Symptoms](https://vikaspedia.in/agriculture/crop-production/integrated-pest-managment/ipm-for-cerels/ipm-strategies-for-wheat/wheat-diseases-and-symptoms) | NIPHM text, on the Vikaspedia portal | Read in full. The portal relays NIPHM; the original NIPHM document was not seen, so these are treated as secondary |
| `eppo_karnal_bunt` | [EPPO datasheet: *Tilletia indica*](https://gd.eppo.int/taxon/NEOVIN/datasheet) | EPPO | Read in full |
| `bala_2020_karnal_bunt` | [Bala & Kaur, Karnal bunt: a threat to export of Indian wheat](https://epubs.icar.org.in/index.php/IndFarm/article/download/111437/43673/289726), Indian Farming 70(09): 32-34, 2020 | ICAR | Read in full |
| `chowdhury_2013_spot_blotch` | [Chowdhury et al., Spot blotch disease of wheat](https://epubs.icar.org.in/index.php/JWR/article/download/36730/16366/84384), J. Wheat Res. 5(2): 1-11, 2013 | Society for Advancement of Wheat Research | Read in full |
| `singh_2023_terminal_heat` | [Singh et al., Terminal heat stress in wheat](https://epubs.icar.org.in/index.php/IndFarm/article/download/133793/50127/361734), Indian Farming 73(05): 15-18, 2023 | ICAR | Read in full |
| `tnau_irrigation` | [Irrigation management: wheat](https://agritech.tnau.ac.in/agriculture/agri_irrigationmgt_wheat.html) | TNAU Agritech Portal | Read by summary. Tamil Nadu guidance, used only to name critical stages |

Read during research but not cited by the engine: Anand et al. 2026, *Wheat Rust Epidemiology Across
Various Sowing Windows at Two Agroclimatic Locations of Punjab*, J. Cereal Res. 18(1): 69-80, which
disagrees with PAU on one point (see [Where sources disagree](#where-sources-disagree)).

**Sources that could not be used.** `iiwbr.icar.gov.in` did not resolve during research, so no IIWBR
page was verified. No NCIPM, CRIDA or IMD Agromet page was successfully read. FarmAgent cites none
of them.

## What the sources do not say

These gaps were searched for and not found. FarmAgent does not fill them from memory.

| Gap | What FarmAgent does instead |
|---|---|
| A rule for skipping irrigation on **forecast** rain | PAU's rain rule covers rain that has already fallen. FarmAgent applies it prospectively, as "if it falls, PAU's rule would lengthen the interval", and treats the rain thresholds as design heuristics |
| Quantified waterlogging damage (hours or days to yield loss) | No quantity is stated. Reported wet soil holds irrigation, citing PAU's "avoid excessive irrigation" |
| A frost temperature threshold | Frost is **not modelled**. FarmAgent neither warns of frost nor assesses it |
| Weather triggers for aphids in Punjab | Aphids are monitoring-only and always "uncertain" from weather |
| An instruction to report findings to a KVK | Referring farmers to extension officers and Krishi Vigyan Kendras is a design choice, not a sourced rule |
| A Punjab table of growth stages by days after sowing | FarmAgent does not guess the stage from the sowing date. The farmer selects it |

## Weather inputs

| Rule | Value | Basis |
|---|---|---|
| Weather-dependent assessment requires validated weather | Otherwise status is `insufficient_information` and no recommendation is given | Product rule |
| Forecast window for rain and demand | Next 48 hours (16 three-hour periods) | Design heuristic |
| Recent rain | Entered by the farmer. OpenWeatherMap's current endpoint gives only 1 h and 3 h rain, so multi-day history is unknown unless entered | Data limit |
| Rain probability and amount | Always kept separate. A probability never stands in for an amount | Product rule |

## Irrigation engine

`intelligence/irrigation.py`. Each factor adds a whole-number weight. Positive favours irrigating,
negative favours waiting. The total is a tally, not a probability.

### Factors and weights

All weights are **design heuristics**. They express relative importance and were not fitted to data.

| Factor | Condition | Weight | Basis of the condition |
|---|---|---|---|
| Soil moisture | Low | +3 | Farmer's observation |
| | Adequate | -1 | Farmer's observation |
| | High or waterlogged | -4 | PAU: "Avoid excessive irrigation" |
| | Not provided | 0 (unknown) | Never assumed |
| Forecast rain, 48 h | At least 10 mm and at least 60% chance | -3 | 10 mm comes from PAU's "per cm" rule. The probability is a design heuristic |
| | At least 5 mm and at least 50% chance | -2 | Design heuristic |
| | Under 2 mm and at least 60% chance | 0 | Design heuristic: likely rain, too small to replace irrigation |
| | Under 1 mm and at most 30% chance | +1 | Design heuristic |
| | Anything else | 0 | Too uncertain or small to change the decision alone |
| | Amount or probability missing | 0 (unknown) | Never assumed |
| Recent rain | At least 10 mm | -2 | PAU's interval rule. The threshold is a design heuristic |
| | At least 5 mm | -1 | As above |
| | Less | 0 | |
| | Not provided | 0 (unknown) | Never assumed |
| Heat and dryness | At least 35 °C and at most 40% humidity | +2 | Design heuristic, informed by Singh et al. 2023 on heat stress |
| | Above the stage's PAU upper temperature and at most 60% humidity | +1 | Temperature from PAU; humidity is a design heuristic |
| | At most 25 °C and at least 70% humidity | -1 | Design heuristic |
| | Otherwise | 0 | |
| Growth stage | Maturity | -3 | Derived: PAU ends irrigation by a set date, and no irrigation is useful at maturity |
| | Crown root initiation, or ear emergence and flowering | +1 | TNAU names CRI and flowering as most critical |
| | Other stages | 0 | |
| | Not provided | 0 (unknown) | Never assumed |
| Soil type | Sandy or loamy sand | +1 | FAO Table 19 and PAU, which advances the first irrigation on light soils |
| | Clay or clay loam, at germination or CRI | -1 | PAU delays the first irrigation by a week on heavy paddy soils |
| | Other | 0 | |
| Wind | At least 8 m/s (about 29 km/h), now or in the next 24 h | -2 | PAU says not to irrigate on windy days but gives **no speed**. 8 m/s is a design heuristic |
| PAU timetable (only with a sowing date in range) | Inside a window | +1 | PAU timetable |
| | After the last irrigation date | -2 | PAU timetable |
| | Between windows | 0 | |

### From tally to status

The tally alone does not decide. These rules run in order, and the first match wins
(`_decide` in `irrigation.py`). All are design choices.

| # | Condition | Status | Action |
|---|---|---|---|
| 1 | Soil moisture is high | Caution | Hold irrigation |
| 2 | Stage is maturity, or the PAU season has ended | Monitor | Hold irrigation |
| 3 | Windy | Caution | Consider postponing |
| 4 | Forecast rain weight is negative and total is at most -1 | Caution | Consider postponing |
| 5 | Low soil moisture, weather not out of date, rain known, no rain signal, total at least +3 | **Favorable** | Consider irrigating |
| 6 | Low soil moisture otherwise | Monitor | Check soil and reassess |
| 7 | Adequate soil moisture | Monitor | Check soil and reassess |
| 8 | Soil moisture unknown | Monitor | Check soil and reassess |

The consequence of rule 5 is deliberate: **FarmAgent never suggests irrigating unless the farmer has
reported low soil moisture.** Weather alone cannot show that a field is dry.

### PAU facts used directly

| Rule | Value | Source |
|---|---|---|
| Rain interval rule | Each 1 cm of rain lengthens the interval to the next irrigation by 5 days up to the end of January, then by 2 days | PAU p. 16 |
| First irrigation | Relatively light. 3 weeks after sowing for October-sown wheat, 4 weeks for wheat sown later | PAU p. 16 |
| Later irrigations, weeks after the previous one (sandy loam or heavier) | Sown up to 21 Nov: 5-6, 5-6, 4. Sown 22 Nov to 20 Dec: 5-6, 3-4, 2. Sown 21 Dec to 15 Jan: 4, 3, 2 | PAU p. 16 |
| Variation | Intervals may vary by 2 or 3 days either side. FarmAgent uses 3 for single-value intervals | PAU p. 16 |
| Season end | End of March for timely sown wheat, 10 April for wheat sown after 5 December | PAU p. 16 |
| Soil adjustment | Advance the first irrigation on light soils, delay it a week on heavy paddy soils | PAU p. 16 |
| Wind | Do not irrigate on windy days, to avoid lodging | PAU p. 16 |
| Variety | PBW 1 Chapati on medium-textured soils: reduce one irrigation to prevent lodging | PAU |
| Temperature ranges for higher productivity | Maximum 15-22 °C vegetative and 21-28 °C grain development. Minimum 4-11 °C and 7-13 °C | PAU p. 1 |

Assumptions in applying the timetable:

- Sowing dates **before 1 October** or **after 15 January** have no published window, so no schedule
  is produced and the app says so. PAU's table begins with "up to November 21"; taking 1 October as
  its start is an assumption (October is the earliest sowing the first-irrigation rule mentions).
- Windows chain from the midpoint of the previous window, and assume earlier irrigations ran on
  time. A real farm's dates will drift, and the app says that beside the windows.
- Windows do not include the rain adjustment.
- The table is for sandy loam or heavier soils. The assessment says lighter soils may need earlier
  irrigation.

### Soil water holding

| Soil | Available water, mm per m | Basis |
|---|---|---|
| Sandy | 50-110 | FAO Table 19 (sand) |
| Loamy sand | 60-120 | FAO Table 19 |
| Sandy loam | 110-150 | FAO Table 19 |
| Loam | 130-180 | FAO Table 19 |
| Silt loam | 130-190 | FAO Table 19 |
| Clay loam | 130-180 | **Assumption.** Table 19 has no clay loam row, so the nearest row, silt clay loam, is used |
| Clay | 120-200 | FAO Table 19 |

These values are explanatory text. Only the soil class affects the tally, not the numbers.

### Crop water use (shown for context, not used in the decision)

| Rule | Value | Basis |
|---|---|---|
| Reference ET0 | Hargreaves: 0.0023 (Tmean + 17.8) (Tmax - Tmin)^0.5 Ra | FAO-56 Eq. 52 |
| Days used | Full forecast days with at least 7 of 8 periods and a range of at least 1 °C | Design heuristic: partial days understate the range |
| Kc initial | 0.7 (winter wheat, non-frozen soils) | FAO Table 12. Choosing this row for Punjab is an inference; FAO does not label it so |
| Kc mid | 1.15 | FAO Table 12 |
| Kc end | 0.4 | FAO Table 12, top of the 0.25-0.4 range |
| Kc development 0.93, late 0.78 | Midpoints of the rising and falling limbs | **Assumption**, not from a table |

Limits stated by FAO: Eq. 52 should be verified regionally, tends to under-predict in strong wind
(u2 above 3 m/s), and over-predicts at high humidity. Table 12 values are for subhumid climates (RHmin
about 45%, u2 about 2 m/s) and are not adjusted here.

## Weather-related pest and disease risk

`intelligence/pest_risk.py` and `crops/wheat.py`.

**This is not a diagnosis.** Weather can show that conditions favour a problem. It cannot show the
problem is in the field. FarmAgent never says a crop has a pest or disease, and never prescribes a
pesticide, product or dose, even though some cited sources do. The server rejects a final answer from
Claude that contains a dosage.

### Classification (design heuristics)

| Classification | Rule |
|---|---|
| Elevated | At least 8 forecast periods (24 hours) fit, or for yellow rust at least 2 forecast days fit |
| Moderate | At least 3 periods (9 hours) fit, or for yellow rust 1 day fits, or current conditions fit with no forecast |
| Low | Fewer fit, or the crop is not at a susceptible stage |
| Uncertain | Required data is missing, or the rule has no verified weather trigger |

The overall label is the highest of the above. If nothing is moderate or elevated and any rule could
not be judged, it is "uncertain" rather than all clear. Aphids do not affect the overall label.

### Rules

| Threat | Sourced conditions | How the engine applies them | Stages | Source |
|---|---|---|---|---|
| Yellow (stripe) rust | Night minimum 7-13 °C with 85-100% night humidity, and day maximum 15-24 °C | Per 24-hour block of the forecast: min and max in range, and peak humidity at least 85%. Forecast humidity is not specifically night humidity, which is an approximation | After emergence | PAU pp. 19-20 |
| Brown (leaf) rust | 20-25 °C with free moisture from rain or dew | Per period: 20-25 °C, and humidity at least 85% or any rain. **85% as a proxy for free moisture is an assumption** | After emergence | NIPHM |
| Powdery mildew | High humidity, not necessarily rain, and 20-21 °C | Per period: 18-23 °C and humidity at least 85%. **The 2 °C tolerance and 85% are assumptions** | After emergence | NIPHM |
| Karnal bunt | 8-20 °C with high humidity, light rain and cloud at ear emergence and flowering | Per period: 8-20 °C, humidity at least 80%, and rain. **80% is an assumption**. Cloud is not checked | Ear emergence and flowering | EPPO; Bala & Kaur |
| Foliar blight (spot blotch) | 18-32 °C, humidity near 95%, more than 12-18 h of leaf wetness | Per period: 18-32 °C and humidity at least 90%. **90% is an assumption**. Leaf wetness is not observed | After emergence | Chowdhury et al. |
| Aphids | PAU threshold: 5 aphids per ear head, counted on 10 random ear heads in each of 4 quarters of one acre | Never judged from weather. Always "uncertain", with scouting advice | Ear-head and grain filling | PAU p. 18 |
| Terminal heat stress | Above 30 °C after anthesis and during grain development | Per period: at least 30 °C | Flowering, grain filling | Singh et al.; PAU |
| Early-season heat stress | PAU: poor tillering and early heading above 15-22 °C in the vegetative stage | Per period: at least 30 °C. **The source gives a range, not 30 °C. Flagging only from 30 °C is a design heuristic**, chosen so ordinary warm days are not flagged | Before anthesis | PAU p. 1 |

Humidity thresholds in summary: yellow rust's 85% is sourced. All others are assumptions.

### Threats not modelled

| Threat | Why |
|---|---|
| Black (stem) rust | NIPHM gives moisture and above 20 °C. An ICAR paper says it matters more in central and peninsular states. Not covered in the PAU wheat chapter, so low priority for Punjab, and left out |
| Frost | No temperature threshold was found |
| Termites, armyworm and other pests | No verified weather trigger was found |

### Regional notes shown to the farmer

- Yellow rust: PAU reports it appears first in Punjab's sub-mountainous areas, and that rain with wind
  in February-March can worsen its spread. Monitor from the second week of December.
- Karnal bunt: PAU authors link high-incidence years to February-March rain and humidity at flowering,
  and note it is difficult to predict.
- Spot blotch: reported as mainly a problem of the warmer North Eastern Plains Zone.

## Confidence

`intelligence/confidence.py`. A statement about inputs, never a percentage.

| Level | Condition |
|---|---|
| Insufficient | No verified weather |
| Limited | Soil moisture, growth stage or forecast rain amount is missing, or the weather is out of date |
| Moderate | Soil type, recent rain, sowing date or irrigation method is missing |
| Good | All of the above were provided |

Choosing soil moisture, stage and rain amount as the critical inputs is a design decision.

## Where sources disagree

| Topic | Disagreement | What FarmAgent does |
|---|---|---|
| Second irrigation | PAU's nitrogen advice says about 50-55 days after sowing. PAU's timetable works out to about 56-63 days for October-sown wheat, about 63-70 days for wheat sown from November to 20 December, and about 56 days for wheat sown after that | Uses the timetable, which is the irrigation-specific table |
| First irrigation | TNAU puts crown root initiation at 15-20 days after sowing. PAU's first irrigation is about 21-28 days | Uses PAU, the Punjab authority. TNAU only supplies the names of critical stages |
| Yellow rust and rain | The PAU Package says rain and high humidity favour it. Anand et al. 2026 found rainfall and humidity negatively correlated with severity at Ludhiana and Gurdaspur, within seasons where temperature rises over time, while their narrative still says low temperature and high humidity favour it | Follows the PAU Package |

## Reviewing these rules

Before relying on FarmAgent in the field, an agronomist should review, in this order:

1. The rain thresholds and rule 4, which together decide when to postpone.
2. The 8 m/s wind threshold, which has no source.
3. The risk period counts and the assumed humidity thresholds.
4. Whether wheat at 30 °C before anthesis is the right point to flag heat.
5. Whether farms outside Punjab should be warned or refused.
