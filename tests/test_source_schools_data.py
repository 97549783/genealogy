"""Native v2.1 loading, source integrity and migration-preservation contract."""
from __future__ import annotations
import copy
import json
from collections import Counter

import pytest

from core.source_schools.data import (
    SOURCE_SCHOOLS_DATA_DIR, SourceSchoolDataError, build_source_school_index,
    load_source_school_catalog, load_source_school_file, normalize_source_school_document,
    validate_source_school_document,
)
from source_school_fixtures import TEMPLATE, VYGOTSKY_PATH, load_vygotsky, synthetic_document


def test_vygotsky_v2_preserves_composition_names_sources_and_primary_categories():
    d = load_source_school_file(VYGOTSKY_PATH)
    assert d['версия_схемы'] == '2.1'
    assert d['школа']['идентификатор_школы'] == 'vygotsky_cultural_historical_school'
    assert sum(m['решение']=='включено' for m in d['состав']) == 51
    assert sum(m['решение']=='кандидат' for m in d['состав']) == 11
    assert len(d['источники']) == 35
    assert len(d['основания']) >= 99
    primary=d['классификации']['основное_деление']
    assert [c['код'] for c in primary['категории']] == ['A1','A2','A3','A4']
    assignments=[a for a in d['классификационные_назначения'] if a['измерение']==primary['id'] and a['решение']=='принято']
    assert Counter(a['значение'] for a in assignments)=={'a1':28,'a2':13,'a3':4,'a4':5}
    assert len({a['персона'] for a in assignments}) == 50
    names={p['id']:p['имя'] for p in d['объекты']['персоны']}
    assert {k:names[k] for k in ['m_b_eidinova','e_i_pashkovskaya','k_i_veresotskaya','a_a_shein']} == {
        'm_b_eidinova':'Мария Борисовна Эйдинова','e_i_pashkovskaya':'Екатерина Ильинична Пашковская',
        'k_i_veresotskaya':'Ксения Ивановна Вересотская','a_a_shein':'А. А. Шеин'}
    by_person={a['персона']:a['значение'] for a in assignments}
    assert by_person['panteleimon_lyubimov']=='a2'
    assert by_person['kurt_koffka']==by_person['fedor_shemyakin']=='a3'
    assert by_person['filipp_bassin']=='a4'


def test_catalog_contains_all_six_native_schools_and_no_template():
    catalog=load_source_school_catalog(SOURCE_SCHOOLS_DATA_DIR)
    assert {c['school_id'] for c in catalog} == {
        'vygotsky_cultural_historical_school','bryansk_scientific_philosophical_school','perm_philosophical_school',
        'russian_noosphere_scientific_school','ural_philosophical_school','rostov_philosophical_school'}
    assert all(c['label'] and c['school_id'] for c in catalog)


def test_indexes_use_raw_native_registries_including_candidates():
    d=load_vygotsky(); indexes=build_source_school_index(d)
    assert len(indexes['persons']) == 62
    assert len(indexes['sources']) == 35
    assert set(indexes['evidence']) == {b['id'] for b in d['основания']}
    assert indexes['persons']['a_a_shein']['имя'] == 'А. А. Шеин'


def test_optional_primary_and_zero_or_many_facets_are_valid():
    for primary,n in [(False,0),(False,5),(True,3)]:
        validate_source_school_document(synthetic_document(primary=primary,facet_count=n))


def test_duplicate_primary_membership_is_rejected():
    d=synthetic_document(primary=True)
    a=copy.deepcopy(d['классификационные_назначения'][-2]);a['id']='another_primary';a['значение']='category_beta'
    d['классификационные_назначения'].append(a)
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


@pytest.mark.parametrize('registry', ['персоны','источники','основания'])
def test_duplicate_global_ids_are_rejected(registry):
    d=synthetic_document()
    rows=d['объекты']['персоны'] if registry=='персоны' else d[registry]
    rows[1]['id']=rows[0]['id']
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


