"""Структурное представление универсального JSON школы v2.1."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Mapping

import networkx as nx
import pandas as pd

from .data import SourceSchoolDataError
from .model import MEMBERSHIP_GROUP_LABELS, membership_index, uses_membership_division
from .presentation import get_first_field

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


def build_supplementary_dimension_catalog(
    document: Mapping[str, Any], *, include_unverified: bool = False,
) -> dict[str, tuple[SupplementaryDimensionValue, ...]]:
    """Возвращает все гибкие измерения; гипотезы не входят в активные фильтры.

    Параметр ``include_unverified`` сохранён для совместимости вызовов. Принятые
    редакторские интерпретации активны независимо от состояния сверки.
    """
    return _universal_dimension_catalog(document)


def build_person_primary_relation_index(document: Mapping[str, Any]) -> dict[str, str]:
    """Подписи принятых взаимоисключающих категорий с учётом области применения."""
    primary = document.get("классификации", {}).get("основное_деление")
    if not isinstance(primary, Mapping):
        return {}
    labels = {str(c["id"]): str(c.get("название", c["id"])) for c in primary.get("категории", [])}
    members = {str(m["персона"]): m for m in document.get("состав", []) if m.get("решение") == "включено"}
    pool = {str(p["id"]) for p in _included_people(document)}
    scope = primary.get("область_применения", ["представитель", "связанное_лицо", "не_установлено"])
    excluded = set(primary.get("исключённые_персоны", []))
    result = {}
    for assignment in document.get("классификационные_назначения", []):
        pid = str(assignment.get("персона"))
        if assignment.get("измерение") != primary.get("id") or assignment.get("решение") != "принято" or pid not in pool or pid in excluded:
            continue
        if members[pid].get("отношение_к_школе") not in scope:
            continue
        value = str(assignment.get("значение"))
        if value not in labels or pid in result:
            raise SourceSchoolDataError("Несогласованное основное деление школы.")
        result[pid] = labels[value]
    return result


def build_source_school_tree_edges_dataframe(tree: SourceSchoolTree) -> pd.DataFrame:
    """Возвращает стабильные структурные рёбра для отображения и экспорта."""
    return pd.DataFrame([{"Источник": tree.graph.nodes[a].get("label", a), "Цель": tree.graph.nodes[b].get("label", b)}
                         for a, b in tree.graph.edges], columns=["Источник", "Цель"])


def _included_people(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Единый реестр состава задаёт отображаемых персон, включая связанных лиц."""
    allowed = document.get("отображение", {}).get(
        "показывать_отношения_к_школе", ["представитель", "связанное_лицо", "не_установлено"]
    )
    included = {
        str(item["персона"])
        for item in document.get("состав", [])
        if item.get("решение") == "включено" and item.get("отношение_к_школе") in allowed
    }
    return [p for p in document.get("объекты", {}).get("персоны", []) if str(p.get("id")) in included]


def _ordered(items):
    return sorted(enumerate(items), key=lambda pair: (pair[1].get("порядок", pair[0] + 1) or pair[0] + 1, pair[0]))


