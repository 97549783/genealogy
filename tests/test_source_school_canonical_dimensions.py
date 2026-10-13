"""Регрессионные проверки единого источника классификационных назначений."""
import copy
import json
import io
import zipfile
from pathlib import Path

import pytest
import pandas as pd
from streamlit.testing.v1 import AppTest

from core.source_schools.data import SourceSchoolDataError, normalize_source_school_document, validate_source_school_document
from core.source_schools.dimensions import build_dimension_coverage, build_dimension_memberships, project_dimension_memberships
from core.source_schools.tables import build_classification_dataframes, build_people_dataframe, filter_people_dataframe
from core.source_schools.export import build_source_school_export_bundle
from core.source_schools.tree import build_source_school_overview_tree
from core.source_schools.tree import build_supplementary_dimension_catalog, combine_supplementary_selections


def canonical_document():
    document = json.loads(Path("data/source_schools/vygotsky_school_sources_demo.v1.json").read_text(encoding="utf-8"))
    school = document["школа"]
    for index, period in enumerate(school["хронология"]["периоды_развития"]):
        period["id"] = f"stage_{index}"
    school["хронология"]["периоды_развития"][0]["основные_представители"] = ["alexei_leontiev"]
    for index, direction in enumerate(school["внутренняя_структура"]["направления"]):
        direction["id"] = f"research_{index}"
    school["внутренняя_структура"]["исследовательские_группы"] = [
        group for group in school["внутренняя_структура"]["исследовательские_группы"] if group["id"] != "concept_context"
    ]
    school["внутренняя_структура"]["исследовательские_группы"].append(
        {"id": "concept_context", "название": "Исследования понятий", "вид": "контекст"}
    )
    evidence = school["подтверждения"][0]
    assignments = []
    for person, dimension, value, status in (
        ("alexei_leontiev", "historical_group", "kharkov_group", "подтверждено"),
        ("natalia_morozova", "historical_group", "defectology_group", "интерпретация"),
        ("natalia_menchinskaya", "historical_group", "concept_context", "не_проверено"),
        ("alexei_leontiev", "period", "stage_0", "подтверждено"),
        ("natalia_morozova", "period", "stage_0", "интерпретация"),
        ("vladimir_kogan", "research_direction", "research_0", "подтверждено"),
        ("natalia_morozova", "research_direction", "research_0", "не_проверено"),
    ):
        assignments.append({
            "id": f"assignment_{len(assignments)}", "персона": person, "измерение": dimension,
            "значение": value, "статус": status,
            "источниковые_атрибуции": [{"идентификатор_источника": evidence["идентификатор_источника"], "подтверждение": evidence["id"]}],
        })
    school["классификационные_назначения"] = assignments
    return document


def test_canonical_assignments_override_incomplete_or_stale_legacy_lists():
    document = canonical_document()
    validate_source_school_document(document)
    values = build_dimension_memberships(document)
    assert values["historical_group"]["kharkov_group"] == ("alexei_leontiev",)
    assert values["period"]["stage_0"] == ("alexei_leontiev", "natalia_morozova")
    assert values["research_direction"]["research_0"] == ("vladimir_kogan",)
    catalog = build_supplementary_dimension_catalog(document)
    assert next(value for value in catalog["historical_group"] if value.id == "group:concept_context").label.startswith("Контекст:")


def test_period_filters_use_all_assignments_and_keep_major_representatives_separate():
    document = canonical_document()
    major = copy.deepcopy(document["школа"]["хронология"]["периоды_развития"][0]["основные_представители"])
    projected = project_dimension_memberships(document)
    period = projected["школа"]["хронология"]["периоды_развития"][0]
    assert period["участники"] == ["alexei_leontiev", "natalia_morozova"]
    assert period["основные_представители"] == major
    assert "natalia_morozova" not in major


def test_stable_ids_do_not_depend_on_catalog_order():
    document = canonical_document()
    before = {value.id: value.person_ids for value in build_supplementary_dimension_catalog(document)["period"]}
    document["школа"]["хронология"]["периоды_развития"].reverse()
    after = {value.id: value.person_ids for value in build_supplementary_dimension_catalog(document)["period"]}
    assert before == after
    assert "period:stage_0" in after


