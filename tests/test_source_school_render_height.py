"""Высота iframe должна совпадать с внутренней высотой большого дерева."""
from __future__ import annotations

import json
import re

import pytest
from streamlit.testing.v1 import AppTest

from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import build_markmap_html
from source_school_fixtures import VYGOTSKY_PATH


@pytest.mark.parametrize('school_id', [
    'rostov_philosophical_school',
    'russian_noosphere_scientific_school',
])
def test_large_source_tree_iframe_keeps_the_full_renderer_height(school_id):
    document = json.loads((VYGOTSKY_PATH.parent / (school_id + '.json')).read_text(encoding='utf-8'))
    tree = build_source_school_overview_tree(document)
    _, expected_height = build_markmap_html(tree.graph, tree.root_id)
    assert expected_height > 950
    app = AppTest.from_string('''
import streamlit as st
from unittest.mock import patch
from tabs.source_schools.tab import render_source_schools_tab
import tabs.source_schools.sections as sections
original_html=sections.components.html
def capture_height(markup, **kwargs):
    st.session_state['captured_tree_height']=kwargs['height']
    return original_html(markup, **kwargs)
with patch.object(sections.components, 'html', capture_height):
    render_source_schools_tab()
''')
    app.query_params.update(tab='source_schools', school=school_id, view='tree')
    app.run(timeout=60)
    assert not app.exception
    iframe = app.get('iframe')[0].proto
    assert app.session_state['captured_tree_height'] == expected_height
    assert re.search(r'height:\s*' + str(expected_height) + r'px', iframe.srcdoc)


def test_people_table_highlights_matches_and_hides_only_when_requested():
    from source_school_fixtures import synthetic_document

    document = synthetic_document()
    code = (
        'import json\n'
        'from core.source_schools.data import build_source_school_index\n'
        'from tabs.source_schools.sections import render_people_section\n'
        'document=json.loads(' + repr(json.dumps(document, ensure_ascii=False)) + ')\n'
        'render_people_section(document,build_source_school_index(document))'
    )
    app = AppTest.from_string(code).run(timeout=30)
    query = next(w for w in app.text_input if w.label == 'Поиск по представителям')
    query.set_value('Альфа'); app.run(timeout=30)
    assert not app.exception
    treatment = next(w for w in app.radio if w.label == 'Режим отображения')
    assert treatment.value == 'highlight'

    def table_body():
        table = next(m.value for m in app.markdown if '<tbody>' in m.value)
        return table.split('<tbody>', 1)[1].split('</tbody>', 1)[0]

    assert table_body().count('<tr') == 4
    assert table_body().count('<tr class="source-schools-match">') == 1
    treatment.set_value('hide'); app.run(timeout=30)
    assert not app.exception
    assert table_body().count('<tr') == 1
    assert 'Альфа Исследователь' in table_body()
    assert 'Бета Исследователь' not in table_body()
