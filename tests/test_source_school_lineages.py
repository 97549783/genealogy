"""Проверки переходов из персон источниковой школы в генеалогию."""
from __future__ import annotations

import pandas as pd

from core.lineage.graph import build_index, lineage, rows_for
from core.source_schools.lineages import resolve_source_school_lineages
from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import _markmap_node_content, build_markmap_html


def document(name="Алексей Николаевич Леонтьев"):
    from source_school_fixtures import synthetic_document
    d = synthetic_document(facet_count=0)
    d['объекты']['персоны'][0].update(id='leontiev', имя=name)
    d['состав'][0]['персона'] = 'leontiev'
    d['отображение']['центр'] = {'тип': 'персона', 'id': 'leontiev'}
    return d


def index(df):
    return build_index(df, ["supervisors_1.name", "supervisors_2.name"])


def test_source_name_resolves_surname_first_and_requires_supervised_records():
    df = pd.DataFrame([
        {"Code": "1", "candidate_name": "Ученик", "supervisors_1.name": "Леонтьев Алексей Николаевич"},
        {"Code": "2", "candidate_name": "Другой ученик", "supervisors_1.name": "Леонтьев Алексей Николаевич"},
    ])
    resolution = resolve_source_school_lineages(document(), df, index(df))["leontiev"]
    assert resolution.root_name == "Леонтьев Алексей Николаевич"
    assert resolution.record_count == 2
    candidate_only = pd.DataFrame([{"Code": "3", "candidate_name": resolution.root_name, "supervisors_1.name": "Другой руководитель"}])
    assert resolve_source_school_lineages(document(), candidate_only, index(candidate_only)) == {}


def test_unique_initials_of_different_full_name_do_not_enable_link():
    df = pd.DataFrame([{"Code": "1", "candidate_name": "Ученик", "supervisors_1.name": "Леонтьев Александр Николаевич"}])
    assert resolve_source_school_lineages(document(), df, index(df)) == {}


def test_lineage_does_not_merge_conflicting_expanded_names_or_ambiguous_initials():
    df = pd.DataFrame([
        {"Code": "1", "candidate_name": "Ученик Алексея", "supervisors_1.name": "Леонтьев Алексей Николаевич"},
        {"Code": "2", "candidate_name": "Ученик Александра", "supervisors_1.name": "Леонтьев Александр Николаевич"},
        {"Code": "3", "candidate_name": "Неоднозначный ученик", "supervisors_1.name": "Леонтьев А.Н."},
    ])
    idx = index(df)
    assert rows_for(df, idx, "Леонтьев Алексей Николаевич")["Code"].tolist() == ["1"]
    assert rows_for(df, idx, "Леонтьев Александр Николаевич")["Code"].tolist() == ["2"]
    assert rows_for(df, idx, "Леонтьев А.Н.").empty
    graph, _ = lineage(df, idx, "Леонтьев Алексей Николаевич")
    assert set(graph.successors("Леонтьев Алексей Николаевич")) == {"Ученик Алексея"}


def test_unambiguous_initials_and_second_supervisor_are_preserved():
    df = pd.DataFrame([
        {"Code": "1", "candidate_name": "Ученик", "supervisors_1.name": "Другой руководитель", "supervisors_2.name": "Леонтьев Алексей Николаевич"},
        {"Code": "2", "candidate_name": "Второй ученик", "supervisors_1.name": "Леонтьев А.Н.", "supervisors_2.name": ""},
    ])
    assert set(rows_for(df, index(df), "Леонтьев Алексей Николаевич")["Code"]) == {"1", "2"}


def test_parenthesized_surname_alias_and_two_word_name_resolve():
    for source_name, root in [
        ("Иван Михайлович Соловьёв (Соловьёв-Эльпидинский)", "Соловьев-Эльпидинский Иван Михайлович"),
        ("Курт Левин", "Левин Курт"),
    ]:
        df = pd.DataFrame([{"Code": "1", "candidate_name": "Ученик", "supervisors_1.name": root}])
        assert resolve_source_school_lineages(document(source_name), df, index(df))["leontiev"].root_name == root


def test_links_do_not_change_source_tree_edges_and_include_founder():
    doc = document()
    plain = build_source_school_overview_tree(doc)
    url = "https://example.test/?tab=lineages&root=Leontiev"
    linked = build_source_school_overview_tree(doc, lineage_links={"leontiev": {"href": url, "title": "Открыть дерево"}})
    assert set(linked.graph.edges) == set(plain.graph.edges)
    content = _markmap_node_content(linked.graph, linked.root_id)
    assert 'href="https://example.test/?tab=lineages&amp;root=Leontiev"' in content
    assert '<svg ' in content
    assert 'target="_blank"' in content
    assert 'rel="noopener noreferrer"' in content
    for mode in ("bidirectional", "unidirectional"):
        html, _ = build_markmap_html(linked.graph, linked.root_id, branching_mode=mode)
        assert "markmap-lineage-link" in html
        assert "text-decoration: underline" in html
        if mode == "bidirectional":
            assert "innerHTML = rootContent" in html
            assert "pointer-events: auto" in html


