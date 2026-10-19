"""End-to-end Streamlit checks for the shared school views and durable routes."""
from __future__ import annotations
import copy
import json
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import pytest
from streamlit.testing.v1 import AppTest
from source_school_fixtures import load_vygotsky, synthetic_document

APP='from tabs.source_schools.tab import render_source_schools_tab\nrender_source_schools_tab()'


def text(app):
    return '\n'.join(str(getattr(i,'value','')) for group in [app.markdown,app.caption,app.warning,app.error,app.info,app.text,app.subheader] for i in group)


def start(*, school='vygotsky_cultural_historical_school', view=None, person=None, code=APP):
    app=AppTest.from_string(code)
    app.query_params.update({'tab':'source_schools','school':school})
    if view:app.query_params['view']=view
    if person:app.query_params['person']=person
    return app.run(timeout=60)


def widget(app,kind,label):
    return next(w for w in getattr(app,kind) if w.label==label)


def section(app,key):
    widget(app,'radio','Режим просмотра').set_value(key)
    return app.run(timeout=60)


class Anchors(HTMLParser):
    def __init__(self,source):
        super().__init__();self.links=[];self.feed(source)
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.append(dict(attrs))


def catalog_app(documents):
    values=[{'school_id':d['школа']['идентификатор_школы'],'label':d['школа']['каноническое_название'],'path':'virtual.json','document':d} for d in documents]
    return '''
import json
from unittest.mock import patch
import tabs.source_schools.tab as tab
catalog=json.loads(CATALOG)
with patch.object(tab,'load_source_school_catalog',lambda:catalog):
    tab.render_source_schools_tab()
'''.replace('CATALOG',repr(json.dumps(values,ensure_ascii=False)))


def test_overview_loads_the_six_school_catalog_and_vygotsky_invariants():
    app=start();t=text(app)
    assert not app.exception and 'Школы по источникам' in t
    assert len(widget(app,'selectbox','Научная школа').options)==6
    assert any(m.value=='51' for m in app.metric)
    assert any(m.value=='35' for m in app.metric)
    assert widget(app,'radio','Режим просмотра').options==['Обзор','Состав школы','Группы и хронология','Идеи и направления','Источники и подтверждения','Расхождения и качество данных']
    names=[f['название'] for f in load_vygotsky()['классификации']['гибкие_измерения']]
    assert all(any(w.label==name for w in app.multiselect) for name in names)
    assert 'Traceback' not in t


def test_five_facets_and_no_primary_render_without_fixed_vygotsky_categories():
    d=synthetic_document(facet_count=5)
    app=start(school='synthetic_school',view='table',code=catalog_app([d]))
    assert not app.exception
    assert all(any(w.label==f['название'] for w in app.multiselect) for f in d['классификации']['гибкие_измерения'])
    assert 'Научное руководство и обучение' not in text(app)
    assert not any('Основная категория'==w.label for w in app.multiselect)


def test_zero_facets_and_no_primary_render_a_flat_school_view():
    d=synthetic_document(facet_count=0)
    app=start(school='synthetic_school',view='together',code=catalog_app([d]))
    assert not app.exception
    assert 'Альфа Исследователь' in text(app)
    assert app.get('iframe')


def test_common_filters_accept_multiple_dimensions_and_keep_ids_in_session_state():
    app=start();first=widget(app,'multiselect','Исторические группы и контексты');second=widget(app,'multiselect','Периоды')
    first.set_value(['kharkov_group']);second.set_value(['network_1931_1934']);app.run(timeout=60)
    assert not app.exception
    assert widget(app,'multiselect','Исторические группы и контексты').value==['kharkov_group']
    assert widget(app,'multiselect','Периоды').value==['network_1931_1934']


def test_table_names_open_school_context_cards_in_new_tabs():
    app=start(view='table');assert not app.exception
    links=Anchors(text(app)).links
    cards=[]
    for link in links:
        q=parse_qs(urlparse(link.get('href','')).query)
        if q.get('view')==['person'] and q.get('person'):
            cards.append((link,q))
    assert cards
    assert all(link.get('target')=='_blank' for link,q in cards)
    assert all(q['tab']==['source_schools'] and q['school']==['vygotsky_cultural_historical_school'] for link,q in cards)
    assert all(q['person'][0] in {p['id'] for p in load_vygotsky()['объекты']['персоны']} for link,q in cards)


