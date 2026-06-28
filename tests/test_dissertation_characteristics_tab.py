from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pandas as pd

from tabs.dissertation_characteristics import tab
from tabs.dissertation_characteristics.tab import _abstract_link_values, _label, _linked_df, _search_rows


def test_отсутствие_матрицы_не_ломает_связку_первой_подвкладки():
    df = pd.DataFrame({"Code": ["A"], "candidate_name": ["Автор"]})
    index = pd.DataFrame({"Code": ["A"], "section_key": ["research_goal"]})
    assert _linked_df(df, index)["Code"].tolist() == ["A"]


def test_подпись_не_показывает_служебный_код():
    row = pd.Series(
        {
            "candidate_name": "Иванов Иван",
            "title": "Название",
            "year": "2024",
            "degree.science_field": "технические науки",
            "Code": "123_456",
        }
    )

    assert "123_456" not in _label(row)


def test_ссылки_автореферата_соблюдают_правила_результатов_дерева(monkeypatch):
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
    def __init__(self, query: str = "", clicked_keys: set[str] | None = None, inputs: dict[str, str] | None = None) -> None:
        self.captions: list[str] = []
        self.query = query
        self.session_state: dict[str, object] = {}
        self.keys: list[str] = []
        self.buttons: list[tuple[str, str | None]] = []
        self.clicked_keys = clicked_keys or set()
        self.inputs = inputs or {}

    def _register_key(self, key):
        if key is None:
            return
        if key in self.keys:
            raise AssertionError(f"Ключ виджета зарегистрирован повторно: {key}")
        self.keys.append(key)

    def text_input(self, label, key=None, **kwargs):
        self._register_key(key)
        if key in self.inputs:
            return self.inputs[key]
        if key == "diss_char_query_1":
            return self.query
        return ""

    def radio(self, *args, **kwargs):
        self._register_key(kwargs.get("key"))
        return "По автору или названию"

    def selectbox(self, label, options, format_func=None, key=None, index=0):
        self._register_key(key)
        if index is None:
            return self.session_state.get(key)
        return list(options)[index]

    def checkbox(self, *args, **kwargs):
        self._register_key(kwargs.get("key"))
        return True

    def multiselect(self, label, options, default=None, format_func=None, key=None):
        self._register_key(key)
        return default if default is not None else list(options)

    def number_input(self, *args, **kwargs):
        self._register_key(kwargs.get("key"))
        return kwargs.get("value", 10)

    def button(self, label, *args, **kwargs):
        key = kwargs.get("key")
        self._register_key(key)
        self.buttons.append((str(label), key))
        return key in self.clicked_keys

    def caption(self, value):
        self.captions.append(str(value))

    def warning(self, value):
        raise AssertionError(f"Неожиданное предупреждение: {value}")


def test_поиск_по_режимам_сохраняет_прежнюю_семантику():
    df = pd.DataFrame(
        {
            "Code": ["1", "2", "3"],
            "candidate_name": ["Иванов Иван", "Петров Пётр", "Сидорова Анна"],
            "title": ["Исследование школ", "История Иванова метода", "Модели данных"],
        }
    )

    assert _search_rows(df, "иванов", "По автору или названию")["Code"].tolist() == ["1", "2"]
    assert _search_rows(df, "иванов", "Только по автору")["Code"].tolist() == ["1"]
    assert _search_rows(df, "иванов", "Только по названию")["Code"].tolist() == ["2"]


def test_выбор_диссертации_ждёт_отправленного_поиска(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(tab, "st", fake_st)
    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})

    assert tab._select_dissertation(df, "diss_char_view") is None
    assert "Введите параметры и нажмите «Поиск»." in fake_st.captions


def test_результаты_поиска_не_выбираются_автоматически(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["diss_char_view_submitted_search"] = {"query": "Иванов", "mode": "По автору или названию"}
    monkeypatch.setattr(tab, "st", fake_st)
    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})

    assert tab._select_dissertation(df, "diss_char_view") is None


