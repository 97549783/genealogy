from __future__ import annotations

import inspect

from tabs.articles.comparison_mode import render_articles_comparison_mode
from tabs.articles.similar_schools_mode import render_similar_schools_mode
from tabs.articles.single_school_mode import render_single_school_mode


def test_article_modes_accept_prefiltered_articles_dataframe() -> None:
    assert "df_articles" in inspect.signature(render_single_school_mode).parameters
    assert "df_articles" in inspect.signature(render_similar_schools_mode).parameters
    assert "df_articles" in inspect.signature(render_articles_comparison_mode).parameters
