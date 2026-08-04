from __future__ import annotations
import copy
from tabs.source_schools.data import SOURCE_SCHOOLS_DATA_DIR, load_source_school_file
from tabs.source_schools.tables import build_evidence_dataframe, build_people_dataframe, filter_people_dataframe

def doc(): return load_source_school_file(SOURCE_SCHOOLS_DATA_DIR/'vygotsky_school_sources_demo.v1.json')

def test_people_dataframe_and_columns():
    df=build_people_dataframe(doc()); assert len(df)==47
    for c in ['ID','Представитель','Категория','Роли','Связь с Выготским','Период взаимодействия','Группы и контексты','Основной вклад','Уверенность','Число источников','Идентификаторы источников']: assert c in df.columns

def test_source_counts_distinct():
    df=build_people_dataframe(doc()); assert int(df.loc[df['Представитель']=='Александр Романович Лурия','Число источников'].iloc[0])==2

def test_filters_work():
    df=build_people_dataframe(doc())
    assert len(filter_people_dataframe(df, query='лУрИя'))==1
    assert set(filter_people_dataframe(df, categories=['основатель'])['Категория'])=={'основатель'}
    assert all('ученик' in x for x in filter_people_dataframe(df, roles=['ученик'])['Роли'])
    assert all('g1' in x for x in filter_people_dataframe(df, groups=['g1'])['Группы и контексты'])
    assert all('s1' in x for x in filter_people_dataframe(df, source_ids=['s1'])['Идентификаторы источников'])
    assert filter_people_dataframe(df, minimum_confidence=.95)['Уверенность'].min()>=.95
    assert len(filter_people_dataframe(df, categories=['ученик'], roles=['ученик'], minimum_confidence=.55))>0

def test_transformations_do_not_mutate_document():
    d=doc(); before=copy.deepcopy(d); build_people_dataframe(d); assert d==before

def test_evidence_source_ids_resolved():
    ev=build_evidence_dataframe(doc()); assert 'Источник 1' in set(ev['Источник'])