def _universal_dimension_catalog(document, *, include_unverified=False):
    people = _included_people(document)
    included_ids = {str(p["id"]) for p in people}
    assignments = document.get("классификационные_назначения", [])
    result = {}
    for _, facet in _ordered(document.get("классификации", {}).get("гибкие_измерения", [])):
        dimension_id = str(facet["id"])
        memberships: dict[str, set[str]] = {}
        interpreted: set[str] = set()
        for assignment in assignments:
            accepted = assignment.get("решение") == "принято"
            if assignment.get("измерение") != dimension_id or not accepted:
                continue
            person_id = str(assignment.get("персона"))
            if person_id in included_ids:
                memberships.setdefault(str(assignment.get("значение")), set()).add(person_id)
                if accepted and assignment.get("характер") == "классификационная_интерпретация":
                    interpreted.add(person_id)
        values = []
        for _, value in _ordered(facet.get("значения", [])):
            value_id = str(value["id"])
            members = memberships.get(value_id, set())
            values.append(SupplementaryDimensionValue(
                id=f"{dimension_id}:{value_id}", label=str(value.get("название", value_id)),
                person_ids=tuple(str(p["id"]) for p in people if str(p["id"]) in members),
            ))
        covered = set().union(*memberships.values()) if memberships else set()
        # Служебные значения описывают полноту разметки и не создают исторических категорий.
        values.extend((
            SupplementaryDimensionValue(
                id=f"{dimension_id}:__unclassified__", label="Не размечено / недостаточно источниковых данных",
                person_ids=tuple(str(p["id"]) for p in people if str(p["id"]) not in covered),
            ),
            SupplementaryDimensionValue(
                id=f"{dimension_id}:__interpretative__", label="Редакторские и классификационные интерпретации",
                person_ids=tuple(str(p["id"]) for p in people if str(p["id"]) in interpreted),
            ),
        ))
        result[dimension_id] = tuple(values)
    return result


def _attach_source_links(graph, person_links, lineage_links, school_link, root_id, root_is_person):
    for node_id, attributes in graph.nodes(data=True):
        person_id = attributes.get("person_id")
        if person_id:
            attributes["link_kind"] = "source_person"
            link = (person_links or {}).get(str(person_id))
            if link:
                attributes["href"] = str(link if isinstance(link, str) else link.get("href", ""))
                attributes["link_title"] = (link.get("title") if isinstance(link, Mapping) else None) or "Открыть карточку участника школы в новой вкладке"
                attributes["link_kind"] = "source_person"
            lineage_link = (lineage_links or {}).get(str(person_id))
            if lineage_link:
                attributes["lineage_href"] = str(lineage_link if isinstance(lineage_link, str) else lineage_link.get("href", ""))
                attributes["lineage_title"] = (lineage_link.get("title") if isinstance(lineage_link, Mapping) else None) or "Открыть дерево научного руководства в новой вкладке"
    if school_link and not root_is_person:
        attributes = graph.nodes[root_id]
        attributes["href"] = str(school_link if isinstance(school_link, str) else school_link.get("href", ""))
        attributes["link_title"] = (school_link.get("title") if isinstance(school_link, Mapping) else None) or "Открыть школу в новой вкладке"
        attributes["link_kind"] = "source_school"


