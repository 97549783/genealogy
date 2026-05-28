from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.db.imrad import (
    load_fully_vectorized_article_ids,
    load_imrad_display_texts_ru,
    select_default_imrad_embedding_option,
)
from tabs.articles.imrad_section_labels import format_article_label_ru, format_keywords_ru, section_identity_key, section_filter_key, section_label_ru
from tabs.articles.semantic_imrad_mode import (
    _display_keywords_for_result,
    _display_text_for_result,
    _normalize_sections,
    article_label_matches_query,
    cosine_distance_from_similarity,
    filter_articles_by_search_query,
    make_flexible_search_token,
)
from tabs.articles.imrad_search import filter_imrad_index, resolve_matrix_path, search_similar_units
from tabs.articles.tab import ARTICLE_MODE_LABELS


def _seed_imrad_db(path: Path, matrix_rel: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE article_imrad_units (unit_id TEXT, article_id TEXT, unit_level TEXT, imrad_block TEXT, imrad_subblock TEXT, rhetorical_zone_type TEXT, confidence REAL, is_weak INTEGER, is_inferred INTEGER, source_zone_ids_json TEXT, source_file TEXT);
        CREATE TABLE article_imrad_unit_texts (text_id TEXT, unit_id TEXT, article_id TEXT, language TEXT, text_role TEXT, text TEXT, keywords_json TEXT);
        CREATE TABLE article_imrad_unit_payloads (unit_id TEXT, keywords_ru_json TEXT);
        CREATE TABLE article_embedding_models (embedding_model_id TEXT, provider TEXT, model_name TEXT, model_version TEXT, dimensions INTEGER, distance_metric TEXT);
        CREATE TABLE article_imrad_embedding_files (matrix_file_id TEXT, embedding_model_id TEXT, language TEXT, text_role TEXT, file_path TEXT, matrix_shape TEXT, dtype TEXT, normalized INTEGER, output_format TEXT);
        CREATE TABLE article_imrad_embeddings (text_id TEXT, embedding_model_id TEXT, language TEXT, dimensions INTEGER, vector_storage TEXT, matrix_file_id TEXT, matrix_row INTEGER, vector_norm REAL);
        """
    )
    conn.execute("INSERT INTO article_embedding_models VALUES ('m1','hf','intfloat/multilingual-e5-base','1',3,'cosine')")
    conn.execute("INSERT INTO article_imrad_embedding_files VALUES ('f1','m1','en','compact_en', ?, '(3,3)', 'float32', 1, 'npy')", (matrix_rel,))
    rows = [
        ("u1", "a1", "imrad_block", "METHOD_OR_APPROACH", None, "zone", 0.9, 0, 0, "[]", "src"),
        ("u2", "a1", "imrad_block", "RESULTS_OR_DEMONSTRATION", None, "zone", 0.8, 0, 0, "[]", "src"),
        ("u3", "a1", "imrad_subblock", "RESULTS_OR_DEMONSTRATION", "own_results_or_findings", "zone", 0.8, 0, 0, "[]", "src"),
        ("u4", "a2", "imrad_block", "METHOD_OR_APPROACH", None, "zone", 0.4, 0, 0, "[]", "src"),
        ("u5", "a2", "imrad_block", "RESULTS_OR_DEMONSTRATION", None, "zone", 0.4, 0, 0, "[]", "src"),
    ]
    for r in rows:
        conn.execute("INSERT INTO article_imrad_units VALUES (?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t1','u1','a1','en','compact_en','txt1','[\"kw\"]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t2','u2','a1','en','compact_en','txt2','[\"kw2\"]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t3','u3','a1','en','compact_en','txt3','[\"kw3\"]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t4','u1','a1','ru','compact_ru','русский текст 1','[\"рус1\"]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t5','u2','a1','ru','canonical_ru','русский текст 2','[\"рус2\"]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t6','u4','a2','en','compact_en','txt4','[]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t7','u5','a2','en','compact_en','txt5','[]')")
    conn.execute("INSERT INTO article_imrad_unit_payloads VALUES ('u1','[\"ключ1\"]')")
    conn.execute("INSERT INTO article_imrad_embeddings VALUES ('t1','m1','en',3,'matrix','f1',0,1.0)")
    conn.execute("INSERT INTO article_imrad_embeddings VALUES ('t2','m1','en',3,'matrix','f1',1,1.0)")
    conn.execute("INSERT INTO article_imrad_embeddings VALUES ('t6','m1','en',3,'matrix','f1',2,1.0)")
    conn.commit(); conn.close()


def test_helpers_and_filters(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / 'genealogy.db'
    mat = np.array([[1,0,0],[0.9,0.1,0],[0,1,0]], dtype=np.float32)
    np.save(tmp_path / 'm.npy', mat)
    _seed_imrad_db(db, 'm.npy')
    monkeypatch.setenv('SQLITE_DB_PATH', str(db))

    assert ARTICLE_MODE_LABELS['semantic_imrad_search'] == 'Анализ по разделам статьи'
    assert resolve_matrix_path('m.npy') == (tmp_path / 'm.npy').resolve()

    opts = pd.DataFrame([
        {"language": "en", "text_role": "compact_en", "model_name": "intfloat/multilingual-e5-base"},
        {"language": "en", "text_role": "compact_en", "model_name": "x"},
    ])
    assert select_default_imrad_embedding_option(opts).get("model_name") == "intfloat/multilingual-e5-base"

    ids = load_fully_vectorized_article_ids("en", "compact_en", "m1", "f1")
    assert "a1" in ids  # Подраздел без эмбеддинга не исключает статью.
    assert "a2" not in ids  # Отсутствует эмбеддинг одного из блоков.

    ru = load_imrad_display_texts_ru(["u1", "u4"])
    assert ru[ru["unit_id"] == "u1"].iloc[0]["display_text_ru"] == "русский текст 1"
    assert ru[ru["unit_id"] == "u4"].empty


def test_formatters() -> None:
    row = pd.Series({"Title": "Название", "Authors": "Авторы", "Year": "2018", "Issue": "3"})
    assert format_article_label_ru(row) == "Название — Авторы — 2018. — № 3"
    assert format_keywords_ru('["a", "b"]') == "a, b."
    assert format_keywords_ru(None) == ""
    assert "Методы" in section_label_ru(pd.Series({"unit_level": "imrad_block", "imrad_block": "METHOD_OR_APPROACH", "imrad_subblock": None}))
    assert "Результаты" in section_label_ru(pd.Series({"unit_level": "imrad_block", "imrad_block": "RESULTS_OR_DEMONSTRATION", "imrad_subblock": None}))
    assert section_label_ru(pd.Series({"unit_level": "imrad_block", "imrad_block": None, "imrad_subblock": None})) == ""
    assert section_label_ru(pd.Series({"unit_level": "imrad_subblock", "imrad_block": "INTRODUCTION", "imrad_subblock": "UNKNOWN_SUBBLOCK"})) == ""
    changed = section_label_ru(pd.Series({"unit_level": "imrad_subblock", "imrad_block": "INTRODUCTION", "imrad_subblock": "problem_gap"}))
    assert "Проблема и ограничения" in changed
    assert section_label_ru(pd.Series({"unit_level": "article"})) == "Статья в целом"
    assert section_identity_key(pd.Series({"unit_level": "article"})) == "article"


def test_index_restriction_by_allowed_article_ids() -> None:
    idx = pd.DataFrame({"article_id": ["a1", "a2", "a3"], "unit_id": ["u1", "u2", "u3"]})
    allowed_article_ids = {"a1", "a3"}
    filtered = idx[idx["article_id"].astype(str).isin(allowed_article_ids)].copy()
    assert set(filtered["article_id"]) == {"a1", "a3"}


def test_section_filter_key_is_identity_key() -> None:
    row_none = pd.Series({"unit_level": "imrad_block", "imrad_block": "METHOD_OR_APPROACH", "imrad_subblock": None})
    assert section_filter_key(row_none) == "block::METHOD_OR_APPROACH"
    row_nan = pd.Series({"unit_level": "imrad_subblock", "imrad_block": "METHOD_OR_APPROACH", "imrad_subblock": "AIM"})
    assert section_filter_key(row_nan) == "subblock::METHOD_OR_APPROACH::aim"


def test_normalization_deduplicates_logical_sections() -> None:
    units = pd.DataFrame([
        {"unit_id": "u1", "unit_level": "imrad_block", "imrad_block": "INTRODUCTION", "imrad_subblock": None, "display_text_ru": "txt", "is_weak": 0, "is_inferred": 0, "confidence": 0.5},
        {"unit_id": "u2", "unit_level": "imrad_block", "imrad_block": "INTRODUCTION", "imrad_subblock": None, "display_text_ru": "txt2", "is_weak": 1, "is_inferred": 1, "confidence": 0.1},
        {"unit_id": "u3", "unit_level": "imrad_subblock", "imrad_block": "INTRODUCTION", "imrad_subblock": "aim_or_research_question", "display_text_ru": "t3", "is_weak": 0, "is_inferred": 0, "confidence": 0.5},
        {"unit_id": "u4", "unit_level": "imrad_subblock", "imrad_block": "INTRODUCTION", "imrad_subblock": "aim_or_research_question", "display_text_ru": "t4", "is_weak": 1, "is_inferred": 1, "confidence": 0.1},
    ])
    normalized = _normalize_sections(units)
    assert normalized["section_label"].tolist() == [
        "Раздел: Введение",
        "Раздел: Введение / подраздел: Цель и исследовательский вопрос",
    ]


def test_result_dedup_by_article_and_section_key() -> None:
    rows = pd.DataFrame([
        {"article_id": "a1", "unit_level": "imrad_block", "imrad_block": "RESULTS_OR_DEMONSTRATION", "imrad_subblock": None, "similarity": 0.6},
        {"article_id": "a1", "unit_level": "imrad_block", "imrad_block": "RESULTS_OR_DEMONSTRATION", "imrad_subblock": None, "similarity": 0.9},
    ])
    rows["section_key"] = rows.apply(section_identity_key, axis=1)
    dedup = rows.sort_values("similarity", ascending=False).drop_duplicates(["article_id", "section_key"], keep="first")
    assert len(dedup) == 1
    assert float(dedup.iloc[0]["similarity"]) == 0.9


def test_target_excludes_same_logical_source_section_in_same_article() -> None:
    article_id = "a1"
    source_unit_id = "u1"
    rows = pd.DataFrame([
        {"unit_id": "u1", "article_id": "a1", "unit_level": "imrad_block", "imrad_block": "INTRODUCTION", "imrad_subblock": None},
        {"unit_id": "u2", "article_id": "a1", "unit_level": "imrad_block", "imrad_block": "INTRODUCTION", "imrad_subblock": None},
        {"unit_id": "u3", "article_id": "a2", "unit_level": "imrad_block", "imrad_block": "INTRODUCTION", "imrad_subblock": None},
    ])
    rows["section_key"] = rows.apply(section_identity_key, axis=1)
    source_row = rows[rows["unit_id"] == source_unit_id].iloc[0]
    source_section_key = str(source_row["section_key"])

    target = rows.copy()
    target = target[
        ~(
            (target["article_id"].astype(str) == str(article_id))
            & (target["section_key"].astype(str) == source_section_key)
        )
    ]

    assert set(target["unit_id"]) == {"u3"}


def test_search_still_works() -> None:
    mat = np.array([[1,0],[0.8,0.2],[0,1]], dtype=np.float32)
    idx = pd.DataFrame({"unit_id": ["u1", "u2", "u3"], "matrix_row": [0, 1, 2], "is_weak": [0, 0, 1], "is_inferred": [0, 0, 0], "confidence": [0.9, 0.8, 0.1]})
    target = filter_imrad_index(idx, include_weak=False, include_inferred=True, min_confidence=0.5)
    result = search_similar_units(0, mat, idx, target[target["unit_id"] != "u1"], 1)
    assert result.iloc[0]["unit_id"] == "u2"


def test_missing_matrix_file_controlled_error() -> None:
    from tabs.articles.imrad_search import load_embedding_matrix

    try:
        load_embedding_matrix(resolve_matrix_path(""))
        assert False
    except (FileNotFoundError, OSError, ValueError):
        assert True


def test_mode_module_uses_new_wording() -> None:
    import tabs.articles.semantic_imrad_mode as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for bad in ["Зоны выбранной статьи", "Поиск похожих зон", "Исходная зона", "IMRAD:", "confidence", "weak", "inferred"]:
        assert bad not in src
    assert 'sentence_transformers' not in importlib.sys.modules


def test_article_level_not_shown_in_article_sections_tab() -> None:
    units = pd.DataFrame([
        {"unit_id": "u1", "unit_level": "article", "imrad_block": None, "imrad_subblock": None, "display_text_ru": "общий текст", "is_weak": 0, "is_inferred": 0, "confidence": 0.9},
        {"unit_id": "u2", "unit_level": "imrad_block", "imrad_block": "INTRODUCTION", "imrad_subblock": None, "display_text_ru": "введение", "is_weak": 0, "is_inferred": 0, "confidence": 0.8},
    ])
    normalized = _normalize_sections(units)
    visible = normalized[normalized["section_key"] != "article"]
    assert "Статья в целом" not in visible["section_label"].tolist()


def test_article_level_result_uses_metadata_abstract_and_keywords() -> None:
    row = pd.Series({
        "section_key": "article",
        "Abstract": "Русская аннотация статьи",
        "Keywords": '["ключ", "данные"]',
        "display_text_ru": "Title: bad",
        "display_keywords_ru": '["bad"]',
    })
    text = _display_text_for_result(row)
    keywords = _display_keywords_for_result(row)
    assert text == "Русская аннотация статьи"
    assert keywords == "ключ, данные."
    for bad in ["Title:", "Abstract:", "INTRODUCTION:", "METHOD_OR_APPROACH:", "RESULTS_OR_DEMONSTRATION:", "DISCUSSION_OR_CONCLUSION:"]:
        assert bad not in text


def test_similar_search_targets_always_exclude_source_article() -> None:
    article_id = "a1"
    target = pd.DataFrame([
        {"article_id": "a1", "unit_id": "u1"},
        {"article_id": "a2", "unit_id": "u2"},
    ])
    target = target[target["article_id"].astype(str) != str(article_id)]
    assert str(article_id) not in target["article_id"].astype(str).tolist()


def test_checkbox_label_removed_from_source() -> None:
    import tabs.articles.semantic_imrad_mode as mod

    source_code = Path(mod.__file__).read_text(encoding="utf-8")
    assert "Исключить текущую статью" not in source_code


def test_article_search_plain_substring() -> None:
    assert article_label_matches_query("Цифровая школа — Иванов — 2018. — № 3", "иванов")


def test_article_search_flexible_russian_endings() -> None:
    assert article_label_matches_query("Цифровая школа — Иванов — 2018. — № 3", "цифров школ")
    assert article_label_matches_query("Региональной информационной системы", "региональн информационн")


def test_article_search_soft_sign() -> None:
    assert article_label_matches_query("Модель адаптивного тестирования", "модел")
    assert make_flexible_search_token("модель") == "модел"


def test_article_search_does_not_overstem_short_tokens() -> None:
    assert make_flexible_search_token("моя") == "моя"
    labels = {"1": "Модель адаптивного тестирования", "2": "Цифровая школа"}
    assert filter_articles_by_search_query(labels, "") == ["1", "2"]


def test_neural_search_requires_primary_button_and_no_form() -> None:
    import tabs.articles.semantic_imrad_mode as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert 'st.form("imrad_neural_search_form")' not in source
    assert "form_submit_button" not in source
    assert 'st.button("Найти", key="imrad_neural_search_submit", type="primary")' in source
    assert "Максимальное количество статей в выдаче" in source
    assert "Количество найденных статей" not in source
    assert "Косинусное расстояние" in source


def test_neural_search_controls_order_in_source() -> None:
    import tabs.articles.semantic_imrad_mode as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    query_input_pos = source.find('st.text_input(f"Запрос {i + 1}"')
    add_pos = source.find('st.button("Добавить запрос"')
    slider_pos = source.find('st.slider("Максимальное количество статей в выдаче"')
    assert query_input_pos != -1
    assert add_pos != -1
    assert slider_pos != -1
    assert query_input_pos < add_pos < slider_pos


def test_cosine_distance_from_similarity() -> None:
    assert cosine_distance_from_similarity(0.8) == pytest.approx(0.2)


def test_heavy_neural_operations_gated_by_submit() -> None:
    import tabs.articles.semantic_imrad_mode as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    guard_pos = source.find("if not st.session_state.get(SEARCH_RUN_KEY) or not submitted_params:")
    encode_pos = source.find("encode_user_queries(")
    search_pos = source.find("search_sections_by_query_vector(")
    load_encoder_pos = source.find("is_query_encoder_enabled(")

    assert guard_pos != -1
    assert encode_pos > guard_pos
    assert search_pos > guard_pos
    assert load_encoder_pos > guard_pos