def test_person_deeplink_opens_the_requested_card_and_preserves_school_context():
    app=start(view='person',person='a_a_shein');assert not app.exception
    assert 'А. А. Шеин' in text(app)
    assert app.query_params['school']==['vygotsky_cultural_historical_school'] or app.query_params['school']=='vygotsky_cultural_historical_school'
    assert 'SourceSchoolDataError' not in text(app)


def test_school_change_clears_person_route_and_old_filter_state():
    app=start(view='person',person='a_a_shein')
    widget(app,'selectbox','Научная школа').set_value('rostov_philosophical_school');app.run(timeout=60)
    assert not app.exception
    assert app.query_params.get('person') in [None,[],[''],'']
    assert 'А. А. Шеин' not in text(app)
    assert 'Ростовская философская школа' in text(app)


def test_invalid_school_person_and_view_routes_warn_without_tracebacks():
    for params in [{'school':'missing_school'},{'view':'person','person':'missing_person'},{'view':'missing_view'}]:
        app=start(**params)
        assert not app.exception and app.warning
        assert 'Traceback' not in text(app)


def test_all_secondary_sections_render_with_native_data_and_human_labels():
    for key,expected in [('people','Выготский'),('groups','Исследовательские группы'),('ideas','Идея'),('sources','Источники'),('quality','Качество')]:
        app=section(start(),key)
        assert not app.exception
        assert expected.lower() in text(app).lower()
        assert "{'" not in text(app)


def test_invalid_loader_result_shows_a_domain_error_without_traceback():
    code='''
from unittest.mock import patch
import tabs.source_schools.tab as tab
from core.source_schools.data import SourceSchoolDataError
def bad():raise SourceSchoolDataError('Русская ошибка проверки.')
with patch.object(tab,'load_source_school_catalog',bad):tab.render_source_schools_tab()
'''
    app=AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    assert 'Не удалось загрузить' in text(app) and 'Русская ошибка проверки.' in text(app)
    assert 'Traceback' not in text(app)


def test_empty_catalog_has_a_clear_message():
    code='''
from unittest.mock import patch
import tabs.source_schools.tab as tab
with patch.object(tab,'load_source_school_catalog',lambda:[]):tab.render_source_schools_tab()
'''
    app=AppTest.from_string(code).run(timeout=30)
    assert not app.exception and 'В каталоге пока нет доступных школ.' in text(app)


def test_table_has_separate_card_and_genealogy_links_with_safe_new_tabs():
    from core.source_schools.tables import build_people_dataframe
    from tabs.source_schools.sections import _table_html
    d=synthetic_document();df=build_people_dataframe(d).iloc[:1]
    card='https://genealogy.example/?tab=source_schools&school=synthetic_school&view=person&person=person_alpha'
    genealogy='https://genealogy.example/?tab=lineages&root=Alpha'
    html=_table_html(df,['Имя','field:contribution'],{'Имя':'Имя','field:contribution':'Вклад'},
        {'person_alpha':{'href':card}}, {'person_alpha':{'href':genealogy,'title':'Научное руководство'}})
    links=Anchors(html).links
    assert len(links)==2
    assert {a['href'] for a in links}=={card,genealogy}
    assert all(a['target']=='_blank' and 'noopener' in a['rel'] for a in links)
    assert '<svg' in html and 'Научное руководство' in html
    assert parse_qs(urlparse(links[0]['href']).query)['view']==['person']
    unsafe=_table_html(df,['Имя'],{'Имя':'Имя'},{'person_alpha':{'href':'javascript:alert(1)'}},{})
    assert not Anchors(unsafe).links


def test_live_catalog_update_discards_only_obsolete_filter_values():
    old=synthetic_document();new=copy.deepcopy(old)
    new['классификации']['гибкие_измерения'][0]['значения']=[v for v in new['классификации']['гибкие_измерения'][0]['значения'] if v['id']!='group_beta']
    new['классификационные_назначения']=[a for a in new['классификационные_назначения'] if a['значение']!='group_beta']
    code='''
import json
import streamlit as st
from core.source_schools.data import build_source_school_index
from tabs.source_schools.sections import render_overview_section
document=json.loads(NEW if st.session_state.get('updated_catalog') else OLD)
render_overview_section(document,build_source_school_index(document),presentation='table')
'''.replace('NEW',repr(json.dumps(new,ensure_ascii=False))).replace('OLD',repr(json.dumps(old,ensure_ascii=False)))
    app=AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    widget(app,'multiselect','Исторические группы').set_value(['group_alpha','group_beta']);app.run(timeout=30)
    app.session_state['updated_catalog']=True;app.run(timeout=30)
    assert not app.exception
    assert widget(app,'multiselect','Исторические группы').value==['group_alpha']


