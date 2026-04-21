"""
tabs/lineages/rendering.py — функции отрисовки деревьев научного руководства.

Публичный API:
    draw_matplotlib(G, root)   -> plt.Figure
        Статичный PNG-граф через matplotlib / networkx.

    build_pyvis_html(G, root)  -> str
        Интерактивный HTML-граф (pyvis) с кнопками сворачивания ветвей.

Вспомогательные (не для прямого вызова извне):
    _hierarchy_pos(G, root)    -> dict  — ручная иерархическая раскладка
"""

from __future__ import annotations

import json
import textwrap
from collections import deque
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import networkx as nx

from pyvis.network import Network

from core.lineage.graph import multiline, slug


# ---------------------------------------------------------------------------
# Вспомогательная: ручная иерархическая раскладка
# ---------------------------------------------------------------------------

def _hierarchy_pos(G: nx.DiGraph, root: str) -> Dict[str, tuple]:
    """
    Вычисляет координаты узлов для иерархической раскладки сверху вниз.
    Используется как запасной вариант, если graphviz недоступен.
    """
    levels: Dict[int, List[str]] = {}
    q: deque = deque([(root, 0)])
    seen: set = set()
    while q:
        n, d = q.popleft()
        if n in seen:
            continue
        seen.add(n)
        levels.setdefault(d, []).append(n)
        for c in G.successors(n):
            q.append((c, d + 1))
    pos: Dict[str, tuple] = {}
    for depth, nodes in levels.items():
        width = len(nodes)
        for i, n in enumerate(nodes):
            pos[n] = ((i + 1) / (width + 1), -depth)
    return pos


# ---------------------------------------------------------------------------
# Статичный PNG (matplotlib)
# ---------------------------------------------------------------------------

def draw_matplotlib(G: nx.DiGraph, root: str) -> plt.Figure:
    """
    Рисует PNG-граф через matplotlib + networkx.

    Если graphviz установлен — использует `dot`-раскладку,
    иначе откатывается на ручную иерархическую.
    """
    if G.number_of_nodes() == 0:
        fig = plt.figure(figsize=(6, 3.5))
        plt.axis("off")
        plt.text(0.5, 0.5, "Потомки не найдены", ha="center", va="center")
        return fig

    try:
        import networkx.drawing.nx_pydot as nx_pydot  # type: ignore
        pos = nx_pydot.graphviz_layout(G, prog="dot")
    except Exception:
        pos = _hierarchy_pos(G, root)

    fig = plt.figure(figsize=(max(6, len(G) * 0.45), 6))
    nx.draw(
        G,
        pos,
        with_labels=True,
        labels={n: multiline(n) for n in G.nodes},
        node_color="#ADD8E6",
        node_size=2000,
        font_size=7,
        arrows=True,
    )
    plt.title(f"Академическая родословная – {root}", fontsize=10)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Интерактивный HTML-граф (pyvis)
# ---------------------------------------------------------------------------

# Встраиваемый JS/CSS-код для кнопок сворачивания ветвей.
# Вынесен отдельной константой, чтобы не перегружать функцию.
_BRANCH_TOGGLE_CSS = """
<style>
  #mynetwork .branch-toggle-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  #mynetwork .branch-toggle {
    position: absolute;
    transform: translate(-50%, 0);
    border-radius: 50%;
    border: 1px solid #2d3f5f;
    background: #ffffff;
    color: #2d3f5f;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    pointer-events: auto;
    user-select: none;
    padding: 0;
    min-width: 16px;
    min-height: 16px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
    transition: background-color 0.2s ease, color 0.2s ease;
    z-index: 10;
  }

  #mynetwork .branch-toggle:hover {
    background: #2d3f5f;
    color: #ffffff;
  }
</style>
"""

