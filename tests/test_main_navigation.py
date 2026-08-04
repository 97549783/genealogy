from html.parser import HTMLParser

import pytest

from core.ui.main_navigation import build_main_navigation_html, resolve_main_section_id
from tabs.registry import DEFAULT_TAB_ID, TAB_SPECS


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.nav_attributes = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "nav":
            self.nav_attributes = attributes
        elif tag == "a":
            self.links.append(attributes)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, DEFAULT_TAB_ID),
        ("", DEFAULT_TAB_ID),
        ("  ", DEFAULT_TAB_ID),
        (" dissertation_search ", "dissertation_search"),
        ("unknown", DEFAULT_TAB_ID),
        (123, DEFAULT_TAB_ID),
        (["lineages"], DEFAULT_TAB_ID),
    ],
)
def test_resolve_main_section_id(raw_value, expected):
    assert resolve_main_section_id(raw_value) == expected


def test_navigation_contains_ordered_real_links_and_one_active_item():
    html = build_main_navigation_html("school_analysis", {"secret": "скрыто", "query": "поиск"})
    parser = LinkParser()
    parser.feed(html)

    assert parser.nav_attributes["aria-label"] == "Основные разделы"
    assert len(parser.links) == len(TAB_SPECS)
    assert [link["href"] for link in parser.links] == [f"?tab={tab_id}" for tab_id, _ in TAB_SPECS]
    assert sum(link.get("aria-current") == "page" for link in parser.links) == 1
    active_index = [tab_id for tab_id, _ in TAB_SPECS].index("school_analysis")
    assert parser.links[active_index]["aria-current"] == "page"
    assert "secret" not in html
    assert "query" not in html
    assert 'target="_blank"' not in html
    assert "onclick" not in html


def test_source_schools_follows_articles_comparison():
    ids = [tab_id for tab_id, _ in TAB_SPECS]
    labels = dict(TAB_SPECS)
    assert "source_schools" in ids
    assert labels["source_schools"] == "Школы по источникам (демо)"
    assert ids.index("source_schools") == ids.index("articles_comparison") + 1


def test_navigation_escapes_registry_labels(monkeypatch):
    monkeypatch.setattr("core.ui.main_navigation.TAB_SPECS", [("lineages", '<Тест & "проверка">')])
    html = build_main_navigation_html("lineages", {})
    assert "&lt;Тест &amp; &quot;проверка&quot;&gt;" in html
    assert '<Тест & "проверка">' not in html
