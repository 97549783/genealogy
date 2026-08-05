from __future__ import annotations
import copy, json
from pathlib import Path
import pytest
from core.source_schools.data import SOURCE_SCHOOLS_DATA_DIR, SourceSchoolDataError, build_source_school_index, load_source_school_catalog, load_source_school_file, validate_source_school_document

PATH=SOURCE_SCHOOLS_DATA_DIR/'vygotsky_school_sources_demo.v1.json'

def doc(): return load_source_school_file(PATH)

def test_vygotsky_json_loads_and_counts():
    d=doc(); assert d['школа']['идентификатор_школы']=='vygotsky_cultural_historical_school'; assert d['демо_представление']['название_в_выпадающем_списке']=='Лев Семёнович Выготский'; assert len(d['школа']['персоны'])==47; assert len(d['школа']['источники'])==8; assert len(d['школа']['подтверждения'])==34

def test_catalog_contains_one_school():
    c=load_source_school_catalog(SOURCE_SCHOOLS_DATA_DIR); assert len(c)==1; assert c[0]['school_id']=='vygotsky_cultural_historical_school'; assert c[0]['label']=='Лев Семёнович Выготский'

def test_cross_references_resolve():
    idx=build_source_school_index(doc()); assert len(idx['persons'])==47 and len(idx['sources'])==8 and len(idx['evidence'])==34

def test_duplicate_person_id_raises():
    d=copy.deepcopy(doc()); d['школа']['персоны'][1]['id']=d['школа']['персоны'][0]['id']
    with pytest.raises(SourceSchoolDataError, match='повторяющийся идентификатор'): validate_source_school_document(d)

def test_unknown_evidence_in_person_raises():
    d=copy.deepcopy(doc()); d['школа']['персоны'][0]['подтверждения']=['нет']
    with pytest.raises(SourceSchoolDataError, match='неизвестное подтверждение'): validate_source_school_document(d)

def test_unknown_source_in_evidence_raises():
    d=copy.deepcopy(doc()); d['школа']['подтверждения'][0]['идентификатор_источника']='нет'
    with pytest.raises(SourceSchoolDataError, match='неизвестный источник'): validate_source_school_document(d)

def test_unknown_group_participant_raises():
    d=copy.deepcopy(doc()); d['школа']['внутренняя_структура']['исследовательские_группы'][0]['участники'].append('нет')
    with pytest.raises(SourceSchoolDataError, match='Неизвестная персона'): validate_source_school_document(d)

def test_bad_confidence_raises():
    d=copy.deepcopy(doc()); d['школа']['персоны'][0]['уверенность']=1.5
    with pytest.raises(SourceSchoolDataError, match='уверенность'): validate_source_school_document(d)

def test_stale_summary_raises():
    d=copy.deepcopy(doc()); d['демо_представление']['сводные_показатели']['число_персон']=1
    with pytest.raises(SourceSchoolDataError, match='Сводные показатели устарели'): validate_source_school_document(d)

def test_duplicate_school_id_across_catalog_raises(tmp_path):
    text=PATH.read_text(encoding='utf-8'); (tmp_path/'a.json').write_text(text,encoding='utf-8'); (tmp_path/'b.json').write_text(text,encoding='utf-8')
    with pytest.raises(SourceSchoolDataError, match='идентификатор школы'): load_source_school_catalog(tmp_path)

def test_malformed_json_raises(tmp_path):
    p=tmp_path/'bad.json'; p.write_text('{',encoding='utf-8')
    with pytest.raises(SourceSchoolDataError, match='некорректный JSON'): load_source_school_file(p)

def test_missing_directory_returns_empty_catalog(tmp_path):
    assert load_source_school_catalog(tmp_path/'нет') == []


def test_summary_aliases_from_supplied_contract_are_supported():
    d = copy.deepcopy(doc())
    summary = d['демо_представление']['сводные_показатели']
    summary['количество_персон'] = summary.pop('число_персон')
    summary['количество_источников'] = summary.pop('число_источников')
    summary['количество_подтверждений'] = summary.pop('число_подтверждений')
    summary['по_категориям'] = summary.pop('персоны_по_категориям')
    d['контроль_качества'].pop('персоны_по_категориям')
    validate_source_school_document(d)


