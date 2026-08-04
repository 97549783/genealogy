from __future__ import annotations

from typing import Dict, List, Tuple

TAB_SPECS: List[Tuple[str, str]] = [
    ("lineages", "Построение деревьев"),
    ("dissertation_search", "Поиск диссертаций"),
    ("dissertation_characteristics", "Характеристики диссертаций"),
    ("school_search", "Поиск научных школ"),
    ("intersection", "Взаимосвязи научных школ"),
    ("school_analysis", "Анализ научной школы"),
    ("school_comparison", "Сравнение научных школ"),
    ("articles_comparison", "Анализ статей (демо)"),
    ("source_schools", "Школы по источникам (демо)"),
]
TAB_ID_TO_LABEL: Dict[str, str] = dict(TAB_SPECS)
TAB_LABEL_TO_ID: Dict[str, str] = {label: tab_id for tab_id, label in TAB_SPECS}
DEFAULT_TAB_ID = "lineages"
