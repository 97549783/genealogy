"""
utils/tree_renderers.py — вспомогательные функции для альтернативных
визуализаций деревьев (помимо matplotlib и pyvis).

Публичный API:
    build_xmind_html(G, root) -> tuple[str, int]
        Генерирует самодостаточный HTML-строку + рекомендуемую
        высоту холста в пикселях для st.components.v1.html.

        Дизайн:
        • Корень в центре, ветви расходятся влево и вправо (RL + LR).
        • Каждая ветвь 1-го уровня своего цвета (палитра 10 цветов XMind).
        • Цвет ветви наследуется потомками до листьев.
        • Скруглённые заливные коннекторы, пилл-бейджи узлов.
        • Листья — чистый текст без фона.
        • Плавная анимация при клике, pan + zoom мышью.
        • Адаптивная высота холста и глубина по умолчанию.

    build_markmap_markdown(G, root, initial_expand_level) -> str
        Генерирует строку Markdown для streamlit-markmap (Markmap.js).
        Mind-карта в стиле XMind: корень в центре, цветные ветви,
        автоматический layout, защита от циклов.
        Повторно используется в любых вкладках.

Функции этого модуля могут повторно использоваться в любых других
вкладках, где нужна XMind-визуализация дерева.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

# ---------------------------------------------------------------------------
# Палитра XMind — 10 цветов, назначаются ветвям 1-го уровня циклически.
# Цвет передаётся всем потомкам ветви без изменений.
# ---------------------------------------------------------------------------
_BRANCH_PALETTE: List[str] = [
    "#ef5350",  # красный
    "#ab47bc",  # фиолетовый
    "#5c6bc0",  # тёмно-синий
    "#29b6f6",  # голубой
    "#26a69a",  # бирюзовый
    "#66bb6a",  # зелёный
    "#d4e157",  # жёлто-зелёный
    "#ffa726",  # оранжевый
    "#ff7043",  # глубокий оранжевый
    "#8d6e63",  # коричневый
]

# Цвет текста на пилле узла
_BRANCH_TEXT: List[str] = [
    "#fff", "#fff", "#fff", "#fff", "#fff",
    "#1a1a1a",  # жёлто-зелёный — тёмный текст
    "#1a1a1a",  # жёлтый — тёмный текст
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
    """
    Рекурсивно строит словарь узла для ECharts `tree` series.

    Для листьев (depth > 0 и нет потомков) — простой текст (нет фона).
    Для внутренних узлов — пилл с фоном цвета ветви.
    """
    successors = list(G.successors(node))
    is_leaf = len(successors) == 0

    if is_leaf:
        # Лист: чистый текст, цвет как у ветви, но без заливки
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
        # Внутренний узел: пилл с цветом ветви
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
        # collapsed=True если глубже initial_depth
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
    """Возвращает один ECharts tree-series."""
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
        "lineStyle": {
            "color": line_color,
            "width": 1.8,
            "curveness": 0.45,
        },
        "label": {
            "show": True,
            "position": "inside",
            "verticalAlign": "middle",
            "align": "center",
        },
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
    Генерирует самодостаточный HTML для передачи в st.components.v1.html.

    Дизайн в стиле XMind:
    - Корень в центре (реализовано через две series: RL влево + LR вправо)
    - Каждая ветвь 1-го уровня — своего цвета
    - Цвет передаётся потомкам до листьев
    - Листья — чистый текст без фона
    - Скруглённые пилл-узлы для внутренних узлов
    - Pan + zoom; клик — свернуть/развернуть ветвь
    - Адаптивная высота холста

    Returns:
        (html_str, height_px)
    """
    if G.number_of_nodes() == 0:
        return "<p style='color:#888'>&#x1f6ab; Данных нет</p>", 120

    n_nodes = G.number_of_nodes()
    n_children = list(G.successors(root))
    n_top = len(n_children)

    # Автовыбор глубины по умолчанию
    if n_nodes <= 10:
        initial_depth = -1  # всё раскрыто
    elif n_nodes <= 40:
        initial_depth = 3
    elif n_nodes <= 100:
        initial_depth = 2
    else:
        initial_depth = 1

    # Адаптивная высота: 38 px на узел, min 520, max 2000
    height_px = max(520, min(n_nodes * 38, 2000))

    # --- Разбиваем детей корня: половина влево (RL), половина вправо (LR) ---
    left_children = n_children[: n_top // 2]
    right_children = n_children[n_top // 2 :]

    series: List[Dict[str, Any]] = []
    palette_idx = 0

    def make_branch_root(
        branch_child: str,
        color: str,
        text_color: str,
    ) -> Dict[str, Any]:
        """"""
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

    # Дети влево — серия RL
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
                "show": True,
                "color": "#fff",
                "fontSize": 13,
                "fontWeight": "bold",
                "fontFamily": "'Segoe UI','Noto Sans',Arial,sans-serif",
                "overflow": "break",
                "width": max(96, min(len(root) * 8, 216)),
                "backgroundColor": "#37474f",
            },
            "children": left_tree_children,
        }
        series.append(_echarts_series(
            left_root_data, "RL",
            left="50%", right="2%", top="2%", bottom="2%",
            line_color="#b0bec5",
            initial_depth=initial_depth,
        ))

    # Дети вправо — серия LR
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
                "show": True,
                "color": "#fff",
                "fontSize": 13,
                "fontWeight": "bold",
                "fontFamily": "'Segoe UI','Noto Sans',Arial,sans-serif",
                "overflow": "break",
                "width": max(96, min(len(root) * 8, 216)),
                "backgroundColor": "#37474f",
            },
            "children": right_tree_children,
        }
        series.append(_echarts_series(
            right_root_data, "LR",
            left="50%", right="2%", top="2%", bottom="2%",
            line_color="#b0bec5",
            initial_depth=initial_depth,
        ))

    # Если детей нет вообще — одна series LR
    if not series:
        root_data: Dict[str, Any] = {
            "name": root,
            "symbol": "roundRect",
            "symbolSize": [max(100, min(len(root) * 8, 220)), 32],
            "itemStyle": {"color": "#37474f", "borderColor": "#37474f"},
            "label": {
                "show": True, "color": "#fff",
                "fontSize": 13, "fontWeight": "bold",
                "backgroundColor": "#37474f",
            },
        }
        series.append(_echarts_series(
            root_data, "LR",
            left="5%", right="5%", top="5%", bottom="5%",
            line_color="#b0bec5",
            initial_depth=initial_depth,
        ))

    # Если только одна сторона — расширяем на весь холст
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
            "trigger": "item",
            "triggerOn": "mousemove",
            "formatter": "{b}",
            "backgroundColor": "rgba(30,30,30,0.88)",
            "borderWidth": 0,
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

  // Привязываем левую series к правой половине canvas
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
# Markmap — генерация Markdown для streamlit-markmap (Markmap.js)
# ---------------------------------------------------------------------------

