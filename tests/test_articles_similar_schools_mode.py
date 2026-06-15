from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_similar_schools_has_no_preselected_source_school() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
def _fake_build(*args, **kwargs):
    st.session_state["_dataset_built"] = True
    return pd.DataFrame()
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.run(timeout=10)
    assert "_dataset_built" not in app.session_state
    assert any("Выберите исходную научную школу для поиска похожих школ." in value.value for value in app.info)


def test_similar_schools_does_not_search_after_manual_school_selection() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1"}])
def _fake_build(*args, **kwargs):
    st.session_state["_dataset_built"] = True
    return pd.DataFrame()
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.run(timeout=10)
    app.selectbox[0].select("Иванов И.И.").run(timeout=10)
    assert "_dataset_built" not in app.session_state
    assert any("Задайте параметры и нажмите «Поиск»." in value.value for value in app.info)


def test_similar_schools_searches_after_button_click() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И.", "Year": "2020", "Keywords": "а", "Has_thematic_scores": True, "1": 1.0}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "а"}])
mode.load_article_authors = lambda: pd.DataFrame()
mode.get_article_feature_columns = lambda df: ["1"]
mode.get_available_block_columns = lambda df, classifier_labels=None: []
def _fake_build(option, *args, **kwargs):
    st.session_state["_dataset_built"] = True
    article_id = "A1" if option == "Иванов И.И." else "A2"
    return pd.DataFrame([{"Article_id": article_id, "Authors": option, "Year": "2020", "Keywords": "а", "Has_thematic_scores": True, "1": 1.0}])
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.run(timeout=10)
    app.selectbox[0].select("Иванов И.И.").run(timeout=10)
    app.button[0].click().run(timeout=10)
    assert app.session_state["_dataset_built"] is True
    assert len(app.dataframe) == 1


def test_similar_schools_parameter_change_does_not_recalculate() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И.", "Year": "2020", "Keywords": "а", "Has_thematic_scores": True, "1": 1.0}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "а"}])
mode.load_article_authors = lambda: pd.DataFrame()
mode.get_article_feature_columns = lambda df: ["1"]
mode.get_available_block_columns = lambda df, classifier_labels=None: []
def _fake_build(option, *args, **kwargs):
    st.session_state["_build_calls"] = st.session_state.get("_build_calls", 0) + 1
    article_id = "A1" if option == "Иванов И.И." else "A2"
    return pd.DataFrame([{"Article_id": article_id, "Authors": option, "Year": "2020", "Keywords": "а", "Has_thematic_scores": True, "1": 1.0}])
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.run(timeout=10)
    app.selectbox[0].select("Иванов И.И.").run(timeout=10)
    app.button[0].click().run(timeout=10)
    build_calls = app.session_state["_build_calls"]

    app.number_input[0].set_value(2).run(timeout=10)

    assert app.session_state["_build_calls"] == build_calls
    assert len(app.dataframe) == 0
    assert any("Параметры изменены. Нажмите «Поиск», чтобы обновить результаты." in value.value for value in app.info)


def test_similar_schools_builds_author_index_once_per_uncached_search() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П.", "Сидоров С.С."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only", "Сидоров С.С.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И.", "Year": "2020", "Keywords": "а", "Has_thematic_scores": True, "1": 1.0}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "а"}])
mode.load_article_authors = lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Иванов И.И."}])
mode.get_article_feature_columns = lambda df: ["1"]
mode.get_available_block_columns = lambda df, classifier_labels=None: []
def _fake_author_index(article_authors):
    st.session_state["_author_index_calls"] = st.session_state.get("_author_index_calls", 0) + 1
    return {"иванов и.и.": {"A1"}}
mode.build_article_author_index = _fake_author_index
def _fake_build(option, *args, **kwargs):
    assert kwargs.get("article_author_index") == {"иванов и.и.": {"A1"}}
    st.session_state["_build_calls"] = st.session_state.get("_build_calls", 0) + 1
    article_id = "A1" if option == "Иванов И.И." else f"A_{option}"
    return pd.DataFrame([{"Article_id": article_id, "Authors": option, "Year": "2020", "Keywords": "а", "Has_thematic_scores": True, "1": 1.0}])
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.run(timeout=10)
    app.selectbox[0].select("Иванов И.И.").run(timeout=10)
    app.button[0].click().run(timeout=10)

    assert app.session_state["_author_index_calls"] == 1
    assert app.session_state["_build_calls"] == 3


