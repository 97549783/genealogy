from __future__ import annotations

import pandas as pd

from tabs.school_search import search as ss


def test_classifier_mode_uses_targeted_node_scores(monkeypatch):
    df = pd.DataFrame([{"Code": "1"}, {"Code": "2"}, {"Code": "3"}])
    monkeypatch.setattr(ss, "get_db_signature", lambda: ("x", 1.0, 1))
    monkeypatch.setattr(ss, "get_all_school_member_codes", lambda *a, **k: {"Root1": {"1", "2"}, "Root2": {"3"}})
    monkeypatch.setattr(ss, "get_school_basic_stats", lambda *a, **k: {
        "Root1": {"n_members": 2, "year_range": "2020–2021", "n_cities": 2},
        "Root2": {"n_members": 1, "year_range": "2021–2021", "n_cities": 1},
    })
    monkeypatch.setattr(
        ss,
        "fetch_dissertation_node_score_by_codes",
        lambda codes, classifier_node: pd.DataFrame(
            [{"Code": "1", "node_score": 5.0}, {"Code": "2", "node_score": 1.0}, {"Code": "3", "node_score": 10.0}]
        ),
    )

    out = ss.search_by_classifier_score(df, {}, None, None, "1.1", scope="all", top_n=10)
    assert list(out.columns) == ["#", "Руководитель", "Средний балл (1.1)", "Всего членов", "Годы активности", "Уникальных городов"]
    assert out.iloc[0]["Руководитель"] == "Root2"
    assert out.iloc[0]["Средний балл (1.1)"] == 10.0
    assert out.iloc[1]["Руководитель"] == "Root1"
    assert out.iloc[1]["Средний балл (1.1)"] == 3.0
