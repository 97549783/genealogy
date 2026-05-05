from __future__ import annotations

import pandas as pd

from tabs.school_search import search as ss


def test_search_by_supervisor_rate_without_rows_for(monkeypatch):
    monkeypatch.setattr(ss, "get_db_signature", lambda: ("x", 1.0, 1))
    monkeypatch.setattr(
        ss,
        "get_supervisor_rate_stats",
        lambda *a, **k: {
            "Root1": {"direct_count": 2, "supervisor_count": 1, "rate": 50.0},
            "Root2": {"direct_count": 1, "supervisor_count": 1, "rate": 100.0},
        },
    )
    monkeypatch.setattr(
        ss,
        "get_school_basic_stats",
        lambda *a, **k: {
            "Root1": {"n_members": 5, "year_range": "2020–2024", "n_cities": 2},
            "Root2": {"n_members": 3, "year_range": "2019–2024", "n_cities": 1},
        },
    )

    def rows_for_should_not_be_called(*args, **kwargs):
        raise AssertionError("rows_for_func не должен вызываться в оптимизированном режиме")

    out = ss.search_by_supervisor_rate(
        df=pd.DataFrame(),
        index={},
        lineage_func=None,
        rows_for_func=rows_for_should_not_be_called,
        scope="all",
        top_n=10,
    )
    assert out.iloc[0]["Руководитель"] == "Root2"
    assert "Таких учеников" in out.columns
    assert "Прямых учеников" in out.columns
