from __future__ import annotations

import pandas as pd

from tabs.profiles.entropy import interpret_entropy, search_by_entropy


def test_entropy_module_import_and_search_smoke() -> None:
    scores_df = pd.DataFrame([
        {"Code": "A1", "1.1": 4.0, "1.2": 0.0},
        {"Code": "A2", "1.1": 2.0, "1.2": 2.0},
    ])

    result = search_by_entropy(
        scores_df=scores_df,
        feature_columns=["1.1", "1.2"],
        use_hierarchical=False,
        min_threshold=0.0,
        ascending=True,
    )

    assert list(result["Code"]) == ["A1", "A2"]
    assert "entropy" in result.columns
    assert interpret_entropy(float(result.iloc[0]["entropy"]))
