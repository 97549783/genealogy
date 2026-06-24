from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from core.db.dissertation_sections import load_dissertation_section_index, resolve_dissertation_sections_db_path
from tabs.dissertation_characteristics.labels import DISPLAY_SECTION_KEYS, SEARCHABLE_SECTION_KEYS
from tabs.dissertation_characteristics.tab import _linked_df


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE dissertation_section_texts (text_id INTEGER, Code TEXT, section_key TEXT, section_order INTEGER, text TEXT, text_hash TEXT, matrix_row INTEGER)")
    conn.execute("CREATE TABLE dissertation_vector_meta (key TEXT, value TEXT)")
    conn.execute("INSERT INTO dissertation_section_texts VALUES (1, 'A', 'research_goal', 1, 'цель', 'h1', 0)")
    conn.execute("INSERT INTO dissertation_section_texts VALUES (2, 'B', 'research_goal', 1, 'цель', 'h2', 1)")
    conn.execute("INSERT INTO dissertation_vector_meta VALUES ('matrix_file', 'm.npy')")
    conn.commit(); conn.close()
    np.save(path.parent / 'm.npy', np.eye(2, dtype=np.float32))


def test_db_path_resolution_uses_environment(monkeypatch, tmp_path):
    db = tmp_path / "sections.db"
    monkeypatch.setenv("DISSERTATION_SECTIONS_DB_PATH", str(db))
    assert resolve_dissertation_sections_db_path() == db.resolve()


def test_db_path_fallback(monkeypatch):
    monkeypatch.delenv("DISSERTATION_SECTIONS_DB_PATH", raising=False)
    assert str(resolve_dissertation_sections_db_path()).endswith("data-nonsynchronized/dissertation_sections/dissertation_sections.db")


def test_section_key_policy():
    assert "publications" in DISPLAY_SECTION_KEYS
    assert "structure" in DISPLAY_SECTION_KEYS
    assert "publications" not in SEARCHABLE_SECTION_KEYS
    assert "structure" not in SEARCHABLE_SECTION_KEYS


def test_unlinked_records_are_excluded(monkeypatch, tmp_path):
    db = tmp_path / "sections.db"
    _make_db(db)
    monkeypatch.setenv("DISSERTATION_SECTIONS_DB_PATH", str(db))
    index = load_dissertation_section_index()
    main = pd.DataFrame({"Code": ["A"], "candidate_name": ["Автор"]})
    linked = _linked_df(main, index)
    assert linked["Code"].tolist() == ["A"]
