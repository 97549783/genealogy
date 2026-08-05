from __future__ import annotations
from streamlit.testing.v1 import AppTest

APP='''
from tabs.source_schools.tab import render_source_schools_tab
render_source_schools_tab()
'''

def text(app):
    return '\n'.join(getattr(i,'value','') for col in [app.markdown,app.caption,app.warning,app.error,app.info,app.text,app.subheader] for i in col)

def test_renderer_overview_runs():
    app=AppTest.from_string(APP).run(timeout=30); t=text(app)
    assert not app.exception; assert 'Школы по источникам (демо)' in t; assert app.selectbox[0].label=='Научная школа'; assert 'Лев Семёнович Выготский' in app.selectbox[0].options; assert app.radio[0].options==['Обзор','Состав школы','Группы и хронология','Идеи и направления','Источники и подтверждения','Расхождения и качество данных']; assert any(m.label=='Представители' and m.value=='47' for m in app.metric); assert any(m.label=='Источники' and m.value=='8' for m in app.metric); assert any(m.label=='Подтверждения' and m.value=='34' for m in app.metric)

def test_people_mode_shows_filters_and_attributions():
    app=AppTest.from_string(APP).run(timeout=30); app.radio[0].set_value('Состав школы'); app.run(timeout=30); t=text(app)
    assert not app.exception; assert app.text_input[0].label=='Поиск по представителям'; assert 'Найдено представителей: 47' in t; assert 'Источниковые атрибуции' in t

def test_sources_mode_shows_bibliography_and_evidence():
    app=AppTest.from_string(APP).run(timeout=30); app.radio[0].set_value('Источники и подтверждения'); app.run(timeout=30); t=text(app)
    assert not app.exception; assert 'Дата обращения' in t; assert app.multiselect[0].label=='Источник подтверждения'

def test_invalid_loader_result_shows_error_without_traceback():
    app=AppTest.from_string('''
from unittest.mock import patch
import tabs.source_schools.tab as tab
from tabs.source_schools.data import SourceSchoolDataError
def bad(): raise SourceSchoolDataError("Русская ошибка проверки.")
with patch.object(tab, "load_source_school_catalog", bad):
    tab.render_source_schools_tab()
''').run(timeout=30); t=text(app)
    assert not app.exception; assert 'Не удалось загрузить данные школ по источникам.' in t; assert 'Русская ошибка проверки.' in t; assert 'Traceback' not in t

def test_empty_catalog_message():
    app=AppTest.from_string('''
from unittest.mock import patch
import tabs.source_schools.tab as tab
with patch.object(tab, "load_source_school_catalog", lambda: []):
    tab.render_source_schools_tab()
''').run(timeout=30)
    assert 'В каталоге пока нет доступных школ.' in text(app)


def test_groups_ideas_and_quality_modes_are_rendered_without_raw_ids():
    for mode, expected in [
        ('Группы и хронология', 'Исследовательские группы'),
        ('Идеи и направления', 'Основная идея'),
        ('Расхождения и качество данных', 'Качество данных'),
    ]:
        app=AppTest.from_string(APP).run(timeout=30)
        app.radio[0].set_value(mode)
        app.run(timeout=30)
        t=text(app)
        assert not app.exception
        assert expected in t
        assert 'ev_' not in t
        assert "{'" not in t


def test_overview_shows_nested_contract_fields_without_technical_ids():
    app = AppTest.from_string(APP).run(timeout=30)
    t = text(app)
    assert 'Дисциплинарные области' in t
    assert 'Ключевые слова' in t
    assert 'Проблема' in t
    assert 'Гипотеза' in t
    assert 'Теория' in t
    assert 'Метод' in t
    assert 'ev_' not in t
    assert 'src_' not in t
