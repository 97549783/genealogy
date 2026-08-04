"""Табличные преобразования для демо школ по источникам."""
from __future__ import annotations
from typing import Any, Collection, Mapping
import pandas as pd

def _join(v):
    return "; ".join(map(str, v)) if isinstance(v, list) else ("" if v is None else str(v))

def resolve_person_names(person_ids: Collection[str], person_index: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Заменяет идентификаторы персон отображаемыми именами."""
    return [person_index[i].get("полное_имя", i) for i in person_ids if i in person_index]

def build_people_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    """Формирует таблицу представителей школы."""
    rows=[]
    for p in document["школа"]["персоны"]:
        sids=[a.get("идентификатор_источника") for a in p.get("источниковые_атрибуции", []) if a.get("идентификатор_источника")]
        rows.append({"ID":p.get("id"),"Представитель":p.get("полное_имя",""),"Категория":p.get("категория_включения",""),"Роли":_join(p.get("роль_в_школе",[])),"Связь с Выготским":p.get("статус_связи_с_выготским",""),"Период взаимодействия":p.get("период_взаимодействия",""),"Группы и контексты":_join(p.get("группы_и_контексты",[])),"Основной вклад":p.get("основной_вклад",""),"Уверенность":float(p.get("уверенность",0) or 0),"Число источников":len(set(sids)),"Идентификаторы источников":"; ".join(dict.fromkeys(sids))})
    return pd.DataFrame(rows)

def _contains_any(series, values):
    return series.fillna("").str.split("; ").apply(lambda xs: bool(set(xs) & set(values)))

def filter_people_dataframe(dataframe: pd.DataFrame, *, query: str = "", categories: Collection[str] = (), roles: Collection[str] = (), groups: Collection[str] = (), source_ids: Collection[str] = (), minimum_confidence: float = 0.0) -> pd.DataFrame:
    """Фильтрует таблицу представителей без изменения исходного DataFrame."""
    df=dataframe.copy()
    mask=df["Уверенность"]>=minimum_confidence
    if query.strip():
        q=query.strip().lower(); cols=["Представитель","Категория","Роли","Связь с Выготским","Группы и контексты","Основной вклад"]
        mask &= df[cols].fillna("").agg(" ".join,axis=1).str.lower().str.contains(q, regex=False)
    if categories: mask &= df["Категория"].isin(categories)
    if roles: mask &= _contains_any(df["Роли"], roles)
    if groups: mask &= _contains_any(df["Группы и контексты"], groups)
    if source_ids: mask &= _contains_any(df["Идентификаторы источников"], source_ids)
    return df.loc[mask].copy()

def build_sources_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    """Формирует таблицу библиографических источников."""
    return pd.DataFrame([{"ID":s.get("id"),"Источник":s.get("краткое_название") or s.get("библиографическое_описание",""),"Год":s.get("год",""),"Тип":s.get("тип",""),"DOI":s.get("doi",""),"Роль в описании":s.get("роль_в_описании",""),"Примечание":s.get("примечание","")} for s in document["школа"]["источники"]])

def build_evidence_dataframe(document: Mapping[str, Any]) -> pd.DataFrame:
    """Формирует таблицу подтверждений с названиями источников."""
    labels={s["id"]:s.get("краткое_название") or s.get("библиографическое_описание",s["id"]) for s in document["школа"]["источники"]}
    return pd.DataFrame([{"ID":e.get("id"),"Источник":labels.get(e.get("идентификатор_источника"),e.get("идентификатор_источника")),"Тип утверждения":e.get("тип_утверждения",""),"Содержание свидетельства":e.get("содержание_свидетельства",""),"Локатор":e.get("локатор",""),"Статус":"Явное утверждение" if e.get("явное_утверждение") else "Интерпретация","Уверенность":float(e.get("уверенность",0) or 0)} for e in document["школа"]["подтверждения"]])
