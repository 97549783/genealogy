from __future__ import annotations

import pandas as pd

from tabs.articles.blocks import ARTICLE_ANALYSIS_BLOCK_GROUPS, get_available_block_columns


def test_article_blocks_use_product_labels_without_placeholders() -> None:
    digital_blocks = ARTICLE_ANALYSIS_BLOCK_GROUPS["digital_technologies"]["codes"]
    label_by_code = {item["code"]: item["label"] for item in digital_blocks}

    assert label_by_code["2.2.1.1"] == "Большие языковые модели (ChatGPT, LLM)"
    assert all("тематический блок" not in item["label"].lower() for item in digital_blocks)


def test_available_blocks_keep_labels_and_hide_missing_codes() -> None:
    df = pd.DataFrame({"2.2.1.1": [4.0], "нет_такого_кода": [1.0]})

    result = get_available_block_columns(df)

    assert result == [
        {
            "code": "2.2.1.1",
            "label": "Большие языковые модели (ChatGPT, LLM)",
            "group": "Цифровые технологии в образовании",
        }
    ]
