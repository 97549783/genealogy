from __future__ import annotations

from tabs.articles.data import make_elibrary_url, make_journal_article_url


def test_article_link_helpers() -> None:
    assert make_journal_article_url("1329") == "https://info.infojournal.ru/jour/article/view/1329"
    assert make_elibrary_url("10.32517/0234-0453-2025-40-4-76-86") == "https://elibrary.ru/10.32517/0234-0453-2025-40-4-76-86"
    assert make_elibrary_url("") == ""
    assert make_elibrary_url(None) == ""
