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


RUSSELL_SUGIMOTO_2009 = MetricSource(
    "Russell, Sugimoto 2009",
    (
        "Russell T. G., Sugimoto C. R. MPACT Family Trees: Quantifying Academic "
        "Genealogy in Library and Information Science // Journal of Education for "
        "Library and Information Science. 2009. Vol. 50. No. 4. P. 248-262."
    ),
    None,
    "verified",
)

ROSSI_2017 = MetricSource(
    "Rossi, Freire, Mena-Chalco 2017",
    (
        "Rossi L., Freire I. L., Mena-Chalco J. P. Genealogical Index: A Metric "
        "to Analyze Advisor-Advisee Relationships // Journal of Informetrics. "
        "2017. Vol. 11. No. 2. P. 564-582."
    ),
    "10.1016/j.joi.2017.04.001",
    "verified",
)

ROSSI_2018 = MetricSource(
    "Rossi et al. 2018",
    (
        "Rossi L., Damaceno R. J. P., Freire I. L., Bechara E. J. H., "
        "Mena-Chalco J. P. Topological metrics in academic genealogy graphs // "
        "Journal of Informetrics. 2018. Vol. 12. No. 4. P. 1042-1058."
    ),
    "10.1016/j.joi.2018.08.004",
    "verified",
)

DORES_2016 = MetricSource(
    "Dores, Benevenuto, Laender 2016",
    (
        "Dores W., Benevenuto F., Laender A. H. Extracting academic genealogy "
        "trees from the networked digital library of theses and dissertations // "
        "Proceedings of the 16th ACM/IEEE-CS Joint Conference on Digital Libraries. "
        "2016. P. 163-166."
    ),
    "10.1145/2910896.2910916",
    "verified",
)

LIENARD_2018 = MetricSource(
    "Liénard et al. 2018",
    (
        "Liénard J. F., Achakulvisut T., Acuna D. E., David S. V. Intellectual "
        "synthesis in mentorship determines success in academic careers // "
        "Nature Communications. 2018. Vol. 9. Article 4840."
    ),
    "10.1038/s41467-018-07034-y",
    "verified",
)

STANDARD = MetricSource("Стандартная графовая формализация", None, None, "standard")
DERIVED = MetricSource("Прикладная производная метрика", None, None, "derived")

