"""Построение структурного дерева школы и наложенных классификаций."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Mapping

import networkx as nx
import pandas as pd

from .data import SourceSchoolDataError
from .presentation import as_list, get_first_field

_CATEGORY_LABELS = {
    "ядро": "Ядро",
    "прямой_ученик": "Прямые ученики",
    "прямой_сотрудник": "Прямые сотрудники",
    "связанная_группа": "Связанные группы",
    "периферийный_участник": "Периферийные участники",
}

_HIGHLIGHT_COLOR = "#ff8f00"
_DIMMED_COLOR = "#cfd8dc"


@dataclass(frozen=True)
class SupplementaryDimensionValue:
    """Одно выбираемое значение дополнительного измерения графа."""

    id: str
    label: str
    person_ids: tuple[str, ...]


@dataclass(frozen=True)
class SourceSchoolTree:
    """Контейнер графа структурного дерева школы."""

    graph: nx.DiGraph
    root_id: str
    root_label: str
    basis: str


def _name(person: Mapping[str, Any]) -> str:
    return str(get_first_field(person, "полное_имя", "имя")).strip()


def _find_root(school: Mapping[str, Any], persons: list[Mapping[str, Any]]) -> tuple[str, str]:
    by_id = {str(person.get("id")): person for person in persons}
    founder_ids = as_list(get_first_field(school.get("представители", {}), "основатели", default=[]))
    founders = [by_id[item] for item in founder_ids if item in by_id]
    if len(founders) != 1:
        founders = [person for person in persons if "основатель" in as_list(person.get("роль_в_школе"))]
    if len(founders) != 1:
        founders = [person for person in persons if person.get("категория_включения") == "ядро"]
    if len(founders) == 1:
        person = founders[0]
        return f"person:{person.get('id')}", _name(person)
    return f"school:{school.get('идентификатор_школы', 'school')}", str(school.get("каноническое_название", "Школа"))


def _primary_relation_categories(school: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    model = school.get("классификация_связи_с_выготским", {})
    if not isinstance(model, Mapping):
        return []
    return [item for item in model.get("категории", []) if isinstance(item, Mapping)]


def build_person_primary_relation_index(document: Mapping[str, Any]) -> dict[str, str]:
    """Возвращает пользовательскую подпись единственного типа связи для каждой персоны."""
    school = document.get("школа", {})
    result: dict[str, str] = {}
    for category in _primary_relation_categories(school):
        code = str(category.get("код", "")).strip()
        name = str(category.get("название", code)).strip()
        label = name or code
        for person_id in as_list(get_first_field(category, "участники", "представители")):
            result[str(person_id)] = label
    return result


def build_supplementary_dimension_catalog(
    document: Mapping[str, Any],
) -> dict[str, tuple[SupplementaryDimensionValue, ...]]:
    """Формирует группы, периоды и направления для наложения на основной граф."""
    school = document.get("школа", {})
    structure = school.get("внутренняя_структура", {})

    groups = tuple(
        SupplementaryDimensionValue(
            id=f"group:{group.get('id', index)}",
            label=str(group.get("название") or group.get("id") or f"Группа {index + 1}"),
            person_ids=tuple(str(item) for item in as_list(group.get("участники"))),
        )
        for index, group in enumerate(structure.get("исследовательские_группы", []))
        if isinstance(group, Mapping)
    )
    periods = tuple(
        SupplementaryDimensionValue(
            id=f"period:{index}",
            label=" — ".join(
                part
                for part in (
                    str(get_first_field(period, "временной_диапазон", "период", default="")).strip(),
                    str(get_first_field(period, "название_периода", "название", default=f"Период {index + 1}")).strip(),
                )
                if part
            ),
            person_ids=tuple(
                str(item)
                for item in as_list(get_first_field(period, "основные_представители", "персоны"))
            ),
        )
        for index, period in enumerate(school.get("хронология", {}).get("периоды_развития", []))
        if isinstance(period, Mapping)
    )
    directions = tuple(
        SupplementaryDimensionValue(
            id=f"direction:{index}",
            label=str(
                get_first_field(
                    direction,
                    "название_направления",
                    "название",
                    default=f"Направление {index + 1}",
                )
            ),
            person_ids=tuple(
                str(item)
                for item in as_list(get_first_field(direction, "представители", "участники"))
            ),
        )
        for index, direction in enumerate(structure.get("направления", []))
        if isinstance(direction, Mapping)
    )
    return {
        "historical_group": groups,
        "period": periods,
        "research_direction": directions,
    }


def combine_supplementary_selections(
    catalog: Mapping[str, Collection[SupplementaryDimensionValue]],
    selections: Mapping[str, Collection[str]],
    *,
    mode: str = "intersection",
) -> set[str] | None:
    """Объединяет значения внутри измерения и компонует активные измерения."""
    active_sets: list[set[str]] = []
    for dimension_id, selected_value_ids in selections.items():
        selected_ids = {str(item) for item in selected_value_ids}
        if not selected_ids:
            continue
        value_index = {value.id: value for value in catalog.get(dimension_id, ())}
        within_dimension: set[str] = set()
        for value_id in selected_ids:
            value = value_index.get(value_id)
            if value:
                within_dimension.update(value.person_ids)
        active_sets.append(within_dimension)
    if not active_sets:
        return None
    if mode == "union":
        return set().union(*active_sets)
    if mode == "intersection":
        return set.intersection(*active_sets)
    raise ValueError(f"Неизвестный режим композиции измерений: {mode}.")


def _add_person_node(
    graph: nx.DiGraph,
    parent_id: str,
    person_id: str,
    person: Mapping[str, Any],
    highlighted_person_ids: set[str] | None,
    hidden_person_ids: set[str] | None,
) -> None:
    attributes: dict[str, Any] = {
        "label": _name(person),
        "kind": "person",
        "person_id": person_id,
    }
    if highlighted_person_ids is not None:
        attributes["highlighted"] = person_id in highlighted_person_ids
        attributes["color"] = _HIGHLIGHT_COLOR if attributes["highlighted"] else _DIMMED_COLOR
    if hidden_person_ids is not None:
        attributes["hidden"] = person_id in hidden_person_ids
    node_id = f"person:{person_id}"
    graph.add_node(node_id, **attributes)
    graph.add_edge(parent_id, node_id)


def build_source_school_overview_tree(
    document: Mapping[str, Any],
    *,
    highlighted_person_ids: Collection[str] | None = None,
    hidden_person_ids: Collection[str] | None = None,
) -> SourceSchoolTree:
    """Строит дерево обзорной структуры школы."""
    school = document["школа"]
    persons = [person for person in school.get("персоны", []) if isinstance(person, Mapping)]
    by_id = {str(person.get("id")): person for person in persons}
    root_id, root_label = _find_root(school, persons)
    selected = None if highlighted_person_ids is None else {str(item) for item in highlighted_person_ids}
    hidden = None if hidden_person_ids is None else {str(item) for item in hidden_person_ids}
    root_person_id = root_id.removeprefix("person:") if root_id.startswith("person:") else None
    root_color = _HIGHLIGHT_COLOR if selected is not None and root_person_id in selected else "#37474f"
    graph = nx.DiGraph()
    graph.add_node(root_id, label=root_label, kind="root", person_id=root_person_id, color=root_color)
    used: set[str] = {root_id.removeprefix("person:")} if root_id.startswith("person:") else set()
    structure = school.get("внутренняя_структура", {})
    relation_categories = _primary_relation_categories(school)
    generations = [item for item in structure.get("поколения", []) if isinstance(item, Mapping)]
    if relation_categories:
        for category in relation_categories:
            code = str(category.get("код", "")).strip()
            label = str(category.get("название", code)).strip()
            ids = [
                str(item)
                for item in as_list(get_first_field(category, "участники", "представители"))
                if str(item) not in used
            ]
            if not ids:
                continue
            category_id = f"relation:{code or len(graph)}"
            graph.add_node(
                category_id,
                label=label,
                kind="relation_category",
                relation_code=code,
            )
            graph.add_edge(root_id, category_id)
            for person_id in ids:
                if person_id in used:
                    raise SourceSchoolDataError(f"Персона {person_id} включена в дерево несколько раз.")
                person = by_id.get(person_id)
                if person:
                    _add_person_node(graph, category_id, person_id, person, selected, hidden)
                    used.add(person_id)
        basis = "классификация_связи_с_выготским"
    elif generations:
        for generation in generations:
            ids = [str(item) for item in as_list(get_first_field(generation, "представители", "участники"))]
            ids = [item for item in ids if item not in used]
            if not ids:
                continue
            number = generation.get("номер", generation.get("поколение", len(graph)))
            generation_id = f"generation:{number}:{len(graph)}"
            graph.add_node(generation_id, label=str(generation.get("название") or f"Поколение {number}"), kind="generation")
            graph.add_edge(root_id, generation_id)
            for person_id in ids:
                if person_id in used:
                    raise SourceSchoolDataError(f"Персона {person_id} включена в дерево несколько раз.")
                person = by_id.get(person_id)
                if person:
                    _add_person_node(graph, generation_id, person_id, person, selected, hidden)
                    used.add(person_id)
        basis = "поколения"
    else:
        for category, label in _CATEGORY_LABELS.items():
            ids = [str(person.get("id")) for person in persons if person.get("категория_включения") == category and str(person.get("id")) not in used]
            if not ids:
                continue
            category_id = f"category:{category}"
            graph.add_node(category_id, label=label, kind="category")
            graph.add_edge(root_id, category_id)
            for person_id in ids:
                person = by_id[person_id]
                _add_person_node(graph, category_id, person_id, person, selected, hidden)
                used.add(person_id)
        basis = "категории"
    other = [person for person in persons if str(person.get("id")) not in used]
    if other:
        other_id = "category:other"
        graph.add_node(other_id, label="Другие представители", kind="category")
        graph.add_edge(root_id, other_id)
        for person in other:
            person_id = str(person.get("id"))
            _add_person_node(graph, other_id, person_id, person, selected, hidden)
    return SourceSchoolTree(graph=graph, root_id=root_id, root_label=root_label, basis=basis)


def build_source_school_tree_edges_dataframe(tree: SourceSchoolTree) -> pd.DataFrame:
    """Формирует таблицу рёбер дерева для экспорта."""
    return pd.DataFrame([{"Источник": tree.graph.nodes[a].get("label", a), "Цель": tree.graph.nodes[b].get("label", b)} for a, b in tree.graph.edges])
