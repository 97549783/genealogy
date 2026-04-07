"""
utils/tree_renderers.py — вспомогательные функции для альтернативных
визуализаций деревьев (помимо matplotlib и pyvis).

Публичный API:
    build_xmind_html(G, root) -> tuple[str, int]
        Генерирует самодостаточный HTML (ECharts) для st.components.v1.html.

    build_markmap_html(G, root, initial_expand_level) -> tuple[str, int]
        Генерирует самодостаточный HTML (Markmap.js через ESM + JSON-дерево)
        для st.components.v1.html. Без autoloader, без Transformer,
        без streamlit-markmap.
        Двунаправное дерево: дети основателя делятся пополам и расходятся
        влево и вправо через два отдельных SVG-инстанса Markmap.

    build_markmap_markdown(G, root, initial_expand_level) -> str
        Генерирует строку Markdown для экспорта .md-файлов.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

_BRANCH_PALETTE: List[str] = [
    "#ef5350", "#ab47bc", "#5c6bc0", "#29b6f6", "#26a69a",
    "#66bb6a", "#d4e157", "#ffa726", "#ff7043", "#8d6e63",
]

_BRANCH_TEXT: List[str] = [
    "#fff", "#fff", "#fff", "#fff", "#fff",
    "#1a1a1a", "#1a1a1a",
    "#fff", "#fff", "#fff",
]


def _build_tree_data(
    G: nx.DiGraph,
    node: str,
    branch_color: str,
    branch_text_color: str,
    depth: int = 0,
    initial_depth: int = 2,
) -> Dict[str, Any]:
    successors = list(G.successors(node))
    is_leaf = len(successors) == 0

    if is_leaf:
        result: Dict[str, Any] = {
            "name": node,
            "symbol": "circle",
            "symbolSize": 5,
            "itemStyle": {"color": branch_color, "borderColor": branch_color},
            "label": {
                "show": True,
                "color": "#333",
                "fontSize": 11,
                "fontFamily": "'Segoe UI', 'Noto Sans', Arial, sans-serif",
                "backgroundColor": "transparent",
                "padding": 0,
            },
        }
    else:
        result = {
            "name": node,
            "symbol": "roundRect",
            "symbolSize": [max(80, min(len(node) * 7, 200)), 26],
            "itemStyle": {"color": branch_color, "borderColor": branch_color},
            "label": {
                "show": True,
                "color": branch_text_color,
                "fontSize": 11,
                "fontFamily": "'Segoe UI', 'Noto Sans', Arial, sans-serif",
                "fontWeight": "500",
                "overflow": "break",
                "width": max(76, min(len(node) * 7, 196)),
            },
        }
        if depth >= initial_depth:
            result["collapsed"] = True
        result["children"] = [
            _build_tree_data(G, child, branch_color, branch_text_color, depth + 1, initial_depth)
            for child in successors
        ]

    return result


def _echarts_series(
    data: Dict[str, Any],
    orient: str,
    left: str,
    right: str,
    top: str,
    bottom: str,
    line_color: str,
    initial_depth: int,
) -> Dict[str, Any]:
    return {
        "type": "tree",
        "data": [data],
        "orient": orient,
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "symbol": "roundRect",
        "roam": True,
        "initialTreeDepth": initial_depth,
        "lineStyle": {"color": line_color, "width": 1.8, "curveness": 0.45},
        "label": {"show": True, "position": "inside", "verticalAlign": "middle", "align": "center"},
        "leaves": {
            "symbol": "circle",
            "symbolSize": 5,
            "label": {
                "show": True,
                "position": "right" if orient == "LR" else "left",
                "verticalAlign": "middle",
                "align": "left" if orient == "LR" else "right",
                "color": "#444",
                "fontSize": 11,
                "fontFamily": "'Segoe UI', 'Noto Sans', Arial, sans-serif",
                "backgroundColor": "transparent",
            },
        },
        "emphasis": {
            "focus": "descendant",
            "itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(0,0,0,0.25)"},
        },
        "expandAndCollapse": True,
        "animationDuration": 500,
        "animationDurationUpdate": 700,
        "animationEasing": "cubicInOut",
        "animationEasingUpdate": "cubicInOut",
    }


def build_xmind_html(G: nx.DiGraph, root: str) -> Tuple[str, int]:
    """
    Генерирует самодостаточный HTML (ECharts, XMind-стиль) для st.components.v1.html.
    Returns: (html_str, height_px)
    """
    if G.number_of_nodes() == 0:
        return "<p style='color:#888'>&#x1f6ab; Данных нет</p>", 120

    n_nodes = G.number_of_nodes()
    n_children = list(G.successors(root))
    n_top = len(n_children)

    if n_nodes <= 10:
        initial_depth = -1
    elif n_nodes <= 40:
        initial_depth = 3
    elif n_nodes <= 100:
        initial_depth = 2
    else:
        initial_depth = 1

    height_px = max(520, min(n_nodes * 38, 2000))

    left_children = n_children[: n_top // 2]
    right_children = n_children[n_top // 2 :]

    series: List[Dict[str, Any]] = []
    palette_idx = 0

    def make_branch_root(branch_child: str, color: str, text_color: str) -> Dict[str, Any]:
        children = list(G.successors(branch_child))
        is_leaf = len(children) == 0
        node_data = {
            "name": branch_child,
            "symbol": "circle" if is_leaf else "roundRect",
            "symbolSize": 5 if is_leaf else [max(80, min(len(branch_child) * 7, 200)), 26],
            "itemStyle": {"color": color, "borderColor": color},
            "label": {
                "show": True,
                "color": text_color if not is_leaf else "#333",
                "fontSize": 11,
                "fontFamily": "'Segoe UI','Noto Sans',Arial,sans-serif",
                "fontWeight": "500" if not is_leaf else "normal",
                "overflow": "break" if not is_leaf else "none",
                "width": max(76, min(len(branch_child) * 7, 196)) if not is_leaf else None,
                "backgroundColor": "transparent" if is_leaf else color,
            },
        }
        if not is_leaf:
            if 0 >= initial_depth:
                node_data["collapsed"] = True
            node_data["children"] = [
                _build_tree_data(G, c, color, text_color, 1, initial_depth)
                for c in children
            ]
        return node_data

    if left_children:
        left_tree_children = []
        for child in left_children:
            color = _BRANCH_PALETTE[palette_idx % len(_BRANCH_PALETTE)]
            text_color = _BRANCH_TEXT[palette_idx % len(_BRANCH_TEXT)]
            left_tree_children.append(make_branch_root(child, color, text_color))
            palette_idx += 1
        left_root_data: Dict[str, Any] = {
            "name": root,
            "symbol": "roundRect",
            "symbolSize": [max(100, min(len(root) * 8, 220)), 32],
            "itemStyle": {"color": "#37474f", "borderColor": "#37474f"},
            "label": {
                "show": True, "color": "#fff", "fontSize": 13, "fontWeight": "bold",
                "fontFamily": "'Segoe UI','Noto Sans',Arial,sans-serif",
                "overflow": "break", "width": max(96, min(len(root) * 8, 216)),
                "backgroundColor": "#37474f",
            },
            "children": left_tree_children,
        }
        series.append(_echarts_series(
            left_root_data, "RL", left="50%", right="2%", top="2%", bottom="2%",
            line_color="#b0bec5", initial_depth=initial_depth,
        ))

    if right_children:
        right_tree_children = []
        for child in right_children:
            color = _BRANCH_PALETTE[palette_idx % len(_BRANCH_PALETTE)]
            text_color = _BRANCH_TEXT[palette_idx % len(_BRANCH_TEXT)]
            right_tree_children.append(make_branch_root(child, color, text_color))
            palette_idx += 1
        right_root_data: Dict[str, Any] = {
            "name": root,
            "symbol": "roundRect",
            "symbolSize": [max(100, min(len(root) * 8, 220)), 32],
            "itemStyle": {"color": "#37474f", "borderColor": "#37474f"},
            "label": {
                "show": True, "color": "#fff", "fontSize": 13, "fontWeight": "bold",
                "fontFamily": "'Segoe UI','Noto Sans',Arial,sans-serif",
                "overflow": "break", "width": max(96, min(len(root) * 8, 216)),
                "backgroundColor": "#37474f",
            },
            "children": right_tree_children,
        }
        series.append(_echarts_series(
            right_root_data, "LR", left="50%", right="2%", top="2%", bottom="2%",
            line_color="#b0bec5", initial_depth=initial_depth,
        ))

    if not series:
        root_data: Dict[str, Any] = {
            "name": root,
            "symbol": "roundRect",
            "symbolSize": [max(100, min(len(root) * 8, 220)), 32],
            "itemStyle": {"color": "#37474f", "borderColor": "#37474f"},
            "label": {"show": True, "color": "#fff", "fontSize": 13, "fontWeight": "bold", "backgroundColor": "#37474f"},
        }
        series.append(_echarts_series(
            root_data, "LR", left="5%", right="5%", top="5%", bottom="5%",
            line_color="#b0bec5", initial_depth=initial_depth,
        ))

    if len(series) == 1:
        s = series[0]
        orient = s["orient"]
        if orient == "LR":
            s["left"], s["right"] = "12%", "5%"
        else:
            s["left"], s["right"] = "5%", "12%"

    option = {
        "backgroundColor": "#ffffff",
        "tooltip": {
            "trigger": "item", "triggerOn": "mousemove", "formatter": "{b}",
            "backgroundColor": "rgba(30,30,30,0.88)", "borderWidth": 0,
            "textStyle": {"color": "#fff", "fontSize": 12},
            "extraCssText": "border-radius:6px;padding:6px 10px",
        },
        "series": series,
    }
    option_json = json.dumps(option, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  #chart {{ width: 100%; height: {height_px}px; }}
</style>
</head>
<body>
<div id="chart"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script>
(function () {{
  var chart = echarts.init(document.getElementById('chart'), null, {{renderer: 'canvas'}});
  var option = {option_json};
  if (option.series.length >= 2) {{
    option.series[0].left  = '2%';
    option.series[0].right = '50%';
    option.series[1].left  = '50%';
    option.series[1].right = '2%';
  }}
  chart.setOption(option);
  window.addEventListener('resize', function () {{ chart.resize(); }});
}})();
</script>
</body>
</html>"""
    return html, height_px


