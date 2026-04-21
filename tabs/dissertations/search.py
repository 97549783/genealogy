from __future__ import annotations

from typing import Dict, List

import pandas as pd


def get_available_criteria() -> Dict[str, str]:
    return {
        "title": "Название диссертации",
        "candidate_name": "ФИО автора",
        "supervisors": "ФИО научного руководителя",
        "opponents": "ФИО оппонента",
        "institution_prepared": "Организация выполнения",
        "leading_organization": "Ведущая организация",
        "defense_location": "Место защиты",
        "city": "Город защиты",
        "year": "Год защиты",
        "specialties": "Специальность",
    }


def build_filter_options(df: pd.DataFrame) -> Dict[str, List[str]]:
    all_years = sorted(
        [str(y) for y in df["year"].dropna().unique() if str(y).strip()],
        reverse=True,
    )
    all_cities = sorted(
        [str(c) for c in df["city"].dropna().unique() if str(c).strip()]
    )
    all_specialties = set()
    for col in [
        "specialties_1.code",
        "specialties_1.name",
        "specialties_2.code",
        "specialties_2.name",
    ]:
        if col in df.columns:
            all_specialties.update(
                [str(v).strip() for v in df[col].dropna().unique() if str(v).strip()]
            )

    return {
        "year": all_years,
        "city": all_cities,
        "specialties": sorted(all_specialties),
    }


def _filter_contains(df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    return df[df[column].astype(str).str.contains(value, case=False, na=False)]


def filter_dissertations(df: pd.DataFrame, search_params: Dict[str, str]) -> pd.DataFrame:
    result_df = df.copy()

    for criterion, value in search_params.items():
        if not value or value == "Все":
            continue

        if criterion in [
            "title",
            "candidate_name",
            "institution_prepared",
            "leading_organization",
            "defense_location",
        ]:
            result_df = _filter_contains(result_df, criterion, value)
        elif criterion == "supervisors":
            mask = pd.Series([False] * len(result_df), index=result_df.index)
            for col in ["supervisors_1.name", "supervisors_2.name"]:
                if col in result_df.columns:
                    mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
            result_df = result_df[mask]
        elif criterion == "opponents":
            mask = pd.Series([False] * len(result_df), index=result_df.index)
            for col in ["opponents_1.name", "opponents_2.name", "opponents_3.name"]:
                if col in result_df.columns:
                    mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
            result_df = result_df[mask]
        elif criterion in ["city", "year"]:
            result_df = _filter_contains(result_df, criterion, value)
        elif criterion == "specialties":
            mask = pd.Series([False] * len(result_df), index=result_df.index)
            for col in [
                "specialties_1.code",
                "specialties_1.name",
                "specialties_2.code",
                "specialties_2.name",
            ]:
                if col in result_df.columns:
                    mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
            result_df = result_df[mask]

    return result_df
