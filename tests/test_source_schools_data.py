from __future__ import annotations

import copy

import pytest

from core.source_schools.data import (
    SOURCE_SCHOOLS_DATA_DIR,
    SourceSchoolDataError,
    build_source_school_index,
    load_source_school_catalog,
    load_source_school_file,
    validate_source_school_document,
)

PATH = SOURCE_SCHOOLS_DATA_DIR / "vygotsky_school_sources_demo.v1.json"


def load_demo_document():
    return load_source_school_file(PATH)


def make_canonical_document():
    return {
        "школа": {
            "идентификатор_школы": "synthetic_school",
            "каноническое_название": "Синтетическая школа",
            "персоны": [
                {
                    "id": "person_alpha",
                    "полное_имя": "Альфа Исследователь",
                    "категория_включения": "ядро",
                    "роль_в_школе": ["участник"],
                    "статус_связи_с_выготским": "демонстрационная связь",
                    "основной_вклад": "Проверка связности",
                    "уверенность": 0.9,
                    "подтверждения": ["evidence_alpha"],
                    "источниковые_атрибуции": [
                        {
                            "идентификатор_источника": "source_alpha",
                            "подтверждение": "evidence_alpha",
                            "формулировка_роли": "участник",
                            "нормализованная_роль": "участник",
                            "явное_утверждение": True,
                            "уверенность": 0.9,
                        }
                    ],
                },
                {
                    "id": "person_beta",
                    "полное_имя": "Бета Исследователь",
                    "категория_включения": "последователь",
                    "роль_в_школе": ["последователь"],
                    "статус_связи_с_выготским": "опосредованная связь",
                    "основной_вклад": "Проверка агрегатов",
                    "уверенность": 0.8,
                    "подтверждения": ["evidence_beta"],
                    "источниковые_атрибуции": [
                        {
                            "идентификатор_источника": "source_beta",
                            "подтверждение": "evidence_beta",
                            "формулировка_роли": "последователь",
                            "нормализованная_роль": "последователь",
                            "явное_утверждение": False,
                            "уверенность": 0.8,
                        }
                    ],
                },
            ],
            "источники": [
                {
                    "id": "source_alpha",
                    "краткое_название": "Источник Альфа",
                    "библиографическое_описание": "Описание источника Альфа",
                    "url": "https://example.org/alpha",
                },
                {
                    "id": "source_beta",
                    "краткое_название": "Источник Бета",
                    "библиографическое_описание": "Описание источника Бета",
                },
            ],
            "подтверждения": [
                {
                    "id": "evidence_alpha",
                    "идентификатор_источника": "source_alpha",
                    "содержание_свидетельства": "Свидетельство Альфа",
                    "локатор": "с. 1",
                    "явное_утверждение": True,
                    "уверенность": 0.9,
                },
                {
                    "id": "evidence_beta",
                    "идентификатор_источника": "source_beta",
                    "содержание_свидетельства": "Свидетельство Бета",
                    "локатор": "с. 2",
                    "явное_утверждение": False,
                    "уверенность": 0.8,
                },
            ],
            "внутренняя_структура": {
                "исследовательские_группы": [
                    {
                        "id": "group_alpha",
                        "название": "Группа Альфа",
                        "участники": ["person_alpha"],
                        "подтверждения": ["evidence_alpha"],
                    }
                ],
                "направления": [
                    {
                        "название": "Направление Альфа",
                        "представители": ["person_alpha"],
                        "подтверждения": ["evidence_alpha"],
                    }
                ],
                "поколения": [{"название": "Поколение", "представители": ["person_beta"]}],
            },
            "хронология": {
                "периоды_развития": [
                    {"название": "Период", "персоны": ["person_alpha"], "описание": "Описание периода"}
                ]
            },
            "историографические_расхождения": [
                {
                    "вопрос": "Вопрос",
                    "позиции": [{"формулировка": "Позиция", "источники": ["source_alpha"]}],
                }
            ],
        },
        "демо_представление": {
            "название_в_выпадающем_списке": "Синтетическая школа",
            "заголовок_страницы": "Синтетическая школа",
            "подзаголовок": "Проверка",
            "рекомендуемые_разделы": ["Обзор"],
            "методологическое_предупреждение": "Предупреждение",
            "сводные_показатели": {
                "число_персон": 2,
                "число_источников": 2,
                "число_подтверждений": 2,
                "персоны_по_категориям": {"ядро": 1, "последователь": 1},
            },
        },
        "контроль_качества": {
            "число_персон": 2,
            "число_источников": 2,
            "число_подтверждений": 2,
            "персоны_по_категориям": {"ядро": 1, "последователь": 1},
        },
    }