# ---------------------------------------------------------------------------
# Markmap HTML
#
# markmap-view не имеет встроенной опции direction/bidirectional
# (открытый feature request #235/#265).
#
# Решение: два отдельных SVG-инстанса Markmap рядом:
#   • правый SVG — LR (ветви вправо), корень = первая половина детей
#   • левый SVG — LR тоже, но весь контейнер зеркально отражён
#     scaleX(-1), а текст каждого узла возвращается JS-патчем
#     (чтобы читальный текст не был зеркальным)
#   • в центре — HTML-блок с именем основателя
# ---------------------------------------------------------------------------

_EXPAND_THRESHOLD = 35  # порог суммарного числа узлов уровней 1+2


def _count_levels(G: nx.DiGraph, root: str, levels: int = 2) -> int:
    """
    Считает общее количество узлов на уровнях 1..levels (корень — уровень 0).
    """
    frontier = list(G.successors(root))  # уровень 1
    total = len(frontier)
    for _ in range(levels - 1):
        next_frontier: List[str] = []
        for node in frontier:
            next_frontier.extend(G.successors(node))
        total += len(next_frontier)
        frontier = next_frontier
    return total


def _build_markmap_node(
    G: nx.DiGraph,
    node: str,
    visited: Set[str],
    depth: int,
    max_depth: int,
) -> Dict[str, Any]:
    """
    Рекурсивно строит JSON-узел в формате INode Markmap.js:
    { content: str, children: [...], payload: {fold: 1} }
    """
    if node in visited:
        return {"content": node, "children": []}
    visited.add(node)

    children_nodes = list(G.successors(node))
    children_data = [
        _build_markmap_node(G, c, visited, depth + 1, max_depth)
        for c in children_nodes
    ]

    result: Dict[str, Any] = {
        "content": node,
        "children": children_data,
    }
    # Сворачиваем узлы глубже max_depth (max_depth=0 — всё раскрыто)
    if max_depth > 0 and depth >= max_depth and children_data:
        result["payload"] = {"fold": 1}

    return result


