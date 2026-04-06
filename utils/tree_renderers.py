"""
utils/tree_renderers.py — вспомогательные функции для альтернативных
визуализаций деревьев (помимо matplotlib и pyvis).

Публичный API:
    build_xmind_html(G, root) -> tuple[str, int]
        Генерирует самодостаточный HTML-строку + рекомендуемую
        высоту холста в пикселях для st.components.v1.html.

    build_markmap_html(G, root, initial_expand_level) -> tuple[str, int]
        Генерирует самодостаточный HTML с Markmap.js 0.17.2 (mind-карта
        в стиле XMind). Передаётся в st.components.v1.html — без
        зависимости от streamlit-markmap.

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
# Версия 0.17.2 — последняя стабильная с синхронным API (Markmap.create,
# mm.fit). Версии 0.17.9 и 0.18.x на jsdelivr не дают корректного
# window.markmap с Transformer + Markmap через простые <script> теги.
#
# Скрипты загружаются через 4 последовательных <script defer> —
# браузер выполняет defer-скрипты строго по порядку после парсинга DOM,
# без race condition, без addEventListener('load', ...).
# ---------------------------------------------------------------------------


def build_markmap_html(G: nx.DiGraph, root: str, initial_expand_level: int = -1) -> Tuple[str, int]:
    """
    Генерирует самодостаточный HTML с Markmap.js 0.17.2 (mind-карта в стиле XMind).
    Передаётся в st.components.v1.html — без зависимости от streamlit-markmap.

    Версия 0.17.2 — последняя с синхронным API (Markmap.create, mm.fit).
    Четыре <script defer> гарантируют порядок загрузки без race condition.

    Returns: (html_str, height_px)
    """
    if G.number_of_nodes() == 0:
        return "<p style='color:#888'>Данных нет</p>", 300

    n_nodes = G.number_of_nodes()
    height_px = max(600, min(n_nodes * 32, 2000))

    if initial_expand_level < 0:
        if n_nodes <= 15:
            iel = -1
        elif n_nodes <= 50:
            iel = 3
        else:
            iel = 2
    else:
        iel = initial_expand_level

    md_lines: List[str] = []
    visited: Set[str] = set()

    def _walk(node: str, depth: int) -> None:
        if node in visited:
            return
        visited.add(node)
        md_lines.append("#" * max(1, depth) + " " + node)
        for child in G.successors(node):
            _walk(child, depth + 1)

    _walk(root, 1)

    # Правильное экранирование для JS template literal
    md_escaped = (
        "\n".join(md_lines)
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )

    palette_js = json.dumps(_BRANCH_PALETTE)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0;
    background: #fff;
    overflow: hidden;
    width: 100%; height: {height_px}px;
  }}
  #mindmap {{
    width: 100%;
    height: {height_px}px;
    display: block;
  }}
  #mm-err {{
    display: none;
    position: absolute; top: 8px; left: 8px; right: 8px;
    background: #fee2e2; color: #991b1b;
    padding: 8px 12px; border-radius: 6px;
    font: 13px monospace; white-space: pre-wrap;
    z-index: 9999;
  }}
</style>
</head>
<body>
<svg id="mindmap"></svg>
<div id="mm-err"></div>

<!--
  markmap 0.17.2 — последняя версия с синхронным API и корректным
  window.markmap {{ Transformer, Markmap }}.
  defer гарантирует выполнение скриптов строго по порядку после парсинга DOM.
-->
<script defer src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/markmap-lib@0.17.2/dist/browser/index.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/markmap-view@0.17.2/dist/browser/index.js"></script>
<script defer>
(function () {{
  try {{
    var mm_ns = window.markmap;
    if (!mm_ns || !mm_ns.Transformer || !mm_ns.Markmap) {{
      var errEl = document.getElementById('mm-err');
      errEl.style.display = 'block';
      errEl.textContent =
        'Markmap не загружен. Проверьте интернет-соединение и обновите страницу.\\n' +
        'window.markmap = ' + JSON.stringify(mm_ns ? Object.keys(mm_ns) : null);
      return;
    }}

    var Transformer = mm_ns.Transformer;
    var Markmap     = mm_ns.Markmap;
    var palette     = {palette_js};

    var md          = `{md_escaped}`;
    var transformer = new Transformer();
    var result      = transformer.transform(md);
    var rootNode    = result.root;
    var features    = result.features;

    var assets = transformer.getUsedAssets(features);
    if (assets.styles) mm_ns.loadCSS(assets.styles);

    function renderMap() {{
      var svg = document.getElementById('mindmap');
      var mm  = Markmap.create(svg, {{
        autoFit:            true,
        pan:                true,
        zoom:               true,
        initialExpandLevel: {iel},
        duration:           500,
        maxWidth:           300,
        nodeMinHeight:      20,
        spacingVertical:    8,
        spacingHorizontal:  60,
        fitRatio:           0.92,
        color: function (node) {{
          return palette[(node.state ? node.state.key : 0) % palette.length];
        }},
      }}, rootNode);

      // Двойной fit обходит баг с iframe-размером Streamlit
      setTimeout(function () {{ mm.fit(); }}, 200);
      setTimeout(function () {{ mm.fit(); }}, 700);
      window.addEventListener('resize', function () {{ mm.fit(); }});
    }}

    if (assets.scripts && assets.scripts.length > 0) {{
      mm_ns.loadJS(assets.scripts, {{ getMarkmap: function () {{ return window.markmap; }} }})
        .then(renderMap)
        .catch(function (e) {{
          var errEl = document.getElementById('mm-err');
          errEl.style.display = 'block';
          errEl.textContent = 'Ошибка загрузки assets: ' + e.message;
        }});
    }} else {{
      renderMap();
    }}
  }} catch (e) {{
    var errEl = document.getElementById('mm-err');
    errEl.style.display = 'block';
    errEl.textContent = 'Ошибка Markmap: ' + e.message + '\\n' + e.stack;
  }}
}})();
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