def test_похожие_разделы_не_открывают_матрицу_без_выбора_диссертации(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["diss_char_similar_submitted_search"] = {"query": "Иванов", "mode": "По автору или названию"}
    monkeypatch.setattr(tab, "st", fake_st)
    monkeypatch.setattr(tab, "load_current_dissertation_matrix", Mock(return_value=np.zeros((2, 2))))
    monkeypatch.setattr(tab, "load_dissertation_sections_by_code", Mock(return_value=pd.DataFrame()))

    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})
    index_df = pd.DataFrame({"Code": ["789"], "section_key": ["research_goal"], "matrix_row": [1]})
    tab._render_similar_search(df, index_df, {"normalized": "true"})

    tab.load_current_dissertation_matrix.assert_not_called()
    tab.load_dissertation_sections_by_code.assert_not_called()


def test_поиск_похожих_разделов_ждёт_кнопку_поиска(monkeypatch):
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
    assert "Введите параметры и нажмите «Поиск»." in fake_st.captions
    tab.load_current_dissertation_matrix.assert_not_called()
    tab.load_dissertation_sections_by_code.assert_not_called()


def test_нейросетевой_поиск_по_запросу_ждёт_кнопку_поиска(monkeypatch):
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
    assert "Введите запрос и нажмите «Найти по запросу»." in fake_st.captions


def _sections_for_similar_search() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "text_id": [1],
            "section_key": ["research_goal"],
            "section_label": ["Цель исследования"],
            "matrix_row": [0],
        }
    )


def test_поиск_похожих_разделов_с_выбранной_диссертацией_имеет_уникальные_ключи(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["diss_char_similar_submitted_search"] = {"query": "Иванов", "mode": "По автору или названию"}
    fake_st.session_state["diss_char_similar_select"] = 0
    monkeypatch.setattr(tab, "st", fake_st)
    monkeypatch.setattr(tab, "load_current_dissertation_matrix", Mock(return_value=np.zeros((2, 2))))
    monkeypatch.setattr(tab, "load_dissertation_sections_by_code", Mock(return_value=_sections_for_similar_search()))

    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})
    index_df = pd.DataFrame({"Code": ["789"], "section_key": ["research_goal"], "matrix_row": [1]})
    tab._render_similar_search(df, index_df, {"normalized": "true"})

    assert len(fake_st.keys) == len(set(fake_st.keys))
    assert "Настройте параметры и нажмите «Найти похожие»." in fake_st.captions
    tab.load_current_dissertation_matrix.assert_not_called()


def test_кнопки_поиска_диссертации_и_похожих_разделов_имеют_разные_ключи(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["diss_char_similar_submitted_search"] = {"query": "Иванов", "mode": "По автору или названию"}
    fake_st.session_state["diss_char_similar_select"] = 0
    monkeypatch.setattr(tab, "st", fake_st)
    monkeypatch.setattr(tab, "load_dissertation_sections_by_code", Mock(return_value=_sections_for_similar_search()))

    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})
    index_df = pd.DataFrame({"Code": ["789"], "section_key": ["research_goal"], "matrix_row": [1]})
    tab._render_similar_search(df, index_df, {"normalized": "true"})

    assert ("Поиск", "diss_char_similar_dissertation_search_button") in fake_st.buttons
    assert ("Найти похожие", "diss_char_similar_find_similar_button") in fake_st.buttons
    assert "diss_char_similar_dissertation_search_button" != "diss_char_similar_find_similar_button"


def test_кнопка_поиска_диссертации_только_сохраняет_параметры_и_сбрасывает_выбор(monkeypatch):
    fake_st = _FakeStreamlit(
        clicked_keys={"diss_char_similar_dissertation_search_button"},
        inputs={"diss_char_similar_query": "Иванов"},
    )
    fake_st.session_state["diss_char_similar_select"] = 0
    monkeypatch.setattr(tab, "st", fake_st)
    monkeypatch.setattr(tab, "load_current_dissertation_matrix", Mock(return_value=np.zeros((2, 2))))
    monkeypatch.setattr(tab, "load_dissertation_sections_by_code", Mock(return_value=_sections_for_similar_search()))

    df = pd.DataFrame({"Code": ["123_456"], "candidate_name": ["Иванов Иван"], "title": ["Название"]})
    index_df = pd.DataFrame({"Code": ["789"], "section_key": ["research_goal"], "matrix_row": [1]})
    tab._render_similar_search(df, index_df, {"normalized": "true"})

    assert fake_st.session_state["diss_char_similar_submitted_search"] == {"query": "Иванов", "mode": "По автору или названию"}
    assert fake_st.session_state["diss_char_similar_select"] is None
    tab.load_current_dissertation_matrix.assert_not_called()
    tab.load_dissertation_sections_by_code.assert_not_called()
