import json

from core.classifier.data_it_2_3 import CLASSIFIER_JSON_PATH
from core.classifier.registry import (
    get_classifier_by_profile_source,
    get_classifier_labels_by_profile_source,
)


def test_pedagogy_classifier_registered():
    classifier = get_classifier_by_profile_source("pedagogy_5_8")
    labels = get_classifier_labels_by_profile_source("pedagogy_5_8")
    assert classifier
    assert "1.1.1" in labels


def test_it_classifier_registered():
    classifier = get_classifier_by_profile_source("it_2_3")
    labels = get_classifier_labels_by_profile_source("it_2_3")

    assert classifier
    assert labels["1"] == "Объект исследования и предметная область"
    assert labels["1.1"] == "Типы систем"
    assert labels["1.1.3"] == "Системы управления"
    assert labels["1.1.4"] == "Информационные системы"
    assert labels["1.1.5"] == "Программные системы"
    assert labels["1.1.6"] == "Системы информационной безопасности"
    assert labels["1.2"] == "Типы данных и информации"
    assert labels["1.3"] == "Отрасли и сферы применения"
    assert labels["2"] == "Методы, технологии и процессы"
    assert labels["2.1"] == "Системный анализ и моделирование"
    assert labels["2.2"] == "Теория управления и оптимизация"
    assert labels["2.3.1"] == "Статистические методы"
    assert labels["2.5.4"] == "Визуализация и интерфейсы"
    assert labels["3"] == "Результаты и целевые характеристики"
    assert labels["3.1.1"] == "Теоретические результаты"
    assert labels["3.1.2"] == "Архитектурно-структурные решения"
    assert labels["3.2.1"] == "Решаемые задачи управления"
    assert labels["3.3.1"] == "Производительность"
    assert labels["3.3.6.4"] == "Удобство использования (Usability)"
    assert "1.1.1.1" in labels
    assert "2.4.2.3" in labels
    assert "3.1.1.1" in labels
    assert "3.3.6.4" in labels


def test_it_classifier_json_is_source_of_truth():
    payload = json.loads(CLASSIFIER_JSON_PATH.read_text(encoding="utf-8"))
    expected = {item["code"]: item["title"] for item in payload["items"]}

    labels = get_classifier_labels_by_profile_source("it_2_3")
    assert labels == expected


def test_it_classifier_json_has_unique_codes_and_existing_parents():
    payload = json.loads(CLASSIFIER_JSON_PATH.read_text(encoding="utf-8"))
    codes = [item["code"] for item in payload["items"]]

    assert all("disabled" not in item for item in payload["items"])
    assert len(codes) == len(set(codes))

    code_set = set(codes)
    for code in codes:
        if "." in code:
            assert code.rsplit(".", 1)[0] in code_set


def test_it_classifier_disabled_flags_are_derived_from_children():
    classifier = {
        code: disabled
        for code, _title, disabled in get_classifier_by_profile_source("it_2_3")
    }

    assert classifier["1"] is True
    assert classifier["1.1"] is True
    assert classifier["1.1.1"] is True
    assert classifier["1.1.1.1"] is False
    assert classifier["2.5.4"] is True
    assert classifier["2.5.4.4"] is False
    assert classifier["3.3.6"] is True
    assert classifier["3.3.6.4"] is False