_BRANCH_TOGGLE_JS = """
<script>
(function() {
  const config = __CONFIG_JSON__;
  const network = window.network;
  if (!network || !network.body || !network.body.data) { return; }
  const container = document.getElementById("mynetwork");
  if (!container) { return; }

  const childrenMap = config.childrenMap || {};
  const rootId = config.root;
  const originalNodes = Array.isArray(config.nodes) ? config.nodes : [];
  const originalEdges = Array.isArray(config.edges) ? config.edges : [];
  const originalNodeSet = new Set(originalNodes);
  const originalEdgeSet = new Set(
    originalEdges.map(function(edge) { return edge.from + "\u2192" + edge.to; })
  );

  const toggleLayer = document.createElement("div");
  toggleLayer.className = "branch-toggle-layer";
  container.appendChild(toggleLayer);

  const toggles = new Map();
  const collapsed = {};
  const descendantCache = {};

  function getDescendants(nodeId) {
    if (descendantCache[nodeId]) { return descendantCache[nodeId]; }
    const result = [];
    const queue = (childrenMap[nodeId] || []).slice();
    const seen = new Set();
    while (queue.length) {
      const current = queue.shift();
      if (seen.has(current)) { continue; }
      seen.add(current);
      result.push(current);
      const children = childrenMap[current];
      if (children && children.length) { queue.push.apply(queue, children); }
    }
    descendantCache[nodeId] = result;
    return result;
  }

  function updateButton(nodeId) {
    const button = toggles.get(nodeId);
    if (!button) { return; }
    button.textContent = collapsed[nodeId] ? "+" : "\u2212";
    const node = network.body.data.nodes.get(nodeId);
    if (node && node.hidden) { button.style.display = "none"; }
    else { button.style.display = "flex"; }
  }

  function setNodesHidden(ids, hidden) {
    if (!ids.length) { return; }
    const updates = [];
    ids.forEach(function(id) {
      if (!originalNodeSet.has(id)) { return; }
      updates.push({ id: id, hidden: hidden });
    });
    if (updates.length) { network.body.data.nodes.update(updates); }
  }

  function setEdgesHidden(idSet, hidden) {
    if (!idSet.size) { return; }
    const updates = [];
    network.body.data.edges.forEach(function(edge) {
      const key = edge.from + "\u2192" + edge.to;
      if (!originalEdgeSet.has(key)) { return; }
      if (idSet.has(edge.from) || idSet.has(edge.to)) {
        updates.push({ id: edge.id, hidden: hidden });
      }
    });
    if (updates.length) { network.body.data.edges.update(updates); }
  }

  function hideBranch(nodeId) {
    if (!childrenMap[nodeId] || !childrenMap[nodeId].length) { return; }
    collapsed[nodeId] = true;
    const descendants = getDescendants(nodeId);
    const idSet = new Set(descendants);
    setNodesHidden(descendants, true);
    setEdgesHidden(idSet, true);
    descendants.forEach(function(id) {
      const button = toggles.get(id);
      if (button) { button.style.display = "none"; }
    });
    updateButton(nodeId);
    window.requestAnimationFrame(updatePositions);
  }

  function showBranch(nodeId) {
    if (!childrenMap[nodeId] || !childrenMap[nodeId].length) { return; }
    collapsed[nodeId] = false;
    const descendants = getDescendants(nodeId);
    const idSet = new Set(descendants);
    setNodesHidden(descendants, false);
    setEdgesHidden(idSet, false);
    updateButton(nodeId);
    descendants.forEach(function(id) { updateButton(id); });
    descendants.forEach(function(id) {
      if (collapsed[id]) {
        hideBranch(id);
        const button = toggles.get(id);
        if (button) { button.style.display = "flex"; }
      }
    });
    if (descendants.length > 8) { network.stabilize(); }
    window.requestAnimationFrame(updatePositions);
  }

  function toggleBranch(nodeId) {
    if (collapsed[nodeId]) { showBranch(nodeId); } else { hideBranch(nodeId); }
  }

  function updatePositions() {
    toggles.forEach(function(button, nodeId) {
      const node = network.body.data.nodes.get(nodeId);
      if (!node || node.hidden) { return; }
      const bounding = network.getBoundingBox(nodeId);
      if (!bounding) { return; }
      const bottomCenterCanvas = {
        x: (bounding.left + bounding.right) / 2,
        y: bounding.bottom,
      };
      const domPos = network.canvasToDOM(bottomCenterCanvas);
      button.style.left = domPos.x + "px";
      button.style.top = domPos.y + "px";
    });
  }

  function initToggles() {
    Object.keys(childrenMap).forEach(function(nodeId) {
      if (toggles.has(nodeId)) { return; }
      const button = document.createElement("button");
      button.className = "branch-toggle";
      button.textContent = "\u2212";
      button.setAttribute("aria-label", "Свернуть ветвь");
      button.style.fontSize = "12px";
      button.style.width = "18px";
      button.style.height = "18px";
      button.addEventListener("click", function(e) {
        e.stopPropagation();
        toggleBranch(nodeId);
      });
      toggleLayer.appendChild(button);
      toggles.set(nodeId, button);
    });
    updatePositions();
  }

  network.on("stabilized", function() {
    initToggles();
    updatePositions();
  });
  network.on("zoom", updatePositions);
  network.on("dragEnd", updatePositions);
  network.on("animationFinished", updatePositions);

  setTimeout(function() { initToggles(); updatePositions(); }, 800);
})();
</script>
"""


