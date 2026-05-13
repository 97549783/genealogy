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
    assert meta["Иванов И.И."] == "article_author"


def test_selectable_people_labels_are_article_author_names(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Аспирант", "supervisors_1.name": "Иванов Иван Иванович"}])
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Иванов И.И."}]))

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=True)

    assert "Иванов И.И." in options
    assert "Иванов Иван Иванович" not in options
    assert meta["Иванов И.И."] == "article_author"


def test_selectable_people_returns_empty_when_article_authors_empty(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Иванов Иван Иванович", "supervisors_1.name": ""}])
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame(columns=["Article_id", "Name"]))

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=True)

    assert options == []
    assert meta == {}


def test_initials_only_options_come_from_article_authors(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame([{"candidate_name": "Иванов Иван Иванович", "supervisors_1.name": ""}])
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Неизвестный Н.Н."}]))

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=False)

    assert "Неизвестный Н.Н." in options
    assert meta["Неизвестный Н.Н."] == "article_author"


def test_all_article_authors_appear(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame(
        [
            {"candidate_name": "Григорьев Сергей Георгиевич", "supervisors_1.name": ""},
            {"candidate_name": "Григорьева Марина Александровна", "supervisors_1.name": ""},
        ]
    )
    monkeypatch.setattr(
        matching,
        "load_article_authors",
        lambda: pd.DataFrame(
            [
                {"Article_id": "A1", "Name": "Григорьев Сергей Георгиевич"},
                {"Article_id": "A2", "Name": "Григорьев Н.Ф."},
                {"Article_id": "A3", "Name": "Григорьева Марина Александровна"},
            ]
        ),
    )

    options, meta = matching.compute_selectable_people(df_lineage, include_without_descendants=False)

    assert options == ["Григорьев Н.Ф.", "Григорьев Сергей Георгиевич", "Григорьева Марина Александровна"]
    assert meta == {option: "article_author" for option in options}


def test_exact_full_name_match_beats_initials_ambiguity(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame(
        [
            {"candidate_name": "Григорьев Сергей Георгиевич", "supervisors_1.name": ""},
            {"candidate_name": "Григорьев Семён Георгиевич", "supervisors_1.name": ""},
        ]
    )
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Григорьев Сергей Георгиевич"}]))

    resolution = matching.resolve_article_author_to_lineage_root("Григорьев Сергей Георгиевич", df_lineage)

    assert resolution.root_name == "Григорьев Сергей Георгиевич"
    assert resolution.ambiguous_full_names == ()
    assert resolution.is_exact_match is True


def test_short_initials_remain_ambiguous(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame(
        [
            {"candidate_name": "Григорьев Сергей Георгиевич", "supervisors_1.name": ""},
            {"candidate_name": "Григорьев Семён Георгиевич", "supervisors_1.name": ""},
        ]
    )
    monkeypatch.setattr(matching, "load_article_authors", lambda: pd.DataFrame([{"Article_id": "A1", "Name": "Григорьев С.Г."}]))

    resolution = matching.resolve_article_author_to_lineage_root("Григорьев С.Г.", df_lineage)

    assert resolution.root_name is None
    assert set(resolution.ambiguous_full_names) == {"Григорьев Сергей Георгиевич", "Григорьев Семён Георгиевич"}


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
        {"Иванов И.И.": "article_author"},
        df_lineage,
        {},
        "direct",
    )

    assert seen["root"] == "Иванов Иван Иванович"
    assert names == {"Иванов Иван Иванович", "Ученик Уч Ученикович"}


def test_school_membership_uses_tree_tab_root_for_exact_full_name(monkeypatch) -> None:
    _clear_matching_caches()
    df_lineage = pd.DataFrame(
        [
            {"candidate_name": "Григорьев Сергей Георгиевич", "supervisors_1.name": ""},
            {"candidate_name": "Григорьев Семён Георгиевич", "supervisors_1.name": ""},
        ]
    )
    seen = {}

    class _Graph:
        def has_node(self, node):
            return node == "Григорьев Сергей Георгиевич"

        def successors(self, node):
            return []

        def nodes(self):
            return ["Григорьев Сергей Георгиевич"]

    def _fake_lineage(df, idx, root):
        seen["root"] = root
        return _Graph(), None

    monkeypatch.setattr(matching, "lineage", _fake_lineage)

    names = matching.get_school_member_names(
        "Григорьев Сергей Георгиевич",
        {"Григорьев Сергей Георгиевич": "article_author"},
        df_lineage,
        {},
        "all",
    )

    assert seen["root"] == "Григорьев Сергей Георгиевич"
    assert names == {"Григорьев Сергей Георгиевич"}
