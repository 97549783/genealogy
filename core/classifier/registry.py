from __future__ import annotations

from core.domain.profile_sources import get_profile_source

from .data_it_2_3 import IT_2_3_CLASSIFIER
from .data_pedagogy_5_8 import PEDAGOGY_5_8_CLASSIFIER, ClassifierItem

_CLASSIFIERS: dict[str, list[ClassifierItem]] = {
    "pedagogy_5_8": PEDAGOGY_5_8_CLASSIFIER,
    "it_2_3": IT_2_3_CLASSIFIER,
}


def get_classifier(classifier_id: str) -> list[ClassifierItem]:
    try:
        return _CLASSIFIERS[classifier_id]
    except KeyError as exc:
        raise ValueError(f"Неизвестный классификатор: {classifier_id}") from exc


def get_classifier_labels(classifier_id: str) -> dict[str, str]:
    return {code: title for code, title, _ in get_classifier(classifier_id)}


def get_classifier_by_profile_source(profile_source_id: str | None) -> list[ClassifierItem]:
    source = get_profile_source(profile_source_id)
    return get_classifier(source.classifier_id)


def get_classifier_labels_by_profile_source(profile_source_id: str | None) -> dict[str, str]:
    source = get_profile_source(profile_source_id)
    return get_classifier_labels(source.classifier_id)
