"""Deep-link encoding, card/tree distinction and safe keyboard-accessible icons."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import networkx as nx
import pytest

from core.source_schools import links
from core.source_schools.tree import build_source_school_overview_tree
from core.ui.tree_renderers import _markmap_node_content, build_markmap_html
from source_school_fixtures import synthetic_document


class Anchors(HTMLParser):
    def __init__(self, content):
        super().__init__(); self.links=[]; self.feed(content)
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.links.append(dict(attrs))


def test_stable_school_and_person_urls_replace_stale_state_and_encode_values():
    href = links.build_source_school_url('school & <x>', person_id='person/я', view='person', base_url='http://localhost:8501/app?school=old&root=wrong#fragment')
    split = urlsplit(href)
    assert split.scheme == 'http' and split.netloc == 'localhost:8501' and split.path == '/app' and not split.fragment
    assert parse_qs(split.query) == dict(tab=['source_schools'], school=['school & <x>'], person=['person/я'], view=['person'])
    assert links.build_source_school_url('school', base_url='') == '?tab=source_schools&school=school'
    assert links.build_source_school_url('school', base_url='/app').startswith('/app?')


def test_default_school_url_uses_shared_configured_share_base(monkeypatch):
    calls=[]
    monkeypatch.setattr('core.ui.links.build_share_url_from_params', lambda params: calls.append(params) or 'https://example.test/link')
    assert links.build_source_school_url('school') == 'https://example.test/link'
    assert calls == [dict(tab='source_schools', school='school')]


@pytest.mark.parametrize('base', ['javascript:alert(1)', 'data:text/html,x', '//evil.test', 'https://user:pw@example.test/', 'https://example.test/\nfoo', 'relative/path'])
def test_bad_bases_rejected(base):
    with pytest.raises(ValueError): links.build_source_school_url('school', base_url=base)


@pytest.mark.parametrize('bad', ['javascript:alert(1)', 'data:text/html,x', '//evil.test', 'https:javascript:alert(1)', 'https://example.test/\nfoo', 'https://user:pw@example.test/'])
def test_tree_icon_rejects_executable_or_ambiguous_urls(bad):
    assert links.tree_icon_link(bad) == ''


def test_svg_icon_is_small_safe_and_accessible():
    content = links.tree_icon_link('https://example.test/?root=a&x=b', 'Открыть <дерево> "имя"')
    anchor = Anchors(content).links[0]
    assert anchor['href'] == 'https://example.test/?root=a&x=b'
    assert anchor['target'] == '_blank' and anchor['rel'] == 'noopener noreferrer'
    assert anchor['aria-label'] == 'Открыть <дерево> "имя"' and anchor['title'] == anchor['aria-label']
    assert '<svg ' in content and 'aria-hidden="true"' in content and 'focusable="false"' in content


def test_source_person_name_goes_to_card_and_separate_icon_goes_to_lineage():
    d = synthetic_document()
    card='https://example.test/?tab=source_schools&school=s&person=person_alpha&view=person'
    lineage='https://example.test/?tab=lineages&root=Альфа'
    tree = build_source_school_overview_tree(d, person_links={'person_alpha':dict(href=card)}, lineage_links={'person_alpha':dict(href=lineage)}, school_link='https://example.test/?tab=source_schools&school=s')
    content = _markmap_node_content(tree.graph, 'person:person_alpha')
    anchors = Anchors(content).links
    assert [a['href'] for a in anchors] == [card, lineage]
    assert 'markmap-source-link' in anchors[0]['class'] and 'source-school-tree-icon' in anchors[1]['class']
    assert len(Anchors(_markmap_node_content(tree.graph, 'person:person_beta')).links) == 0
    for mode in ['bidirectional', 'unidirectional']:
        html, _ = build_markmap_html(tree.graph, tree.root_id, branching_mode=mode)
        assert 'event.stopPropagation()' in html and "'keydown'" in html and ':focus-visible' in html
        if mode == 'bidirectional': assert 'innerHTML = rootContent' in html and 'pointer-events: auto' in html


def test_no_lineage_means_no_icon_and_source_label_is_escaped():
    d=synthetic_document();d['объекты']['персоны'][0]['имя']='</script><img src=x onerror=alert(1)>'
    tree=build_source_school_overview_tree(d, person_links={'person_alpha':dict(href='?tab=source_schools&school=s&person=p')})
    content=_markmap_node_content(tree.graph,'person:person_alpha')
    assert '<img ' not in content and '&lt;img ' in content and '<svg ' not in content
    html,_=build_markmap_html(tree.graph,tree.root_id)
    assert '</script><img' not in html
    # Generic non-source graphs retain the established name-to-lineage link.
    graph=nx.DiGraph();graph.add_node('root',label='Root',href='https://example.test/?root=Root')
    assert Anchors(_markmap_node_content(graph,'root')).links[0]['class']=='markmap-lineage-link'


def test_cold_source_school_ui_import_has_no_renderer_link_cycle():
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, '-c',
         'import tabs.source_schools.tab; '
         'from core.source_schools.links import build_source_school_url, tree_icon_link; '
         'assert build_source_school_url("school", base_url="").startswith("?tab=source_schools"); '
         'assert "<svg " in tree_icon_link("https://example.test/?root=Root")'],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
