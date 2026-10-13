"""Границы выводов из источников и выборки, которые ранее теряли персон."""
import copy
import json

import pytest
from streamlit.testing.v1 import AppTest

from core.source_schools.data import SOURCE_SCHOOLS_DATA_DIR, SourceSchoolDataError, load_source_school_file, validate_source_school_document
from core.source_schools.dimensions import build_dimension_memberships
from core.source_schools.tables import build_people_dataframe
from core.source_schools.tree import build_person_primary_relation_index, build_supplementary_dimension_catalog


def document():
    return load_source_school_file(SOURCE_SCHOOLS_DATA_DIR / "vygotsky_school_sources_demo.v1.json")


def test_edi_conference_filter_includes_morozova_and_birenbaum_without_assuming_employment():
    doc = document()
    memberships = build_dimension_memberships(doc)
    participants = set(memberships["historical_group"]["edi_clinical_conferences_1931"])
    assert participants == {
        "lev_vygotsky", "alexei_leontiev", "alexander_luria", "ivan_solovyev",
        "leonid_zankov", "gita_birenbaum", "natalia_morozova", "rakhil_boskis",
    }
    assert participants.issubset(memberships["period"]["network_1931_1934"])
    group = next(g for g in doc["школа"]["внутренняя_структура"]["исследовательские_группы"] if g["id"] == "edi_clinical_conferences_1931")
    assert group["вид"] == "контекст"
    assert "штатного" in group["описание"]


def test_conference_1933_and_individual_topics_are_filterable():
    memberships = build_dimension_memberships(document())
    assert set(memberships["historical_group"]["research_conference_oct1933"]) == {
        "lev_vygotsky", "roza_averbukh", "vera_schmidt", "maria_pevzner",
    }
    assert "a_a_shein" in memberships["research_direction"]["concept_formation_direction"]
    assert {"roza_averbukh", "vera_schmidt"}.issubset(memberships["research_direction"]["psychoanalysis"])


def test_archived_hypotheses_never_reenter_filters_even_in_legacy_inclusive_mode():
    doc = document()
    school = doc["школа"]
    assert len(school["журнал_классификационных_гипотез"]) == 4
    assert all(a["статус"] != "не_проверено" for a in school["классификационные_назначения"])
    for inclusive in [False, True]:
        membership = build_dimension_memberships(doc, include_unverified=inclusive)
        assert "mark_lebedinsky" not in membership["historical_group"]["clinical_group"]
        assert "nina_kaulina" not in membership["historical_group"]["clinical_group"]
        assert "nina_kaulina" not in membership["historical_group"]["clinical_research"]
        assert "natalia_morozova" not in membership["period"]["circles_1934_1936"]
    assert not any(v.id.endswith(":__unverified__") for values in build_supplementary_dimension_catalog(doc).values() for v in values)


def test_source_attributed_guidance_and_critical_contact_do_not_create_dissertation_claims():
    doc = document()
    index = build_person_primary_relation_index(doc)
    assert index["k_i_veresotskaya"] == index["mark_lebedinsky"] == "Научное руководство и обучение"
    assert index["fedor_shemyakin"] == "Внешнее научное взаимодействие"
    people = {p["id"]: p for p in doc["школа"]["персоны"]}
    assert "формальная аспирантура" in people["k_i_veresotskaya"]["примечание"]
    assert "формальная аспирантура" in people["maria_levina"]["примечание"]
    assert "критического" in people["fedor_shemyakin"]["статус_связи_с_выготским"]


def test_unresolved_dates_and_names_stay_qualified_and_survive_person_export():
    doc = document()
    people = {p["id"]: p for p in doc["школа"]["персоны"]}
    assert people["tatiana_konnikova"]["даты"]["рождение"] is None
    assert people["lia_geshelina"]["даты"]["смерть"] is None
    assert people["a_a_shein"]["имя"] == "А. А. Шеин"
    table = build_people_dataframe(doc).set_index("ID")
    assert table.loc["tatiana_konnikova", "Годы жизни"] == "?–1975"
    assert "1907" in table.loc["tatiana_konnikova", "Разночтения и ограничения"]
    assert "1909" in table.loc["tatiana_konnikova", "Разночтения и ограничения"]
    assert "1972?" in table.loc["lia_geshelina", "Разночтения и ограничения"]


def test_local_sources_have_pages_and_provenance_without_invented_urls():
    doc = document()
    sources = {s["id"]: s for s in doc["школа"]["источники"]}
    for source_id in ["src_luria_1982_ru", "src_vygodskaya_lifanova_1996", "src_leontiev_1990_bio", "src_vygotsky_notebooks_2017"]:
        source = sources[source_id]
        assert source["url"] is None
        assert len(source["проверка_источника"]["sha256_экземпляра"]) == 64
    assert sources["src_luria_1982_ru"]["связанные_издания"] == ["src_luria_1979"]
    journal = doc["школа"]["журнал_проверки_источников"]
    assert len(journal) == 28
    assert all(item["ограничения"] and item["принятое_решение"] for item in journal)
    assert all(a["идентификатор_источника"] in sources and a["печатная_страница"] > 0 for item in journal for a in item["источниковые_атрибуции"])


@pytest.mark.parametrize("mutation,message", [
    ("variant_source", "Разночтение"), ("journal_source", "Журнал проверки"),
    ("journal_page", "печатную страницу"), ("journal_duplicate", "уникальные"),
    ("reactivate_hypothesis", "активном реестре"),
])
def test_invalid_review_references_and_reactivated_hypotheses_are_rejected(mutation, message):
    doc = copy.deepcopy(document())
    school = doc["школа"]
    if mutation == "variant_source":
        person = next(p for p in school["персоны"] if p.get("разночтения"))
        person["разночтения"][0]["варианты"][0]["источники"] = ["missing_source"]
    elif mutation == "journal_source":
        school["журнал_проверки_источников"][0]["источниковые_атрибуции"][0]["идентификатор_источника"] = "missing_source"
    elif mutation == "journal_page":
        school["журнал_проверки_источников"][0]["источниковые_атрибуции"][0]["печатная_страница"] = 0
    elif mutation == "journal_duplicate":
        school["журнал_проверки_источников"].append(copy.deepcopy(school["журнал_проверки_источников"][0]))
    elif mutation == "reactivate_hypothesis":
        school["классификационные_назначения"].append(copy.deepcopy(school["журнал_классификационных_гипотез"][0]))
    with pytest.raises(SourceSchoolDataError, match=message):
        validate_source_school_document(doc)


def test_person_card_shows_source_variants_pages_and_limitations():
    doc = document()
    person = next(p for p in doc["школа"]["персоны"] if p["id"] == "zhozefina_shif")
    code = '''
import json
from core.source_schools.data import build_source_school_index
from tabs.source_schools.sections import _render_person_source_notes
doc = json.loads(DOCUMENT)
person = next(p for p in doc['школа']['персоны'] if p['id'] == 'zhozefina_shif')
_render_person_source_notes(person, build_source_school_index(doc))
'''.replace("DOCUMENT", repr(json.dumps(doc, ensure_ascii=False)))
    app = AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "1930–1932" in text and "1931–1933" in text
    assert "358–359" in text and "Единственный интервал" in text
    assert person["примечание"] in text
