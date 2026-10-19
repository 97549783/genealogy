"""Дополнительные проверки инвариантов универсальной модели школ."""
from __future__ import annotations

import copy
import json

import pytest

from core.source_schools.data import (
    SourceSchoolDataError, build_source_school_summary, load_source_school_catalog,
    validate_source_school_document,
)
from core.source_schools.model import information_text, person_qualifications
from core.source_schools.tables import build_people_dataframe, filter_people_dataframe
from source_school_fixtures import synthetic_document


def test_catalog_cache_returns_independent_raw_documents_and_invalidates_changes(tmp_path):
    document = synthetic_document(facet_count=5)
    path = tmp_path / "school.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    first = load_source_school_catalog(tmp_path)
    first[0]["document"]["школа"]["каноническое_название"] = "Повреждение копии"
    assert load_source_school_catalog(tmp_path)[0]["document"] == document
    document["школа"]["каноническое_название"] = "Новое название школы"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    assert load_source_school_catalog(tmp_path)[0]["label"] == "Новое название школы"


def test_support_graph_rejects_cycles():
    document = synthetic_document()
    a, b = document["сведения"][:2]
    a["опирается_на"] = [b["id"]]
    b["опирается_на"] = [a["id"]]
    with pytest.raises(SourceSchoolDataError, match="Цикл зависимостей"):
        validate_source_school_document(document)


def test_accepted_record_cannot_depend_on_a_rejected_assertion():
    document = synthetic_document()
    a, b = document["сведения"][:2]
    a["опирается_на"] = [b["id"]]
    b["решение"] = "отклонено"
    with pytest.raises(SourceSchoolDataError, match="непринятую"):
        validate_source_school_document(document)


def test_unknown_card_field_and_duplicate_dictionary_codes_are_rejected():
    document = synthetic_document()
    document["отображение"]["поля_карточки"] = ["missing_field"]
    with pytest.raises(SourceSchoolDataError, match="поле карточки"):
        validate_source_school_document(document)
    document = synthetic_document()
    document["словари"]["поля_сведений"].append(copy.deepcopy(document["словари"]["поля_сведений"][0]))
    with pytest.raises(SourceSchoolDataError, match="повторяющиеся коды"):
        validate_source_school_document(document)


def test_center_person_requires_included_membership():
    document = synthetic_document()
    document["отображение"]["центр"] = {"тип": "персона", "id": "person_candidate"}
    with pytest.raises(SourceSchoolDataError, match="Центральная персона"):
        validate_source_school_document(document)


def test_variant_remains_a_qualification_without_becoming_a_canonical_value():
    document = synthetic_document()
    variant = copy.deepcopy(document["сведения"][0])
    variant.update(id="variant_alpha", поле="death_date", роль_значения="вариант",
                   значение={"вид": "дата", "значение": {"исходная_запись": "1972?", "год": 1972,
                       "месяц": None, "день": None, "эра": "н_э", "точность": "год", "определённость": "под_вопросом"}})
    document["сведения"].append(variant)
    validate_source_school_document(document)
    assert information_text(document, "person_alpha", "death_date") == ""
    assert "1972?" in person_qualifications(document, "person_alpha")


def test_summary_separates_primary_and_flexible_assignments_and_candidates():
    document = synthetic_document(primary=True, facet_count=5)
    summary = build_source_school_summary(document)
    assert summary["included_count"] == 4
    assert summary["candidate_count"] == 1
    assert summary["primary_assignment_count"] == 2
    assert summary["assignment_count"] == summary["primary_assignment_count"] + summary["flexible_assignment_count"]


def test_display_pool_is_distinct_from_complete_included_export():
    document = synthetic_document()
    document["состав"][1]["отношение_к_школе"] = "связанное_лицо"
    document["отображение"]["показывать_отношения_к_школе"] = ["представитель"]
    assert len(build_people_dataframe(document)) == 3
    assert len(build_people_dataframe(document, display_only=False)) == 4
    summary = build_source_school_summary(document)
    assert summary["included_count"] == 4
    assert summary["displayed_count"] == 3


def test_personless_school_can_be_filtered_without_losing_table_headers():
    document = synthetic_document(facet_count=0)
    document["состав"] = []
    document["объекты"]["персоны"] = []
    document["сведения"] = []
    frame = build_people_dataframe(document)
    filtered = filter_people_dataframe(frame, query="Нет персон", source_ids=["source_alpha"])
    assert filtered.empty
    assert list(filtered.columns) == list(frame.columns)


def test_ready_requires_checked_support_but_allows_inactive_hypotheses():
    document = synthetic_document()
    document["метаданные"]["статус"] = "готово"
    validate_source_school_document(document)
    document["сведения"][0]["основания"] = []
    with pytest.raises(SourceSchoolDataError, match="источниковая опора"):
        validate_source_school_document(document)
    document = synthetic_document()
    document["метаданные"]["статус"] = "готово"
    document["основания"][0]["проверка"]["статус"] = "не_проверено"
    with pytest.raises(SourceSchoolDataError, match="не сверена"):
        validate_source_school_document(document)


def test_ready_cannot_silently_inherit_old_review():
    document = synthetic_document()
    document["метаданные"]["статус"] = "готово"
    document["сведения"][0]["проверка"]["статус"] = "унаследовано"
    with pytest.raises(SourceSchoolDataError, match="унаследованная проверка"):
        validate_source_school_document(document)
    record = document["сведения"][0]
    record["проверка"]["примечание"] = "Сохранена проверка предыдущей редакции; оригинал повторно не читался."
    record["происхождение"] = [{"способ": "миграция", "документ": "Предыдущая редакция"}]
    with pytest.raises(SourceSchoolDataError, match="редакторского решения"):
        validate_source_school_document(document)
    document["редактура"]["журнал_решений"].append({
        "id": "admission", "дата": None, "предмет": "Допуск прежней проверки", "записи": [{"реестр": "сведение", "id": record["id"]}],
        "принятое_решение": "Допустить запись с явным указанием происхождения проверки", "основания": [], "проверка": {"статус": "сверено"},
    })
    validate_source_school_document(document)


def test_impossible_live_date_is_rejected_without_reinterpreting_archival_snapshots():
    document = synthetic_document()
    value = {"исходная_запись": "31 февраля 2020", "год": 2020, "месяц": 2, "день": 31,
             "эра": "н_э", "точность": "день", "определённость": "точно"}
    record = copy.deepcopy(document["сведения"][0])
    record.update(id="invalid_date", поле="death_date", значение={"вид": "дата", "значение": value})
    document["сведения"].append(record)
    with pytest.raises(SourceSchoolDataError, match="невозможный день"):
        validate_source_school_document(document)
    document["сведения"].pop()
    document["редактура"]["журнал_решений"].append({
        "id": "archived_review", "дата": None, "предмет": "Старое извлечение", "записи": [],
        "до_проверки": None, "выявлено": "Ошибочная дата в прежнем извлечении", "исходная_рекомендация": None,
        "старое_значение": value, "новое_значение": None, "принятое_решение": "Сохранить архивный снимок",
        "результат": None, "основания": [], "проверка": {"статус": "сверено"},
    })
    validate_source_school_document(document)
