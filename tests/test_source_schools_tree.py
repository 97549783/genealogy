"""Проверки структурного дерева школ по источникам."""
import json
from pathlib import Path

from core.source_schools.tree import build_source_school_overview_tree, build_source_school_tree_edges_dataframe
from core.ui.tree_renderers import build_markmap_html

PATH = Path("data/source_schools/vygotsky_school_sources_demo.v1.json")


def test_дерево_строится_с_пользовательскими_метками():
    tree = build_source_school_overview_tree(json.loads(PATH.read_text(encoding="utf-8")))
    labels = " ".join(str(data.get("label", "")) for _, data in tree.graph.nodes(data=True))
    assert "person:" not in labels
    assert build_source_school_tree_edges_dataframe(tree).columns.tolist() == ["Источник", "Цель"]


def test_markmap_использует_метки():
    tree = build_source_school_overview_tree(json.loads(PATH.read_text(encoding="utf-8")))
    html, height = build_markmap_html(tree.graph, tree.root_id)
    assert height > 0
    assert tree.root_label in html
