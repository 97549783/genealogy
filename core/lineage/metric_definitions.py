from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MetricScope = Literal["chapter", "extended", "technical"]
MetricSourceStatus = Literal["verified", "source_required", "standard", "derived"]


@dataclass(frozen=True)
class MetricSource:
    """Описание источника метрики."""

    short_citation: str
    full_citation: str | None
    doi_or_url: str | None
    status: MetricSourceStatus
    note: str = ""


@dataclass(frozen=True)
class MetricDefinition:
    """Описание метрики для справки, таблиц и документации."""

    key: str
    title: str
    aliases: tuple[str, ...]
    group: str
    scope: MetricScope
    short_description: str
    formula_markdown: str
    interpretation: str
    caveats: tuple[str, ...]
    sources: tuple[MetricSource, ...]


RUSSELL = MetricSource("Russell et al. [223]", None, None, "source_required", "Нужно уточнить полную библиографическую запись.")
ROSSI = MetricSource("Rossi et al. [219]", None, None, "source_required", "Нужно уточнить полную библиографическую запись.")
DAMACENO = MetricSource("Damaceno et al. [96]", None, None, "source_required", "Нужно уточнить полную библиографическую запись.")
DORES = MetricSource("Dores et al. [107]", None, None, "source_required", "Нужно уточнить полную библиографическую запись.")
LINARD = MetricSource("Linard et al. [176]", None, None, "source_required", "Нужно уточнить полную библиографическую запись.")
STANDARD = MetricSource("Стандартная графовая формализация", None, None, "standard")
DERIVED = MetricSource("Прикладная производная метрика", None, None, "derived")

