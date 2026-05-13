from __future__ import annotations

import pandas as pd

import tabs.articles.author_matching as matching


def _clear_matching_caches() -> None:
    matching._extract_author_names_from_article_authors.clear()
    matching._extract_author_initials_from_article_authors.clear()
    matching.build_initials_to_fullnames.clear()
    matching.compute_selectable_people.clear()


def test_selectable_people_uses_article_authors_not_metadata_authors(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame(
        [
            {"candidate_name": "Аспирант 1", "supervisors_1.name": "Иванов Иван Иванович"},
            {"candidate_name": "Аспирант 2", "supervisors_1.name": "Петров Петр Петрович"},
            {"candidate_name": "Аспирант 3", "supervisors_1.name": "Сидоров Сидор Сидорович"},
        ]
    )
    monkeypatch.setattr(
        matching,
        "load_articles_data",
        lambda: pd.DataFrame(
            [
                {"Article_id": "A1", "Authors": "Сидоров С.С."},
                {"Article_id": "A2", "Authors": "Сидоров С.С."},
            ]
        ),
    )
    monkeypatch.setattr(
        matching,
        "load_article_authors",
        lambda: pd.DataFrame(
            [
                {"Article_id": "A1", "Name": "Иванов И.И."},
                {"Article_id": "A2", "Name": "Петров П.П."},
            ]
        ),
    )

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=True)

    assert "Иванов И.И." in options
    assert "Петров П.П." in options
    assert "Иванов Иван Иванович" not in options
    assert "Петров Петр Петрович" not in options
    assert "Сидоров Сидор Сидорович" not in options
    assert meta["Иванов И.И."] == "leader"



def test_selectable_people_labels_are_article_author_names(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Аспирант", "supervisors_1.name": "Иванов Иван Иванович"}])
    monkeypatch.setattr(matching, "load_articles_data", lambda: pd.DataFrame([{"Article_id": "A1", "Authors": ""}]))
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Иванов И.И."}]))

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=True)

    assert "Иванов И.И." in options
    assert "Иванов Иван Иванович" not in options
    assert meta["Иванов И.И."] == "leader"


def test_selectable_people_returns_empty_when_article_authors_empty(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Иванов Иван Иванович", "supervisors_1.name": ""}])
    monkeypatch.setattr(matching, "load_articles_data", lambda: pd.DataFrame([{"Article_id": "A1", "Authors": "Иванов И.И."}]))
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame(columns=["Article_id", "Name"]))

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=True)

    assert options == []
    assert meta == {}


def test_initials_only_options_come_from_article_authors(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Иванов Иван Иванович", "supervisors_1.name": ""}])
    monkeypatch.setattr(matching, "load_articles_data", lambda: pd.DataFrame([{"Article_id": "A1", "Authors": ""}]))
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Неизвестный Н.Н."}]))

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=True)

    assert "Неизвестный Н.Н." in options
    assert meta["Неизвестный Н.Н."] == "initials_only"


def test_school_member_names_resolve_article_author_label_to_lineage_full_name(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Аспирант", "supervisors_1.name": "Иванов Иван Иванович"}])
    seen = {}

    class _Graph:
        def has_node(self, node):
            return node == "Иванов Иван Иванович"

        def successors(self, node):
            return ["Ученик Уч Ученикович"]

        def nodes(self):
            return ["Иванов Иван Иванович", "Ученик Уч Ученикович"]

    def _fake_lineage(df, idx, root):
        seen["root"] = root
        return _Graph(), None

    monkeypatch.setattr(matching, "lineage", _fake_lineage)

    names = matching.get_school_member_names(
        "Иванов И.И.",
        {"Иванов И.И.": "leader"},
        df_lineage,
        {},
        "direct",
    )

    assert seen["root"] == "Иванов Иван Иванович"
    assert names == {"Иванов Иван Иванович", "Ученик Уч Ученикович"}