def test_node_content_escapes_text_and_rejects_script_urls():
    tree = build_source_school_overview_tree(document('<script>alert("x")</script>'))
    tree.graph.nodes[tree.root_id]["href"] = "javascript:alert(1)"
    content = _markmap_node_content(tree.graph, tree.root_id)
    assert "<script>" not in content
    assert "&lt;script&gt;" in content
    assert "<a " not in content


def test_native_alias_requires_real_evidence_and_unique_root():
    doc=document('А. Н. Леонтьев')
    person=doc['объекты']['персоны'][0]
    person['варианты_имени']=[dict(написание='Алексей Николаевич Леонтьев', вид='как_в_источнике', основания=['evidence_alpha'])]
    df=pd.DataFrame([{'Code':'1','candidate_name':'Ученик','supervisors_1.name':'Леонтьев Алексей Николаевич'}])
    assert resolve_source_school_lineages(doc,df,index(df))['leontiev'].record_count==1
    person['варианты_имени'][0]['основания']=['absent']
    assert not resolve_source_school_lineages(doc,df,index(df))
    person['варианты_имени'][0]['основания']=['evidence_alpha']
    doc['основания'][0]['проверка']['статус']='ошибка'
    assert not resolve_source_school_lineages(doc,df,index(df))


def test_initials_partial_names_and_ambiguous_identification_do_not_create_tree():
    df=pd.DataFrame([{'Code':'1','candidate_name':'Ученик','supervisors_1.name':'Леонтьев Алексей Николаевич'}])
    assert not resolve_source_school_lineages(document('Леонтьев А. Н.'),df,index(df))
    assert not resolve_source_school_lineages(document('Леонтьев Алексей Н.'),df,index(df))
    doc=document();doc['объекты']['персоны'][0]['идентификация']['статус']='неоднозначная'
    assert not resolve_source_school_lineages(doc,df,index(df))
    doc=document();doc['состав'][0]['решение']='кандидат'
    assert not resolve_source_school_lineages(doc,df,index(df))


def test_only_confirmed_addressable_database_root_mapping_can_override_uncertain_name():
    doc=document('А. Н. Леонтьев');person=doc['объекты']['персоны'][0]
    person['идентификация']['статус']='вероятная'
    identifier=dict(система='academic_genealogy:root_name', значение='Леонтьев Алексей Николаевич', решение='кандидат', основания=['evidence_alpha'])
    person['внешние_идентификаторы']=[identifier]
    df=pd.DataFrame([{'Code':'1','candidate_name':'Ученик','supervisors_1.name':'Леонтьев Алексей Николаевич'}])
    assert not resolve_source_school_lineages(doc,df,index(df))
    identifier['решение']='подтверждено'
    assert resolve_source_school_lineages(doc,df,index(df))['leontiev'].record_count==1
    identifier['система']='wikidata'
    assert not resolve_source_school_lineages(doc,df,index(df))


def test_two_attested_full_aliases_matching_distinct_roots_remain_ambiguous():
    doc=document();doc['объекты']['персоны'][0]['варианты_имени']=[dict(написание='Александр Николаевич Леонтьев', вид='как_в_источнике', основания=['evidence_alpha'])]
    df=pd.DataFrame([{'Code':'1','candidate_name':'A','supervisors_1.name':'Леонтьев Алексей Николаевич'},
                     {'Code':'2','candidate_name':'B','supervisors_1.name':'Леонтьев Александр Николаевич'}])
    assert not resolve_source_school_lineages(doc,df,index(df))


def test_cache_invalidates_database_path_scope_and_alias_changes():
    from core.source_schools.lineages import get_source_school_lineages, _cached_source_school_lineages
    _cached_source_school_lineages.clear()
    doc=document();df=pd.DataFrame([{'Code':'1','candidate_name':'A','supervisors_1.name':'Леонтьев Алексей Николаевич'}])
    first=get_source_school_lineages(doc,df,index(df),('first.db',1,10))
    assert first['leontiev'].record_count==1
    expanded=pd.concat([df,pd.DataFrame([{'Code':'2','candidate_name':'B','supervisors_1.name':'Леонтьев Алексей Николаевич'}])],ignore_index=True)
    assert get_source_school_lineages(doc,expanded,index(expanded),('second.db',1,10))['leontiev'].record_count==2
    assert get_source_school_lineages(doc,expanded,index(expanded),('first.db',1,10))['leontiev'].record_count==2
    doc['объекты']['персоны'][0]['имя']='Другое Полное Имя'
    assert not get_source_school_lineages(doc,expanded,index(expanded),('first.db',1,10))
