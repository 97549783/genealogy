from __future__ import annotations

import numpy as np
import pandas as pd

from tabs.articles.metrics import compute_block_score_summary, compute_keyword_overlap, cosine_similarity_safe


def test_compute_block_score_summary_hides_rows_below_default_threshold() -> None:
    df = pd.DataFrame({"1.1.1": [2.0, 2.5], "2.2": [3.5, 4.0]})
    blocks = [{"code": "1.1.1", "label": "Первый блок"}, {"code": "2.2", "label": "Второй блок"}]

    result = compute_block_score_summary(df, blocks)

    assert result["Блок"].tolist() == ["Второй блок"]


def test_compute_block_score_summary_shows_all_when_requested_by_caller() -> None:
    df = pd.DataFrame({"1.1.1": [2.0, 2.5], "2.2": [3.5, 4.0]})
    blocks = [{"code": "1.1.1", "label": "Первый блок"}, {"code": "2.2", "label": "Второй блок"}]

    result = compute_block_score_summary(df, blocks, show_all=True)

    assert result["Блок"].tolist() == ["Первый блок", "Второй блок"]


def test_compute_keyword_overlap_returns_count_and_jaccard() -> None:
    result = compute_keyword_overlap({"Информатика", "Образование"}, {"информатика", "Школа"})

    assert result["intersection_count"] == 1
    assert result["jaccard"] == 1 / 3
    assert result["intersection_keywords"] == ["информатика"]


def test_cosine_similarity_safe_returns_zero_for_zero_vectors() -> None:
    assert cosine_similarity_safe(np.array([0.0, 0.0]), np.array([1.0, 2.0])) == 0.0