_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("direct_students", "Прямые ученики", ("A-score", "плодовитость", "fecundity", "direct fertility", "out-degree"), "Руководитель", "chapter", "Число непосредственных учеников выбранного руководителя.", "$A(r)=|Ch(r)|$", "Показывает ширину первого уровня научного руководства.", ("A-score показывает число случаев научного руководства.", "Fecundity показывает число непосредственных академических потомков.", "Out-degree показывает число исходящих связей от вершины руководителя."), (RUSSELL_SUGIMOTO_2009, ROSSI_2017, ROSSI_2018, DORES_2016, STANDARD)),
    MetricDefinition("continuing_students", "Ученики-продолжатели", ("фертильность", "fertility", "1-fertility"), "Руководитель", "chapter", "Число прямых учеников, у которых есть собственные ученики.", "$FT^+(r)=\\{u\\in V:(r,u)\\in E\\ \\text{and}\\ f^+(u)>0\\},\\quad ft^+(r)=|FT^+(r)|$", "Показывает воспроизводство научного руководства среди прямых учеников.", ("Fertility показывает число учеников, которые сами стали руководителями.", "1-fertility учитывает прямых учеников с как минимум одним собственным учеником."), (ROSSI_2017, ROSSI_2018)),
    MetricDefinition("continuing_rate_percent", "Доля продолжателей", ("fertility / fecundity",), "Руководитель", "chapter", "Доля прямых учеников, ставших научными руководителями.", "$\\frac{ft^+(r)}{f^+(r)}\\cdot100\\%$", "Позволяет сравнивать воспроизводство научного руководства у школ разного размера.", ("Показатель нормирует fertility на число прямых учеников.", "Если прямых учеников нет, значение не выводится."), (ROSSI_2018, DERIVED)),
    MetricDefinition("descendants", "Все потомки", ("T-score", "descendants"), "Потомки", "chapter", "Все уникальные достижимые потомки выбранного руководителя во всех поколениях.", "$Desc(r)=\\{v\\in V:r\\leadsto v,\\ v\\ne r\\},\\quad |Desc(r)|$", "Отражает общий размер видимой линии научного руководства.", ("T-score показывает общее число потомков в академическом дереве.", "Descendants включают прямых и непрямых академических потомков.", "Вершины с несколькими руководителями учитываются один раз."), (RUSSELL_SUGIMOTO_2009, ROSSI_2018, STANDARD)),
    MetricDefinition("descendant_generations", "Поколений потомков", ("G-score", "generations", "depth"), "Топология", "chapter", "Максимальное расстояние от корня до потомка.", "$G(r)=\\max_{v\\in Desc(r)} g(v)$", "Показывает глубину линии преемственности.", ("G-score показывает число поколений академических потомков.", "Generations показывает длину крупнейшей цепочки потомков.", "При нескольких путях поколение определяется по кратчайшему пути от корня."), (RUSSELL_SUGIMOTO_2009, ROSSI_2018, DORES_2016, STANDARD)),
    MetricDefinition("levels_including_root", "Уровней с корнем", ("уровни дерева",), "Топология", "chapter", "Число уровней в отображаемом графе с включением корня как уровня 0.", "$L(r)=G(r)+1$", "Помогает читать глубину дерева в интерфейсе.", ("Корень считается уровнем 0.", "Значение на единицу больше числа поколений потомков."), (DERIVED, STANDARD)),
    MetricDefinition("max_width", "Максимальная ширина", ("W-score", "width score", "ширина поколения"), "Топология", "chapter", "Максимальное число потомков в одном поколении.", "$W(r)=\\max_{k\\ge1}|\\{v\\in Desc(r):g(v)=k\\}|$", "Показывает самое широкое поколение научной школы.", ("W-score измеряет размер крупнейшего поколения потомков.", "При равенстве выбирается самое раннее поколение."), (RUSSELL_SUGIMOTO_2009, STANDARD)),
    MetricDefinition("genealogical_index", "Генеалогический индекс", ("genealogical index", "g-index"), "Руководитель", "chapter", "Индекс, оценивающий наличие разветвлённой структуры потомков на нескольких уровнях.", "$g^{(d)}(v)=\\max\\{k\\in\\mathbb N:l(v)\\ge k\\ \\text{and}\\ |A^{(k)}_{(d)}(v)|\\ge k\\}$", "Характеризует устойчивость воспроизводства научного руководства в нескольких поколениях.", ("Численный расчёт требует отдельной реализации формулы genealogical index.", "В текущей версии значение не выводится."), (ROSSI_2017,)),
    MetricDefinition("academic_proliferation", "Академическая пролиферация", ("academic proliferation", "proliferation rate"), "Динамика", "chapter", "Рост числа академических потомков во времени.", "$P(t)=\\sum_{\\tau\\le t} n_\\tau$", "Показывает, как линия научного руководства разрасталась по годам защит.", ("Proliferation rate у Liénard et al. измеряется как среднее число подготовленных исследователей за десятилетие.", "В приложении используется годовая динамика по наблюдаемым годам защит."), (LIENARD_2018, DERIVED)),
)

