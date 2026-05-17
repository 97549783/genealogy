from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_single_school_has_no_preselected_person() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.single_school_mode as mode

mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})

def _fake_build(*args, **kwargs):
    st.session_state["_dataset_built"] = True
    return pd.DataFrame()

mode.build_articles_dataset_for_school = _fake_build
mode.render_single_school_mode(pd.DataFrame(), {})
"""
    )
    app.run(timeout=10)
    assert "_dataset_built" not in app.session_state
    assert any("Выберите научную школу для анализа." in value.value for value in app.info)


def test_single_school_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import tabs.articles.single_school_mode as mode

mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И.", "Title": "T", "Year": "2020", "Keywords": "ключ", "DOI": "10", "1": 3.0}])
mode.load_article_authors = lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Иванов И.И."}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "ключ"}])
mode.get_available_block_columns = lambda dataset, classifier_labels=None: []
mode.compute_block_score_summary = lambda dataset, blocks, threshold, show_all: pd.DataFrame()
mode.create_yearly_articles_chart = lambda yearly_df: plt.figure()
mode.share_params_button = lambda payload, key: st.session_state.update({"_share_payload": payload, "_share_key": key})

def _fake_build(*args, **kwargs):
    st.session_state["_dataset_built"] = True
    return mode.load_articles_data()

mode.build_articles_dataset_for_school = _fake_build
mode.render_single_school_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["tab"] = "articles_comparison"
    app.query_params["articles_mode"] = "single_school"
    app.query_params["aa_school"] = "Иванов И.И."
    app.query_params["aa_scope"] = "all"
    app.query_params["aa_threshold"] = "2.5"
    app.query_params["aa_show_all_blocks"] = "true"
    app.run(timeout=10)
    assert app.session_state["aa_single_school"] == "Иванов И.И."
    assert app.session_state["_dataset_built"] is True
    assert app.session_state["_share_key"] == "aa_single_share"
    assert app.session_state["_share_payload"] == {
        "tab": "articles_comparison",
        "articles_mode": "single_school",
        "aa_journals": ["all"],
        "aa_school": "Иванов И.И.",
        "aa_scope": "all",
        "aa_threshold": 2.5,
        "aa_show_all_blocks": True,
    }


def test_single_school_rehydrates_when_query_changes() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.single_school_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.build_articles_dataset_for_school = lambda *args, **kwargs: pd.DataFrame()
mode.load_articles_data = lambda: pd.DataFrame()
mode.render_single_school_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["aa_school"] = "Иванов И.И."
    app.run(timeout=10)
    assert app.session_state["aa_single_school"] == "Иванов И.И."
    app.query_params["aa_school"] = "Петров П.П."
    app.run(timeout=10)
    assert app.session_state["aa_single_school"] == "Петров П.П."


def test_single_school_shows_message_when_articles_have_no_scores() -> None:
    app = AppTest.from_string(
        """
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import tabs.articles.single_school_mode as mode

mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И."], {"Иванов И.И.": "initials_only"})
mode.load_article_authors = lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Иванов И.И."}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "ключ"}])
mode.compute_block_score_summary = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Нельзя считать профиль без баллов"))
mode.create_yearly_articles_chart = lambda yearly_df: plt.figure()
mode.share_params_button = lambda payload, key: None
mode.build_articles_dataset_for_school = lambda *args, **kwargs: pd.DataFrame([
    {"Article_id": "A1", "Authors": "Иванов И.И.", "Title": "T", "Year": "2020", "Keywords": "ключ", "Has_thematic_scores": False, "1": pd.NA}
])
mode.render_single_school_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["aa_school"] = "Иванов И.И."
    app.run(timeout=10)
    assert any(
        "Для выбранной школы найдены статьи, но среди них нет статей с рассчитанными тематическими профилями." in value.value
        for value in app.info
    )