def test_unclassified_and_uncertain_are_distinct_and_follow_explicit_mode():
    document = canonical_document()
    default = build_dimension_coverage(document)["historical_group"]
    inclusive = build_dimension_coverage(document, include_unverified=True)["historical_group"]
    assert default["assigned_person_count"] == 2
    assert "natalia_menchinskaya" in default["unclassified_person_ids"]
    assert "natalia_morozova" not in default["unclassified_person_ids"]
    assert default["interpretative_person_ids"] == ("natalia_morozova",)
    assert default["unverified_person_ids"] == ("natalia_menchinskaya",)
    assert inclusive["assigned_person_count"] == 3
    assert "natalia_menchinskaya" not in inclusive["unclassified_person_ids"]
    catalog = build_supplementary_dimension_catalog(document)
    assert all(value.id != "group:__unverified__" for value in catalog["historical_group"])
    interpreted = combine_supplementary_selections(catalog, {"historical_group": ["group:__interpretative__"]})
    assert interpreted == {"natalia_morozova"}
    assert combine_supplementary_selections(catalog, {}) is None


def test_empty_canonical_assignments_never_fall_back_to_old_lists():
    document = canonical_document()
    document["школа"]["классификационные_назначения"] = []
    assert all(not ids for values in build_dimension_memberships(document).values() for ids in values.values())
    assert all(len(value["unclassified_person_ids"]) == len(document["школа"]["персоны"]) for value in build_dimension_coverage(document).values())


def test_person_table_uses_same_canonical_classifications_without_text_inference():
    document = canonical_document()
    person = next(person for person in document["школа"]["персоны"] if person["id"] == "vladimir_kogan")
    person["группы_и_контексты"] = ["Харьковская группа"]
    person["период_взаимодействия"] = "1924–1926"
    dataframe = build_people_dataframe(document).set_index("ID")
    assert dataframe.loc["vladimir_kogan", "Группы и контексты"] == ""
    assert dataframe.loc["vladimir_kogan", "Периоды развития"] == ""
    assert dataframe.loc["vladimir_kogan", "Научные направления"]
    assert dataframe.loc["alexei_leontiev", "Группы и контексты"] == "Харьковская группа"


def test_classification_transformations_do_not_mutate_document():
    document = canonical_document()
    before = copy.deepcopy(document)
    normalize_source_school_document(document)
    build_supplementary_dimension_catalog(document)
    build_people_dataframe(document)
    assert document == before


@pytest.mark.parametrize("field,value", [("персона", "missing_person"), ("измерение", "missing_dimension"), ("значение", "missing_value"), ("статус", "certain")])
def test_unknown_assignment_references_and_status_are_rejected(field, value):
    document = canonical_document()
    document["школа"]["классификационные_назначения"][0][field] = value
    with pytest.raises(SourceSchoolDataError):
        validate_source_school_document(document)


def test_duplicate_person_dimension_value_is_rejected():
    document = canonical_document()
    duplicate = copy.deepcopy(document["школа"]["классификационные_назначения"][0])
    duplicate["id"] = "another_id"
    document["школа"]["классификационные_назначения"].append(duplicate)
    with pytest.raises(SourceSchoolDataError, match="Повторное классификационное"):
        validate_source_school_document(document)


def test_period_requires_stable_id_in_canonical_contract():
    document = canonical_document()
    document["школа"]["хронология"]["периоды_развития"][0].pop("id")
    with pytest.raises(SourceSchoolDataError, match="стабильные id"):
        validate_source_school_document(document)


def test_addressed_source_and_locator_are_required():
    document = canonical_document()
    item = document["школа"]["классификационные_назначения"][0]
    item["источниковые_атрибуции"] = []
    with pytest.raises(SourceSchoolDataError, match="адресной источниковой"):
        validate_source_school_document(document)
    item["источниковые_атрибуции"] = [{"идентификатор_источника": document["школа"]["источники"][0]["id"]}]
    with pytest.raises(SourceSchoolDataError, match="локатор"):
        validate_source_school_document(document)


def test_assignment_source_must_match_evidence_source():
    document = canonical_document()
    attribution = document["школа"]["классификационные_назначения"][0]["источниковые_атрибуции"][0]
    attribution["идентификатор_источника"] = next(source["id"] for source in document["школа"]["источники"] if source["id"] != attribution["идентификатор_источника"])
    with pytest.raises(SourceSchoolDataError, match="несогласованное подтверждение"):
        validate_source_school_document(document)


def test_overview_ui_uses_canonical_ids_and_never_offers_unverified_memberships():
    document = canonical_document()
    code = '''
import json
from core.source_schools.data import build_source_school_index
from tabs.source_schools.sections import render_overview_section
document = json.loads(DOCUMENT)
render_overview_section(document, build_source_school_index(document))
'''.replace("DOCUMENT", repr(json.dumps(document, ensure_ascii=False)))
    app = AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    assert all(item.label != "Учитывать непроверенные назначения" for item in app.checkbox)
    app.multiselect[0].set_value(["group:__unclassified__"]).run(timeout=30)
    assert not app.exception
    assert any(f"{len(document['школа']['персоны']) - 2} персон" in caption.value for caption in app.caption)
    app.multiselect[0].set_value([])
    app.multiselect[1].set_value(["period:stage_0"]).run(timeout=30)
    assert not app.exception
    assert any("2 персон" in caption.value for caption in app.caption)