def make_full_contract_document():
    document = make_canonical_document()
    school = document["школа"]
    school["дисциплинарная_принадлежность"] = {
        "области": ["психология"],
        "ключевые_слова": ["развитие"],
    }
    school["основная_идея"] = {
        "краткая_формулировка": "Краткая формулировка идеи.",
        "центральная_проблема": "Проблема развития.",
        "центральная_гипотеза": "Гипотеза развития.",
        "центральная_теория": "Теория развития.",
        "центральный_метод": "Метод исследования.",
        "подтверждения": ["evidence_alpha"],
    }
    school["теоретические_основания"] = {
        "понятия": ["понятие"],
        "теории": ["теория"],
        "методы": ["метод"],
        "интеллектуальные_источники": ["источник идей"],
    }
    school["основные_результаты"] = ["результат"]
    school["связи_с_другими_школами"] = [{"название": "Другая школа", "уверенность": 0.7}]
    school["представители"] = {"ядро": ["person_alpha"], "последователи": ["person_beta"]}
    period = school["хронология"]["периоды_развития"][0]
    period["название_периода"] = period.pop("название")
    period["временной_диапазон"] = "1924–1934"
    period["основные_представители"] = period.pop("персоны")
    school["хронология"]["дата_или_период_возникновения"] = "1924"
    school["хронология"]["период_активности"] = "1924–1934"
    school["метаданные_извлечения"] = {"метод_извлечения": "ручная проверка", "общая_уверенность": 0.9}
    document["контроль_качества"] = {
        "число_персон": 2,
        "число_источников": 2,
        "число_подтверждений": 2,
        "использовано_несколько_источников": True,
        "расхождения_источников_сохранены": True,
        "прямые_и_косвенные_связи_разделены": True,
        "поля_с_недостаточной_информацией": ["границы"],
        "потенциально_интерпретативные_выводы": ["роль"],
        "замечания": ["замечание"],
    }
    return document


def test_vygotsky_json_loads_and_counts():
    document = load_demo_document()
    assert document["школа"]["идентификатор_школы"] == "vygotsky_cultural_historical_school"
    assert document["демо_представление"]["название_в_выпадающем_списке"] == "Лев Семёнович Выготский"
    assert len(document["школа"]["персоны"]) == 47
    assert len(document["школа"]["источники"]) == 8
    assert len(document["школа"]["подтверждения"]) == 34


def test_catalog_contains_one_school():
    catalog = load_source_school_catalog(SOURCE_SCHOOLS_DATA_DIR)
    assert len(catalog) == 1
    assert catalog[0]["school_id"] == "vygotsky_cultural_historical_school"
    assert catalog[0]["label"] == "Лев Семёнович Выготский"


def test_cross_references_resolve():
    indexes = build_source_school_index(load_demo_document())
    assert len(indexes["persons"]) == 47
    assert len(indexes["sources"]) == 8
    assert len(indexes["evidence"]) == 34


def test_duplicate_person_id_raises():
    document = make_canonical_document()
    document["школа"]["персоны"][1]["id"] = document["школа"]["персоны"][0]["id"]
    with pytest.raises(SourceSchoolDataError, match="повторяющийся идентификатор"):
        validate_source_school_document(document)


def test_unknown_evidence_in_person_raises():
    document = make_canonical_document()
    document["школа"]["персоны"][0]["подтверждения"] = ["unknown_evidence"]
    with pytest.raises(SourceSchoolDataError, match="неизвестное подтверждение"):
        validate_source_school_document(document)


def test_unknown_source_in_evidence_raises():
    document = make_canonical_document()
    document["школа"]["подтверждения"][0]["идентификатор_источника"] = "unknown_source"
    with pytest.raises(SourceSchoolDataError, match="неизвестный источник"):
        validate_source_school_document(document)


