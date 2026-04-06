"""
utils/tree_renderers.py — вспомогательные функции для альтернативных
визуализаций деревьев (помимо matplotlib и pyvis).

Публичный API:
    build_echarts_tree_option(G, root) -> dict
        Возвращает опции для streamlit_echarts (тип «tree»)
        в стиле XMind: горизонтальная раскладка, цвета по уровням,
        плавное сворачивание ветвей, автоматически масштабируемая высота.

Функции этого модуля могут повторно использоваться в любых других
вкладках, которым нужна ECharts-визуализация иерархического графа.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import networkx as nx

# ---------------------------------------------------------------------------
# Палитра уровней — первый элемент для корня, далее циклически по уровням.
# Цвета подобраны так, чтобы хорошо смотреться и на светлом фоне.
# ---------------------------------------------------------------------------
_LEVEL_COLORS: List[str] = [
    "#4361ee",  # уровень 0 — корень, насыщенный синий
    "#3a86ff",  # уровень 1 — голубой
    "#06d6a0",  # уровень 2 — бирюзово-зелёный
    "#ffb703",  # уровень 3 — золотисто-жёлтый
    "#fb8500",  # уровень 4 — оранжевый
    "#e63946",  # уровень 5+ — красный
]

# Цвет текста на узле: белый на тёмном фоне, тёмный на светлом.
_LEVEL_TEXT_COLORS: List[str] = [
    "#ffffff",  # на синем корне
    "#ffffff",  # на голубом
    "#1a1a2e",  # на бирюзовом
    "#1a1a2e",  # на жёлтом
    "#ffffff",  # на оранжевом
    "#ffffff",  # на красном
]


def _node_to_echarts(
    G: nx.DiGraph,
    node: str,
    depth: int = 0,
    max_depth: int = 99,
) -> Dict[str, Any]:
    """
    Рекурсивно превращает поддерево, начиная с ``node``, в словарь
    для ECharts-серии типа «tree».

    Args:
        G:         Направленный граф научных родословных.
        node:      Текущий узел.
        depth:     Глубина от корня (0 = корень).
        max_depth: Ограничение глубины (защита от случайных циклов).
    """
    color_idx = min(depth, len(_LEVEL_COLORS) - 1)
    color = _LEVEL_COLORS[color_idx]
    text_color = _LEVEL_TEXT_COLORS[color_idx]

    # Узел корня отображается крупнее и жирнее
    is_root = depth == 0
    symbol_size = 14 if is_root else 8
    font_weight = "bold" if is_root else "normal"
    font_size = 13 if is_root else 11

    result: Dict[str, Any] = {
        "name": node,
        "value": node,  # показывается в tooltip
        "symbolSize": symbol_size,
        "itemStyle": {"color": color, "borderColor": color},
        "label": {
            "color": text_color,
            "fontWeight": font_weight,
            "fontSize": font_size,
            "backgroundColor": color,
            "padding": [3, 6, 3, 6],
            "borderRadius": 4,
        },
    }

    if depth < max_depth:
        successors = list(G.successors(node))
        if successors:
            result["children"] = [
                _node_to_echarts(G, child, depth + 1, max_depth)
                for child in successors
            ]

    return result


def build_echarts_tree_option(
    G: nx.DiGraph,
    root: str,
    initial_depth: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Строит словарь опций для ``streamlit_echarts`` (тип «tree»).

    Визуализация в стиле XMind:
    - горизонтальная ориентация (LR, слева направо);
    - цвет узлов варьируется по уровню дерева;
    - узлы с потомками можно сворачивать/разворачивать кликом;
    - плавная CSS-анимация (550 мс);
    - высота холста автоматически масштабируется по числу узлов;
    - по умолчанию раскрываются первые 2 уровня (можно задать
      через ``initial_depth``).

    Args:
        G:             Направленный граф (результат lineage()).
        root:          Имя корневого узла.
        initial_depth: Сколько уровней раскрыто при первом показе.
                       None → 2 для больших деревьев (>15 узлов),
                       иначе раскрывается всё дерево (-1).

    Returns:
        dict с ключами ``option`` и ``height`` для передачи
        в st_echarts / для прямого использования.
        Пустой dict, если граф не содержит узлов.
    """
    if G.number_of_nodes() == 0:
        return {}

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    # --- Автовыбор начальной глубины ---
    if initial_depth is None:
        if n_nodes <= 15:
            initial_depth = -1   # маленькое дерево — раскрыть всё
        elif n_nodes <= 60:
            initial_depth = 3
        else:
            initial_depth = 2    # большое дерево — показать 2 уровня

    # --- Высота холста ---
    # Базовая высота ~28 px на узел, но зажимаем в разумных пределах.
    height_px = max(420, min(n_nodes * 30, 1400))
    # Для очень маленьких деревьев дополнительный запас сверху/снизу
    if n_nodes <= 6:
        height_px = max(height_px, 320)

    # --- Отступы: для широких деревьев даём правому краю больше места ---
    max_label_len = max((len(n) for n in G.nodes), default=10)
    right_margin = f"{min(max(15, max_label_len * 0.6), 35):.0f}%"

    tree_data = _node_to_echarts(G, root)

    option: Dict[str, Any] = {
        "backgroundColor": "#fafafa",
        "tooltip": {
            "trigger": "item",
            "triggerOn": "mousemove",
            "formatter": "{b}",
            "backgroundColor": "rgba(30,30,60,0.85)",
            "borderColor": "#4361ee",
            "textStyle": {"color": "#fff", "fontSize": 12},
        },
        "series": [
            {
                "type": "tree",
                "data": [tree_data],
                "orient": "LR",
                "top": "4%",
                "left": "8%",
                "bottom": "4%",
                "right": right_margin,
                "symbol": "roundRect",
                "symbolSize": 8,
                "roam": True,           # pan + zoom мышью
                "initialTreeDepth": initial_depth,
                "lineStyle": {
                    "color": "#adb5bd",
                    "width": 1.5,
                    "curveness": 0.5,   # скруглённые коннекторы
                },
                "label": {
                    "show": True,
                    "position": "inside",
                    "verticalAlign": "middle",
                    "align": "center",
                    "fontSize": 11,
                    "overflow": "truncate",
                    "width": 140,
                },
                "leaves": {
                    "label": {
                        "show": True,
                        "position": "inside",
                        "verticalAlign": "middle",
                        "align": "center",
                    }
                },
                "emphasis": {
                    "focus": "descendant",
                    "itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(67,97,238,0.4)"},
                },
                "expandAndCollapse": True,
                "animationDuration": 550,
                "animationDurationUpdate": 750,
                "animationEasing": "cubicOut",
                "animationEasingUpdate": "cubicOut",
            }
        ],
    }

    return {"option": option, "height": height_px}
