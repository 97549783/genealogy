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


def test_similar_schools_hydrates_query_and_builds_share_payload() -> None:
    app = AppTest.from_string(
        """
import pandas as pd
import streamlit as st
import tabs.articles.similar_schools_mode as mode
mode.compute_selectable_people = lambda df_lineage, include_without_descendants: (["Иванов И.И.", "Петров П.П."], {"Иванов И.И.": "initials_only", "Петров П.П.": "initials_only"})
mode.load_articles_data = lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И.", "Year": "2020", "Keywords": "а", "1": 1.0}, {"Article_id": "A2", "Authors": "Петров П.П.", "Year": "2021", "Keywords": "а", "1": 0.5}])
mode.load_article_keywords = lambda: pd.DataFrame([{"Article_id": "A1", "Keyword": "а"}, {"Article_id": "A2", "Keyword": "а"}])
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