def build_pyvis_html(G: nx.DiGraph, root: str) -> str:
    """
    Генерирует самодостаточный HTML-файл с интерактивным pyvis-графом.

    Граф включает:
    - иерархическую раскладку UD (сверху вниз);
    - кнопки «–» / «+» на узлах для сворачивания/разворачивания ветвей;
    - физику hierarchicalRepulsion для красивого автоматического размещения.
    """
    net = Network(height="1000px", width="100%", directed=True, bgcolor="#ffffff")
    net.toggle_physics(True)

    children_map: Dict[str, List[str]] = {}
    nodes_payload: List[str] = []
    for n in G.nodes:
        node_id = str(n)
        nodes_payload.append(node_id)
        successors = [str(child) for child in G.successors(n)]
        if successors:
            children_map[node_id] = successors
        net.add_node(
            node_id,
            label=multiline(n),
            title=str(n),
            shape="box",
            color="#ADD8E6",
        )

    edges_payload: List[Dict[str, str]] = []
    for u, v in G.edges:
        src, dst = str(u), str(v)
        edges_payload.append({"from": src, "to": dst})
        net.add_edge(src, dst, arrows="to")

    vis_opts = {
        "nodes": {"font": {"size": 12}},
        "layout": {"hierarchical": {"direction": "UD", "sortMethod": "directed"}},
        "interaction": {"hover": True},
        "physics": {
            "hierarchicalRepulsion": {
                "nodeDistance": 140,
                "springLength": 160,
                "springConstant": 0.01,
            },
            "solver": "hierarchicalRepulsion",
            "stabilization": {"iterations": 200},
            "minVelocity": 0.1,
        },
    }
    net.set_options(json.dumps(vis_opts))

    try:
        html = net.generate_html()  # type: ignore[attr-defined]
    except Exception:
        tmp = Path("_tmp_pyvis.html")
        net.save_graph(str(tmp))
        html = tmp.read_text(encoding="utf-8")
        try:
            tmp.unlink()
        except Exception:
            pass

    # Собираем конфиг для JS-кода управления ветвями
    config = {
        "root": str(root),
        "childrenMap": children_map,
        "nodes": nodes_payload,
        "edges": edges_payload,
    }
    config_json = json.dumps(config, ensure_ascii=False)
    injection = _BRANCH_TOGGLE_CSS + _BRANCH_TOGGLE_JS.replace(
        "__CONFIG_JSON__", config_json
    )

    # Вставляем injection перед закрывающим </body>
    if "</body>" in html:
        html = html.replace("</body>", injection + "\n</body>", 1)
    else:
        html += injection

    return html