def build_markmap_html(G: nx.DiGraph, root: str, initial_expand_level: int = -1) -> Tuple[str, int]:
    """
    Генерирует самодостаточный HTML (Markmap.js) для st.components.v1.html.

    Двунаправное дерево: дети основателя делятся пополам и расходятся влево
    и вправо через два отдельных SVG-инстанса Markmap рядом.
    markmap-view не имеет встроенной опции direction='bidirectional',
    поэтому двунаправность реализована вручную.

    Правило авто-раскрытия (initial_expand_level < 0):
      - Подсчитываем суммарное число узлов на уровнях 1 и 2.
      - Если > {_EXPAND_THRESHOLD}: по умолчанию развёрнут только уровень 1 (max_depth=1).
      - Если <= {_EXPAND_THRESHOLD}: по умолчанию развёрнуты уровни 1 и 2 (max_depth=2).

    Returns: (html_str, height_px)
    """
    if G.number_of_nodes() == 0:
        return "<p style='color:#888'>Данных нет</p>", 300

    n_nodes = G.number_of_nodes()
    height_px = max(600, min(n_nodes * 32, 2000))

    if initial_expand_level < 0:
        nodes_l1_l2 = _count_levels(G, root, levels=2)
        max_depth = 1 if nodes_l1_l2 > _EXPAND_THRESHOLD else 2
    else:
        max_depth = initial_expand_level

    # -----------------------------------------------------------------------
    # Делим детей основателя пополам
    # -----------------------------------------------------------------------
    all_children: List[str] = list(G.successors(root))
    half = len(all_children) // 2
    left_children  = all_children[:half]   # пойдут влево
    right_children = all_children[half:]   # пойдут вправо

    palette_js = json.dumps(_BRANCH_PALETTE)
    root_json = json.dumps(root)

    def _make_subtree_json(children: List[str], palette_offset: int) -> str:
        """
        Строит INode-дерево с фиктивным корнем (content=''),
        чьи children — переданные ветви. Цвета считаются
        от palette_offset, чтобы левая и правая половины не пересекались
        по цвету.
        """
        child_nodes = []
        for i, child in enumerate(children):
            visited: Set[str] = set()
            node = _build_markmap_node(G, child, visited, depth=1, max_depth=max_depth)
            # цвет ветви (palette_offset + i)
            node["_palette_idx"] = palette_offset + i
            child_nodes.append(node)
        root_node: Dict[str, Any] = {
            "content": "",
            "children": child_nodes,
        }
        return json.dumps(root_node, ensure_ascii=False)

    left_json  = _make_subtree_json(left_children,  palette_offset=0)
    right_json = _make_subtree_json(right_children, palette_offset=half)

    # Если детей мало (только правая половина), левый SVG пустой
    has_left  = bool(left_children)
    has_right = bool(right_children)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0; background: #fff;
    overflow: hidden;
    width: 100%; height: {height_px}px;
  }}
  #mm-wrapper {{
    position: relative;
    display: flex;
    flex-direction: row;
    width: 100%;
    height: {height_px}px;
  }}
  /* Левый SVG: зеркально отображаем весь контейнер */
  #mm-left-wrap {{
    transform: scaleX(-1);
    transform-origin: center center;
  }}
  .mm-side {{
    flex: 1;
    min-width: 0;
    position: relative;
    overflow: hidden;
  }}
  .mm-side svg {{
    width: 100%;
    height: {height_px}px;
    display: block;
  }}
  /* Основатель: поверх всех SVG, выровнен по центру */
  #mm-root-label {{
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    background: #37474f;
    color: #fff;
    font: bold 13px \'Segoe UI\',\'Noto Sans\',Arial,sans-serif;
    padding: 6px 14px;
    border-radius: 6px;
    white-space: nowrap;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    z-index: 10;
    pointer-events: none;
    box-shadow: 0 2px 8px rgba(0,0,0,0.18);
  }}
