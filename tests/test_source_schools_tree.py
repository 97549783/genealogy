"""Проверки структурного дерева школ по источникам."""
import json
from pathlib import Path

from core.source_schools.tree import (
    build_source_school_overview_tree,
    build_source_school_tree_edges_dataframe,
    build_supplementary_dimension_catalog,
    combine_supplementary_selections,
)
from core.ui.tree_renderers import build_markmap_html

PATH = Path("data/source_schools/vygotsky_school_sources_demo.v1.json")


def test_дерево_строится_с_пользовательскими_метками():
    tree = build_source_school_overview_tree(json.loads(PATH.read_text(encoding="utf-8")))
    labels = " ".join(str(data.get("label", "")) for _, data in tree.graph.nodes(data=True))
    assert "person:" not in labels
    assert build_source_school_tree_edges_dataframe(tree).columns.tolist() == ["Источник", "Цель"]


def test_основное_дерево_использует_четыре_взаимоисключающие_категории_a():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    tree = build_source_school_overview_tree(document)
    assert tree.basis == "классификация_связи_с_выготским"
    branch_labels = [tree.graph.nodes[node]["label"] for node in tree.graph.successors(tree.root_id)]
    assert branch_labels == [
        "Прямое руководство / обучение",
        "Прямое сотрудничество",
        "Внешнее прямое взаимодействие",
        "Косвенная преемственность",
    ]
    assert not any(label.startswith(("A1", "A2", "A3", "A4")) for label in branch_labels)
    person_nodes = [node for node, data in tree.graph.nodes(data=True) if data.get("kind") == "person"]
    assert len(person_nodes) == 50
    assert all(tree.graph.in_degree(node) == 1 for node in person_nodes)
    person_labels = {tree.graph.nodes[node]["label"] for node in person_nodes}
    assert {
        "Филипп Вениаминович Бассин",
        "Курт Коффка",
        "Пантелеймон Саввич Любимов",
        "Фёдор Николаевич Шемякин",
    }.issubset(person_labels)


def test_дополнительные_измерения_накладываются_без_изменения_ребер():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    catalog = build_supplementary_dimension_catalog(document)
    assert set(catalog) == {"historical_group", "period", "research_direction"}
    kharkov = next(value for value in catalog["historical_group"] if value.label == "Харьковская группа")
    base = build_source_school_overview_tree(document)
    highlighted = build_source_school_overview_tree(document, highlighted_person_ids=kharkov.person_ids)
    assert set(base.graph.edges) == set(highlighted.graph.edges)
    assert highlighted.graph.nodes["person:alexei_leontiev"]["color"] == "#ff8f00"
    assert highlighted.graph.nodes["person:daniil_elkonin"]["color"] == "#cfd8dc"


def test_многозначные_измерения_объединяются_внутри_и_компонуются_между_собой():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    catalog = build_supplementary_dimension_catalog(document)
    selections = {
        "historical_group": ["group:pyaterka", "group:kharkov_group"],
        "research_direction": ["direction:1"],
        "period": [],
    }
    intersection = combine_supplementary_selections(catalog, selections, mode="intersection")
    union = combine_supplementary_selections(catalog, selections, mode="union")
    assert {"lidia_bozhovich", "alexander_zaporozhets", "lia_slavina"}.issubset(intersection or set())
    assert intersection and union and intersection < union


def test_режим_скрытия_сохраняет_полную_структуру_графа():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    base = build_source_school_overview_tree(document)
    hidden = build_source_school_overview_tree(
        document,
        highlighted_person_ids={"alexei_leontiev"},
        hidden_person_ids={"daniil_elkonin"},
    )
    assert set(base.graph.edges) == set(hidden.graph.edges)
    assert hidden.graph.nodes["person:daniil_elkonin"]["hidden"] is True


def test_markmap_использует_метки():
    tree = build_source_school_overview_tree(json.loads(PATH.read_text(encoding="utf-8")))
    html, height = build_markmap_html(tree.graph, tree.root_id)
    assert height > 0
    assert tree.root_label in html
    assert '"fold": 1' not in html


def test_markmap_сохраняет_цвета_наложенного_измерения():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    tree = build_source_school_overview_tree(document, highlighted_person_ids={"alexei_leontiev"})
    html, _ = build_markmap_html(tree.graph, tree.root_id)
    assert "#ff8f00" in html
    assert "#cfd8dc" in html
    hidden_tree = build_source_school_overview_tree(
        document,
        highlighted_person_ids={"alexei_leontiev"},
        hidden_person_ids={"daniil_elkonin"},
    )
    hidden_html, _ = build_markmap_html(hidden_tree.graph, hidden_tree.root_id)
    assert '"_hidden": true' in hidden_html
    assert "applyVisibility" in hidden_html