def test_live_session_catalog_change_clears_obsolete_ids_and_keeps_existing_ids():
    updated = canonical_document()
    updated["школа"]["внутренняя_структура"]["исследовательские_группы"] = [
        group for group in updated["школа"]["внутренняя_структура"]["исследовательские_группы"]
        if group["id"] != "troika"
    ]
    old = canonical_document()
    old["школа"].pop("классификационные_назначения")
    for period in old["школа"]["хронология"]["периоды_развития"]:
        period.pop("id")
    for direction in old["школа"]["внутренняя_структура"]["направления"]:
        direction.pop("id")
    code = '''
import json
import streamlit as st
from core.source_schools.data import build_source_school_index
from tabs.source_schools.sections import render_overview_section
document = json.loads(NEW_DOCUMENT if st.session_state.get("updated_catalog") else OLD_DOCUMENT)
render_overview_section(document, build_source_school_index(document))
'''.replace("NEW_DOCUMENT", repr(json.dumps(updated, ensure_ascii=False))).replace("OLD_DOCUMENT", repr(json.dumps(old, ensure_ascii=False)))
    app = AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    app.multiselect[0].set_value(["group:kharkov_group", "group:troika"])
    app.multiselect[1].set_value(["period:0"])
    app.multiselect[2].set_value(["direction:0"])
    app.run(timeout=30)
    assert not app.exception
    app.session_state["updated_catalog"] = True
    app.run(timeout=30)
    assert not app.exception
    assert app.multiselect[0].value == ["group:kharkov_group"]
    assert app.multiselect[1].value == []
    assert app.multiselect[2].value == []


def test_format_func_handles_ids_disappearing_from_catalog_without_raw_id_leak():
    from tabs.source_schools.sections import _supplementary_value_label

    label = _supplementary_value_label("period:0", {}, show_count=True)
    assert label == "Значение отсутствует в текущем каталоге"
    assert "period:" not in label


def test_unknown_confidence_stays_unknown_and_default_filter_retains_people():
    document = canonical_document()
    for person in document["школа"]["персоны"]:
        person["уверенность"] = None
    dataframe = build_people_dataframe(document)
    assert dataframe["Уверенность"].isna().all()
    assert len(filter_people_dataframe(dataframe)) == len(document["школа"]["персоны"])
    assert filter_people_dataframe(dataframe, minimum_confidence=0.5).empty


def test_canonical_exports_preserve_all_assignments_statuses_and_addressed_sources(tmp_path):
    document = canonical_document()
    tree = build_source_school_overview_tree(document)
    assignments, attributions = build_classification_dataframes(document)
    assert len(assignments) == len(document["школа"]["классификационные_назначения"])
    assert len(attributions) == sum(len(item["источниковые_атрибуции"]) for item in document["школа"]["классификационные_назначения"])
    bundle = build_source_school_export_bundle(document=document, source_path=tmp_path / "unused.json", tree=tree, tree_html="<html></html>", tree_png=b"png")
    workbook = pd.ExcelFile(io.BytesIO(bundle.xlsx_bytes))
    assert {"Периоды развития", "Классификации", "Основания классификаций"}.issubset(workbook.sheet_names)
    exported = pd.read_excel(workbook, sheet_name="Классификации")
    assert set(exported["ID назначения"]) == set(assignments["ID назначения"])
    assert "не_проверено" in set(exported["Статус"])
    archive = zipfile.ZipFile(io.BytesIO(bundle.zip_bytes))
    slug = document["школа"]["идентификатор_школы"]
    exported_csv = pd.read_csv(io.BytesIO(archive.read(f"{slug}.классификационные_назначения.csv")))
    assert set(exported_csv["ID назначения"]) == set(assignments["ID назначения"])
    assert f"{slug}.основания_классификации.csv" in archive.namelist()


def test_empty_canonical_exports_keep_structured_headers():
    document = canonical_document()
    document["школа"]["классификационные_назначения"] = []
    assignments, attributions = build_classification_dataframes(document)
    assert assignments.empty and attributions.empty
    assert "ID назначения" in assignments.columns
    assert "ID источника" in attributions.columns
