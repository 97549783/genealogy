from __future__ import annotations


def test_core_ui_and_lineage_modules_importable():
    import core.lineage.graph as lineage_graph
    import core.ui.chrome as chrome
    import core.ui.links as links
    import core.ui.table_display as table_display

    assert hasattr(lineage_graph, "build_index")
    assert hasattr(chrome, "feedback_button")
    assert hasattr(links, "share_button")
    assert hasattr(table_display, "render_dissertations_widget")


def test_dissertation_search_instruction_text_uses_subtabs() -> None:
    from core.ui.chrome import INSTRUCTIONS
    from tabs.profiles.topics_mode import INSTRUCTION_BY_TOPICS

    assert "## Подвкладка «Поиск по формальным признакам»" in INSTRUCTIONS["dissertations"]
    assert "На этой подвкладке доступен поиск диссертаций" in INSTRUCTIONS["dissertations"]
    assert "## Подвкладка «Поиск по тематическим профилям»" in INSTRUCTIONS["profiles"]
    assert "На этой подвкладке реализован содержательный поиск" in INSTRUCTIONS["profiles"]
    assert "На этой подвкладке реализован содержательный поиск" in INSTRUCTION_BY_TOPICS
    assert "Вкладка «Поиск информации о диссертациях»" not in INSTRUCTIONS["dissertations"]
    assert "Вкладка «Поиск по тематическим профилям»" not in INSTRUCTIONS["profiles"]
