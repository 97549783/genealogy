from __future__ import annotations
import copy, json
from pathlib import Path
import pytest
from tabs.source_schools.data import SOURCE_SCHOOLS_DATA_DIR, SourceSchoolDataError, build_source_school_index, load_source_school_catalog, load_source_school_file, validate_source_school_document

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
