from __future__ import annotations

import pandas as pd
import pytest

from core.lineage.graph import build_index
import core.lineage.membership as membership
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




@pytest.fixture(autouse=True)
def clear_membership_caches():
    for cached in (
        membership._roots_cached,
        membership._member_codes_cached,
        membership._lineage_cached,
        membership._all_school_member_codes_cached,
        membership._school_basic_stats_cached,
        membership._get_author_by_code_cached,
        membership._get_supervisor_norm_set_cached,
        membership._get_author_supervisor_flags_by_code_cached,
        membership._get_supervisor_rate_stats_cached,
    ):
        cached.clear()
    yield

def _context_key(sig=("x", 1.0, 1), fields=()):
    return (sig, tuple(fields), ("supervisors_1.name", "supervisors_2.name"))


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
    key = _context_key(sig)
    roots = get_cached_roots(df, sig, context_key=key)
    assert "Root" in roots
    assert set(get_school_member_codes(df, idx, "Root", "direct", sig, context_key=key)) == {"1", "3"}
    assert set(get_school_member_codes(df, idx, "Root", "all", sig, context_key=key)) == {"1", "2", "3"}
    subset = get_school_subset(df, idx, "Root", "all", sig, context_key=key)
    assert len(subset) == 3
    g, _ = get_school_lineage(df, idx, "Root", "doctors", sig, context_key=key)
    assert g.number_of_edges() == 2


def test_membership_cache_unknown_scope():
    df = _df()
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    key = _context_key(sig)
    try:
        get_school_member_codes(df, idx, "Root", "bad", sig, context_key=key)
        assert False
    except ValueError as exc:
        assert "Неизвестная область" in str(exc)


def test_bulk_school_stats():
    df = _df()
    df["year"] = ["2010", "2015", "2018"]
    df["city"] = ["Москва", "Казань", "Москва"]
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    key = _context_key(sig)
    codes = get_all_school_member_codes(df, idx, "all", sig, context_key=key)
    assert codes["Root"] == {"1", "2", "3"}
    stats = get_school_basic_stats(df, idx, "all", sig, context_key=key)
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
    key = _context_key(sig)
    authors = get_author_by_code(df, sig, context_key=key)
    assert authors["2"] == "Иванов Иван Иванович"
    flags = get_author_supervisor_flags_by_code(df, idx, sig, context_key=key)
    assert flags["2"] is True
    assert flags["3"] is True
    assert flags["6"] is False
    stats = get_supervisor_rate_stats(df, idx, sig, context_key=key)
    assert stats["Root"]["direct_count"] == 2
    assert stats["Root"]["supervisor_count"] == 2
    assert stats["Root"]["rate"] == 100.0
    assert stats["C"]["rate"] == 0.0


def test_get_all_school_member_codes_does_not_call_get_school_member_codes(monkeypatch):
    df = _df()
    idx = build_index(df, ["supervisors_1.name", "supervisors_2.name"])
    sig = ("x", 1.0, 1)
    monkeypatch.setattr(
        membership,
        "get_school_member_codes",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bulk helper не должен вызывать get_school_member_codes")),
    )
    key = _context_key(sig)
    out = membership.get_all_school_member_codes(df, idx, "direct", sig, context_key=key)
    assert out["Root"] == {"1", "3"}


def test_same_signature_different_context_keys_are_isolated():
    sig = ("x", 1.0, 1)
    df_all = _df()
    idx_all = build_index(df_all, ["supervisors_1.name", "supervisors_2.name"])
    df_filtered = df_all[df_all["Code"] != "3"].copy()
    idx_filtered = build_index(df_filtered, ["supervisors_1.name", "supervisors_2.name"])

    all_codes = get_school_member_codes(df_all, idx_all, "Root", "direct", sig, context_key=_context_key(sig, ()))
    filtered_codes = get_school_member_codes(
        df_filtered,
        idx_filtered,
        "Root",
        "direct",
        sig,
        context_key=_context_key(sig, ("technical",)),
    )

    assert set(all_codes) == {"1", "3"}
    assert set(filtered_codes) == {"1"}


def test_cached_helper_large_arguments_are_underscore_prefixed():
    import inspect

    helper_names = [
        "_roots_cached",
        "_member_codes_cached",
        "_lineage_cached",
        "_all_school_member_codes_cached",
        "_school_basic_stats_cached",
        "_get_author_by_code_cached",
        "_get_supervisor_norm_set_cached",
        "_get_author_supervisor_flags_by_code_cached",
        "_get_supervisor_rate_stats_cached",
    ]
    for name in helper_names:
        params = inspect.signature(getattr(membership, name)).parameters
        assert "context_key" in params
        assert not {"df", "idx"} & set(params)