def build_markmap_markdown(G: nx.DiGraph, root: str, initial_expand_level: int = 2) -> str:
    """
    Генерирует строку Markdown для передачи в streamlit-markmap.

    Уровни вложенности отображаются как заголовки Markdown::

      ---
      markmap:
        initialExpandLevel: <initial_expand_level>
        autoFit: true
        pan: true
        scrollForPan: false
        zoom: true
      ---
      # root
      ## branch1
      ### branch1_child1
      ...

    Опции в front matter:
        autoFit:      true  — карта автоматически центрируется по содержимому
        pan:          true  — перетаскивание (drag-to-pan)
        scrollForPan: false — отключает scroll-to-pan, чтобы не конфликтовать
                              с прокруткой страницы Streamlit внутри iframe
        zoom:         true  — масштабирование колёсиком мыши

    Markmap.js отрисовывает это как mind-карту в стиле XMind:
    - Корень в центре, ветви расходятся в стороны
    - Цветные линии ветвей (автоматически по HSL, как в XMind)
    - Узлы сворачиваются/разворачиваются по клику
    - Pan + zoom колёсиком мыши

    Функция намеренно вынесена в utils, чтобы повторно использоваться
    в любых других вкладках, где нужна XMind-визуализация дерева.

    Args:
        G:                    Ориентированный граф NetworkX (дерево)
        root:                 Имя корневого узла
        initial_expand_level: Глубина раскрытия по умолчанию
                              (1 = только корень, 2 = до внуков, -1 = авто).
                              При -1 глубина определяется по размеру графа.

    Returns:
        Строка Markdown с YAML front matter и заголовками (#, ##, ### ...)
    """
    if G.number_of_nodes() == 0:
        return f"# {root}"

    # Адаптивный initial_expand_level при авто-режиме
    n_nodes = G.number_of_nodes()
    if initial_expand_level < 0:
        if n_nodes <= 15:
            initial_expand_level = -1  # markmap: всё раскрыто
        elif n_nodes <= 50:
            initial_expand_level = 3
        else:
            initial_expand_level = 2

    front_matter = (
        "---\n"
        "markmap:\n"
        f"  initialExpandLevel: {initial_expand_level}\n"
        "  autoFit: true\n"
        "  pan: true\n"
        "  scrollForPan: false\n"
        "  zoom: true\n"
        "---"
    )

    lines: List[str] = [front_matter]
    visited: Set[str] = set()  # защита от циклов в графе

    def _walk(node: str, depth: int) -> None:
        if node in visited:
            return
        visited.add(node)
        prefix = "#" * max(1, depth)
        lines.append(f"{prefix} {node}")
        for child in G.successors(node):
            _walk(child, depth + 1)

    _walk(root, 1)
    return "\n".join(lines)
