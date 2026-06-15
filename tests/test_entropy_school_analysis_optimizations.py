from __future__ import annotations

import math

import pandas as pd
from pandas.testing import assert_frame_equal

from tabs.profiles.entropy import (
    build_hierarchy_from_codes,
    calculate_entropy_hierarchical,
    calculate_entropy_shannon,
    search_by_entropy,
)
from tabs.school_analysis.analysis import (
    DEGREE_LEVEL_COLUMN,
    YEAR_COLUMN,
    compute_overview,
    compute_yearly_stats,
)


def _legacy_search_by_entropy(
    scores_df: pd.DataFrame,
    feature_columns: list[str],
    use_hierarchical: bool = False,
    min_threshold: float = 0.0,
    ascending: bool = True,
) -> pd.DataFrame:
    """Повторяет прежний построчный алгоритм для проверки совместимости."""
    results = []
    hierarchy = build_hierarchy_from_codes(feature_columns) if use_hierarchical else None

    for _, row in scores_df.iterrows():
        profile_dict = {}
        for col in feature_columns:
            try:
                val = row[col]
                profile_dict[col] = 0.0 if pd.isna(val) else float(val)
            except (ValueError, TypeError):
                profile_dict[col] = 0.0

        profile = pd.Series(profile_dict)
        if use_hierarchical and hierarchy:
            entropy = calculate_entropy_hierarchical(profile, hierarchy, min_threshold)
        else:
            entropy = calculate_entropy_shannon(profile, min_threshold)

        results.append(
            {
                "Code": str(row["Code"]),
                "entropy": float(entropy),
                "features_count": int(
                    sum(1 for v in profile.values if v >= min_threshold)
                ),
            }
        )

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        results_df = results_df.sort_values(by="entropy", ascending=ascending)
    return results_df


def test_search_by_entropy_matches_legacy_edge_values() -> None:
    scores_df = pd.DataFrame(
        {
            "Code": ["A", "B", "C", "D"],
            "1": [1, 0, None, "bad"],
            "1.1": [1, 0, 2, "3"],
            "1.2": [0, 0, 2, None],
        }
    )
    feature_columns = ["1", "1.1", "1.2"]

    for use_hierarchical in [False, True]:
        for min_threshold in [0.0, 1.0]:
            for ascending in [True, False]:
                result = search_by_entropy(
                    scores_df,
                    feature_columns,
                    use_hierarchical=use_hierarchical,
                    min_threshold=min_threshold,
                    ascending=ascending,
                ).reset_index(drop=True)
                expected = _legacy_search_by_entropy(
                    scores_df,
                    feature_columns,
                    use_hierarchical=use_hierarchical,
                    min_threshold=min_threshold,
                    ascending=ascending,
                ).reset_index(drop=True)

                assert_frame_equal(result, expected)
                assert result["Code"].map(type).eq(str).all()
                assert pd.api.types.is_float_dtype(result["entropy"])
                assert pd.api.types.is_integer_dtype(result["features_count"])
                assert (
                    result["entropy"].is_monotonic_increasing is ascending
                    or result["entropy"].is_monotonic_decreasing is (not ascending)
                )
                zero_entropy = result.loc[result["Code"].eq("B"), "entropy"].iloc[0]
                assert math.isclose(float(zero_entropy), 0.0)


def test_compute_overview_counts_degree_prefixes_vectorized() -> None:
    subset = pd.DataFrame(
        {
            DEGREE_LEVEL_COLUMN: [
                "кандидат",
                "Кандидат наук",
                "кан.",
                "доктор",
                "Доктор наук",
                "док.",
                "",
                None,
            ]
        }
    )

    overview = compute_overview(
        subset=subset,
        root="Иванов И.И.",
        index={},
        lineage_func=lambda *args: None,
        df_full=pd.DataFrame(),
        scope="direct",
    )

    assert overview["candidates"] == 3
    assert overview["doctors"] == 3


def test_compute_yearly_stats_preserves_safe_year_fraction_semantics() -> None:
    subset = pd.DataFrame(
        {
            YEAR_COLUMN: [
                "1980",
                "1980.0",
                1981,
                None,
                "",
                "bad",
                "1900",
                "2100",
                "1900.9",
                "2099.9",
            ],
            DEGREE_LEVEL_COLUMN: [
                "кандидат",
                "доктор",
                "кан.",
                "док.",
                "кандидат",
                "доктор",
                "кандидат",
                "доктор",
                "кандидат",
                "док.",
            ],
        }
    )

    result = compute_yearly_stats(subset)

    expected = pd.DataFrame(
        [
            {"Год": 1980, "Всего": 2, "Кандидатских": 1, "Докторских": 1},
            {"Год": 1981, "Всего": 1, "Кандидатских": 1, "Докторских": 0},
            {"Год": 2099, "Всего": 1, "Кандидатских": 0, "Докторских": 1},
        ]
    )
    assert_frame_equal(result, expected)
