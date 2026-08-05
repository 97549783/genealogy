"""Построение структурного дерева школы по источникам."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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


def build_source_school_overview_tree(document: Mapping[str, Any]) -> SourceSchoolTree:
    """Строит дерево обзорной структуры школы."""
    school = document["школа"]
    persons = [person for person in school.get("персоны", []) if isinstance(person, Mapping)]
    by_id = {str(person.get("id")): person for person in persons}
    root_id, root_label = _find_root(school, persons)
    graph = nx.DiGraph()
    graph.add_node(root_id, label=root_label, kind="root")
    used: set[str] = {root_id.removeprefix("person:")} if root_id.startswith("person:") else set()
    structure = school.get("внутренняя_структура", {})
    generations = [item for item in structure.get("поколения", []) if isinstance(item, Mapping)]
    if generations:
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
                    node_id = f"person:{person_id}"
                    graph.add_node(node_id, label=_name(person), kind="person")
                    graph.add_edge(generation_id, node_id)
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
                graph.add_node(f"person:{person_id}", label=_name(person), kind="person")
                graph.add_edge(category_id, f"person:{person_id}")
                used.add(person_id)
        basis = "категории"
    other = [person for person in persons if str(person.get("id")) not in used]
    if other:
        other_id = "category:other"
        graph.add_node(other_id, label="Другие представители", kind="category")
        graph.add_edge(root_id, other_id)
        for person in other:
            person_id = str(person.get("id"))
            graph.add_node(f"person:{person_id}", label=_name(person), kind="person")
            graph.add_edge(other_id, f"person:{person_id}")
    return SourceSchoolTree(graph=graph, root_id=root_id, root_label=root_label, basis=basis)


def build_source_school_tree_edges_dataframe(tree: SourceSchoolTree) -> pd.DataFrame:
    """Формирует таблицу рёбер дерева для экспорта."""
    return pd.DataFrame([{"Источник": tree.graph.nodes[a].get("label", a), "Цель": tree.graph.nodes[b].get("label", b)} for a, b in tree.graph.edges])
