from __future__ import annotations

import importlib
import sqlite3

import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs.dissertations.search import filter_dissertations, get_available_criteria


def _create_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE diss_metadata (Code TEXT, candidate_name TEXT, title TEXT, institution_prepared TEXT, leading_organization TEXT, defense_location TEXT, city TEXT, year TEXT, `supervisors_1.name` TEXT, `supervisors_2.name` TEXT, `opponents_1.name` TEXT, `opponents_2.name` TEXT, `opponents_3.name` TEXT, `specialties_1.code` TEXT, `specialties_1.name` TEXT, `specialties_2.code` TEXT, `specialties_2.name` TEXT)"
    )
    conn.executemany(
        "INSERT INTO diss_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("1", "Иванов И.И.", "Анализ методики", "МГУ", "РАН", "Москва", "Москва", "2020", "Петров П.П.", "", "Сидоров С.С.", "", "", "13.00.01", "Общая педагогика", "", ""),
            ("2", "Смирнова А.А.", "Цифровая дидактика", "СПбГУ", "НИУ ВШЭ", "Санкт-Петербург", "Санкт-Петербург", "2021", "Кузнецов К.К.", "", "Орлова О.О.", "", "", "13.00.08", "Теория и методика проф. образования", "", ""),
        ],
    )
    conn.commit()
    conn.close()


def test_filter_dissertations_supports_all_required_criteria(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    import core.db.dissertations as dissertations
    importlib.reload(dissertations)

    assert len(filter_dissertations(None, {"title": "методики"})) == 1
    assert len(filter_dissertations(None, {"supervisors": "петров"})) == 1
    assert len(filter_dissertations(None, {"opponents": "орлова"})) == 1
    assert len(filter_dissertations(None, {"city": "санкт"})) == 1
    assert len(filter_dissertations(None, {"year": "2020"})) == 1
    assert len(filter_dissertations(None, {"specialties": "13.00.08"})) == 1


def test_tab_hydrates_query_and_builds_share_payload(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_string(
        """
import streamlit as st
import pandas as pd
import tabs.dissertations.tab as diss_tab


def _fake_share(payload, key):
    st.session_state["_captured_share_payload"] = payload
    st.session_state["_captured_share_key"] = key


def _fake_render(**kwargs):
    st.session_state["_captured_render_kwargs"] = kwargs


diss_tab.share_params_button = _fake_share
diss_tab.render_dissertations_widget = _fake_render

sample_df = pd.DataFrame([{"title": "x"}])

diss_tab.render_dissertations_tab(sample_df)
"""
    )

    app.query_params["diss_criterion"] = ["title"]
    app.query_params["diss_title"] = "метод"

    app.run()

    assert app.session_state["diss_search_query_hydrated"] is True
    assert app.session_state["dissertation_search_criteria"] == ["title"]
    assert app.session_state["diss_search_title"] == "метод"
    assert app.session_state["diss_search_should_run"] is True
    assert len(app.session_state["diss_search_result"]) == 1


def test_criteria_dictionary_contract() -> None:
    criteria = get_available_criteria()
    assert list(criteria.keys()) == [
        "title",
        "candidate_name",
        "supervisors",
        "opponents",
        "institution_prepared",
        "leading_organization",
        "defense_location",
        "city",
        "year",
        "specialties",
    ]


def test_dissertations_tab_passes_use_fuzzy_and_adds_mode_to_share_payload(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "genealogy.db"
    _create_db(db_path)
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    app = AppTest.from_string(
        """
import streamlit as st
import pandas as pd
import tabs.dissertations.tab as diss_tab

def _fake_filter(df, search_params, use_fuzzy=False):
    st.session_state["_captured_use_fuzzy"] = use_fuzzy
    return pd.DataFrame([{"Code": "1", "candidate_name": "Иванов И.И.", "title": "Тест"}])

def _fake_share(payload, key):
    st.session_state["_captured_share_payload"] = payload

def _fake_render(**kwargs):
    pass

diss_tab.filter_dissertations = _fake_filter
diss_tab.share_params_button = _fake_share
diss_tab.render_dissertations_widget = _fake_render

sample_df = pd.DataFrame([{"title": "x"}])
diss_tab.render_dissertations_tab(sample_df)
"""
    )
    app.query_params["diss_criterion"] = ["title"]
    app.query_params["diss_title"] = "метод"
    app.query_params["diss_text_search_mode"] = "fuzzy"
    app.run()
    assert app.session_state["_captured_use_fuzzy"] is True
    assert app.session_state["_captured_share_payload"]["diss_text_search_mode"] == "fuzzy"
