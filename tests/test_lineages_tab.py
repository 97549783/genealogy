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
    df=pd.DataFrame([{"candidate_name": "x"}]),
    idx={},
    all_supervisor_names=["Иванов И.И."],
    shared_roots=["Иванов И.И.", "Ручной Руководитель"],
)
"""
    )

    app.run(timeout=15)

    assert app.session_state["lineages_built"] is True
    assert app.session_state["lineages_selected_roots"] == ["Иванов И.И."]
    assert app.session_state["lineages_manual_roots"] == "Ручной Руководитель"
    assert app.session_state["_lineages_share_key"] == "lineages_share"
    assert app.session_state["_lineages_share_extra"] == {"tab": "lineages"}
    assert app.session_state["_lineages_share_roots"] == ["Иванов И.И.", "Ручной Руководитель"]