def build_source_school_overview_tree(
    document: Mapping[str, Any], *,
    highlighted_person_ids: Collection[str] | None = None,
    hidden_person_ids: Collection[str] | None = None,
    lineage_links: Mapping[str, Mapping[str, str]] | None = None,
    person_links: Mapping[str, Mapping[str, str]] | None = None,
    school_link: str | Mapping[str, str] | None = None,
) -> SourceSchoolTree:
    """Строит структуру школы; исторические отношения не выводятся из расположения узлов.

    Фильтрация меняет только атрибуты узлов: порядок категорий, состав и рёбра сохраняются.
    """
    school = document["школа"]
    persons = _included_people(document)
    by_id = {str(p["id"]): p for p in persons}
    selected = None if highlighted_person_ids is None else set(map(str, highlighted_person_ids))
    hidden = None if hidden_person_ids is None else set(map(str, hidden_person_ids))
    center = document.get("отображение", {}).get("центр", {})
    root_is_person = center.get("тип") == "персона"
    root_person_id = str(center.get("id")) if root_is_person else None
    if root_is_person and root_person_id not in by_id:
        raise SourceSchoolDataError("Центральная персона должна быть включена в отображаемый состав школы.")
    root_id = f"person:{root_person_id}" if root_is_person else f"school:{school['идентификатор_школы']}"
    root_label = _name(by_id[root_person_id]) if root_is_person else str(school["каноническое_название"])
    graph = nx.DiGraph()
    graph.add_node(root_id, label=root_label, kind="root", person_id=root_person_id, color="#37474f")
    if root_is_person and selected is not None:
        graph.nodes[root_id].update(highlighted=root_person_id in selected,
                                    color=_HIGHLIGHT_COLOR if root_person_id in selected else _DIMMED_COLOR)
    used = {root_person_id} if root_is_person else set()
    primary = document.get("классификации", {}).get("основное_деление")
    if uses_membership_division(document):
        members = membership_index(document)
        for relation, label in MEMBERSHIP_GROUP_LABELS.items():
            ids = [pid for pid in by_id if pid not in used and members[pid]["отношение_к_школе"] == relation]
            if not ids:
                continue
            node_id = "membership:" + relation
            graph.add_node(node_id, label=label, kind="membership_category", membership_relation=relation)
            graph.add_edge(root_id, node_id)
            for person_id in ids:
                _add_person_node(graph, node_id, person_id, by_id[person_id], selected, hidden)
                used.add(person_id)
        basis = "отношение_к_школе"
    elif not isinstance(primary, Mapping):
        for person_id, person in by_id.items():
            if person_id not in used:
                _add_person_node(graph, root_id, person_id, person, selected, hidden)
        basis = "плоский_список"
    else:
        categories = [category for _, category in _ordered(primary.get("категории", []))]
        category_ids = {str(c["id"]) for c in categories}
        included_memberships = {str(m["персона"]): m for m in document.get("состав", []) if m.get("решение") == "включено"}
        scope = primary.get("область_применения", ["представитель", "связанное_лицо", "не_установлено"])
        exclusions = set(map(str, primary.get("исключённые_персоны", [])))
        eligible = {pid for pid in by_id if pid not in exclusions and included_memberships[pid].get("отношение_к_школе") in scope}
        assigned = {}
        for assignment in document.get("классификационные_назначения", []):
            if assignment.get("измерение") != primary.get("id") or assignment.get("решение") != "принято":
                continue
            pid, value = str(assignment.get("персона")), str(assignment.get("значение"))
            if pid not in eligible:
                continue
            if value not in category_ids:
                raise SourceSchoolDataError(f"Неизвестная основная категория {value}.")
            if pid in assigned:
                raise SourceSchoolDataError(f"Персона {pid} имеет несколько принятых основных отнесений.")
            assigned[pid] = assignment
        for category in categories:
            cid = str(category["id"])
            node_id = f"primary:{primary['id']}:{cid}"
            graph.add_node(node_id, label=str(category.get("название", cid)), kind="relation_category", relation_code=category.get("код") or cid)
            graph.add_edge(root_id, node_id)
            rows = [(i, person_id) for i, person_id in enumerate(by_id) if person_id not in used and assigned.get(person_id, {}).get("значение") == cid]
            rows.sort(key=lambda pair: (assigned[pair[1]].get("порядок") or pair[0] + 1, pair[0]))
            for _, person_id in rows:
                _add_person_node(graph, node_id, person_id, by_id[person_id], selected, hidden)
                used.add(person_id)
        unclassified = [pid for pid in by_id if pid in eligible and pid not in used]
        outside = [pid for pid in by_id if pid not in eligible and pid not in used]
        for ids, label, suffix in [(unclassified, "Не классифицировано", "unclassified"), (outside, "Вне основного деления", "outside")]:
            if ids:
                node_id = f"service:{suffix}"
                graph.add_node(node_id, label=label, kind="service_category")
                graph.add_edge(root_id, node_id)
                for person_id in ids:
                    _add_person_node(graph, node_id, person_id, by_id[person_id], selected, hidden)
        basis = "основное_деление"
    _attach_source_links(graph, person_links, lineage_links, school_link, root_id, root_is_person)
    return SourceSchoolTree(graph=graph, root_id=root_id, root_label=root_label, basis=basis)


# Прежнее имя API сохранено для потребителей экспорта структурных рёбер.
build_tree_edges_dataframe = build_source_school_tree_edges_dataframe
