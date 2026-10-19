"""Universal source-school layout: one optional division, any number of facets."""
from __future__ import annotations

import copy

import pytest

from core.source_schools.data import SourceSchoolDataError
from core.source_schools.tree import (
    build_person_primary_relation_index,
    build_source_school_overview_tree,
    build_source_school_tree_edges_dataframe,
    build_supplementary_dimension_catalog,
    combine_supplementary_selections,
)
from core.ui.tree_renderers import build_markmap_html
from source_school_fixtures import load_vygotsky, synthetic_document


def test_vygotsky_retains_four_categories_and_one_center_person():
    tree = build_source_school_overview_tree(load_vygotsky())
    assert tree.basis == 'основное_деление'
    assert tree.root_id == 'person:lev_vygotsky'
    assert [tree.graph.nodes[n]['label'] for n in tree.graph.successors(tree.root_id)] == [
        'Научное руководство и обучение', 'Непосредственное научное сотрудничество',
        'Внешнее научное взаимодействие', 'Опосредованная научная преемственность',
    ]
    leaves = [n for n, a in tree.graph.nodes(data=True) if a.get('kind') == 'person']
    assert len(leaves) == 50 and all(tree.graph.in_degree(n) == 1 for n in leaves)
    assert sum(a.get('person_id') == 'lev_vygotsky' for _, a in tree.graph.nodes(data=True)) == 1
    assert len(build_person_primary_relation_index(load_vygotsky())) == 50
    assert build_source_school_tree_edges_dataframe(tree).columns.tolist() == ['Источник', 'Цель']


@pytest.mark.parametrize('facet_count', [0, 1, 3, 5])
def test_no_primary_is_a_flat_included_list_with_arbitrary_facets(facet_count):
    d = synthetic_document(facet_count=facet_count)
    tree = build_source_school_overview_tree(d)
    assert tree.root_id == 'school:synthetic_school' and tree.basis == 'плоский_список'
    assert tree.graph.number_of_nodes() == 5
    assert all(a['kind'] == 'person' for n, a in tree.graph.nodes(data=True) if n != tree.root_id)
    assert 'person:person_candidate' not in tree.graph
    assert len(build_supplementary_dimension_catalog(d)) == facet_count
    assert build_person_primary_relation_index(d) == {}


def test_optional_primary_supports_any_number_and_source_order():
    d = synthetic_document(primary=True)
    primary = d['классификации']['основное_деление']
    primary['категории'].append(dict(id='empty', название='Пустая категория', порядок=3))
    primary['категории'].reverse()
    tree = build_source_school_overview_tree(d)
    assert [tree.graph.nodes[n]['label'] for n in tree.graph.successors(tree.root_id)] == [
        'Категория Альфа', 'Категория Бета', 'Пустая категория', 'Не классифицировано',
    ]
    assert set(tree.graph.successors('service:unclassified')) == {'person:person_gamma', 'person:person_delta'}
    assert build_person_primary_relation_index(d) == {'person_alpha': 'Категория Альфа', 'person_beta': 'Категория Бета'}


def test_primary_scope_and_exclusions_do_not_remove_people_or_create_memberships():
    d = synthetic_document(primary=True)
    d['состав'][1]['отношение_к_школе'] = 'связанное_лицо'
    d['классификации']['основное_деление']['исключённые_персоны'] = ['person_gamma']
    tree = build_source_school_overview_tree(d)
    assert set(tree.graph.successors('service:outside')) == {'person:person_beta', 'person:person_gamma'}
    assert 'person:person_delta' in tree.graph.successors('service:unclassified')
    assert build_person_primary_relation_index(d) == {'person_alpha': 'Категория Альфа'}


def test_duplicate_primary_is_rejected_and_hypothesis_never_classifies():
    d = synthetic_document(primary=True)
    duplicate = copy.deepcopy(d['классификационные_назначения'][-1])
    duplicate.update(id='duplicate', персона='person_alpha')
    d['классификационные_назначения'].append(duplicate)
    with pytest.raises(SourceSchoolDataError):
        build_source_school_overview_tree(d)
    duplicate['решение'] = 'гипотеза'
    assert build_source_school_overview_tree(d).graph.in_degree('person:person_alpha') == 1


def test_highlight_hide_do_not_rebuild_edges_categories_or_order():
    d = synthetic_document(primary=True, facet_count=5)
    plain = build_source_school_overview_tree(d)
    overlay = build_source_school_overview_tree(d, highlighted_person_ids={'person_alpha'}, hidden_person_ids={'person_beta'})
    assert list(plain.graph.nodes) == list(overlay.graph.nodes)
    assert list(plain.graph.edges) == list(overlay.graph.edges)
    assert overlay.graph.nodes['person:person_alpha']['color'] == '#ff8f00'
    assert overlay.graph.nodes['person:person_beta']['color'] == '#cfd8dc'
    assert overlay.graph.nodes['person:person_beta']['hidden'] is True
    for mode in ['bidirectional', 'unidirectional']:
        html, height = build_markmap_html(overlay.graph, overlay.root_id, branching_mode=mode)
        assert height > 0 and '"_hidden": true' in html
        assert ".style('visibility'" in html and 'applyVisibility' in html


def test_center_person_stays_once_and_candidates_cannot_be_centers():
    d = synthetic_document(primary=True)
    d['отображение']['центр'] = dict(тип='персона', id='person_alpha')
    tree = build_source_school_overview_tree(d)
    assert tree.root_id == 'person:person_alpha'
    assert tree.graph.in_degree(tree.root_id) == 0
    assert sum(a.get('person_id') == 'person_alpha' for _, a in tree.graph.nodes(data=True)) == 1
    d['отображение']['центр']['id'] = 'person_candidate'
    with pytest.raises(SourceSchoolDataError):
        build_source_school_overview_tree(d)


def test_dynamic_filter_or_within_and_across_and_hypotheses_inactive():
    d = synthetic_document(facet_count=5)
    catalog = build_supplementary_dimension_catalog(d, include_unverified=True)
    selections = {'historical_group': ['historical_group:group_alpha', 'historical_group:group_beta'],
                  'place_context': ['place_context:place_alpha']}
    assert combine_supplementary_selections(catalog, selections) == {'person_beta'}
    assert combine_supplementary_selections(catalog, selections, mode='union') == {'person_alpha', 'person_beta'}
    assert combine_supplementary_selections(catalog, {}) is None
    assert next(v for v in catalog['historical_group'] if v.id.endswith(':concept_context')).person_ids == ()
