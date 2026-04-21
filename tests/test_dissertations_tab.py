from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from tabs.dissertations.search import filter_dissertations, get_available_criteria


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "title": "Анализ методики",
                "candidate_name": "Иванов И.И.",
                "institution_prepared": "МГУ",
                "leading_organization": "РАН",
                "defense_location": "Москва",
                "city": "Москва",
                "year": "2020",
                "supervisors_1.name": "Петров П.П.",
                "supervisors_2.name": "",
                "opponents_1.name": "Сидоров С.С.",
                "opponents_2.name": "",
                "opponents_3.name": "",
                "specialties_1.code": "13.00.01",
                "specialties_1.name": "Общая педагогика",
                "specialties_2.code": "",
                "specialties_2.name": "",
            },
            {
                "title": "Цифровая дидактика",
                "candidate_name": "Смирнова А.А.",
                "institution_prepared": "СПбГУ",
                "leading_organization": "НИУ ВШЭ",
                "defense_location": "Санкт-Петербург",
                "city": "Санкт-Петербург",
                "year": "2021",
                "supervisors_1.name": "Кузнецов К.К.",
                "supervisors_2.name": "",
                "opponents_1.name": "Орлова О.О.",
                "opponents_2.name": "",
                "opponents_3.name": "",
                "specialties_1.code": "13.00.08",
                "specialties_1.name": "Теория и методика проф. образования",
                "specialties_2.code": "",
                "specialties_2.name": "",
            },
        ]
    )


def test_filter_dissertations_supports_all_required_criteria() -> None:
    df = _sample_df()

    assert len(filter_dissertations(df, {"title": "методики"})) == 1
    assert len(filter_dissertations(df, {"supervisors": "петров"})) == 1
    assert len(filter_dissertations(df, {"opponents": "орлова"})) == 1
    assert len(filter_dissertations(df, {"city": "санкт"})) == 1
    assert len(filter_dissertations(df, {"year": "2020"})) == 1
    assert len(filter_dissertations(df, {"specialties": "13.00.08"})) == 1


def test_tab_hydrates_query_and_builds_share_payload() -> None:
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

sample_df = pd.DataFrame([
    {
        "title": "Анализ методики",
        "candidate_name": "Иванов И.И.",
        "institution_prepared": "МГУ",
        "leading_organization": "РАН",
        "defense_location": "Москва",
        "city": "Москва",
        "year": "2020",
        "supervisors_1.name": "Петров П.П.",
        "supervisors_2.name": "",
        "opponents_1.name": "Сидоров С.С.",
        "opponents_2.name": "",
        "opponents_3.name": "",
        "specialties_1.code": "13.00.01",
        "specialties_1.name": "Общая педагогика",
        "specialties_2.code": "",
        "specialties_2.name": "",
    }
])

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

    assert app.session_state["_captured_share_key"] == "diss_search_share"
    assert app.session_state["_captured_share_payload"] == {
        "tab": "dissertations",
        "diss_criterion": ["title"],
        "diss_title": "метод",
    }
    assert app.session_state["_captured_render_kwargs"]["key"] == "поиск_диссертаций"


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
