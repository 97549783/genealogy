from __future__ import annotations
import copy
from core.source_schools.data import SOURCE_SCHOOLS_DATA_DIR, load_source_school_file
from core.source_schools.tables import build_evidence_dataframe, build_people_dataframe, filter_people_dataframe

def doc(): return load_source_school_file(SOURCE_SCHOOLS_DATA_DIR/'vygotsky_school_sources_demo.v1.json')

def test_people_dataframe_and_columns():
    df=build_people_dataframe(doc()); assert len(df)==47
    for c in ['ID','Представитель','Категория','Роли','Связь с Выготским','Период взаимодействия','Группы и контексты','Основной вклад','Уверенность','Число источников','Идентификаторы источников']: assert c in df.columns

def test_source_counts_distinct():
    d = doc()
    df = build_people_dataframe(d)
    person = next(p for p in d['школа']['персоны'] if len({a['идентификатор_источника'] for a in p.get('источниковые_атрибуции', [])}) > 1)
    expected = len({a['идентификатор_источника'] for a in person.get('источниковые_атрибуции', [])})
    actual = int(df.loc[df['ID'] == person['id'], 'Число источников'].iloc[0])
    assert actual == expected

def test_filters_work():
    df = build_people_dataframe(doc())
    sample = df.iloc[1]
    query_fragment = str(sample['Представитель'])[:4].swapcase()
    category = sample['Категория']
    role = str(sample['Роли']).split('; ')[0]
    group = str(sample['Группы и контексты']).split('; ')[0]
    source_id = str(sample['Идентификаторы источников']).split('; ')[0]
    assert sample['ID'] in set(filter_people_dataframe(df, query=query_fragment)['ID'])
    assert set(filter_people_dataframe(df, categories=[category])['Категория']) == {category}
    assert all(role in x for x in filter_people_dataframe(df, roles=[role])['Роли'])
    assert all(group in x for x in filter_people_dataframe(df, groups=[group])['Группы и контексты'])
    assert all(source_id in x for x in filter_people_dataframe(df, source_ids=[source_id])['Идентификаторы источников'])
    assert filter_people_dataframe(df, minimum_confidence=.95)['Уверенность'].min() >= .95
    assert sample['ID'] in set(filter_people_dataframe(df, categories=[category], roles=[role], minimum_confidence=0)['ID'])

def test_transformations_do_not_mutate_document():
    d=doc(); before=copy.deepcopy(d); build_people_dataframe(d); assert d==before

def test_evidence_source_ids_resolved():
    d = doc()
    ev = build_evidence_dataframe(d)
    source_labels = {s.get('краткое_название') or s.get('библиографическое_описание') for s in d['школа']['источники']}
    assert set(ev['Источник']).issubset(source_labels)
