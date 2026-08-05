"""Табличные преобразования для демо школ по источникам."""
from __future__ import annotations

from typing import Any, Collection, Mapping

import pandas as pd

from .data import normalize_source_school_document
from .bibliography import build_source_number_index
from .presentation import as_display_text, as_list, get_first_field


def _group_labels(document: Mapping[str, Any]) -> dict[str, str]:
    structure = document.get("школа", {}).get("внутренняя_структура", {}) if isinstance(document.get("школа", {}), Mapping) else {}
    return {str(group.get("id")): str(group.get("название", group.get("id"))) for group in structure.get("исследовательские_группы", []) if isinstance(group, Mapping)}


def _join_groups(value: Any, labels: Mapping[str, str]) -> str:
    return "; ".join(as_display_text(labels.get(str(item), item)) for item in as_list(value) if as_display_text(labels.get(str(item), item)))


def _join_values(value: Any) -> str:
    return "; ".join(as_display_text(item) for item in as_list(value) if as_display_text(item))


def resolve_person_names(
    person_ids: Collection[str],
    person_index: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Заменяет идентификаторы персон отображаемыми именами."""
    return [get_first_field(person_index[person_id], "полное_имя", "имя", default=person_id) for person_id in person_ids if person_id in person_index]


def build_people_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    """Формирует таблицу представителей школы."""
    normalized = normalize_source_school_document(document)
    group_labels = _group_labels(normalized)
    rows: list[dict[str, Any]] = []
    for person in normalized["школа"]["персоны"]:
        source_ids = [
            attribution.get("идентификатор_источника")
            for attribution in person.get("источниковые_атрибуции", [])
            if isinstance(attribution, Mapping) and attribution.get("идентификатор_источника")
        ]
        rows.append(
            {
                "ID": person.get("id"),
                "Представитель": get_first_field(person, "полное_имя", "имя"),
                "Категория": person.get("категория_включения", ""),
                "Роли": _join_values(person.get("роль_в_школе", [])),
                "Связь с Выготским": person.get("статус_связи_с_выготским", ""),
                "Период взаимодействия": person.get("период_взаимодействия", ""),
                "Группы и контексты": _join_groups(person.get("группы_и_контексты", []), group_labels),
                "Основной вклад": get_first_field(person, "основной_вклад", "основные_идеи_или_вклад"),
                "Уверенность": float(person.get("уверенность", 0) or 0),
                "Число источников": len(set(source_ids)),
                "Идентификаторы источников": "; ".join(dict.fromkeys(source_ids)),
            }
        )
    return pd.DataFrame(rows)


def _contains_any(series: pd.Series, values: Collection[str]) -> pd.Series:
    selected = set(values)
    return series.fillna("").str.split("; ").apply(lambda items: bool(set(items) & selected))


def filter_people_dataframe(
    dataframe: pd.DataFrame,
    *,
    query: str = "",
    categories: Collection[str] = (),
    roles: Collection[str] = (),
    groups: Collection[str] = (),
    source_ids: Collection[str] = (),
    minimum_confidence: float = 0.0,
) -> pd.DataFrame:
    """Фильтрует таблицу представителей без изменения исходного DataFrame."""
    filtered = dataframe.copy()
    mask = filtered["Уверенность"] >= minimum_confidence
    if query.strip():
        query_lower = query.strip().lower()
        search_columns = [
            "Представитель",
            "Категория",
            "Роли",
            "Связь с Выготским",
            "Группы и контексты",
            "Основной вклад",
        ]
        text = filtered[search_columns].fillna("").agg(" ".join, axis=1).str.lower()
        mask &= text.str.contains(query_lower, regex=False)
    if categories:
        mask &= filtered["Категория"].isin(categories)
    if roles:
        mask &= _contains_any(filtered["Роли"], roles)
    if groups:
        mask &= _contains_any(filtered["Группы и контексты"], groups)
    if source_ids:
        mask &= _contains_any(filtered["Идентификаторы источников"], source_ids)
    return filtered.loc[mask].copy()


def build_sources_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    """Формирует таблицу библиографических источников."""
    normalized = normalize_source_school_document(document)
    numbers = build_source_number_index(normalized)
    return pd.DataFrame(
        [
            {
                "ID": source.get("id"),
                "№": numbers.get(str(source.get("id")), ""),
                "Источник": source.get("краткое_название") or source.get("библиографическое_описание", ""),
                "Год": source.get("год", ""),
                "Тип": source.get("тип", ""),
                "DOI": source.get("doi", ""),
                "Роль в описании": source.get("роль_в_описании", ""),
                "Примечание": source.get("примечание", ""),
            }
            for source in normalized["школа"]["источники"]
        ]
    )


def build_evidence_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    """Формирует таблицу подтверждений с названиями источников."""
    normalized = normalize_source_school_document(document)
    numbers = build_source_number_index(normalized)
    labels = {
        source["id"]: f"Источник [{numbers.get(str(source.get('id')), '?')}]"
        for source in normalized["школа"]["источники"]
    }
    return pd.DataFrame(
        [
            {
                "ID": evidence.get("id"),
                "Источник": labels.get(evidence.get("идентификатор_источника"), evidence.get("идентификатор_источника")),
                "Тип утверждения": evidence.get("тип_утверждения", ""),
                "Содержание свидетельства": evidence.get("содержание_свидетельства", ""),
                "Локатор": evidence.get("локатор", ""),
                "Статус": "Явное утверждение" if evidence.get("явное_утверждение") else "Интерпретация",
                "Уверенность": float(evidence.get("уверенность", 0) or 0),
            }
            for evidence in normalized["школа"]["подтверждения"]
        ]
    )
