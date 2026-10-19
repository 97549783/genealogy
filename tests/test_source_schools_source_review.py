"""Historical qualifications and source-audit decisions survive native v2 views."""
from __future__ import annotations
import copy
import json

import pytest
from streamlit.testing.v1 import AppTest

from core.source_schools.data import SourceSchoolDataError, validate_source_school_document
from core.source_schools.dimensions import build_dimension_memberships
from core.source_schools.model import accepted_information, format_value
from core.source_schools.tables import build_people_dataframe
from core.source_schools.tree import build_person_primary_relation_index, build_supplementary_dimension_catalog
from source_school_fixtures import load_vygotsky


def test_edi_conference_filter_preserves_participation_without_assuming_employment():
    d=load_vygotsky();membership=build_dimension_memberships(d)
    participants=set(membership['historical_group']['edi_clinical_conferences_1931'])
    assert participants=={'lev_vygotsky','alexei_leontiev','alexander_luria','ivan_solovyev','leonid_zankov','gita_birenbaum','natalia_morozova','rakhil_boskis'}
    assert participants.issubset(membership['period']['network_1931_1934'])
    context=next(o for o in d['объекты']['прочие'] if o['id']=='edi_clinical_conferences_1931')
    assert context['подтип']=='контекст'
    descriptions=next(v['описание'] for f in d['классификации']['гибкие_измерения'] for v in f['значения'] if v['id']==context['id'])
    assert 'штатного' in descriptions


def test_conference_1933_and_individual_topics_remain_filterable():
    membership=build_dimension_memberships(load_vygotsky())
    assert set(membership['historical_group']['research_conference_oct1933'])=={'lev_vygotsky','roza_averbukh','vera_schmidt','maria_pevzner'}
    assert 'a_a_shein' in membership['research_direction']['concept_formation_direction']
    assert {'roza_averbukh','vera_schmidt'}.issubset(membership['research_direction']['psychoanalysis'])


def test_archived_hypotheses_never_reenter_filters_in_any_verification_mode():
    d=load_vygotsky();assert sum(a['решение']=='гипотеза' for a in d['классификационные_назначения'])==4
    for inclusive in [False,True]:
        m=build_dimension_memberships(d,include_unverified=inclusive)
        assert 'mark_lebedinsky' not in m['historical_group']['clinical_group']
        assert 'nina_kaulina' not in m['historical_group']['clinical_group']
        assert 'nina_kaulina' not in m['historical_group']['clinical_research']
        assert 'natalia_morozova' not in m['period']['circles_1934_1936']
    assert not any(v.id.endswith(':__unverified__') for vs in build_supplementary_dimension_catalog(d).values() for v in vs)


def test_guidance_and_critical_contact_do_not_create_dissertation_relationships():
    d=load_vygotsky();index=build_person_primary_relation_index(d)
    assert index['k_i_veresotskaya']==index['mark_lebedinsky']=='Научное руководство и обучение'
    assert index['fedor_shemyakin']=='Внешнее научное взаимодействие'
    people={p['id']:p for p in d['объекты']['персоны']}
    assert 'формальная аспирантура' in people['k_i_veresotskaya']['примечание']
    assert 'формальная аспирантура' in people['maria_levina']['примечание']
    assert 'критическ' in people['fedor_shemyakin']['примечание']
    assert not any(r['тип']=='dissertation_supervision' for r in d['связи'])


def test_uncertain_dates_and_names_remain_qualified_in_person_export():
    d=load_vygotsky();people={p['id']:p for p in d['объекты']['персоны']}
    assert not accepted_information(d,'tatiana_konnikova','birth_date')
    assert not accepted_information(d,'lia_geshelina','death_date')
    assert people['a_a_shein']['имя']=='А. А. Шеин'
    df=build_people_dataframe(d).set_index('id')
    assert df.loc['tatiana_konnikova','field:birth_date']==''
    assert df.loc['tatiana_konnikova','field:death_date']=='1975'
    assert '1907' in df.loc['tatiana_konnikova','Разночтения и ограничения']
    assert '1909' in df.loc['tatiana_konnikova','Разночтения и ограничения']
    assert '1972?' in df.loc['lia_geshelina','Разночтения и ограничения']


def test_local_sources_preserve_hashes_editions_and_28_audit_findings_without_fake_urls():
    d=load_vygotsky();sources={s['id']:s for s in d['источники']}
    for sid in ['src_luria_1982_ru','src_vygodskaya_lifanova_1996','src_leontiev_1990_bio','src_vygotsky_notebooks_2017']:
        s=sources[sid]
        assert not s['доступы']
        assert any(len(f.get('sha256') or '')==64 and f['путь_ресурса'] is None for f in s['файлы'])
    assert any(e['источник']=='src_luria_1979' for e in sources['src_luria_1982_ru']['связанные_издания'])
    assert sources['src_luria_1982_ru']['группа_зависимости']==sources['src_luria_1979']['группа_зависимости']
    findings=[r for r in d['редактура']['журнал_решений'] if any(p.get('исходное_поле','').startswith('/школа/журнал_проверки_источников/') for p in r.get('происхождение',[]))]
    assert len(findings)==28
    assert all(r.get('ограничения') and r.get('принятое_решение') for r in findings)
    assert all(r['проверка']['статус']=='унаследовано' for r in findings)
    assert all('старое_значение' in r and r['основания'] for r in findings)


@pytest.mark.parametrize('mutation',['variant_basis','journal_basis','pdf_page','journal_duplicate','duplicate_reactivated_hypothesis'])
def test_invalid_review_references_and_duplicate_hypothesis_reactivation_are_rejected(mutation):
    d=load_vygotsky()
    if mutation=='variant_basis':d['редактура']['разночтения'][0]['варианты'][0]['основания']=['missing_basis']
    elif mutation=='journal_basis':d['редактура']['журнал_решений'][0]['основания']=['missing_basis']
    elif mutation=='pdf_page':
        b=d['основания'][0];b['локатор']={'страницы_pdf':[0],'печатные_страницы':[]}
    elif mutation=='journal_duplicate':d['редактура']['журнал_решений'].append(copy.deepcopy(d['редактура']['журнал_решений'][0]))
    else:
        a=copy.deepcopy(next(a for a in d['классификационные_назначения'] if a['решение']=='гипотеза'))
        a.update(id='reactivated_duplicate',решение='принято');d['классификационные_назначения'].append(a)
    with pytest.raises(SourceSchoolDataError):validate_source_school_document(d)


def test_person_deeplink_card_shows_variants_pages_and_limitations():
    app=AppTest.from_string('from tabs.source_schools.tab import render_source_schools_tab\nrender_source_schools_tab()')
    app.query_params.update({'tab':'source_schools','school':'vygotsky_cultural_historical_school','view':'person','person':'zhozefina_shif'})
    app.run(timeout=45)
    assert not app.exception
    text=' '.join(str(x.value) for group in [app.markdown,app.caption,app.warning,app.info] for x in group)
    assert '1930–1932' in text and '1931–1933' in text
    assert '358–359' in text and 'Единственный интервал' in text
    assert 'Начало работы' in text
    assert 'Адресные разночтения для этой карточки не указаны.' not in text
