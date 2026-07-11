from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_lineages_tab_prefills_builds_and_shares_roots() -> None:
    app = AppTest.from_string(
        """
import networkx as nx
import pandas as pd
import streamlit as st
import tabs.lineages.tab as lineages_tab


def _fake_lineage(df, idx, root, first_level_filter=None):
    graph = nx.DiGraph()
    graph.add_edge(root, f"{root} Ученик")
    subset = pd.DataFrame([
        {"candidate_name": f"{root} Ученик", "supervisors_1.name": root}
    ])
    return graph, subset


def _fake_draw(graph, root):
    import matplotlib.pyplot as plt
    fig, _ = plt.subplots()
    return fig


def _fake_markmap_widget(graph, root, key):
    return "Одностороннее ветвление", b"<html></html>"


def _fake_table(**kwargs):
    st.session_state["_lineages_table_key"] = kwargs["key"]


def _fake_share(roots, key, extra_params=None):
    st.session_state["_lineages_share_roots"] = roots
    st.session_state["_lineages_share_key"] = key
    st.session_state["_lineages_share_extra"] = extra_params


lineages_tab.lineage = _fake_lineage
lineages_tab.draw_matplotlib = _fake_draw
lineages_tab._render_markmap_widget = _fake_markmap_widget
lineages_tab.render_dissertations_widget = _fake_table
lineages_tab.share_button = _fake_share

lineages_tab.render_school_trees_tab(
    df=pd.DataFrame([{"candidate_name": "x", "supervisors_1.name": "Иванов И.И."}]),
    idx={},
    all_supervisor_names=["Иванов И.И."],
    shared_roots=["Иванов И.И.", "Ручной Руководитель"],
    db_signature=("test", 1.0, 1),
)
"""
    )

    app.run(timeout=15)

    assert app.session_state["lineages_built"] is True
    assert app.session_state["lineages_selected_roots_all"] == ["Иванов И.И."]
    assert app.session_state["lineages_manual_roots_all"] == "Ручной Руководитель"
    assert app.session_state["_lineages_share_key"] == "lineages_share"
    assert app.session_state["_lineages_share_extra"] == {"tab": "lineages"}
    assert app.session_state["_lineages_share_roots"] == ["Иванов И.И.", "Ручной Руководитель"]


def test_lineages_tab_metrics_use_rendered_graph_before_results() -> None:
    app = AppTest.from_string(
        """
import networkx as nx
import pandas as pd
import streamlit as st
import tabs.lineages.tab as lineages_tab

_RENDERED_GRAPH = nx.DiGraph()
_RENDERED_GRAPH.add_edge("Иванов И.И.", "Иванов И.И. Ученик")
_RENDERED_SUBSET = pd.DataFrame([
    {"candidate_name": "Иванов И.И. Ученик", "supervisors_1.name": "Иванов И.И."}
])


def _fake_lineage(df, idx, root, first_level_filter=None):
    return _RENDERED_GRAPH, _RENDERED_SUBSET


def _fake_draw(graph, root):
    st.session_state["_lineages_rendered_graph_id"] = id(graph)
    import matplotlib.pyplot as plt
    fig, _ = plt.subplots()
    return fig


def _fake_markmap_widget(graph, root, key):
    st.session_state["_lineages_markmap_graph_id"] = id(graph)
    return "Одностороннее ветвление", b"<html></html>"


def _fake_compute_metrics(graph, root, subset, include_extended=True):
    st.session_state["_lineages_compute_graph_id"] = id(graph)
    st.session_state["_lineages_compute_subset_id"] = id(subset)
    st.session_state["_lineages_expected_subset_id"] = id(_RENDERED_SUBSET)
    st.session_state["_lineages_compute_root"] = root
    st.session_state["_lineages_compute_include_extended"] = include_extended
    return {"root": root}


def _fake_render_metrics(metrics, **kwargs):
    st.session_state.setdefault("_lineages_order", []).append("metrics")
    st.session_state["_lineages_metrics_key_prefix"] = kwargs["key_prefix"]
    st.session_state["_lineages_metrics_context"] = kwargs["context_label"]


def _fake_table(subset, key, **kwargs):
    st.session_state.setdefault("_lineages_order", []).append("table")
    st.session_state["_lineages_table_subset_id"] = id(subset)
    st.session_state["_lineages_table_key"] = key


def _fake_share(roots, key, extra_params=None):
    st.session_state["_lineages_share_roots"] = roots
    st.session_state["_lineages_share_key"] = key
    st.session_state["_lineages_share_extra"] = extra_params


lineages_tab.lineage = _fake_lineage
lineages_tab.draw_matplotlib = _fake_draw
lineages_tab._render_markmap_widget = _fake_markmap_widget
lineages_tab.compute_lineage_metrics = _fake_compute_metrics
lineages_tab.render_lineage_metrics_panel = _fake_render_metrics
lineages_tab._render_tree_table = _fake_table
lineages_tab.share_button = _fake_share

lineages_tab.render_school_trees_tab(
    df=pd.DataFrame([{"candidate_name": "x", "supervisors_1.name": "Иванов И.И."}]),
    idx={},
    all_supervisor_names=["Иванов И.И."],
    shared_roots=["Иванов И.И."],
    db_signature=("test", 1.0, 1),
)
"""
    )

    app.run(timeout=15)

    assert app.session_state["_lineages_compute_graph_id"] == app.session_state["_lineages_rendered_graph_id"]
    assert app.session_state["_lineages_compute_graph_id"] == app.session_state["_lineages_markmap_graph_id"]
    assert app.session_state["_lineages_compute_subset_id"] == app.session_state["_lineages_expected_subset_id"]
    assert app.session_state["_lineages_table_subset_id"] == app.session_state["_lineages_expected_subset_id"]
    assert app.session_state["_lineages_compute_root"] == "Иванов И.И."
    assert app.session_state["_lineages_compute_include_extended"] is True
    assert app.session_state["_lineages_order"] == ["metrics", "table"]
    assert app.session_state["_lineages_metrics_key_prefix"] == "all_Иванов_И_И"
    assert app.session_state["_lineages_table_key"] == "all_Иванов_И_И"
    assert app.session_state["_lineages_metrics_context"] == "Общее дерево: Иванов И.И."
    assert app.session_state["_lineages_share_key"] == "lineages_share"
    assert app.session_state["_lineages_share_extra"] == {"tab": "lineages"}
