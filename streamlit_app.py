"""Точка композиции Streamlit-приложения."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Академическая генеалогия", layout="wide")


def _maybe_redirect_to_mukhina_tree() -> None:
    """Перенаправляет секретный запрос на самостоятельную HTML-страницу дерева."""
    if "mukina_tree" not in st.query_params:
        return

    st.markdown(
        """
<meta http-equiv="refresh" content="0; url=/app/static/mukhina_tree.html">
<style>
  [data-testid="stHeader"],
  [data-testid="stToolbar"],
  footer {
    display: none !important;
  }
  [data-testid="stMainBlockContainer"] {
    max-width: none !important;
    padding: 0 !important;
  }
  iframe {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    border: 0 !important;
    z-index: 999999 !important;
  }
</style>
""",
        unsafe_allow_html=True,
    )
    components.iframe("/app/static/mukhina_tree.html", height=1200, scrolling=False)
    st.stop()


_maybe_redirect_to_mukhina_tree()

# Тяжёлые модули основного приложения импортируются только после проверки
# самостоятельной статической страницы.
from core.app import (  # noqa: E402
    build_app_context,
    maybe_render_admin_page_and_stop,
    render_app_header,
)
from core.ui.main_navigation import (  # noqa: E402
    render_main_navigation,
    resolve_main_section_id,
)
from tabs.articles.tab import render_articles_analysis_tab  # noqa: E402
from tabs.dissertation_search.tab import render_dissertation_search_tab  # noqa: E402
from tabs.dissertation_characteristics.tab import render_dissertation_characteristics_tab  # noqa: E402
from tabs.intersection.tab import render_opponents_intersection_tab  # noqa: E402
from tabs.lineages.tab import render_school_trees_tab  # noqa: E402
from tabs.registry import DEFAULT_TAB_ID  # noqa: E402
from tabs.school_analysis.tab import render_school_analysis_tab  # noqa: E402
from tabs.school_comparison.tab import render_school_comparison_tab  # noqa: E402
from tabs.source_schools.tab import render_source_schools_tab  # noqa: E402
from tabs.school_search.tab import render_school_search_tab  # noqa: E402

st.markdown(
    """
<meta name="google" content="notranslate">
<style>
  iframe { width: 100%; }
</style>
""",
    unsafe_allow_html=True,
)

maybe_render_admin_page_and_stop()
ctx = build_app_context()
render_app_header()

requested_tab_id = resolve_main_section_id(st.query_params.get("tab", DEFAULT_TAB_ID))
render_main_navigation(requested_tab_id, st.query_params)


def render_selected_section(section_id: str) -> None:
    """Запускает только обработчик выбранного основного раздела."""
    if section_id == "lineages":
        render_school_trees_tab(
            df=ctx.df,
            idx=ctx.idx,
            all_supervisor_names=ctx.all_supervisor_names,
            shared_roots=ctx.valid_shared_roots,
            db_signature=ctx.db_signature,
        )
    elif section_id == "dissertation_search":
        render_dissertation_search_tab(df=ctx.df, idx=ctx.idx, db_signature=ctx.db_signature)
    elif section_id == "dissertation_characteristics":
        render_dissertation_characteristics_tab(df=ctx.df)
    elif section_id == "school_search":
        render_school_search_tab(df=ctx.df, idx=ctx.idx, db_signature=ctx.db_signature)
    elif section_id == "intersection":
        render_opponents_intersection_tab(df=ctx.df, idx=ctx.idx, db_signature=ctx.db_signature)
    elif section_id == "school_analysis":
        render_school_analysis_tab(df=ctx.df, idx=ctx.idx, db_signature=ctx.db_signature)
    elif section_id == "school_comparison":
        render_school_comparison_tab(df=ctx.df, idx=ctx.idx, db_signature=ctx.db_signature)
    elif section_id == "articles_comparison":
        render_articles_analysis_tab(df_lineage=ctx.df, idx_lineage=ctx.idx)
    elif section_id == "source_schools":
        render_source_schools_tab()


render_selected_section(requested_tab_id)
