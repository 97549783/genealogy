from __future__ import annotations

import pandas as pd

from tabs.school_search import search as ss


def _context_key():
    return (("x", 1.0, 1), (), ("supervisors_1.name", "supervisors_2.name"))


def _df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Code": "1", "candidate_name": "A", "year": "2020", "city": "Москва", "institution_prepared": "МГУ", "defense_location": "МГУ", "leading_organization": "РАН", "opponents_1.name": "Петров П.П.", "supervisors_1.name": "Root1", "supervisors_2.name": ""},
        {"Code": "2", "candidate_name": "B", "year": "2021", "city": "Казань", "institution_prepared": "КФУ", "defense_location": "КФУ", "leading_organization": "РАН", "opponents_1.name": "Иванов И.И.", "supervisors_1.name": "Root1", "supervisors_2.name": ""},
        {"Code": "3", "candidate_name": "C", "year": "2021", "city": "Москва", "institution_prepared": "СПбГУ", "defense_location": "СПбГУ", "leading_organization": "РФФИ", "opponents_1.name": "ПЕТРОВ П.П.", "supervisors_1.name": "Root2", "supervisors_2.name": ""},
    ])


def test_year_and_text_modes_use_sqlite_first(monkeypatch):
    df = _df()
    key = _context_key()
    monkeypatch.setattr(ss, "get_all_school_member_codes", lambda *a, **k: {"Root1": {"1", "2"}, "Root2": {"3"}})
    monkeypatch.setattr(ss, "get_school_basic_stats", lambda *a, **k: {
        "Root1": {"n_members": 2, "year_range": "2020–2021", "n_cities": 2},
        "Root2": {"n_members": 1, "year_range": "2021–2021", "n_cities": 1},
    })
    monkeypatch.setattr(ss, "fetch_dissertation_codes_by_year_range", lambda a, b: {"2", "3"})
    monkeypatch.setattr(ss, "fetch_dissertation_codes_by_year", lambda y: {"2", "3"})
    monkeypatch.setattr(
        ss,
        "fetch_dissertation_text_candidates",
        lambda cols, query, use_like_prefilter=False: pd.DataFrame(
            [{"Code": "1", "column": cols[0], "value": "Москва"}, {"Code": "3", "column": cols[0], "value": "Москва"}]
        ),
    )

    by_period = ss.search_by_members_in_period(df, {}, None, None, 2021, 2021, lineage_context_key=key)
    assert set(by_period["Руководитель"]) == {"Root1", "Root2"}
    by_city, _ = ss.search_by_city(df, {}, None, None, "Москва", lineage_context_key=key)
    assert set(by_city["Руководитель"]) == {"Root1", "Root2"}


def test_org_modes_and_opponent_use_prefilter_by_mode(monkeypatch):
    df = _df()
    key = _context_key()
    monkeypatch.setattr(ss, "get_all_school_member_codes", lambda *a, **k: {"Root1": {"1", "2"}, "Root2": {"3"}})
    monkeypatch.setattr(ss, "get_school_basic_stats", lambda *a, **k: {
        "Root1": {"n_members": 2, "year_range": "2020–2021", "n_cities": 2},
        "Root2": {"n_members": 1, "year_range": "2021–2021", "n_cities": 1},
    })
    calls = []

    def _fake_fetch(cols, query, use_like_prefilter=False):
        calls.append((tuple(cols), use_like_prefilter))
        if "opponents_1.name" in cols:
            return pd.DataFrame([
                {"Code": "1", "column": "opponents_1.name", "value": "Петров П.П."},
                {"Code": "3", "column": "opponents_2.name", "value": "ПЕТРОВ П.П."},
            ])
        return pd.DataFrame([
            {"Code": "1", "column": cols[0], "value": "Московский государственный университет"},
            {"Code": "3", "column": cols[0], "value": "МГУ"},
        ])

    monkeypatch.setattr(ss, "fetch_dissertation_text_candidates", _fake_fetch)

    r1, _ = ss.search_by_institution_prepared(df, {}, None, None, "МГУ", use_fuzzy=True, lineage_context_key=key)
    r2, _ = ss.search_by_defense_location(df, {}, None, None, "МГУ", use_fuzzy=True, lineage_context_key=key)
    r3, _ = ss.search_by_leading_organization(df, {}, None, None, "РАН", use_fuzzy=True, lineage_context_key=key)
    r4, _ = ss.search_by_opponent(df, {}, None, None, "Петров", use_fuzzy=True, lineage_context_key=key)
    assert not r1.empty and not r2.empty and not r4.empty
    assert all(flag is False for _, flag in calls)


def test_member_lineage_uses_exact_normalized_author_match() -> None:
    df = pd.DataFrame([
        {"candidate_name": "Иванов Иван Иванович", "supervisors_1.name": "Петров Петр Петрович", "supervisors_2.name": ""},
        {"candidate_name": "Иванов Иван", "supervisors_1.name": "Сидоров Сидор Сидорович", "supervisors_2.name": ""},
        {"candidate_name": "Петров Петр Петрович", "supervisors_1.name": "", "supervisors_2.name": ""},
    ])

    partial_results = ss.search_member_lineage_chains(df, "Иванов Иван")
    exact_results = ss.search_member_lineage_chains(df, "Иванов Иван Иванович")

    assert [result["author_name"] for result in partial_results] == ["Иванов Иван"]
    assert [result["author_name"] for result in exact_results] == ["Иванов Иван Иванович"]