_EXTENDED_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("terminal_descendants", "Терминальные потомки", (), "Состав", "extended", "Число потомков без собственных учеников в текущем графе.", "$|\\{v\\in Desc(r):outdegree(v)=0\\}|$", "Показывает, сколько ветвей пока не имеют продолжения в базе.", (), (DERIVED, STANDARD)),
    MetricDefinition("terminal_share_percent", "Доля терминальных потомков", (), "Состав", "extended", "Доля потомков без собственных учеников.", "$\\frac{|\\{v\\in Desc(r):outdegree(v)=0\\}|}{|Desc(r)|}\\cdot100\\%$", "Помогает оценить, насколько дерево насыщено конечными ветвями.", (), (DERIVED, STANDARD)),
    MetricDefinition("internal_descendants", "Внутренние потомки", (), "Состав", "extended", "Число потомков, которые сами имеют учеников.", "$|\\{v\\in Desc(r):outdegree(v)>0\\}|$", "Показывает число активных продолжателей внутри всей линии.", (), (DERIVED, STANDARD)),
    MetricDefinition("internal_share_percent", "Доля внутренних потомков", (), "Состав", "extended", "Доля потомков, которые имеют собственных учеников.", "$\\frac{|\\{v\\in Desc(r):outdegree(v)>0\\}|}{|Desc(r)|}\\cdot100\\%$", "Помогает оценить воспроизводимость научного руководства во всей линии.", (), (DERIVED, STANDARD)),
    MetricDefinition("mean_branching_factor", "Среднее ветвление", (), "Ветвление", "extended", "Среднее число учеников у вершин, имеющих хотя бы одного ученика.", "$\\frac{\\sum_{v\\in V_r}|Ch(v)|}{|\\{v\\in V_r:|Ch(v)|>0\\}|}$", "Показывает среднюю интенсивность ветвления среди активных руководителей.", (), (DERIVED, STANDARD)),
    MetricDefinition("median_branching_factor", "Медианное ветвление", (), "Ветвление", "extended", "Медиана числа учеников у вершин, имеющих хотя бы одного ученика.", "$median(|Ch(v)|)$", "Более устойчива к одному сверхкрупному руководителю, чем среднее.", (), (DERIVED, STANDARD)),
    MetricDefinition("max_local_branching", "Максимальное локальное ветвление", (), "Ветвление", "extended", "Наибольшее число прямых учеников у одной вершины внутри текущего графа.", "$\\max_{v\\in V_r}|Ch(v)|$", "Помогает найти главные точки разрастания внутри школы.", (), (DERIVED, STANDARD)),
    MetricDefinition("max_local_branching_nodes", "Узлы максимального ветвления", (), "Ветвление", "extended", "Вершины, на которых достигается максимальное локальное ветвление.", "$\\{v\\in V_r:|Ch(v)|=\\max |Ch|\\}$", "Показывает персоналии, через которые идёт наиболее сильное разветвление.", (), (DERIVED, STANDARD)),
    MetricDefinition("mean_descendant_generation", "Среднее поколение потомков", (), "Форма дерева", "extended", "Среднее поколение всех потомков.", "$\\frac{1}{|Desc(r)|}\\sum_{v\\in Desc(r)}g(v)$", "Отличает плоские школы от многоступенчатых линий преемственности.", (), (DERIVED,)),
    MetricDefinition("normalized_depth", "Глубина относительно размера", (), "Форма дерева", "extended", "Нормированная глубина с учётом размера дерева.", "$\\frac{G(r)}{\\log_2(|Desc(r)|+1)}$", "Позволяет сравнивать глубину школ разного размера.", ("Это прикладная нормировка приложения.",), (DERIVED,)),
    MetricDefinition("branch_balance", "Баланс ветвей первого уровня", (), "Форма дерева", "extended", "Нормированная энтропия распределения потомков по ветвям прямых учеников.", "$-\\frac{\\sum_i p_i\\log p_i}{\\log m}$", "Значение ближе к 1 означает более равномерное развитие ветвей.", (), (DERIVED,)),
    MetricDefinition("largest_branch_share_percent", "Доля крупнейшей ветви", (), "Форма дерева", "extended", "Доля потомков, приходящаяся на крупнейшую ветвь первого уровня.", "$\\frac{\\max_i s_i}{\\sum_i s_i}\\cdot100\\%$", "Показывает, насколько дерево зависит от одной линии преемственности.", (), (DERIVED,)),
    MetricDefinition("structural_h_index", "Структурный h-индекс линии", (), "Форма дерева", "extended", "Прикладный h-подобный индекс, рассчитанный по размерам ветвей прямых учеников.", "$h=\\max\\{k:\\text{есть хотя бы }k\\text{ ветвей размера не менее }k\\}$", "Компактно объединяет ширину первого уровня и размер ветвей.", ("Это прикладная метрика приложения.",), (DERIVED,)),
    MetricDefinition("linearity_index_percent", "Индекс линейности", (), "Форма дерева", "extended", "Доля активных вершин, у которых ровно один ученик.", "$\\frac{|\\{v\\in V_r:|Ch(v)|=1\\}|}{|\\{v\\in V_r:|Ch(v)|>0\\}|}\\cdot100\\%$", "Показывает, насколько структура похожа на цепочку, а не на разветвлённое дерево.", (), (DERIVED, STANDARD)),
    MetricDefinition("activity_span_years", "Период активности", (), "Динамика", "extended", "Число лет между первым и последним наблюдаемым годом защиты потомков.", "$t_{max}-t_{min}+1$", "Помогает интерпретировать размер школы с учётом длительности наблюдения.", (), (DERIVED,)),
    MetricDefinition("peak_growth_year", "Год пикового роста", (), "Динамика", "extended", "Год, в который появилось больше всего новых потомков.", "$argmax_t\\ n_t$", "Показывает период максимального разрастания линии.", (), (DERIVED,)),
    MetricDefinition("peak_growth_count", "Пиковое число новых потомков", (), "Динамика", "extended", "Максимальное число новых потомков за один календарный год.", "$\\max_t n_t$", "Дополняет год пикового роста количественным значением.", (), (DERIVED,)),
    MetricDefinition("max_inactive_gap_years", "Максимальный неактивный разрыв", (), "Динамика", "extended", "Максимальное число подряд идущих лет без новых потомков между первым и последним наблюдаемым годом.", "$\\max\\ \\text{длины интервала, где } n_t=0$", "Показывает прерывистость воспроизводства школы.", (), (DERIVED,)),
    MetricDefinition("recent_activity_5_years", "Недавняя активность за 5 лет", (), "Динамика", "extended", "Число потомков за последние пять лет относительно последнего наблюдаемого года в данных.", "$|\\{v:y(v)\\ge t_{max}-4\\}|$", "Показывает активность в последнем наблюдаемом окне базы.", (), (DERIVED,)),
    MetricDefinition("doctor_descendants", "Потомки-доктора", (), "Состав", "extended", "Число потомков с докторской степенью.", "$|\\{v\\in Desc(r):degree(v)=doctor\\}|$", "Показывает состав линии по уровню степени.", (), (DERIVED,)),
    MetricDefinition("candidate_descendants", "Потомки-кандидаты", (), "Состав", "extended", "Число потомков с кандидатской степенью.", "$|\\{v\\in Desc(r):degree(v)=candidate\\}|$", "Показывает состав линии по уровню степени.", (), (DERIVED,)),
    MetricDefinition("unknown_degree_descendants", "Потомки с неизвестной степенью", (), "Состав", "extended", "Число потомков, для которых уровень степени не определён.", "$|\\{v\\in Desc(r):degree(v)=unknown\\}|$", "Показывает полноту данных о степени.", (), (DERIVED,)),
    MetricDefinition("doctor_share_percent", "Доля докторов", (), "Состав", "extended", "Доля потомков с докторской степенью.", "$\\frac{doctor}{|Desc(r)|}\\cdot100\\%$", "Показывает долю докторских защит среди потомков.", (), (DERIVED,)),
    MetricDefinition("candidate_share_percent", "Доля кандидатов", (), "Состав", "extended", "Доля потомков с кандидатской степенью.", "$\\frac{candidate}{|Desc(r)|}\\cdot100\\%$", "Показывает долю кандидатских защит среди потомков.", (), (DERIVED,)),
    MetricDefinition("unknown_degree_share_percent", "Доля неизвестных степеней", (), "Состав", "extended", "Доля потомков с неопределённым уровнем степени.", "$\\frac{unknown}{|Desc(r)|}\\cdot100\\%$", "Показывает долю неполных данных о степени.", (), (DERIVED,)),
)

