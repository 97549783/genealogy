from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from core.db.imrad import (
    load_fully_vectorized_article_ids,
    load_imrad_display_texts_ru,
    select_default_imrad_embedding_option,
)
from tabs.articles.imrad_section_labels import format_article_label_ru, format_keywords_ru, section_identity_key, section_filter_key, section_label_ru
from tabs.articles.semantic_imrad_mode import _normalize_sections
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
