import networkx as nx
import pandas as pd

from core.lineage.metric_tables import build_generation_counts_df, build_lineage_metrics_summary_df, build_proliferation_df
from core.lineage.metrics import compute_lineage_metrics


def test_metric_tables():
    graph = nx.DiGraph([("root", "A"), ("A", "B")])
    metrics = compute_lineage_metrics(graph, "root", pd.DataFrame({"candidate_name": ["A", "B"], "year": [2000, 2002]}))
    base = build_lineage_metrics_summary_df(metrics, include_extended=False)
    assert "direct_students" in set(base["key"])
    assert "terminal_descendants" not in set(base["key"])
    assert "Тип метрики" in base.columns
    assert "Входит в диссертационный набор" not in base.columns
    assert base.loc[base["key"] == "g_score", "Метрика"].iloc[0] == "Генеалогический индекс"
    assert base.loc[base["key"] == "g_score", "Статус"].iloc[0] == "пока не рассчитывается"
    full = build_lineage_metrics_summary_df(metrics, include_extended=True)
    assert "terminal_descendants" in set(full["key"])
    assert full.loc[full["key"] == "terminal_descendants", "Тип метрики"].iloc[0] == "Дополнительная"
    assert full.loc[full["key"] == "multi_parent_nodes", "Тип метрики"].iloc[0] == "Качество данных"
    assert full.loc[full["key"] == "g_score", "Значение"].iloc[0] is None
    assert list(build_generation_counts_df(metrics)["Поколение"]) == [0, 1, 2]
    assert list(build_proliferation_df(metrics)["Год"]) == [2000, 2001, 2002]
