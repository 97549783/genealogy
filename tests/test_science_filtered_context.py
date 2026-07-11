import pandas as pd

from core.ui.science_filtering import build_science_filtered_lineage_context


def test_build_science_filtered_lineage_context_filters_and_rebuilds_supervisors():
    df = pd.DataFrame(
        [
            {
                "Code": "A",
                "candidate_name": "Автор A",
                "supervisors_1.name": "Тех Руководитель",
                "degree.science_field": "Технические науки",
            },
            {
                "Code": "B",
                "candidate_name": "Автор B",
                "supervisors_1.name": "Пед Руководитель",
                "degree.science_field": "Педагогические науки",
            },
        ]
    )

    context = build_science_filtered_lineage_context(
        df=df,
        selected_ids=["technical"],
        supervisor_columns=["supervisors_1.name"],
    )

    assert context.df["Code"].tolist() == ["A"]
    assert context.all_supervisor_names == ("Тех Руководитель",)
    assert context.science_field_ids == ("technical",)
    assert context.idx


def _base_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Code": "A", "candidate_name": "Автор A", "supervisors_1.name": "Тех Руководитель", "degree.science_field": "Технические науки"},
        {"Code": "B", "candidate_name": "Автор B", "supervisors_1.name": "Пед Руководитель", "degree.science_field": "Педагогические науки"},
    ])


def test_unfiltered_cached_context_reuses_base_objects_and_skips_index(monkeypatch):
    from core.ui import science_filtering as sf

    sf._get_science_filtered_lineage_context_cached.clear()
    df = _base_df()
    base_idx = {"Тех Руководитель": {0}, "Пед Руководитель": {1}}
    monkeypatch.setattr(sf, "build_index", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("build_index")))
    monkeypatch.setattr(sf, "filter_df_by_science_fields", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("filter")))

    context = sf.get_science_filtered_lineage_context(
        df=df,
        base_idx=base_idx,
        db_signature=("db", 1.0, 1),
        selected_ids=[],
        supervisor_columns=["supervisors_1.name"],
    )

    assert context.df is df
    assert context.idx is base_idx
    assert context.cache_key == (("db", 1.0, 1), (), ("supervisors_1.name",))


def test_filter_order_normalization_reuses_cached_context(monkeypatch):
    from core.ui import science_filtering as sf

    sf._get_science_filtered_lineage_context_cached.clear()
    df = _base_df()
    calls = {"index": 0}

    def _build(filtered_df, columns):
        calls["index"] += 1
        return {"idx": {0}}

    monkeypatch.setattr(sf, "build_index", _build)
    first = sf.get_science_filtered_lineage_context(
        df=df,
        base_idx={},
        db_signature=("db", 1.0, 1),
        selected_ids=[" technical ", "pedagogy"],
        supervisor_columns=["supervisors_1.name"],
    )
    second = sf.get_science_filtered_lineage_context(
        df=df,
        base_idx={},
        db_signature=("db", 1.0, 1),
        selected_ids=["pedagogy", "technical"],
        supervisor_columns=["supervisors_1.name"],
    )

    assert first is second
    assert first.science_field_ids == ("pedagogy", "technical")
    assert calls["index"] == 1


def test_different_filter_has_different_context_key():
    from core.ui import science_filtering as sf

    sf._get_science_filtered_lineage_context_cached.clear()
    df = _base_df()
    technical = sf.get_science_filtered_lineage_context(
        df=df,
        base_idx={},
        db_signature=("db", 1.0, 1),
        selected_ids=["technical"],
        supervisor_columns=["supervisors_1.name"],
    )
    pedagogy = sf.get_science_filtered_lineage_context(
        df=df,
        base_idx={},
        db_signature=("db", 1.0, 1),
        selected_ids=["pedagogy"],
        supervisor_columns=["supervisors_1.name"],
    )

    assert technical.cache_key != pedagogy.cache_key
    assert technical.all_supervisor_names == ("Тех Руководитель",)
    assert pedagogy.all_supervisor_names == ("Пед Руководитель",)
