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
    visible = str(app)
    assert "Фертильность: прямые ученики, ставшие руководителями" in visible
    assert "Среднее число всех потомков у ученика" in visible
    assert "Среднее число прямых потомков у ученика" in visible
    assert "Уровней с корнем" not in visible
    assert "Генеалогический индекс" not in visible
    assert "C-score / фертильность" not in visible
    assert "Входит в диссертационный набор" not in visible
    assert "глава" not in visible.lower()
    assert "не является" not in visible.lower()
