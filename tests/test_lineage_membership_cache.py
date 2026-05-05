from __future__ import annotations

import pandas as pd

from core.lineage.graph import build_index
from core.lineage.membership import (
    get_author_by_code,
    get_author_supervisor_flags_by_code,
    get_all_school_member_codes,
    get_cached_roots,
    get_school_basic_stats,
    get_school_lineage,
    get_school_member_codes,
    get_school_subset,
    get_supervisor_rate_stats,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Code": "1", "candidate_name": "Student A", "supervisors_1.name": "Root", "supervisors_2.name": "", "degree.degree_level": "доктор"},
        {"Code": "2", "candidate_name": "Student B", "supervisors_1.name": "Student A", "supervisors_2.name": "", "degree.degree_level": "кандидат"},
        {"Code": "3", "candidate_name": "Student C", "supervisors_1.name": "Root", "supervisors_2.name": "", "degree.degree_level": "кандидат"},
    ])


def test_membership_cache_basic():
    df = _df()
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    roots = get_cached_roots(df, sig)
    assert "Root" in roots
    assert set(get_school_member_codes(df, idx, "Root", "direct", sig)) == {"1", "3"}
    assert set(get_school_member_codes(df, idx, "Root", "all", sig)) == {"1", "2", "3"}
    subset = get_school_subset(df, idx, "Root", "all", sig)
    assert len(subset) == 3
    g, _ = get_school_lineage(df, idx, "Root", "doctors", sig)
    assert g.number_of_edges() == 2


def test_membership_cache_unknown_scope():
    df = _df()
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    try:
        get_school_member_codes(df, idx, "Root", "bad", sig)
        assert False
    except ValueError as exc:
        assert "Неизвестная область" in str(exc)


def test_bulk_school_stats():
    df = _df()
    df["year"] = ["2010", "2015", "2018"]
    df["city"] = ["Москва", "Казань", "Москва"]
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    codes = get_all_school_member_codes(df, idx, "all", sig)
    assert codes["Root"] == {"1", "2", "3"}
    stats = get_school_basic_stats(df, idx, "all", sig)
    assert stats["Root"]["n_members"] == 3
    assert stats["Root"]["year_min"] == 2010
    assert stats["Root"]["year_max"] == 2018
    assert stats["Root"]["n_cities"] == 2


def test_supervisor_rate_helpers_with_variants():
    df = pd.DataFrame([
        {"Code": "1", "candidate_name": "Root", "supervisors_1.name": "", "supervisors_2.name": ""},
        {"Code": "2", "candidate_name": "Иванов Иван Иванович", "supervisors_1.name": "Root", "supervisors_2.name": ""},
        {"Code": "3", "candidate_name": "B", "supervisors_1.name": "Root", "supervisors_2.name": ""},
        {"Code": "4", "candidate_name": "C", "supervisors_1.name": "Иванов И.И.", "supervisors_2.name": ""},
        {"Code": "5", "candidate_name": "D", "supervisors_1.name": "B", "supervisors_2.name": ""},
        {"Code": "6", "candidate_name": "E", "supervisors_1.name": "C", "supervisors_2.name": ""},
    ])
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    authors = get_author_by_code(df, sig)
    assert authors["2"] == "Иванов Иван Иванович"
    flags = get_author_supervisor_flags_by_code(df, idx, sig)
    assert flags["2"] is True
    assert flags["3"] is True
    assert flags["6"] is False
    stats = get_supervisor_rate_stats(df, idx, sig)
    assert stats["Root"]["direct_count"] == 2
    assert stats["Root"]["supervisor_count"] == 2
    assert stats["Root"]["rate"] == 100.0
    assert stats["C"]["rate"] == 0.0
