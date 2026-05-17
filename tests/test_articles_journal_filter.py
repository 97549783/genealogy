from __future__ import annotations

import pandas as pd

from tabs.articles.data import ALL_JOURNALS_KEY, filter_articles_by_journals


def _articles() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Article_id": "A1", "ISSN": "0234-0453", "Journal": "Информатика и образование"},
            {"Article_id": "A2", "ISSN": "2072-9014", "Journal": "Вестник МГПУ"},
            {"Article_id": "A3", "ISSN": "0234-0453", "Journal": "Информатика & образование"},
        ]
    )


def test_all_journals_selected_returns_all_rows() -> None:
    result = filter_articles_by_journals(_articles(), [ALL_JOURNALS_KEY])

    assert result["Article_id"].tolist() == ["A1", "A2", "A3"]


def test_empty_selection_returns_all_rows() -> None:
    result = filter_articles_by_journals(_articles(), [])

    assert result["Article_id"].tolist() == ["A1", "A2", "A3"]


def test_one_issn_selected_returns_only_that_issn() -> None:
    result = filter_articles_by_journals(_articles(), ["2072-9014"])

    assert result["Article_id"].tolist() == ["A2"]


def test_two_issns_selected_return_both_journals() -> None:
    result = filter_articles_by_journals(_articles(), ["0234-0453", "2072-9014"])

    assert result["Article_id"].tolist() == ["A1", "A2", "A3"]


def test_filtering_by_issn_ignores_journal_title_variants() -> None:
    result = filter_articles_by_journals(_articles(), ["0234-0453"])

    assert result["Article_id"].tolist() == ["A1", "A3"]
