"""Проверки равномерного распределения целых ветвей двустороннего Markmap."""
import itertools
import json
import re
from html import unescape
from pathlib import Path

import networkx as nx
import pytest

from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import (
    _markmap_leaf_count,
    _split_markmap_branches,
    build_markmap_html,
)


def side_data(html, side):
    return json.loads(re.search(rf"const {side}Data = (.*);", html).group(1))


def branch(index, leaves):
    return {
        "content": str(index),
        "children": [{"content": f"{index}:{leaf}", "children": []} for leaf in range(leaves)],
    }


@pytest.mark.parametrize("weights", [
    (20, 20, 4, 6),
    (8, 7, 6, 5, 4),  # Жадное распределение даёт 17/13, оптимальное — 15/15.
    (3, 3, 2, 2, 2),
    (9, 1, 1),
    (1, 5, 1, 1),
    (2, 4, 8, 16),
    (2, 2, 2, 2, 2),
])
def test_partition_minimizes_leaf_difference_and_preserves_whole_branches(weights):
    branches = [branch(index, leaves) for index, leaves in enumerate(weights)]
    left, right = _split_markmap_branches(branches)
    difference = abs(sum(map(_markmap_leaf_count, left)) - sum(map(_markmap_leaf_count, right)))
    optimal = min(
        abs(sum(weights) - 2 * sum(weight for weight, chosen in zip(weights, choices) if chosen))
        for choices in itertools.product((False, True), repeat=len(weights))
    )
    assert difference == optimal
    assert left and right
    assert branches[0] is left[0]
    assert sorted(id(node) for node in left + right) == sorted(id(node) for node in branches)
    for side in (left, right):
        assert [node["content"] for node in side] == sorted(node["content"] for node in side)


def test_zero_single_and_equal_branches_preserve_existing_placement():
    assert _split_markmap_branches([]) == ([], [])
    single = [branch(0, 1)]
    assert _split_markmap_branches(single) == ([], single)
    equal = [branch(index, 2) for index in range(5)]
    assert _split_markmap_branches(equal) == (equal[:2], equal[2:])


def test_many_equal_weights_and_one_larger_branch_can_be_balanced_exactly():
    branches = [branch(index, 1) for index in range(2049)] + [branch(2049, 3)]
    left, right = _split_markmap_branches(branches)
    assert sum(map(_markmap_leaf_count, left)) == sum(map(_markmap_leaf_count, right)) == 1026
    assert len(left) + len(right) == len(branches)


def test_source_school_balances_without_changing_groups_colors_or_filter_placement():
    document = json.loads(Path("data/source_schools/schools/vygotsky_cultural_historical_school.json").read_text(encoding="utf-8"))
    url = "https://example.test/?tab=lineages&root=Leontiev"
    tree = build_source_school_overview_tree(document, lineage_links={"alexei_leontiev": {"href": url}})
    html, _ = build_markmap_html(tree.graph, tree.root_id)
    sides = [side_data(html, side)["children"] for side in ("left", "right")]
    leaf_counts = [sum(map(_markmap_leaf_count, side)) for side in sides]
    weights = [tree.graph.out_degree(group) for group in tree.graph.successors(tree.root_id)]
    optimal = min(abs(sum(weights) - 2 * sum(w for w, chosen in zip(weights, choices) if chosen))
                  for choices in itertools.product((False, True), repeat=len(weights)))
    assert abs(leaf_counts[0] - leaf_counts[1]) == optimal
    assert sum(leaf_counts) == sum(weights)
    indices = [[node["_palette_idx"] for node in side] for side in sides]
    assert sorted(index for side in indices for index in side) == list(range(len(weights)))
    assert all(side == sorted(side) for side in indices)
    by_palette = {node["_palette_idx"]: node for side in sides for node in side}
    for index, group in enumerate(tree.graph.successors(tree.root_id)):
        assert by_palette[index]["content"] == tree.graph.nodes[group]["label"]
        assert [unescape(re.sub(r"<[^>]+>", "", node["content"])) for node in by_palette[index]["children"]] == [
            tree.graph.nodes[child]["label"] for child in tree.graph.successors(group)
        ]
        assert len(by_palette[index]["children"]) == tree.graph.out_degree(group)
    assert any(
        'href="https://example.test/?tab=lineages&amp;root=Leontiev"' in node["content"]
        for node in by_palette[0]["children"]
    )

    hidden = build_source_school_overview_tree(document, hidden_person_ids={"alexei_leontiev", "daniil_elkonin"})
    hidden_html, _ = build_markmap_html(hidden.graph, hidden.root_id, initial_expand_level=1)
    for side, original in zip(("left", "right"), sides):
        modified = side_data(hidden_html, side)["children"]
        assert [node["_palette_idx"] for node in modified] == [node["_palette_idx"] for node in original]
        assert all(node["payload"] == {"fold": 1} for node in modified)
    assert '"_hidden": true' in hidden_html


def test_leaf_count_uses_terminal_nodes_at_all_depths_and_handles_cycles_and_shared_nodes():
    graph = nx.DiGraph([
        ("root", "a"), ("root", "b"),
        ("a", "middle"), ("middle", "shared"), ("middle", "end"),
        ("shared", "a"),
        ("b", "shared"), ("b", "leaf"),
    ])
    html, _ = build_markmap_html(graph, "root")
    sides = [side_data(html, side)["children"] for side in ("left", "right")]
    assert [sum(map(_markmap_leaf_count, side)) for side in sides] == [2, 3]
    assert {node["content"] for side in sides for node in side} == {"a", "b"}
