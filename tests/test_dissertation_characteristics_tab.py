from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pandas as pd

from tabs.dissertation_characteristics import tab
from tabs.dissertation_characteristics.tab import _abstract_link_values, _linked_df


def test_missing_matrix_does_not_break_first_subtab_helper():
    df = pd.DataFrame({"Code": ["A"], "candidate_name": ["Автор"]})
    index = pd.DataFrame({"Code": ["A"], "section_key": ["research_goal"]})
    assert _linked_df(df, index)["Code"].tolist() == ["A"]


def test_abstract_link_values_follow_tree_result_rules(monkeypatch):
    numeric = _abstract_link_values("123_456", "Иванов Иван")
    assert numeric["read"] == "https://viewer.rusneb.ru/ru/123_456?page=1"
    assert numeric["download"].startswith("https://rusneb.ru/local/tools/exalead/getFiles.php?book_id=123_456")

    nlr = _abstract_link_values("NLR-001", "Иванов Иван")
    assert nlr == {"read": "https://viewer.rusneb.ru/ru/NLR-001?page=1", "download": ""}

    unsupported = _abstract_link_values("abc", "Иванов Иван")
    assert unsupported == {"read": "", "download": ""}

    rendered: list[str] = []
    monkeypatch.setattr(tab.st, "markdown", rendered.append)
    row = pd.Series(
        {
            "candidate_name": "Иванов Иван",
            "title": "Название",
            "year": "2024",
            "degree.science_field": "технические науки",
            "Code": "123_456",
        }
    )
    tab._show_metadata(row)

    text = "\n".join(rendered)
    assert "**Code:**" not in text
    assert "Автореферат" in text
    assert "Читать" in text
    assert "Скачать" in text


class _FakeStreamlit:
    def __init__(self, query: str = "") -> None:
        self.captions: list[str] = []
        self.query = query

    def text_input(self, label, key=None):
        if key == "diss_char_query_1":
            return self.query
        return ""

    def radio(self, *args, **kwargs):
        return "По автору или названию"

    def selectbox(self, label, options, format_func=None, key=None):
        return list(options)[0]

    def checkbox(self, *args, **kwargs):
        return True

    def multiselect(self, label, options, default=None, format_func=None, key=None):
        return default if default is not None else list(options)

    def number_input(self, *args, **kwargs):
        return kwargs.get("value", 10)

    def button(self, *args, **kwargs):
        return False

    def caption(self, value):
        self.captions.append(str(value))

    def warning(self, value):
        raise AssertionError(f"Неожиданное предупреждение: {value}")


def test_similar_section_search_waits_for_search_button(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(tab, "st", fake_st)
    monkeypatch.setattr(tab, "load_current_dissertation_matrix", Mock(return_value=np.zeros((2, 2))))
    monkeypatch.setattr(
        tab,
        "load_dissertation_sections_by_code",
        Mock(
            return_value=pd.DataFrame(
                {
                    "text_id": [1],
                    "section_key": ["research_goal"],
                    "section_label": ["Цель исследования"],
                    "matrix_row": [0],
                }
            )
        ),
    )
    filter_targets = Mock(return_value=pd.DataFrame())
    search = Mock(return_value=pd.DataFrame())
    monkeypatch.setattr(tab, "filter_targets_for_similar_search", filter_targets)
    monkeypatch.setattr(tab, "search_similar_dissertation_sections", search)

    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})
    index_df = pd.DataFrame({"Code": ["789"], "section_key": ["research_goal"], "matrix_row": [1]})
    tab._render_similar_search(df, index_df, {"normalized": "true"})

    filter_targets.assert_not_called()
    search.assert_not_called()
    assert "Настройте параметры и нажмите «Поиск»." in fake_st.captions


def test_neural_query_search_waits_for_search_button(monkeypatch):
    fake_st = _FakeStreamlit(query="научная новизна")
    monkeypatch.setattr(tab, "st", fake_st)
    monkeypatch.setattr(tab, "load_current_dissertation_matrix", Mock(return_value=np.zeros((2, 2))))
    encode = Mock(return_value=np.zeros((1, 2)))
    search = Mock(return_value=pd.DataFrame())
    monkeypatch.setattr(tab, "encode_user_queries", encode)
    monkeypatch.setattr(tab, "search_dissertation_sections_by_query_vector", search)

    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})
    index_df = pd.DataFrame({"Code": ["123_456"], "section_key": ["research_goal"], "matrix_row": [0]})
    tab._render_query_search(df, index_df, {"normalized": "true"})

    encode.assert_not_called()
    search.assert_not_called()
    assert "Введите запрос и нажмите «Поиск»." in fake_st.captions