def test_unknown_group_participant_raises():
    document = make_canonical_document()
    document["школа"]["внутренняя_структура"]["исследовательские_группы"][0]["участники"].append("unknown_person")
    with pytest.raises(SourceSchoolDataError, match="Неизвестная персона"):
        validate_source_school_document(document)


def test_bad_confidence_raises():
    document = make_canonical_document()
    document["школа"]["персоны"][0]["уверенность"] = 1.5
    with pytest.raises(SourceSchoolDataError, match="уверенность"):
        validate_source_school_document(document)


def test_stale_summary_raises():
    document = make_canonical_document()
    document["демо_представление"]["сводные_показатели"]["число_персон"] = 1
    with pytest.raises(SourceSchoolDataError, match="Сводные показатели устарели"):
        validate_source_school_document(document)


def test_duplicate_school_id_across_catalog_raises(tmp_path):
    text = PATH.read_text(encoding="utf-8")
    (tmp_path / "a.json").write_text(text, encoding="utf-8")
    (tmp_path / "b.json").write_text(text, encoding="utf-8")
    with pytest.raises(SourceSchoolDataError, match="идентификатор школы"):
        load_source_school_catalog(tmp_path)


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(SourceSchoolDataError, match="некорректный JSON"):
        load_source_school_file(path)


def test_missing_directory_returns_empty_catalog(tmp_path):
    assert load_source_school_catalog(tmp_path / "нет") == []


def test_summary_aliases_from_supplied_contract_are_supported():
    document = make_canonical_document()
    summary = document["демо_представление"]["сводные_показатели"]
    summary.clear()
    summary.update(
        {
            "количество_персон": 2,
            "количество_источников": 2,
            "количество_подтверждений": 2,
            "по_категориям": {"ядро": 1, "последователь": 1},
        }
    )
    document["контроль_качества"].pop("персоны_по_категориям")
    validate_source_school_document(document)


def test_person_field_aliases_are_normalized():
    document = make_canonical_document()
    person = document["школа"]["персоны"][0]
    person["имя"] = person.pop("полное_имя")
    person["даты"] = "1900–1980"
    person["основные_идеи_или_вклад"] = person.pop("основной_вклад")
    validate_source_school_document(document)


def test_attribution_source_must_match_evidence_source():
    document = make_canonical_document()
    document["школа"]["персоны"][0]["источниковые_атрибуции"][0]["подтверждение"] = "evidence_beta"
    with pytest.raises(SourceSchoolDataError, match="подтверждением другого источника"):
        validate_source_school_document(document)


def test_missing_file_has_domain_error(tmp_path):
    with pytest.raises(SourceSchoolDataError, match="Файл школы не найден"):
        load_source_school_file(tmp_path / "нет.json")


def test_wrong_list_item_type_has_domain_error():
    document = make_canonical_document()
    document["школа"]["персоны"].append("не объект")
    with pytest.raises(SourceSchoolDataError, match="должен быть объектом"):
        validate_source_school_document(document)


def test_nested_full_json_contract_is_supported():
    validate_source_school_document(make_full_contract_document())


def test_all_confidence_fields_are_validated():
    document = make_full_contract_document()
    document["школа"]["связи_с_другими_школами"][0]["уверенность"] = 1.5
    with pytest.raises(SourceSchoolDataError, match="уверенность"):
        validate_source_school_document(document)


def test_aggregate_representatives_are_validated():
    document = make_full_contract_document()
    document["школа"]["представители"] = {"ученики": ["unknown_person"]}
    with pytest.raises(SourceSchoolDataError, match="школа.представители"):
        validate_source_school_document(document)


def test_nested_items_have_domain_errors():
    document = make_canonical_document()
    document["школа"]["внутренняя_структура"]["направления"].append("не объект")
    with pytest.raises(SourceSchoolDataError, match="должен быть объектом"):
        validate_source_school_document(document)


def test_chronology_wrong_type_has_domain_error():
    document = make_canonical_document()
    document["школа"]["хронология"] = "не объект"
    with pytest.raises(SourceSchoolDataError, match="хронология"):
        validate_source_school_document(document)