def test_similar_schools_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И.", "Year": "2020", "Keywords": "а", "1": 1.0}, {"Article_id": "A2", "Authors": "Петров П.П.", "Year": "2021", "Keywords": "а", "1": 0.5}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "а"}, {"Article_id": "A2", "Keyword": "а"}])
mode.load_article_authors = lambda: pd.DataFrame()
mode.get_article_feature_columns = lambda df: ["1"]
mode.get_available_block_columns = lambda df, classifier_labels=None: []
mode.share_params_button = lambda payload, key: st.session_state.update({"_share_payload": payload, "_share_key": key})
def _fake_build(option, *args, **kwargs):
    st.session_state["_dataset_built"] = True
    article_id = "A1" if option == "Иванов И.И." else "A2"
    author = option
    return pd.DataFrame([
        {"Article_id": article_id, "Authors": author, "Year": "2020", "Keywords": "а", "1": 1.0},
        {"Article_id": f"{article_id}_2", "Authors": author, "Year": "2021", "Keywords": "а", "1": 0.8},
    ])
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["tab"] = "articles_comparison"
    app.query_params["articles_mode"] = "similar_schools"
    app.query_params["aa_source_school"] = "Иванов И.И."
    app.query_params["aa_scope"] = "all"
    app.query_params["aa_similarity_mode"] = "combined"
    app.query_params["aa_min_articles"] = "2"
    app.query_params["aa_top_n"] = "10"
    app.query_params["aa_threshold"] = "2.5"
    app.run(timeout=10)
    assert app.session_state["aa_source_school"] == "Иванов И.И."
    assert app.session_state["_share_key"] == "aa_similar_share"
    assert app.session_state["_share_payload"] == {
        "tab": "articles_comparison",
        "articles_mode": "similar_schools",
        "aa_journals": ["all"],
        "aa_source_school": "Иванов И.И.",
        "aa_scope": "all",
        "aa_similarity_mode": "combined",
        "aa_min_articles": 2,
        "aa_top_n": 10,
        "aa_threshold": 2.5,
    }


def test_similar_schools_rehydrates_when_query_changes() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.build_articles_dataset_for_school = lambda *args, **kwargs: pd.DataFrame()
mode.load_articles_data = lambda: pd.DataFrame()
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["aa_source_school"] = "Иванов И.И."
    app.run(timeout=10)
    assert app.session_state["aa_source_school"] == "Иванов И.И."
    app.query_params["aa_source_school"] = "Петров П.П."
    app.run(timeout=10)
    assert app.session_state["aa_source_school"] == "Петров П.П."


def test_similar_schools_keyword_mode_works_without_scores() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "а"}, {"Article_id": "A2", "Keyword": "а"}])
mode.load_article_authors = lambda: pd.DataFrame()
mode.get_article_feature_columns = lambda df: ["1"]
mode.get_available_block_columns = lambda df, classifier_labels=None: []
mode.share_params_button = lambda payload, key: st.session_state.update({"_share_payload": payload, "_share_key": key})
def _fake_build(option, *args, **kwargs):
    article_id = "A1" if option == "Иванов И.И." else "A2"
    return pd.DataFrame([{"Article_id": article_id, "Authors": option, "Year": "2020", "Keywords": "а", "Has_thematic_scores": False, "1": pd.NA}])
mode.build_articles_dataset_for_school = _fake_build
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["aa_source_school"] = "Иванов И.И."
    app.query_params["aa_similarity_mode"] = "keywords"
    app.run(timeout=10)
    assert app.session_state["_share_key"] == "aa_similar_share"
    assert app.session_state["_share_payload"]["aa_similarity_mode"] == "keywords"


def test_similar_schools_combined_mode_requires_scored_source_articles() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_article_keywords = lambda: pd.DataFrame()
mode.load_article_authors = lambda: pd.DataFrame()
mode.get_article_feature_columns = lambda df: ["1"]
mode.get_available_block_columns = lambda df, classifier_labels=None: []
mode.build_articles_dataset_for_school = lambda option, *args, **kwargs: pd.DataFrame([{"Article_id": "A1", "Authors": option, "Year": "2020", "Keywords": "а", "Has_thematic_scores": False, "1": pd.NA}])
mode.render_similar_schools_mode(pd.DataFrame(), {})
"""
    )
    app.query_params["aa_source_school"] = "Иванов И.И."
    app.query_params["aa_similarity_mode"] = "combined"
    app.run(timeout=10)
    assert any(
        "Для комбинированного поиска у исходной школы должны быть статьи с рассчитанными тематическими профилями." in value.value
        for value in app.info
    )
