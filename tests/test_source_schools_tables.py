"""Tables share composition, classifications and source grounds with every view."""
from __future__ import annotations
import copy

from core.source_schools.tables import build_evidence_dataframe, build_people_dataframe, filter_people_dataframe
from source_school_fixtures import load_vygotsky, synthetic_document


def test_people_dataframe_uses_included_composition_and_dynamic_columns():
    d=load_vygotsky();df=build_people_dataframe(d)
    assert len(df)==51 and df['id'].is_unique
    for key in ['id','Имя','Отношение к школе','Основная категория','field:contribution','Уверенность','Число источников','Идентификаторы источников']:
        assert key in df.columns
    for facet in d['классификации']['гибкие_измерения']:
        assert 'facet:'+facet['id'] in df.columns
    assert set(df['id'])=={m['персона'] for m in d['состав'] if m['решение']=='включено'}


def test_source_counts_are_distinct_across_identification_membership_and_information():
    d=synthetic_document();df=build_people_dataframe(d).set_index('id')
    assert int(df.loc['person_alpha','Число источников'])==1
    info=next(i for i in d['сведения'] if i['субъект']=='person_alpha')
    info['основания']=['evidence_alpha','evidence_beta']
    df=build_people_dataframe(d).set_index('id')
    assert int(df.loc['person_alpha','Число источников'])==2
    assert set(df.loc['person_alpha','Идентификаторы источников'].split('; '))=={'source_alpha','source_beta'}


def test_source_count_resolves_transitive_support_without_duplicate_sources():
    d=synthetic_document();alpha=d['сведения'][0];beta=d['сведения'][1]
    beta['основания']=['evidence_beta'];alpha['основания']=[];alpha['опирается_на']=[beta['id']]
    df=build_people_dataframe(d).set_index('id')
    assert int(df.loc['person_alpha','Число источников'])==2


def test_filters_accept_name_primary_facet_ids_and_sources():
    d=synthetic_document(primary=True);df=build_people_dataframe(d)
    assert filter_people_dataframe(df,query='аЛьФа')['id'].tolist()==['person_alpha']
    assert filter_people_dataframe(df,primary_categories=['Категория Альфа'])['id'].tolist()==['person_alpha']
    assert filter_people_dataframe(df,facet_selections={'historical_group':['group_alpha']})['id'].tolist()==['person_alpha']
    assert len(filter_people_dataframe(df,source_ids=['source_alpha']))==4
    assert filter_people_dataframe(df,source_ids=['missing_source']).empty


def test_empty_explicit_selection_is_empty_but_no_selection_retains_all_people():
    df=build_people_dataframe(synthetic_document())
    assert len(filter_people_dataframe(df))==4
    assert filter_people_dataframe(df,person_ids=set()).empty
    assert filter_people_dataframe(df,person_ids={'person_beta'})['id'].tolist()==['person_beta']


def test_five_facets_and_no_primary_have_native_columns():
    d=synthetic_document(facet_count=5);df=build_people_dataframe(d)
    assert all('facet:'+f['id'] in df.columns for f in d['классификации']['гибкие_измерения'])
    assert 'Основная категория' not in df.columns or not df['Основная категория'].fillna('').any()
    assert len(df)==4 and 'person_candidate' not in set(df['id'])


def test_archival_confidence_does_not_hide_people_and_unknown_stays_nan():
    d=synthetic_document();d['объекты']['персоны'][0]['оценка_уверенности']={'значение':.01,'происхождение':'прежняя_разметка'}
    df=build_people_dataframe(d).set_index('id')
    assert df.loc['person_alpha','Уверенность']==.01
    assert df.loc[['person_beta','person_gamma','person_delta'],'Уверенность'].isna().all()
    assert len(filter_people_dataframe(df.reset_index()))==4


def test_transformations_do_not_mutate_document():
    d=synthetic_document();before=copy.deepcopy(d)
    build_people_dataframe(d);build_evidence_dataframe(d)
    assert d==before


def test_evidence_source_ids_resolve_to_bibliographic_labels():
    d=synthetic_document();ev=build_evidence_dataframe(d)
    source_labels={s['название'] for s in d['источники']}|{s['библиографическое_описание'] for s in d['источники']}
    assert set(ev['Источник']).issubset(source_labels)
    assert len(ev)==2