@pytest.mark.parametrize('mutation', ['person_evidence','evidence_source','assignment_person','assignment_dimension','assignment_value','information_field','center'])
def test_unknown_live_references_are_rejected(mutation):
    d=synthetic_document()
    if mutation=='person_evidence':d['объекты']['персоны'][0]['идентификация']['основания']=['missing_evidence']
    elif mutation=='evidence_source':d['основания'][0]['источник']='missing_source'
    elif mutation.startswith('assignment_'):
        field={'assignment_person':'персона','assignment_dimension':'измерение','assignment_value':'значение'}[mutation]
        d['классификационные_назначения'][0][field]='missing_reference'
    elif mutation=='information_field':d['сведения'][0]['поле']='missing_field'
    else:d['отображение']['центр']['id']='missing_school'
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_pdf_file_must_belong_to_the_same_source():
    d=synthetic_document();d['основания'][0]['файл']='file_beta'
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


@pytest.mark.parametrize('page',[0,11])
def test_pdf_pages_must_be_positive_and_within_known_file_length(page):
    d=synthetic_document();d['основания'][0]['локатор']['страницы_pdf']=[page]
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_source_and_locator_are_sufficient_without_invented_quote():
    d=synthetic_document()
    assert d['основания'][0]['фрагмент'] is None
    validate_source_school_document(d)


def test_unpublished_file_preserves_hash_without_invented_url():
    d=synthetic_document();f=d['источники'][0]['файлы'][0];f['sha256']='f'*64
    validate_source_school_document(d)
    assert f['путь_ресурса'] is None and d['источники'][0]['доступы']==[]


def test_confidence_with_origin_is_validated():
    d=synthetic_document();d['объекты']['персоны'][0]['оценка_уверенности']={'значение':1.5,'происхождение':'прежняя_разметка'}
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_v1_aliases_and_stale_stored_summaries_are_not_runtime_contract():
    d=synthetic_document();d['демо_представление']={'сводные_показатели':{'число_персон':1}}
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)
    with pytest.raises(SourceSchoolDataError):validate_source_school_document({'школа':{'персоны':[]}})


def test_normalization_does_not_mutate_or_manufacture_legacy_fields():
    d=synthetic_document();before=copy.deepcopy(d);normalized=normalize_source_school_document(d)
    assert d==before and normalized==before and normalized is not d
    assert 'персоны' not in normalized['школа']


def test_duplicate_school_id_across_catalog_is_rejected(tmp_path):
    text=json.dumps(synthetic_document(),ensure_ascii=False)
    for name in ['a.json','b.json']:(tmp_path/name).write_text(text,encoding='utf-8')
    with pytest.raises(SourceSchoolDataError):load_source_school_catalog(tmp_path)


def test_template_is_not_a_catalog_school(tmp_path):
    (tmp_path/'template.json').write_bytes(TEMPLATE.read_bytes())
    assert load_source_school_catalog(tmp_path)==[]


def test_malformed_json_has_a_domain_error(tmp_path):
    p=tmp_path/'bad.json';p.write_text('{',encoding='utf-8')
    with pytest.raises(SourceSchoolDataError):load_source_school_file(p)


def test_missing_file_has_a_domain_error(tmp_path):
    with pytest.raises(SourceSchoolDataError):load_source_school_file(tmp_path/'missing.json')


def test_missing_directory_returns_an_empty_catalog(tmp_path):
    assert load_source_school_catalog(tmp_path/'missing')==[]


@pytest.mark.parametrize('mutation',['wrong_registry_type','missing_stable_id','unknown_decision','unknown_version','invalid_language'])
def test_invalid_native_schema_fields_are_rejected(mutation):
    d=synthetic_document()
    if mutation=='wrong_registry_type':d['объекты']['персоны'][0]='not a record'
    elif mutation=='missing_stable_id':d['классификации']['гибкие_измерения'][0]['значения'][0].pop('id')
    elif mutation=='unknown_decision':d['классификационные_назначения'][0]['решение']='certain'
    elif mutation=='unknown_version':d['версия_схемы']='99.0'
    else:d['метаданные']['языки_данных']=['not a language tag']
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)