</style>
</head>
<body>
<div id="mm-wrapper">
  <div class="mm-side" id="mm-left-side">
    <div id="mm-left-wrap"><svg id="mm-svg-left"></svg></div>
  </div>
  <div class="mm-side" id="mm-right-side">
    <svg id="mm-svg-right"></svg>
  </div>
  <div id="mm-root-label">{{}}</div>
</div>
<script type="module">
import {{ Markmap }} from 'https://esm.sh/markmap-view@0.18';

const palette  = {palette_js};
const rootName = {root_json};

// заполняем заголовок
document.getElementById('mm-root-label').textContent = rootName;

const hasLeft  = {json.dumps(has_left)};
const hasRight = {json.dumps(has_right)};

// Если одна сторона пустая — растягиваем другую
if (!hasLeft)  document.getElementById('mm-left-side').style.display  = 'none';
if (!hasRight) document.getElementById('mm-right-side').style.display = 'none';

// ---------- помощник: назначаем цвета по palette_idx ----------
function assignColors(node, paletteIdx) {{
  node.state = node.state || {{}};
  if (paletteIdx !== undefined) {{
    node.state.color = palette[paletteIdx % palette.length];
  }}
  if (node.children) {{
    node.children.forEach(child => {{
      assignColors(child, node._palette_idx !== undefined ? node._palette_idx : paletteIdx);
    }});
  }}
}}

