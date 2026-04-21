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
