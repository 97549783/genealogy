from __future__ import annotations

import pandas as pd

from tabs.articles.data import build_articles_dataset_for_school


def test_dataset_matching_uses_article_authors_not_metadata_authors() -> None:
    df_lineage = pd.DataFrame([{"candidate_name": "Иванов Иван Иванович", "supervisors_1.name": ""}])
    options_meta = {"Иванов Иван Иванович": "person_no_desc"}
    df_articles = pd.DataFrame(
        [
            {"Article_id": "A1", "Authors": "Сидоров С.С.", "Title": "T1", "Year": "2020"},
            {"Article_id": "A2", "Authors": "Иванов И.И.", "Title": "T2", "Year": "2021"},
        ]
    )
    article_authors = pd.DataFrame(
        [
            {"Article_id": "A1", "Name": "Иванов И.И."},
            {"Article_id": "A2", "Name": "Сидоров С.С."},
        ]
    )

    dataset = build_articles_dataset_for_school(
        "Иванов Иван Иванович",
        options_meta,
        df_lineage,
        {},
        df_articles,
        "direct",
        df_article_authors=article_authors,
    )

    assert dataset["Article_id"].tolist() == ["A1"]
