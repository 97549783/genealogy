"""Проверки нумерации и оформления библиографии школ по источникам."""
import json
from pathlib import Path

from core.source_schools.bibliography import build_bibliography_text, build_numbered_bibliography, format_bibliographic_reference

PATH = Path("data/source_schools/vygotsky_school_sources_demo.v1.json")


def test_источники_нумеруются_по_порядку_json():
    document = json.loads(PATH.read_text(encoding="utf-8"))
    bibliography = build_numbered_bibliography(document)
    assert [row["№"] for row in bibliography] == list(range(1, 9))


def test_doi_url_и_дата_обращения_добавляются_без_дублей():
    source = {"библиографическое_описание": "Описание", "doi": "10.1/test", "url": "https://example.org", "дата_обращения": "2026-08-04"}
    assert format_bibliographic_reference(source) == "Описание. DOI: 10.1/test. URL: https://example.org (дата обращения: 04.08.2026)"
    assert format_bibliographic_reference({"библиографическое_описание": "Описание DOI: 10.1/test URL: https://example.org", "doi": "10.1/test", "url": "https://example.org"}).count("10.1/test") == 1


def test_текстовый_список_содержит_номера():
    text = build_bibliography_text(json.loads(PATH.read_text(encoding="utf-8")))
    for number in range(1, 9):
        assert f"{number}." in text