def test_table_pagination_resets_after_a_filter_changes_the_result():
    app=start(view='table');assert not app.exception
    widget(app,'selectbox','Строк на странице').set_value(25);app.run(timeout=60)
    widget(app,'number_input','Страница таблицы').set_value(3);app.run(timeout=60)
    assert not app.exception
    widget(app,'text_input','Поиск по представителям').set_value('А. А. Шеин')
    widget(app,'radio','Режим отображения').set_value('hide');app.run(timeout=60)
    assert not app.exception
    assert widget(app,'number_input','Страница таблицы').value==1
    assert 'строк в выборке: 1' in text(app)


def test_table_defaults_to_all_rows_and_pagination_is_optional():
    app=start(view='table')
    assert not app.exception

    def row_count():
        table=next(m.value for m in app.markdown if '<tbody>' in m.value)
        return table.split('<tbody>',1)[1].split('</tbody>',1)[0].count('<tr')

    assert widget(app,'selectbox','Строк на странице').value=='all'
    assert not any(w.label=='Страница таблицы' for w in app.number_input)
    assert row_count()==51
    widget(app,'selectbox','Строк на странице').set_value(25);app.run(timeout=60)
    assert not app.exception and row_count()==25
    widget(app,'number_input','Страница таблицы').set_value(3);app.run(timeout=60)
    assert row_count()==1
    widget(app,'selectbox','Строк на странице').set_value('all');app.run(timeout=60)
    assert not app.exception and row_count()==51
    assert not any(w.label=='Страница таблицы' for w in app.number_input)
    widget(app,'text_input','Поиск по представителям').set_value('Нет такого человека')
    widget(app,'radio','Режим отображения').set_value('hide');app.run(timeout=60)
    assert not app.exception and row_count()==0


def test_tree_restores_unidirectional_default_and_can_switch_both_ways():
    app=start(view='tree')
    assert not app.exception
    assert widget(app,'radio','Режим ветвления').value=='Одностороннее ветвление'
    assert '<svg id="mm">' in app.get('iframe')[0].proto.srcdoc
    assert 'mm-svg-left' not in app.get('iframe')[0].proto.srcdoc
    widget(app,'radio','Режим ветвления').set_value('Двустороннее ветвление');app.run(timeout=60)
    assert not app.exception and 'mm-svg-left' in app.get('iframe')[0].proto.srcdoc
    widget(app,'radio','Представление').set_value('together');app.run(timeout=60)
    assert not app.exception
    assert widget(app,'radio','Режим ветвления').value=='Двустороннее ветвление'
    assert 'mm-svg-right' in app.get('iframe')[0].proto.srcdoc
    widget(app,'radio','Режим ветвления').set_value('Одностороннее ветвление');app.run(timeout=60)
    assert not app.exception and '<svg id="mm">' in app.get('iframe')[0].proto.srcdoc


def test_presentation_switch_updates_the_durable_route():
    app=start(view='tree')
    widget(app,'radio','Представление').set_value('table');app.run(timeout=60)
    assert not app.exception
    assert app.query_params['view'] in ['table',['table']]
    assert 'Табличное представление' in text(app)
    widget(app,'radio','Представление').set_value('together');app.run(timeout=60)
    assert not app.exception and app.get('iframe')
    assert app.query_params['view'] in ['together',['together']]
    assert 'Табличное представление' in text(app)


def test_school_change_does_not_apply_previous_schools_facet_values():
    app=start(view='table')
    widget(app,'multiselect','Исторические группы и контексты').set_value(['kharkov_group']);app.run(timeout=60)
    widget(app,'selectbox','Научная школа').set_value('rostov_philosophical_school');app.run(timeout=60)
    assert not app.exception
    assert all(not w.value for w in app.multiselect if w.label in ['Роли в описании','Проблематика','Источниковые контексты'])
    assert not any(w.label=='Исторические группы и контексты' for w in app.multiselect)
    assert 'Харьковская группа' not in text(app)


@pytest.mark.parametrize('school_id',[
    'bryansk_scientific_philosophical_school','perm_philosophical_school','rostov_philosophical_school',
    'ural_philosophical_school','russian_noosphere_scientific_school'])
