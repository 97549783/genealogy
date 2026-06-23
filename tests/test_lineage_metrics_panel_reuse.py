from streamlit.testing.v1 import AppTest


def test_panel_renders_without_lineage_tab():
    app = AppTest.from_string('''
import networkx as nx
import pandas as pd
from core.lineage import compute_lineage_metrics
from core.ui import render_lineage_metrics_panel
metrics = compute_lineage_metrics(nx.DiGraph([("root", "A")]), "root", pd.DataFrame({"candidate_name": ["A"], "year": [2000]}))
render_lineage_metrics_panel(metrics, key_prefix="demo", context_label="Школа: root", expanded=True, include_extended=False, include_help_button=False)
''')
    app.run(timeout=15)
    assert not app.exception
    assert any("Количественные метрики" in item.label for item in app.expander)
    assert "tabs.lineages" not in app.session_state
