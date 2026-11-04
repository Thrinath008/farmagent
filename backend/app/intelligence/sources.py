"""Every agricultural source the engine cites. Each URL was loaded and read during development.

docs/agricultural-assumptions.md maps every rule to these ids, and says which documents were read
in full and which were read through a summarizing fetch.
"""

from app.intelligence.types import SourceRef

_ALL = [
    SourceRef(
        id="pau_pop_rabi_2025",
        title="Package of Practices for Crops of Punjab, Rabi 2025-26 (wheat chapter)",
        publisher="Punjab Agricultural University, Ludhiana",
        url="https://www.pau.edu/content/ccil/pf/pp_rabi.pdf",
    ),
    SourceRef(
        id="fao56_ch6",
        title="FAO Irrigation and Drainage Paper 56, Chapter 6: single crop coefficient (Table 12)",
        publisher="Food and Agriculture Organization of the United Nations",
        url="https://www.fao.org/3/x0490e/x0490e0b.htm",
    ),
    SourceRef(
        id="fao56_ch7",
        title="FAO Irrigation and Drainage Paper 56, Chapter 7: soil water characteristics (Table 19)",
        publisher="Food and Agriculture Organization of the United Nations",
        url="https://www.fao.org/3/x0490e/x0490e0c.htm",
    ),
    SourceRef(
        id="fao56_ch8",
        title="FAO Irrigation and Drainage Paper 56, Chapter 8: rooting depth and depletion (Table 22)",
        publisher="Food and Agriculture Organization of the United Nations",
        url="https://www.fao.org/3/x0490e/x0490e0e.htm",
    ),
    SourceRef(
        id="fao56_hargreaves",
        title="FAO Irrigation and Drainage Paper 56: Hargreaves reference evapotranspiration (Eq. 52)",
        publisher="Food and Agriculture Organization of the United Nations",
        url="https://www.fao.org/3/x0490e/x0490e07.htm",
    ),
    SourceRef(
        id="niphm_vikaspedia",
        title="IPM Strategies for Wheat: Wheat Diseases and Symptoms (NIPHM text on Vikaspedia)",
        publisher="NIPHM, Directorate of Plant Protection, Quarantine & Storage, via Vikaspedia",
        url="https://vikaspedia.in/agriculture/crop-production/integrated-pest-managment/ipm-for-cerels/ipm-strategies-for-wheat/wheat-diseases-and-symptoms",
    ),
    SourceRef(
        id="eppo_karnal_bunt",
        title="EPPO Global Database datasheet: Tilletia indica",
        publisher="European and Mediterranean Plant Protection Organization",
        url="https://gd.eppo.int/taxon/NEOVIN/datasheet",
    ),
    SourceRef(
        id="bala_2020_karnal_bunt",
        title="Karnal bunt: a threat to export of Indian wheat. Indian Farming 70(09): 32-34 (2020)",
        publisher="Indian Council of Agricultural Research",
        url="https://epubs.icar.org.in/index.php/IndFarm/article/download/111437/43673/289726",
    ),
    SourceRef(
        id="chowdhury_2013_spot_blotch",
        title="Spot blotch disease of wheat: a new thrust area. J. Wheat Res. 5(2): 1-11 (2013)",
        publisher="Society for Advancement of Wheat Research",
        url="https://epubs.icar.org.in/index.php/JWR/article/download/36730/16366/84384",
    ),
    SourceRef(
        id="singh_2023_terminal_heat",
        title="Terminal heat stress in wheat and its mitigation options. Indian Farming 73(05): 15-18 (2023)",
        publisher="Indian Council of Agricultural Research",
        url="https://epubs.icar.org.in/index.php/IndFarm/article/download/133793/50127/361734",
    ),
    SourceRef(
        id="tnau_irrigation",
        title="Irrigation management: wheat (Tamil Nadu guidance, used only to name critical stages)",
        publisher="TNAU Agritech Portal, Tamil Nadu Agricultural University",
        url="https://agritech.tnau.ac.in/agriculture/agri_irrigationmgt_wheat.html",
    ),
]

SOURCES: dict[str, SourceRef] = {source.id: source for source in _ALL}


def resolve(source_ids: tuple[str, ...] | list[str]) -> list[SourceRef]:
    seen: list[SourceRef] = []
    for source_id in source_ids:
        source = SOURCES[source_id]
        if source not in seen:
            seen.append(source)
    return seen
