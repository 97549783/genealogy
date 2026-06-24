from __future__ import annotations

import pandas as pd

from tabs.dissertation_characteristics.tab import _linked_df


def test_missing_matrix_does_not_break_first_subtab_helper():
    df = pd.DataFrame({"Code": ["A"], "candidate_name": ["Автор"]})
    index = pd.DataFrame({"Code": ["A"], "section_key": ["research_goal"]})
    assert _linked_df(df, index)["Code"].tolist() == ["A"]