def test_each_philosophical_school_opens_its_own_native_table_and_counts(school_id):
    from source_school_fixtures import VYGOTSKY_PATH
    d=json.loads((VYGOTSKY_PATH.parent/(school_id+'.json')).read_text(encoding='utf-8'))
    app=start(school=school_id,view='table')
    assert not app.exception
    assert d['школа']['каноническое_название'] in text(app)
    metrics={m.label:m.value for m in app.metric}
    assert metrics['В составе описания']==str(sum(m['решение']=='включено' for m in d['состав']))
    assert metrics['Источники']==str(len(d['источники']))
    assert 'Табличное представление' in text(app)
    assert all(any(w.label==f['название'] for w in app.multiselect) for f in d['классификации']['гибкие_измерения'])
    from core.source_schools.tables import build_people_dataframe
    body=next(m.value for m in app.markdown if '<tbody>' in m.value).split('<tbody>',1)[1].split('</tbody>',1)[0]
    assert body.count('<tr')==len(build_people_dataframe(d))
    assert not any(w.label=='Страница таблицы' for w in app.number_input)


def test_incoming_table_permalink_overrides_a_previous_local_section():
    app=section(start(view='table'),'sources')
    assert not app.exception
    app.query_params.clear()
    app.query_params.update({'tab':'source_schools','school':'rostov_philosophical_school','view':'table'})
    app.run(timeout=60)
    assert not app.exception
    assert widget(app,'radio','Режим просмотра').value=='overview'
    assert 'Табличное представление' in text(app)


def test_philosophical_membership_division_filters_tree_and_full_table_together():
    app=start(school='rostov_philosophical_school',view='together')
    assert not app.exception
    assert widget(app,'multiselect','Отношение к школе').options==['Представители','Связанные лица']
    markup=app.get('iframe')[0].proto.srcdoc
    assert 'Представители' in markup and 'Связанные лица' in markup
    widget(app,'multiselect','Отношение к школе').set_value(['связанное_лицо'])
    widget(app,'radio','Режим отображения').set_value('hide');app.run(timeout=60)
    assert not app.exception
    table=next(m.value for m in app.markdown if '<tbody>' in m.value)
    body=table.split('<tbody>',1)[1].split('</tbody>',1)[0]
    assert body.count('<tr')==68 and '<td>Представитель</td>' not in body
    markup=app.get('iframe')[0].proto.srcdoc
    assert 'Представители' in markup and 'Связанные лица' in markup
    assert '"_hidden": true' in markup
    assert 'Совпало персон: 68 из 82' in text(app)


def test_idea_sections_follow_dictionary_metadata_without_parsing_codes_or_prose():
    from tabs.source_schools.sections import _school_idea_records
    d=synthetic_document();school=d['школа']['идентификатор_школы']
    # A school can rename a standard section and use it for custom fields.
    next(f for f in d['словари']['поля_сведений'] if f['код']=='main_ideas')['раздел']='Мировоззрение'
    d['отображение']['разделы_паспорта'].append('Мировоззрение')
    for code,section_name,value in [
        ('custom_explanation','Теоретические основания','Содержательное объяснение'),
        ('custom_procedure','Методы','Исследовательская процедура'),
        ('custom_beliefs','Мировоззрение','Общая интеллектуальная позиция'),
        ('custom_location','География','В названии места есть слова теория и метод, но это география')]:
        definition=copy.deepcopy(d['словари']['поля_сведений'][0])
        definition.update(код=code,раздел=section_name,название='Собственное поле '+code)
        d['словари']['поля_сведений'].append(definition)
        r=copy.deepcopy(d['сведения'][0]);r.update(id='info_'+code,субъект=school,поле=code)
        r['значение']['значение']=value;d['сведения'].append(r)
    rejected=copy.deepcopy(d['сведения'][-4]);rejected.update(id='rejected_idea',решение='отклонено')
    d['сведения'].append(rejected)
    before=copy.deepcopy(d)
    assert {r['id'] for r in _school_idea_records(d)}=={'info_custom_explanation','info_custom_procedure','info_custom_beliefs'}
    assert d==before


def test_vygotsky_idea_view_retains_theory_methods_and_theoretical_qualifications():
    app=section(start(),'ideas')
    assert not app.exception
    t=text(app)
    assert 'Психические функции человека имеют социальное и культурно-опосредствованное происхождение' in t
    assert 'экспериментально-генетический метод и метод двойной стимуляции' in t
    assert 'сравнительно-генетический анализ' in t
    assert 'Не тождествен современному психосемантическому методу' in t
    assert 'Источник №' in t and 'Унаследованная сверка' in t