_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("direct_students", "Прямые ученики", ("A-score", "плодовитость", "fecundity"), "Руководитель", "chapter", "Число непосредственных учеников корня.", "$A(r)=|Ch(r)|$", "Больше значение означает более широкий первый уровень школы.", ("A-score и плодовитость считаются одной и той же величиной.",), (RUSSELL, ROSSI)),
    MetricDefinition("continuing_students", "Ученики-продолжатели", ("C-score", "фертильность", "fertility"), "Руководитель", "chapter", "Число прямых учеников, у которых есть собственные ученики.", "$C(r)=|\\{u\\in Ch(r): |Ch(u)|>0\\}|$", "Показывает воспроизводство научного руководства.", ("C-score и фертильность считаются одной и той же величиной.",), (RUSSELL, ROSSI)),
    MetricDefinition("continuing_rate_percent", "Доля продолжателей", ("C-score / A-score",), "Руководитель", "chapter", "Доля прямых учеников, ставших руководителями.", "$C(r)/A(r)\\cdot100\\%$", "Позволяет сравнивать школы разного размера.", ("Не рассчитывается, если прямых учеников нет.",), (RUSSELL, ROSSI)),
    MetricDefinition("descendants", "Все потомки", ("descendants",), "Плодовитость", "chapter", "Все уникальные достижимые потомки во всех поколениях.", "$|Desc(r)|$", "Отражает общий размер видимой линии руководства.", ("Вершины с несколькими руководителями учитываются один раз.",), (ROSSI, STANDARD)),
    MetricDefinition("descendant_generations", "Поколений потомков", ("number of generations",), "Топология", "chapter", "Максимальное кратчайшее расстояние от корня до потомка.", "$D(r)=\\max g(v)$", "Показывает глубину преемственности без включения корня как поколения потомков.", ("Недоступно при цикле.",), (DAMACENO, DORES, STANDARD)),
    MetricDefinition("levels_including_root", "Уровней с корнем", ("depth",), "Топология", "chapter", "Число уровней с корнем как уровнем 0.", "$D(r)+1$", "Удобно для чтения структуры дерева.", ("Недоступно при цикле.",), (DAMACENO, DORES, STANDARD)),
    MetricDefinition("max_width", "Максимальная ширина", ("width", "number of cousins"), "Топология", "chapter", "Максимальное число вершин в одном поколении потомков.", "$\\max_{k\\ge1} W_k$", "Показывает самое широкое поколение.", ("При равенстве выбирается самое раннее поколение.",), (DAMACENO, DORES, STANDARD)),
    MetricDefinition("g_score", "G-score", ("обобщённый индекс",), "Руководитель", "chapter", "Обобщённый индекс из главы.", "Формула уточняется по первоисточнику.", "Пока не интерпретируется численно.", ("Без верифицированной формулы значение не рассчитывается.",), (RUSSELL,)),
    MetricDefinition("academic_proliferation", "Академическая пролиферация", ("academic proliferation",), "Динамика", "chapter", "Рост числа потомков по годам защиты.", "$P(t)=\\sum_{\\tau\\le t} n_\\tau$", "Показывает накопление потомков во времени.", ("Среднее за год является прикладной операционализацией, а не проверенной формулой Linard et al.",), (LINARD, STANDARD)),
)
_EXTENDED_KEYS = {
    "terminal_descendants": ("Терминальные потомки", "Состав"), "terminal_share_percent": ("Доля терминальных потомков", "Состав"),
    "internal_descendants": ("Внутренние потомки", "Состав"), "internal_share_percent": ("Доля внутренних потомков", "Состав"),
    "mean_branching_factor": ("Среднее ветвление", "Ветвление"), "median_branching_factor": ("Медианное ветвление", "Ветвление"),
    "max_local_branching": ("Максимальное локальное ветвление", "Ветвление"), "max_local_branching_nodes": ("Узлы максимального ветвления", "Ветвление"),
    "mean_descendant_generation": ("Среднее поколение потомков", "Форма дерева"), "normalized_depth": ("Глубина относительно размера", "Форма дерева"),
    "branch_balance": ("Баланс ветвей первого уровня", "Форма дерева"), "largest_branch_share_percent": ("Доля крупнейшей ветви", "Форма дерева"),
    "structural_h_index": ("Структурный h-индекс линии", "Форма дерева"), "linearity_index_percent": ("Индекс линейности", "Форма дерева"),
    "activity_span_years": ("Период активности", "Динамика"), "peak_growth_year": ("Год пикового роста", "Динамика"),
    "peak_growth_count": ("Пиковое число новых потомков", "Динамика"), "max_inactive_gap_years": ("Максимальный неактивный разрыв", "Динамика"),
    "recent_activity_5_years": ("Недавняя активность за 5 лет", "Динамика"),
    "doctor_descendants": ("Потомки-доктора", "Состав"), "candidate_descendants": ("Потомки-кандидаты", "Состав"), "unknown_degree_descendants": ("Потомки с неизвестной степенью", "Состав"),
    "doctor_share_percent": ("Доля докторов", "Состав"), "candidate_share_percent": ("Доля кандидатов", "Состав"), "unknown_degree_share_percent": ("Доля неизвестных степеней", "Состав"),
}
_TECH_KEYS = {"multi_parent_nodes": "Вершины с несколькими руководителями", "multi_parent_share_percent": "Доля вершин с несколькими руководителями", "edge_surplus": "Избыток рёбер относительно дерева", "undated_descendants": "Потомки без валидного года", "undated_share_percent": "Доля потомков без валидного года"}

for key, (title, group) in _EXTENDED_KEYS.items():
    _DEFINITIONS += (MetricDefinition(key, title, (), group, "extended", "Дополнительная метрика для интерпретации структуры.", "Прикладная формула описана в документации.", "Используется как вспомогательный показатель.", ("Не входит в основной набор метрик главы.",), (DERIVED,)),)
for key, title in _TECH_KEYS.items():
    _DEFINITIONS += (MetricDefinition(key, title, (), "Качество данных", "technical", "Диагностический показатель качества и структуры данных.", "Техническая формула описана в документации.", "Не является научной интерпретационной метрикой.", (), (DERIVED,)),)
_BY_KEY = {d.key: d for d in _DEFINITIONS}


def get_metric_definition(key: str) -> MetricDefinition:
    return _BY_KEY[key]


def get_metric_definitions(*, include_extended: bool = True, include_technical: bool = False) -> tuple[MetricDefinition, ...]:
    return tuple(d for d in _DEFINITIONS if d.scope == "chapter" or (include_extended and d.scope == "extended") or (include_technical and d.scope == "technical"))