def test_person_field_aliases_are_normalized():
    d = copy.deepcopy(doc())
    person = d['школа']['персоны'][0]
    person['имя'] = person.pop('полное_имя')
    person['даты'] = person.pop('годы_жизни')
    person['основные_идеи_или_вклад'] = person.pop('основной_вклад')
    loaded_path = SOURCE_SCHOOLS_DATA_DIR / 'vygotsky_school_sources_demo.v1.json'
    normalized = load_source_school_file(loaded_path)
    assert normalized['школа']['персоны'][0]['полное_имя'] == 'Лев Семёнович Выготский'
    validate_source_school_document(d)


def test_attribution_source_must_match_evidence_source():
    d = copy.deepcopy(doc())
    d['школа']['персоны'][0]['источниковые_атрибуции'][0]['подтверждение'] = 'e2'
    with pytest.raises(SourceSchoolDataError, match='подтверждением другого источника'):
        validate_source_school_document(d)


def test_missing_file_has_domain_error(tmp_path):
    with pytest.raises(SourceSchoolDataError, match='Файл школы не найден'):
        load_source_school_file(tmp_path / 'нет.json')


def test_wrong_list_item_type_has_domain_error():
    d = copy.deepcopy(doc())
    d['школа']['персоны'].append('не объект')
    with pytest.raises(SourceSchoolDataError, match='должен быть объектом'):
        validate_source_school_document(d)


def test_nested_full_json_contract_is_supported():
    d = copy.deepcopy(doc())
    school = d['школа']
    school['дисциплинарная_принадлежность'] = {
        'области': school.pop('дисциплинарные_области'),
        'ключевые_слова': school.pop('ключевые_слова'),
    }
    school['основная_идея'] = {
        'краткая_формулировка': 'Развитие высших психических функций культурно опосредовано.',
        'центральная_проблема': school.pop('проблема'),
        'центральная_гипотеза': school.pop('гипотеза'),
        'центральная_теория': school.pop('теория'),
        'центральный_метод': school.pop('метод'),
        'подтверждения': ['e1'],
    }
    school['хронология']['периоды_развития'][0]['название_периода'] = school['хронология']['периоды_развития'][0].pop('название')
    school['хронология']['периоды_развития'][0]['временной_диапазон'] = school['хронология']['периоды_развития'][0].pop('период')
    school['представители'] = {'ядро': ['p1', 'p2']}
    school['связи_с_другими_школами'] = [{'название': 'Деятельностный подход', 'уверенность': 0.8}]
    d['контроль_качества'] = {
        'число_персон': len(school['персоны']),
        'число_источников': len(school['источники']),
        'число_подтверждений': len(school['подтверждения']),
        'использовано_несколько_источников': True,
        'расхождения_источников_сохранены': True,
        'прямые_и_косвенные_связи_разделены': True,
        'поля_с_недостаточной_информацией': ['точные границы'],
        'потенциально_интерпретативные_выводы': ['нормализация ролей'],
        'замечания': ['проверено'],
    }
    validate_source_school_document(d)


def test_all_confidence_fields_are_validated():
    d = copy.deepcopy(doc())
    d['школа']['связи_с_другими_школами'] = [{'название': 'Школа', 'уверенность': 1.5}]
    with pytest.raises(SourceSchoolDataError, match='уверенность'):
        validate_source_school_document(d)


def test_aggregate_representatives_are_validated():
    d = copy.deepcopy(doc())
    d['школа']['представители'] = {'ученики': ['неизвестно']}
    with pytest.raises(SourceSchoolDataError, match='школа.представители'):
        validate_source_school_document(d)


def test_nested_items_have_domain_errors():
    d = copy.deepcopy(doc())
    d['школа']['внутренняя_структура']['направления'].append('не объект')
    with pytest.raises(SourceSchoolDataError, match='должен быть объектом'):
        validate_source_school_document(d)
