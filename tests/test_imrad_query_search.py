from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from tabs.articles.imrad_query_search import (
    average_query_vectors,
    collect_non_empty_queries,
    encode_user_queries,
    search_sections_by_query_vector,
    softmax_percentages,
)
from tabs.articles.imrad_section_labels import section_identity_key
from tabs.articles.semantic_imrad_mode import _display_keywords_for_result, _display_text_for_result, _normalize_sections_per_article


def test_collect_non_empty_queries() -> None:
    assert collect_non_empty_queries(["", "  "]) == []
    assert collect_non_empty_queries(["a", "b", "c", "d", "e", "f"]) == ["a", "b", "c", "d", "e"]


def test_average_vector_ranking() -> None:
    query_vectors = np.array([[1.0, 0.0], [0.8, 0.2]], dtype=np.float32)
    target = pd.DataFrame({"matrix_row": [0, 1], "article_id": ["a1", "a2"], "section_key": ["x", "x"]})
    matrix = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    result = search_sections_by_query_vector(query_vectors, matrix, target, 2, normalized=True)
    assert result.iloc[0]["article_id"] == "a1"


def test_softmax_percentages() -> None:
    weights = softmax_percentages(np.array([2.0, 1.0]))
    assert round(float(weights.sum())) == 100
    assert weights[0] > weights[1]


def test_target_section_filtering() -> None:
    rows = pd.DataFrame([
        {"unit_level": "imrad_block", "imrad_block": "RESULTS_OR_DEMONSTRATION", "imrad_subblock": None},
        {"unit_level": "imrad_block", "imrad_block": "METHOD_OR_APPROACH", "imrad_subblock": None},
    ])
    rows["section_key"] = rows.apply(section_identity_key, axis=1)
    filtered = rows[rows["section_key"] == "block::RESULTS_OR_DEMONSTRATION"]
    assert len(filtered) == 1


def test_no_sentence_transformers_import_on_module_import() -> None:
    import tabs.articles.semantic_imrad_mode  # noqa: F401

    assert "sentence_transformers" not in sys.modules


def test_encode_queries_uses_query_prefix(monkeypatch) -> None:
    captured = {}

    class Dummy:
        def encode(self, values, normalize_embeddings=True):
            captured["values"] = values
            return np.array([[1.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("tabs.articles.imrad_query_search.load_query_encoder", lambda model_name, device: Dummy())
    vec = encode_user_queries(["русский запрос"], "m", True)
    assert vec.shape == (1, 2)
    assert captured["values"] == ["query: русский запрос"]


def test_average_query_vectors_normalized() -> None:
    out = average_query_vectors(np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32))
    assert np.allclose(out, np.array([1.0, 0.0], dtype=np.float32))


def test_target_normalization_keeps_multiple_articles_same_section() -> None:
    rows = pd.DataFrame([
        {"unit_id": "u1", "article_id": "a1", "unit_level": "imrad_block", "imrad_block": "RESULTS_OR_DEMONSTRATION", "imrad_subblock": None, "is_weak": 0, "is_inferred": 0, "confidence": 0.9},
        {"unit_id": "u2", "article_id": "a2", "unit_level": "imrad_block", "imrad_block": "RESULTS_OR_DEMONSTRATION", "imrad_subblock": None, "is_weak": 0, "is_inferred": 0, "confidence": 0.8},
    ])
    normalized = _normalize_sections_per_article(rows)
    assert len(normalized) == 2


def test_non_article_results_receive_display_text_and_not_filtered() -> None:
    result = pd.DataFrame([
        {"section_key": "block::METHOD_OR_APPROACH", "display_text_ru": "Русский текст раздела", "display_keywords_ru": '["ключ"]'}
    ])
    result["render_text_ru"] = result.apply(_display_text_for_result, axis=1)
    result["render_keywords_ru"] = result.apply(_display_keywords_for_result, axis=1)
    visible = result[result["render_text_ru"].astype(str).str.strip() != ""]
    assert len(visible) == 1
    assert visible.iloc[0]["render_text_ru"] == "Русский текст раздела"


def test_article_level_result_still_uses_metadata() -> None:
    row = pd.Series({
        "section_key": "article",
        "Abstract": "Оригинальная аннотация",
        "Keywords": '["k1", "k2"]',
        "display_text_ru": "Служебный текст",
        "display_keywords_ru": '["служебное"]',
    })
    assert _display_text_for_result(row) == "Оригинальная аннотация"
    assert _display_keywords_for_result(row) == "k1, k2."


def test_encode_queries_receives_selected_normalized_flag(monkeypatch) -> None:
    captured = {}

    class Dummy:
        def encode(self, values, normalize_embeddings=True):
            captured["normalize_embeddings"] = normalize_embeddings
            return np.array([[1.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("tabs.articles.imrad_query_search.load_query_encoder", lambda model_name, device: Dummy())
    encode_user_queries(["тест"], "model", False)
    assert captured["normalize_embeddings"] is False