function colorTree(rootNode) {{
  if (rootNode.children) {{
    rootNode.children.forEach((child, i) => {{
      const idx = child._palette_idx !== undefined ? child._palette_idx : i;
      assignColors(child, idx);
    }});
  }}
}}

// ---------- общие опции Markmap ----------
const MM_OPTS = {{
  autoFit: true,
  pan:     true,
  zoom:    true,
  duration: 400,
  maxWidth: 280,
  nodeMinHeight: 16,
  spacingVertical:   5,
  spacingHorizontal: 80,
  fitRatio: 0.92,
  color: (node) => (node.state && node.state.color) || palette[0],
}};

// ---------- Правое дерево ----------
if (hasRight) {{
  const rightData = {right_json};
  colorTree(rightData);
  const svgR = document.getElementById('mm-svg-right');
  const mmR  = Markmap.create(svgR, MM_OPTS, rightData);
  requestAnimationFrame(() => mmR.fit());
  setTimeout(() => mmR.fit(), 300);
  setTimeout(() => mmR.fit(), 800);
}}

// ---------- Левое дерево (макет) ----------
// markmap-view не имеет direction='bidirectional'.
// Мы рендерим LR-дерево в #mm-left-wrap, который CSS·scaleX(-1)
// зеркалит весь контейнер. Результат: ветви растут влево.
// Текст после рендера возвращается отдельным проходом через SVG-элементы.
if (hasLeft) {{
  const leftData = {left_json};
  colorTree(leftData);
  const svgL = document.getElementById('mm-svg-left');
  const mmL  = Markmap.create(svgL, MM_OPTS, leftData);

  // После рендера: проходимся по всем узлам SVG и
  // применяем scaleX(-1) непосредственно к transform-атрибуту
  // текстовых групп, чтобы текст снова стал читаемым.
  function mirrorTextNodes(svgEl) {{
    const nodes = svgEl.querySelectorAll('g.markmap-node');
    nodes.forEach(g => {{
      // Текстовые элементы внутри узла
      g.querySelectorAll('foreignObject, text').forEach(el => {{
        const cur = el.getAttribute('transform') || '';
        if (!cur.includes('scaleX(-1)')) {{
          el.setAttribute('transform', cur + ' scaleX(-1)');
        }}
      }});
    }});
  }}

  function fitAndMirror() {{
    mmL.fit();
    setTimeout(() => mirrorTextNodes(svgL), 50);
  }}

  requestAnimationFrame(fitAndMirror);
  setTimeout(fitAndMirror, 350);
  setTimeout(fitAndMirror, 900);

  // Переприменяем зеркалирование текста при развертывании/сворачивании узлов
  svgL.addEventListener('click', () => {{
    setTimeout(() => mirrorTextNodes(svgL), 600);
  }});
}}

window.addEventListener('resize', () => {{
  document.querySelectorAll('svg').forEach(s => {{
    const mm = s._mm;
    if (mm) mm.fit();
  }});
}});
</script>
</body>
</html>"""

    return html, height_px


# ---------------------------------------------------------------------------
# Markmap Markdown — генерация .md строки (для экспорта файлов)
# Для рендера в Streamlit используйте build_markmap_html.
# ---------------------------------------------------------------------------


def build_markmap_markdown(G: nx.DiGraph, root: str, initial_expand_level: int = 2) -> str:
    """
    Генерирует строку Markdown для экспорта .md-файлов.
    Для рендера в Streamlit используйте build_markmap_html.
    """
    if G.number_of_nodes() == 0:
        return f"# {root}"

    lines: List[str] = []
    visited: Set[str] = set()

    def _walk(node: str, depth: int) -> None:
        if node in visited:
            return
        visited.add(node)
        lines.append("#" * max(1, depth) + " " + node)
        for child in G.successors(node):
            _walk(child, depth + 1)

    _walk(root, 1)
    return "\n".join(lines)
