from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from core.db.imrad import load_imrad_embedding_options, load_imrad_text_index
from tabs.articles.imrad_search import filter_imrad_index, resolve_matrix_path, search_similar_units
from tabs.articles.tab import ARTICLE_MODE_LABELS


def _seed_imrad_db(path: Path, matrix_rel: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE article_imrad_units (unit_id TEXT, article_id TEXT, unit_level TEXT, imrad_block TEXT, imrad_subblock TEXT, rhetorical_zone_type TEXT, confidence REAL, is_weak INTEGER, is_inferred INTEGER, source_zone_ids_json TEXT, source_file TEXT);
        CREATE TABLE article_imrad_unit_texts (text_id TEXT, unit_id TEXT, article_id TEXT, language TEXT, text_role TEXT, text TEXT, keywords_json TEXT);
        CREATE TABLE article_embedding_models (embedding_model_id TEXT, provider TEXT, model_name TEXT, model_version TEXT, dimensions INTEGER, distance_metric TEXT);
        CREATE TABLE article_imrad_embedding_files (matrix_file_id TEXT, embedding_model_id TEXT, language TEXT, text_role TEXT, file_path TEXT, matrix_shape TEXT, dtype TEXT, normalized INTEGER, output_format TEXT);
        CREATE TABLE article_imrad_embeddings (text_id TEXT, embedding_model_id TEXT, language TEXT, dimensions INTEGER, vector_storage TEXT, matrix_file_id TEXT, matrix_row INTEGER, vector_norm REAL);
        """
    )
    conn.execute("INSERT INTO article_embedding_models VALUES ('m1','hf','e5','1',3,'cosine')")
    conn.execute("INSERT INTO article_imrad_embedding_files VALUES ('f1','m1','en','compact_en', ?, '(3,3)', 'float32', 1, 'npy')", (matrix_rel,))
    rows = [
        ("u1", "a1", "unit", "methods", "design", "zone", 0.9, 0, 0, "[]", "src"),
        ("u2", "a2", "unit", "results", "main", "zone", 0.8, 1, 0, "[]", "src"),
        ("u3", "a3", "unit", "results", "main", "zone", 0.4, 0, 1, "[]", "src"),
    ]
    for r in rows:
        conn.execute("INSERT INTO article_imrad_units VALUES (?,?,?,?,?,?,?,?,?,?,?)", r)
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t1','u1','a1','en','compact_en','txt1','[]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t2','u2','a2','en','compact_en','txt2','[]')")
    conn.execute("INSERT INTO article_imrad_unit_texts VALUES ('t3','u3','a3','en','compact_en','txt3','[]')")
    conn.execute("INSERT INTO article_imrad_embeddings VALUES ('t1','m1','en',3,'matrix','f1',0,1.0)")
    conn.execute("INSERT INTO article_imrad_embeddings VALUES ('t2','m1','en',3,'matrix','f1',1,1.0)")
    conn.execute("INSERT INTO article_imrad_embeddings VALUES ('t3','m1','en',3,'matrix','f1',2,1.0)")
    conn.commit(); conn.close()


def test_imrad_loaders_and_search(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / 'genealogy.db'
    mat = np.array([[1,0,0],[0.9,0.1,0],[0,1,0]], dtype=np.float32)
    np.save(tmp_path / 'm.npy', mat)
    _seed_imrad_db(db, 'm.npy')
    monkeypatch.setenv('SQLITE_DB_PATH', str(db))

    opts = load_imrad_embedding_options()
    assert not opts.empty
    idx = load_imrad_text_index('en', 'compact_en', 'm1', 'f1')
    assert set(['text_id', 'unit_id', 'article_id', 'matrix_row']).issubset(idx.columns)

    resolved = resolve_matrix_path('m.npy')
    assert resolved == (tmp_path / 'm.npy').resolve()

    target = filter_imrad_index(idx, include_weak=False, include_inferred=False, min_confidence=0.5)
    assert target['unit_id'].tolist() == ['u1']

    result = search_similar_units(0, mat, idx, idx[idx['unit_id'] != 'u1'], 2)
    assert result.iloc[0]['unit_id'] == 'u2'
    assert result['similarity'].tolist()[0] >= result['similarity'].tolist()[1]


def test_missing_matrix_file_controlled_error(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / 'genealogy.db'
    _seed_imrad_db(db, 'missing.npy')
    monkeypatch.setenv('SQLITE_DB_PATH', str(db))
    from tabs.articles.imrad_search import load_embedding_matrix
    try:
        load_embedding_matrix(resolve_matrix_path('missing.npy'))
        assert False
    except FileNotFoundError:
        assert True


def test_tab_mode_and_lazy_import() -> None:
    assert ARTICLE_MODE_LABELS['semantic_imrad_search'] == 'Семантический поиск по зонам'
    import tabs.articles.semantic_imrad_mode as mod
    assert hasattr(mod, 'render_semantic_imrad_search_mode')
    assert 'sentence_transformers' not in importlib.sys.modules


def test_load_article_units_without_optional_tables(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / 'genealogy.db'
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE article_imrad_units (unit_id TEXT, article_id TEXT, unit_level TEXT, imrad_block TEXT, imrad_subblock TEXT, rhetorical_zone_type TEXT, confidence REAL, is_weak INTEGER, is_inferred INTEGER, source_zone_ids_json TEXT, source_file TEXT)")
    conn.execute("INSERT INTO article_imrad_units VALUES ('u1','a1','unit','intro','gap','zone',0.7,0,0,'[]','src')")
    conn.commit(); conn.close()
    monkeypatch.setenv('SQLITE_DB_PATH', str(db))
    from core.db.imrad import load_article_imrad_units
    df = load_article_imrad_units('a1', language='en', text_role='compact_en')
    assert not df.empty
    assert df.iloc[0]['unit_id'] == 'u1'
