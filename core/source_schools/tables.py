"""Динамические таблицы персон, оснований и классификаций школ формата v2.1."""
from __future__ import annotations

import json
from typing import Any, Collection, Mapping

import pandas as pd

from .bibliography import build_source_number_index
from .dimensions import build_dimension_memberships, build_person_dimension_labels
from .model import (
    dimension_definitions, display_persons, field_definitions, format_locator,
    format_value, included_persons, information_text, membership_index,
    person_qualifications, person_source_ids, primary_category_index,
)

RELATION_LABELS = {"представитель": "Представитель", "связанное_лицо": "Связанное лицо", "не_установлено": "Не установлено"}
SYSTEM_COLUMNS = {"system:name": "Имя", "system:primary_category": "Основная категория",
                  "system:sources": "Число источников", "system:genealogy": "Научное руководство",
                  "system:membership": "Отношение к школе"}


def resolve_person_names(person_ids: Collection[str], person_index: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return [str(person_index[p].get("имя", p)) for p in person_ids if p in person_index]


def table_column_labels(document: Mapping[str, Any]) -> dict[str, str]:
    return {"id": "ID", "Имя": "Имя", "Отношение к школе": "Отношение к школе",
            "Основная категория": "Основная категория", "Число источников": "Число источников",
            "Идентификаторы источников": "Идентификаторы источников", "Уверенность": "Уверенность (прежняя оценка)",
            "Разночтения и ограничения": "Разночтения и ограничения",
            **{f"field:{k}": v["название"] for k, v in field_definitions(document).items()},
            **{f"facet:{k}": v["название"] for k, v in dimension_definitions(document, include_primary=False).items()}}


def configured_table_columns(document: Mapping[str, Any]) -> list[str]:
    """Разрешает ключи столбцов схемы, пропуская отсутствующие генеалогические поля."""
    available = set(table_column_labels(document))
    return list(dict.fromkeys(column for key in document["отображение"]["колонки_таблицы_по_умолчанию"]
                              if (column := SYSTEM_COLUMNS.get(key, key)) in available
                              and (column != "Основная категория" or document["классификации"]["основное_деление"])))


def _people_dataframe(document: Mapping[str, Any], people: Collection[Mapping[str, Any]]) -> pd.DataFrame:
    members = membership_index(document)
    primary = document["классификации"]["основное_деление"]
    primary_labels = primary_category_index(document)
    facets = dimension_definitions(document, include_primary=False)
    dimension_labels = build_person_dimension_labels(document)
    fields = field_definitions(document)
    columns = ["id", "Имя", "Отношение к школе"]
    if primary:
        columns.append("Основная категория")
    columns += [f"field:{code}" for code in fields] + [f"facet:{code}" for code in facets]
    columns += ["Число источников", "Идентификаторы источников", "Уверенность", "Разночтения и ограничения"]
    rows = []
    for person in people:
        pid = person["id"]
        sources = person_source_ids(document, pid)
        confidence = person.get("оценка_уверенности") or {}
        row = {"id": pid, "Имя": person["имя"],
               "Отношение к школе": RELATION_LABELS.get(members.get(pid, {}).get("отношение_к_школе"), "Не установлено"),
               "Число источников": len(sources), "Идентификаторы источников": "; ".join(sources),
               "Уверенность": confidence.get("значение", float("nan")),
               "Разночтения и ограничения": person_qualifications(document, pid)}
        if primary:
            row["Основная категория"] = primary_labels.get(pid, "Не классифицировано")
        row.update({f"field:{code}": information_text(document, pid, code) for code in fields})
        row.update({f"facet:{code}": "; ".join(dimension_labels.get(pid, {}).get(code, [])) for code in facets})
        rows.append(row)
    result = pd.DataFrame(rows, columns=columns)
    result.attrs["column_labels"] = table_column_labels(document)
    result.attrs["facet_memberships"] = build_dimension_memberships(document)
    result.attrs["primary_labels"] = {c["id"]: c["название"] for c in primary["категории"]} if primary else {}
    return result


def build_people_dataframe(document: Mapping[str, Any], *, display_only: bool = True) -> pd.DataFrame:
    """Одна строка на включённую персону с произвольным набором полей и гибких измерений."""
    return _people_dataframe(document, display_persons(document) if display_only else included_persons(document))


def build_candidates_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    candidates = {m["персона"] for m in document["состав"] if m["решение"] == "кандидат"}
    return _people_dataframe(document, [p for p in document["объекты"]["персоны"] if p["id"] in candidates])


def filter_people_dataframe(dataframe: pd.DataFrame, *, query: str = "",
                            person_ids: Collection[str] | None = None,
                            facet_selections: Mapping[str, Collection[str]] | None = None,
                            primary_categories: Collection[str] = (), source_ids: Collection[str] = (),
                            mode: str = "intersection") -> pd.DataFrame:
    """ИЛИ внутри измерения; И/ИЛИ между измерениями. Текст и источники добавляют условие И."""
    if mode not in {"intersection", "union"}:
        raise ValueError(f"Неизвестная логика фильтров: {mode}")
    if dataframe.empty:
        return dataframe.copy()
    mask = pd.Series(True, index=dataframe.index)
    if person_ids is not None:
        mask &= dataframe["id"].isin(set(person_ids))
    if query.strip():
        searchable = dataframe.drop(columns=["Уверенность"], errors="ignore").fillna("").astype(str).agg(" ".join, axis=1)
        mask &= searchable.str.contains(query.strip(), case=False, regex=False)
    active_sets = []
    memberships = dataframe.attrs.get("facet_memberships", {})
    for dimension, selections in (facet_selections or {}).items():
        if selections:
            active_sets.append(set().union(*(set(memberships.get(dimension, {}).get(value, ())) for value in selections)))
    if active_sets:
        selected = set.union(*active_sets) if mode == "union" else set.intersection(*active_sets)
        mask &= dataframe["id"].isin(selected)
    if primary_categories:
        labels = dataframe.attrs.get("primary_labels", {})
        selected_labels = {labels.get(value, value) for value in primary_categories}
        if "Основная категория" not in dataframe:
            mask &= False
        else:
            mask &= dataframe["Основная категория"].isin(selected_labels)
    if source_ids:
        selected = set(source_ids)
        mask &= dataframe["Идентификаторы источников"].fillna("").str.split("; ").map(lambda values: bool(selected.intersection(values)))
    return dataframe.loc[mask].copy()


def build_sources_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    numbers = build_source_number_index(document)
    return pd.DataFrame([{"id": source["id"], "№": numbers[source["id"]],
                          "Источник": source["библиографическое_описание"], "Название": source["название"],
                          "Год": source["год"], "Жанр": source["жанр"], "Языки": "; ".join(source["языки"]),
                          "DOI": source.get("doi") or "", "Проверка": source["проверка"]["статус"],
                          "Роль в описании": source.get("роль_в_описании") or "", "Примечание": source.get("примечание") or ""}
                         for source in document["источники"]],
                        columns=["id", "№", "Источник", "Название", "Год", "Жанр", "Языки", "DOI", "Проверка", "Роль в описании", "Примечание"])


def build_evidence_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    sources = {s["id"]: s for s in document["источники"]}
    rows = []
    for evidence in document["основания"]:
        fragment = evidence.get("фрагмент") or {}
        rows.append({"id": evidence["id"], "ID источника": evidence["источник"],
                     "Источник": sources[evidence["источник"]]["библиографическое_описание"],
                     "ID файла": evidence.get("файл") or "", "Локатор": format_locator(evidence.get("локатор")),
                     "Вид фрагмента": fragment.get("вид", ""), "Содержание свидетельства": fragment.get("текст", ""),
                     "Вид свидетельства": evidence["тип_свидетельства"], "Явность": evidence["явность"],
                     "Проверка": evidence["проверка"]["статус"], "Ограничения": "; ".join(evidence.get("ограничения", []))})
    return pd.DataFrame(rows, columns=["id", "ID источника", "Источник", "ID файла", "Локатор", "Вид фрагмента", "Содержание свидетельства", "Вид свидетельства", "Явность", "Проверка", "Ограничения"])


def build_classification_dataframes(document: Mapping[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Все решения об отнесении и их адресные основания, включая неактивные гипотезы."""
    people = {p["id"]: p["имя"] for p in document["объекты"]["персоны"]}
    definitions = dimension_definitions(document)
    values = {(key, value["id"]): value["название"] for key, d in definitions.items()
              for value in d.get("значения", d.get("категории", []))}
    bases = {e["id"]: e for e in document["основания"]}
    assertions = {r["id"]: r for key in ("сведения", "связи") for r in document[key]}
    rows, attributions = [], []
    for assignment in document["классификационные_назначения"]:
        row = {"ID назначения": assignment["id"], "ID персоны": assignment["персона"], "Имя": people[assignment["персона"]],
               "ID измерения": assignment["измерение"], "Измерение": definitions[assignment["измерение"]]["название"],
               "ID значения": assignment["значение"], "Значение": values[(assignment["измерение"], assignment["значение"])],
               "Решение": assignment["решение"], "Характер": assignment["характер"], "Проверка": assignment["проверка"]["статус"],
               "Временной контекст": "; ".join(format_value({"вид": "интервал", "значение": i}) for i in assignment["интервалы"]),
               "Примечание": assignment.get("примечание") or ""}
        rows.append(row)
        ids, visited = set(), set()
        def collect(record: Mapping[str, Any]) -> None:
            ids.update(record.get("основания", []))
            for identifier in record.get("опирается_на", []):
                if identifier not in visited and identifier in assertions:
                    visited.add(identifier)
                    collect(assertions[identifier])
        collect(assignment)
        for eid in (e["id"] for e in document["основания"] if e["id"] in ids):
            e = bases[eid]
            attributions.append({**row, "ID основания": eid, "ID источника": e["источник"],
                                 "Локатор": format_locator(e.get("локатор")),
                                 "Вид фрагмента": (e.get("фрагмент") or {}).get("вид", ""),
                                 "Фрагмент": (e.get("фрагмент") or {}).get("текст", "")})
    columns = ["ID назначения", "ID персоны", "Имя", "ID измерения", "Измерение", "ID значения", "Значение", "Решение", "Характер", "Проверка", "Временной контекст", "Примечание"]
    return (pd.DataFrame(rows, columns=columns), pd.DataFrame(attributions, columns=columns + ["ID основания", "ID источника", "Локатор", "Вид фрагмента", "Фрагмент"]))


def build_information_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    definitions = field_definitions(document)
    return pd.DataFrame([{"id": r["id"], "Субъект": r["субъект"], "Поле": r["поле"],
                          "Название поля": definitions[r["поле"]]["название"], "Значение": format_value(r["значение"]),
                          "Роль значения": r["роль_значения"], "Характер": r["характер"], "Решение": r["решение"],
                          "Проверка": r["проверка"]["статус"], "Основания": "; ".join(r["основания"])}
                         for r in document["сведения"]], columns=["id", "Субъект", "Поле", "Название поля", "Значение", "Роль значения", "Характер", "Решение", "Проверка", "Основания"])


def build_records_dataframe(records: Collection[Mapping[str, Any]]) -> pd.DataFrame:
    """Преобразует записи реестра в таблицу с сохранением вложенного содержимого."""
    return pd.DataFrame([{key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                          for key, value in record.items()} for record in records])
