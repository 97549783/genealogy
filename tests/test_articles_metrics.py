from __future__ import annotations

import numpy as np
import pandas as pd

from tabs.articles.metrics import compute_block_score_summary, compute_keyword_overlap, cosine_similarity_safe
from tabs.articles.query_params import parse_float_param, parse_int_param
from tabs.articles.single_school_mode import compute_found_school_author_initials


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


def test_compute_found_school_author_initials_counts_only_authors_in_articles() -> None:
    dataset = pd.DataFrame({"Authors": ["Иванов И.И.; Сидоров С.С.", "Петров П.П."]})

    result = compute_found_school_author_initials(dataset, {"иванов и.и.", "кузнецов к.к."})

    assert result == {"иванов и.и."}


def test_query_param_parsers_use_defaults_for_invalid_values() -> None:
    assert parse_float_param("abc", 3.0) == 3.0
    assert parse_int_param("x", 20) == 20
