from __future__ import annotations

import pandas as pd

from tabs.articles.blocks import get_available_block_columns, load_article_analysis_block_groups
from tabs.articles.comparison import load_articles_classifier


def test_article_blocks_resolve_labels_from_merged_classifier() -> None:
    groups = load_article_analysis_block_groups()
    classifier_labels = load_articles_classifier()
    df = pd.DataFrame({code: [4.0] for group in groups.values() for code in group["codes"]})

    blocks = get_available_block_columns(df, classifier_labels=classifier_labels)
    label_by_code = {item["code"]: item["label"] for item in blocks}

    assert label_by_code["1.1.1.5.2"] == "Ординатура"
    assert label_by_code["1.1.2.1.1"] == "Вводный курс (цифровая грамотность, теоретические основы информатики)"
    assert label_by_code["1.1.2.1.3"] == "Искусственный интеллект и машинное обучение"
    assert label_by_code["1.1.2.1.4"] == "Базы данных и информационные системы"
    assert label_by_code["1.1.2.1.5"] == "Компьютерные сети и интернет-технологии"
    assert label_by_code["1.1.2.1.6"] == "Информационная безопасность и кибербезопасность"
    assert label_by_code["1.1.2.1.7"] == "Информационные технологии (офисные программы, мультимедиа, веб-разработка)"
    assert label_by_code["1.1.2.9.1"] == "Педагогическое образование"
    assert label_by_code["1.1.2.9.2"] == "Психолого-педагогическое направление"
    assert label_by_code["2.2.1.1"] == "Большие языковые модели (ChatGPT, LLM)"


def test_available_blocks_skip_codes_without_classifier_labels() -> None:
    df = pd.DataFrame({"1.1.1.5.1": [5.0], "1.1.1.5.2": [4.0], "999.999": [5.0]})

    blocks = get_available_block_columns(
        df,
        classifier_labels={"1.1.1.5.2": "Ординатура"},
    )

    assert blocks == [
        {
            "code": "1.1.1.5.2",
            "label": "Ординатура",
            "group": "Уровень формального образования",
        }
    ]
