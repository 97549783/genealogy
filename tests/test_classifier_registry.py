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
    assert labels["1.1.2"] == "Компьютерные сети"
    assert labels["1.1.2.1"] == "Локальные и корпоративные сети"
    assert labels["1.1.2.2"] == "Глобальные сети и Интернет"
    assert labels["1.1.2.3"] == "Беспроводные и мобильные сети"
    assert labels["2"] == "Методы, технологии и процессы"
    assert labels["2.4.2.3"] == "Распределённые базы данных"
    assert labels["2.6.4.4"] == "Защита сетевой инфраструктуры"
    assert labels["3"] == "Результаты и целевые характеристики"
    assert labels["3.3.6.4"] == "Удобство использования (Usability)"
    assert "1.1.1.1" in labels
    assert "2.4.2.3" in labels
    assert "3.1.1.1" in labels
    assert "3.3.6.4" in labels


def test_it_classifier_disabled_flags():
    classifier = dict((code, disabled) for code, _title, disabled in get_classifier_by_profile_source("it_2_3"))
    assert classifier["1"] is True
    assert classifier["1.1"] is True
    assert classifier["1.1.2"] is True
    assert classifier["1.1.1.1"] is False
    assert classifier["3.3.6.4"] is False