_TECH_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("multi_parent_nodes", "Вершины с несколькими руководителями", (), "Качество данных", "technical", "Число вершин, у которых в текущем графе больше одного входящего ребра.", "$|\\{v\\in V_r:indegree(v)>1\\}|$", "Показывает степень пересечения линий научного руководства.", ("Это диагностический показатель структуры данных.",), (ROSSI_2018, STANDARD)),
    MetricDefinition("multi_parent_share_percent", "Доля вершин с несколькими руководителями", (), "Качество данных", "technical", "Доля потомков с несколькими входящими связями в текущем графе.", "$\\frac{|\\{v\\in Desc(r):indegree(v)>1\\}|}{|Desc(r)|}\\cdot100\\%$", "Помогает оценить степень сетевой структуры внутри отображаемого графа.", ("Это диагностический показатель структуры данных.",), (ROSSI_2018, STANDARD)),
    MetricDefinition("edge_surplus", "Избыток рёбер относительно дерева", (), "Качество данных", "technical", "Разность между числом рёбер текущего графа и числом рёбер строгого дерева того же размера.", "$|E_r|-(|V_r|-1)$", "Значение больше нуля указывает на дополнительные связи научного руководства.", ("Это диагностический показатель структуры данных.",), (ROSSI_2018, STANDARD)),
    MetricDefinition("undated_descendants", "Потомки без валидного года", (), "Качество данных", "technical", "Число потомков без пригодного для временного анализа года защиты.", "$|\\{v\\in Desc(r):y(v)\\ отсутствует\\}|$", "Показывает ограничение временной интерпретации.", ("Это показатель полноты данных.",), (DERIVED,)),
    MetricDefinition("undated_share_percent", "Доля потомков без валидного года", (), "Качество данных", "technical", "Доля потомков без пригодного года защиты.", "$\\frac{undated}{|Desc(r)|}\\cdot100\\%$", "Показывает, насколько надёжна временная динамика.", ("Это показатель полноты данных.",), (DERIVED,)),
)

_DEFINITIONS = _DEFINITIONS + _EXTENDED_DEFINITIONS + _TECH_DEFINITIONS
_BY_KEY = {definition.key: definition for definition in _DEFINITIONS}


def get_metric_definition(key: str) -> MetricDefinition:
    return _BY_KEY[key]


def get_metric_definitions(*, include_extended: bool = True, include_technical: bool = False) -> tuple[MetricDefinition, ...]:
    return tuple(
        definition
        for definition in _DEFINITIONS
        if definition.scope == "chapter"
        or (include_extended and definition.scope == "extended")
        or (include_technical and definition.scope == "technical")
    )
