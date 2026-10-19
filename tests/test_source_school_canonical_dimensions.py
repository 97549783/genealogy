"""One accepted-assignment registry drives filters, tables and exports in v2.1."""
from __future__ import annotations
import copy
from collections import Counter

import pytest

from core.source_schools.data import SourceSchoolDataError, normalize_source_school_document, validate_source_school_document
from core.source_schools.dimensions import build_dimension_coverage, build_dimension_memberships, project_dimension_memberships
from core.source_schools.tables import build_people_dataframe
from core.source_schools.tree import build_supplementary_dimension_catalog, combine_supplementary_selections
from source_school_fixtures import load_vygotsky, synthetic_document


def test_only_accepted_canonical_assignments_define_memberships():
    d=synthetic_document();validate_source_school_document(d);values=build_dimension_memberships(d)
    assert values['historical_group']['group_alpha']==('person_alpha',)
    assert values['period']['stage_0']==('person_alpha','person_beta')
    assert values['research_direction']['research_0']==('person_delta',)
    assert not values['historical_group']['concept_context']


def test_projection_does_not_manufacture_alternative_membership_lists():
    d=synthetic_document();projected=project_dimension_memberships(d)
    assert projected==d and projected is not d
    assert all('участники' not in v for f in projected['классификации']['гибкие_измерения'] for v in f['значения'])


def test_stable_catalog_ids_do_not_depend_on_array_order():
    d=synthetic_document()
    before={v.id:v.person_ids for v in build_supplementary_dimension_catalog(d)['historical_group']}
    d['классификации']['гибкие_измерения'][0]['значения'].reverse()
    after={v.id:v.person_ids for v in build_supplementary_dimension_catalog(d)['historical_group']}
    assert before==after and 'historical_group:group_alpha' in after


def test_acceptance_is_independent_of_verification_and_hypotheses_stay_inactive():
    d=synthetic_document();d['классификационные_назначения'][0]['проверка']['статус']='не_проверено'
    for inclusive in [False,True]:
        c=build_dimension_coverage(d,include_unverified=inclusive)['historical_group']
        assert c['assigned_person_count']==2
        assert set(c['unclassified_person_ids'])=={'person_gamma','person_delta'}
        assert c['interpretative_person_ids']==('person_beta',)
        assert c['unverified_person_ids']==('person_alpha',)
        assert not build_dimension_memberships(d,include_unverified=inclusive)['historical_group']['concept_context']
    catalog=build_supplementary_dimension_catalog(d)
    assert not any(v.id.endswith(':__unverified__') for vs in catalog.values() for v in vs)
    assert combine_supplementary_selections(catalog,{'historical_group':['historical_group:__interpretative__']})=={'person_beta'}


def test_empty_registry_does_not_fall_back_to_archived_legacy_lists():
    d=synthetic_document();d['классификационные_назначения']=[]
    d['редактура']['журнал_решений'].append({'id':'archived_members','дата':None,'предмет':'Исторический снимок',
        'старое_значение':{'участники':['person_alpha'],'классификационные_назначения':[{'персона':'person_alpha'}]}})
    assert all(not ids for vs in build_dimension_memberships(d).values() for ids in vs.values())
    assert all(len(c['unclassified_person_ids'])==4 for c in build_dimension_coverage(d).values())


def test_person_table_uses_the_same_registry_without_text_inference():
    d=synthetic_document()
    next(i for i in d['сведения'] if i['субъект']=='person_delta')['значение']['значение']='Работал с Группой Альфа в ранний период.'
    df=build_people_dataframe(d).set_index('id')
    assert df.loc['person_delta','facet:historical_group']==''
    assert df.loc['person_delta','facet:period']==''
    assert df.loc['person_delta','facet:research_direction']
    assert df.loc['person_alpha','facet:historical_group']=='Группа Альфа'


def test_transformations_are_read_only():
    d=synthetic_document();before=copy.deepcopy(d)
    normalize_source_school_document(d);build_supplementary_dimension_catalog(d);build_people_dataframe(d)
    assert d==before


@pytest.mark.parametrize('field,value',[('персона','missing_person'),('измерение','missing_dimension'),('значение','missing_value'),('решение','certain')])
def test_unknown_assignment_reference_or_decision_is_rejected(field,value):
    d=synthetic_document();d['классификационные_назначения'][0][field]=value
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_duplicate_person_dimension_value_is_rejected_even_with_another_id():
    d=synthetic_document();duplicate=copy.deepcopy(d['классификационные_назначения'][0]);duplicate['id']='another_id'
    d['классификационные_назначения'].append(duplicate)
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_each_dimension_value_requires_a_stable_id():
    d=synthetic_document();d['классификации']['гибкие_измерения'][1]['значения'][0].pop('id')
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_candidate_cannot_have_an_active_filter_assignment():
    d=synthetic_document();d['классификационные_назначения'][0]['персона']='person_candidate'
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_related_people_can_have_accepted_contextual_filters():
    d=synthetic_document();d['состав'][0]['отношение_к_школе']='связанное_лицо'
    validate_source_school_document(d)
    assert build_dimension_memberships(d)['historical_group']['group_alpha']==('person_alpha',)


def test_or_within_dimension_and_and_or_between_dimensions():
    catalog=build_supplementary_dimension_catalog(synthetic_document())
    groups={'historical_group':['historical_group:group_alpha','historical_group:group_beta']}
    assert combine_supplementary_selections(catalog,groups)=={'person_alpha','person_beta'}
    selected={**groups,'research_direction':['research_direction:research_0']}
    assert combine_supplementary_selections(catalog,selected,mode='intersection')==set()
    assert combine_supplementary_selections(catalog,selected,mode='union')=={'person_alpha','person_beta','person_delta'}
    assert combine_supplementary_selections(catalog,{}) is None


def test_zero_and_five_flexible_dimensions_need_no_special_case_schema():
    assert build_supplementary_dimension_catalog(synthetic_document(facet_count=0))=={}
    d=synthetic_document(facet_count=5);catalog=build_supplementary_dimension_catalog(d)
    assert list(catalog)==[f['id'] for f in d['классификации']['гибкие_измерения']]
    assert combine_supplementary_selections(catalog,{'language_context':['language_context:ru_context']})=={'person_alpha'}


def test_vygotsky_has_exactly_375_active_flexible_assignments_and_four_inactive_hypotheses():
    d=load_vygotsky();primary=d['классификации']['основное_деление']['id']
    active=[a for a in d['классификационные_назначения'] if a['измерение']!=primary and a['решение']=='принято']
    assert len(active)==375
    assert Counter(a['характер'] for a in active)=={'источниковое_отнесение':88,'классификационная_интерпретация':287}
    assert sum(a['решение']=='гипотеза' for a in d['классификационные_назначения'])==4
    memberships=build_dimension_memberships(d)
    assert sum(len(ids) for values in memberships.values() for ids in values.values())==375


def test_vygotsky_registry_and_people_table_are_equivalent_for_every_facet_value():
    d=load_vygotsky();memberships=build_dimension_memberships(d);df=build_people_dataframe(d).set_index('id')
    for facet in d['классификации']['гибкие_измерения']:
        for value in facet['значения']:
            listed={pid for pid,row in df.iterrows() if value['название'] in str(row['facet:'+facet['id']]).split('; ')}
            assert listed==set(memberships[facet['id']][value['id']])
