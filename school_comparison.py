"""
Модуль сравнения научных школ по тематическим профилям.
Основная метрика - коэффициент силуэта (Silhouette Score).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Set, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import silhouette_samples, silhouette_score
from sklearn.metrics.pairwise import euclidean_distances, cosine_distances


# ==============================================================================
# ТИПЫ И КОНСТАНТЫ
# ==============================================================================

DistanceMetric = Literal[
    "euclidean_orthogonal",
    "cosine_orthogonal",
    "euclidean_oblique",
    "cosine_oblique"
]

ComparisonScope = Literal["direct", "all"]

DISTANCE_METRIC_LABELS: Dict[DistanceMetric, str] = {
    "euclidean_orthogonal": "Евклидово (прямоугольный базис)",
    "cosine_orthogonal": "Косинусное (прямоугольный базис)",
    "euclidean_oblique": "Евклидово (косоугольный базис)",
    "cosine_oblique": "Косинусное (косоугольный базис)",
}

SCOPE_LABELS: Dict[ComparisonScope, str] = {
    "direct": "Только прямые диссертанты",
    "all": "Все поколения диссертантов",
}

# Яркая цветовая палитра для графика силуэта
SILHOUETTE_COLORS = [
    "#FF8C42",  # Яркий оранжевый
    "#FFD166",  # Жёлтый
    "#F77F00",  # Тёмно-оранжевый
    "#FCBF49",  # Золотисто-жёлтый
    "#EF476F",  # Коралловый/розовый
    "#06D6A0",  # Бирюзовый
    "#118AB2",  # Синий
    "#073B4C",  # Тёмно-синий
    "#E07A5F",  # Терракотовый
    "#81B29A",  # Шалфейный зелёный
]


# ==============================================================================
# РАБОТА С ИЕРАРХИЕЙ КЛАССИФИКАТОРА
# ==============================================================================

def get_code_depth(code: str) -> int:
    """Возвращает глубину (уровень) кода в иерархии."""
    if not code:
        return 0
    return code.count(".") + 1


def get_parent_code(code: str) -> Optional[str]:
    """Возвращает родительский код или None для корневых."""
    if "." not in code:
        return None
    return code.rsplit(".", 1)[0]


def get_ancestor_codes(code: str) -> List[str]:
    """Возвращает список всех предков кода (от корня к текущему)."""
    ancestors = []
    current = code
    while current:
        ancestors.insert(0, current)
        current = get_parent_code(current)
    return ancestors


def is_descendant_of(code: str, ancestor: str) -> bool:
    """Проверяет, является ли code потомком ancestor."""
    if code == ancestor:
        return True
    return code.startswith(ancestor + ".")


def filter_columns_by_nodes(
    columns: List[str],
    selected_nodes: Optional[List[str]] = None
) -> List[str]:
    """Фильтрует колонки по выбранным узлам."""
    if selected_nodes is None or len(selected_nodes) == 0:
        return columns

    filtered = []
    for col in columns:
        for node in selected_nodes:
            if is_descendant_of(col, node):
                filtered.append(col)
                break

    return filtered


def get_nodes_at_level(columns: List[str], level: int) -> List[str]:
    """Возвращает узлы указанного уровня."""
    return sorted(set(col for col in columns if get_code_depth(col) == level))


def get_selectable_nodes(columns: List[str], max_level: int = 3) -> List[str]:
    """Возвращает узлы уровней 1..max_level для выбора пользователем."""
    result = []
    for level in range(1, max_level + 1):
        result.extend(get_nodes_at_level(columns, level))
    return sorted(result)


# ==============================================================================
# КОСОУГОЛЬНЫЙ БАЗИС
# ==============================================================================

def build_oblique_transform_matrix(
    feature_columns: List[str],
    decay_factor: float = 0.5
) -> np.ndarray:
    """Строит матрицу трансформации для косоугольного базиса."""
    n = len(feature_columns)
    col_to_idx = {col: i for i, col in enumerate(feature_columns)}

    transform = np.eye(n)

    for i, col in enumerate(feature_columns):
        ancestors = get_ancestor_codes(col)
        for depth, ancestor in enumerate(ancestors[:-1]):
            if ancestor in col_to_idx:
                j = col_to_idx[ancestor]
                distance = len(ancestors) - depth - 1
                weight = decay_factor ** distance
                transform[i, j] = weight

    return transform


def apply_oblique_transform(
    data: np.ndarray,
    feature_columns: List[str],
    decay_factor: float = 0.5
) -> np.ndarray:
    """Применяет трансформацию косоугольного базиса к данным."""
    transform = build_oblique_transform_matrix(feature_columns, decay_factor)
    return data @ transform.T


# ==============================================================================
# ВЫЧИСЛЕНИЕ РАССТОЯНИЙ
# ==============================================================================

def compute_distance_matrix(
    data: np.ndarray,
    feature_columns: List[str],
    metric: DistanceMetric,
    decay_factor: float = 0.5
) -> np.ndarray:
    """Вычисляет матрицу расстояний между образцами."""
    if metric in ("euclidean_oblique", "cosine_oblique"):
        data = apply_oblique_transform(data, feature_columns, decay_factor)

    if metric in ("euclidean_orthogonal", "euclidean_oblique"):
        return euclidean_distances(data)
    else:
        return cosine_distances(data)


# ==============================================================================
# ЗАГРУЗКА ДАННЫХ
# ==============================================================================

def load_scores_from_folder(
    folder_path: str = "basic_scores",
    specific_files: Optional[List[str]] = None
) -> pd.DataFrame:
    """Загружает данные тематических профилей из CSV файлов.

    Сначала ищет папку относительно CWD, при неудаче — относительно
    директории данного модуля (актуально для Streamlit Cloud).
    """
    base = Path(folder_path).expanduser()
    if not base.is_absolute():
        resolved = base.resolve()
        if not resolved.exists():
            # fallback: рядом с модулем
            resolved = Path(__file__).parent / folder_path
        base = resolved
    else:
        base = base.resolve()

    if specific_files:
        files = [base / f for f in specific_files if (base / f).exists()]
    else:
        files = sorted(base.glob("*.csv"))

    if not files:
        raise FileNotFoundError(f"CSV файлы не найдены в {base}")

    frames: List[pd.DataFrame] = []
    for file in files:
        try:
            frame = pd.read_csv(file)
            if "Code" not in frame.columns:
                raise KeyError(f"Файл {file.name} не содержит колонку 'Code'")
            frames.append(frame)
        except Exception as e:
            print(f"Ошибка при загрузке {file}: {e}")
            continue

    if not frames:
        raise ValueError("Не удалось загрузить ни один файл")

    scores = pd.concat(frames, ignore_index=True)
    scores = scores.dropna(subset=["Code"])
    scores["Code"] = scores["Code"].astype(str).str.strip()
    scores = scores[scores["Code"].str.len() > 0]
    scores = scores.drop_duplicates(subset=["Code"], keep="first")

    feature_columns = get_feature_columns(scores)
    scores[feature_columns] = scores[feature_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    scores[feature_columns] = scores[feature_columns].fillna(0.0)

    return scores


def get_feature_columns(scores: pd.DataFrame) -> List[str]:
    """Возвращает список колонок-узлов классификатора.

    Узлы классификатора начинаются с цифры (1., 2., 3. и т.д.).
    Прочие колонки (year, institution_prepared, supervisor, title и пр.)
    исключаются явно, даже если попадут в CSV.
    """
    return [
        c for c in scores.columns
        if c != "Code" and len(c) > 0 and c[0].isdigit()
    ]


# ==============================================================================
# СБОР ДАННЫХ ДЛЯ НАУЧНЫХ ШКОЛ
# ==============================================================================

def gather_school_dataset(
    df: pd.DataFrame,
    index: Dict[str, Set[int]],
    root: str,
    scores: pd.DataFrame,
    scope: ComparisonScope,
    lineage_func: Callable,
    rows_for_func: Callable,
    author_column: str = "candidate_name",
) -> Tuple[pd.DataFrame, pd.DataFrame, int]:
    """Собирает данные тематических профилей для научной школы."""
    if scope == "direct":
        subset = rows_for_func(df, index, root)
    elif scope == "all":
        _, subset = lineage_func(df, index, root)
    else:
        raise ValueError(f"Неизвестный scope: {scope}")

    if subset is None or subset.empty:
        empty = pd.DataFrame(columns=["Code", "school", author_column])
        return empty, empty, 0

    if "Code" not in subset.columns:
        raise KeyError("В данных отсутствует колонка 'Code'")

    cols_to_keep = ["Code"]
    if author_column in subset.columns:
        cols_to_keep.append(author_column)

    working = subset[cols_to_keep].copy()
    working["Code"] = working["Code"].astype(str).str.strip()
    working = working[working["Code"].str.len() > 0]
    working = working.drop_duplicates(subset=["Code"])

    if working.empty:
        empty = pd.DataFrame(columns=["Code", "school", author_column])
        return empty, empty, 0

    codes = working["Code"].tolist()
    total_count = len(codes)

    scores_copy = scores.copy()
    scores_copy["Code"] = scores_copy["Code"].astype(str).str.strip()

    matched_scores = scores_copy[scores_copy["Code"].isin(codes)].copy()

    if matched_scores.empty:
        missing_info = working.copy()
        missing_info["school"] = root
        empty = pd.DataFrame(columns=list(scores.columns) + ["school", author_column])
        return empty, missing_info, total_count

    matched_scores["school"] = root

    if author_column in working.columns:
        matched_scores = matched_scores.merge(
            working[["Code", author_column]],
            on="Code",
            how="left"
        )
    else:
        matched_scores[author_column] = None

    found_codes = set(matched_scores["Code"].tolist())
    missing_codes = [c for c in codes if c not in found_codes]

    if missing_codes:
        missing_info = working[working["Code"].isin(missing_codes)].copy()
        missing_info["school"] = root
    else:
        missing_info = pd.DataFrame(columns=["Code", "school", author_column])

    return matched_scores, missing_info, total_count


# ==============================================================================
# ВЫЧИСЛЕНИЕ СИЛУЭТА
# ==============================================================================

def compute_silhouette_analysis(
    datasets: Dict[str, pd.DataFrame],
    feature_columns: List[str],
    metric: DistanceMetric,
    selected_nodes: Optional[List[str]] = None,
    decay_factor: float = 0.5,
) -> Tuple[float, np.ndarray, np.ndarray, List[str], List[str]]:
    """Вычисляет анализ силуэта для сравнения научных школ."""
    used_columns = filter_columns_by_nodes(feature_columns, selected_nodes)

    if not used_columns:
        raise ValueError("Нет колонок для анализа после фильтрации")

    all_data = []
    all_labels = []
    school_order = []

    for school_name, dataset in datasets.items():
        if dataset.empty:
            continue

        available_cols = [c for c in used_columns if c in dataset.columns]
        if not available_cols:
            continue

        school_data = dataset[available_cols].fillna(0.0).values

        if school_data.shape[0] > 0:
            all_data.append(school_data)
            all_labels.extend([len(school_order)] * school_data.shape[0])
            school_order.append(school_name)

    if len(school_order) < 2:
        raise ValueError("Необходимо минимум 2 школы с данными для сравнения")

    X = np.vstack(all_data)
    labels = np.array(all_labels)

    if X.shape[0] < 2:
        raise ValueError("Недостаточно образцов для анализа")

    distance_matrix = compute_distance_matrix(X, used_columns, metric, decay_factor)

    try:
        overall_score = silhouette_score(distance_matrix, labels, metric="precomputed")
        sample_scores = silhouette_samples(distance_matrix, labels, metric="precomputed")
    except Exception as e:
        raise ValueError(f"Ошибка вычисления силуэта: {e}")

    return overall_score, sample_scores, labels, school_order, used_columns


# ==============================================================================
# ВИЗУАЛИЗАЦИЯ — ГРАФИК СИЛУЭТА
# ==============================================================================

def create_silhouette_plot(
    sample_scores: np.ndarray,
    labels: np.ndarray,
    school_order: List[str],
    overall_score: float,
    metric_label: str,
) -> plt.Figure:
    """Создаёт график силуэта для научных школ."""
    n_schools = len(school_order)
    fig, ax = plt.subplots(figsize=(10, max(6, n_schools * 1.5)))

    y_lower = 10

    colors = (
        SILHOUETTE_COLORS[:n_schools]
        if n_schools <= len(SILHOUETTE_COLORS)
        else (SILHOUETTE_COLORS * ((n_schools // len(SILHOUETTE_COLORS)) + 1))[:n_schools]
    )

    for idx, school in enumerate(school_order):
        mask = labels == idx
        cluster_scores = sample_scores[mask]

        if cluster_scores.size == 0:
            continue

        cluster_scores = np.sort(cluster_scores)
        size = cluster_scores.size
        y_upper = y_lower + size

        ax.fill_betweenx(
            np.arange(y_lower, y_upper),
            0,
            cluster_scores,
            facecolor=colors[idx],
            edgecolor=colors[idx],
            alpha=0.85,
        )

        ax.text(
            -0.05,
            y_lower + size / 2,
            f"{school} (n={size})",
            fontsize=10,
            va="center",
            ha="right",
            fontweight="medium",
        )

        y_lower = y_upper + 10

    ax.axvline(
        x=overall_score,
        color="#2D3436",
        linestyle="--",
        linewidth=2,
        label=f"Средний силуэт: {overall_score:.3f}"
    )

    ax.set_xlim(-1, 1)
    ax.set_xlabel("Коэффициент силуэта", fontsize=12)
    ax.set_ylabel("Научные школы", fontsize=12)
    ax.set_title(
        f"Анализ силуэта тематических профилей\n{metric_label}",
        fontsize=14,
        fontweight="bold"
    )
    ax.set_yticks([])
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(axis="x", linestyle="--", alpha=0.3)

    ax.axvspan(-1, -0.25, alpha=0.08, color="#e74c3c")
    ax.axvspan(-0.25, 0.25, alpha=0.08, color="#f39c12")
    ax.axvspan(0.25, 0.5, alpha=0.08, color="#27ae60")
    ax.axvspan(0.5, 1, alpha=0.08, color="#16a085")

    fig.tight_layout()
    return fig


# ==============================================================================
# ТАБЛИЦА СРЕДНИХ БАЛЛОВ ПО УЗЛАМ КЛАССИФИКАТОРА
# ==============================================================================

def create_node_scores_table(
    datasets: Dict[str, pd.DataFrame],
    feature_columns: List[str],
    school_order: List[str],
    classifier_labels: Optional[Dict[str, str]] = None,
    selected_nodes: Optional[List[str]] = None,
    level: int = 2,
) -> pd.DataFrame:
    """Строит таблицу средних баллов по узлам классификатора.

    Строки — узлы классификатора указанного уровня (по умолчанию уровень 2).
    Столбцы — сравниваемые научные школы.
    Значения — среднее значение признака по всем диссертациям школы,
    агрегированное по всем потомкам узла (среднее потомков → среднее по школе).

    Args:
        datasets: словарь {название школы: DataFrame с профилями}
        feature_columns: список всех колонок-признаков классификатора
        school_order: порядок школ в таблице
        classifier_labels: словарь {код: название узла}
        selected_nodes: если задан — ограничивает узлы этим списком
        level: уровень иерархии для строк таблицы (1, 2 или 3)
    """
    if classifier_labels is None:
        classifier_labels = {}

    # Определяем узлы нужного уровня
    nodes_at_level = get_nodes_at_level(feature_columns, level)

    # Если заданы selected_nodes — оставляем только пересечение
    if selected_nodes:
        nodes_at_level = [
            n for n in nodes_at_level
            if any(is_descendant_of(n, sn) or n == sn for sn in selected_nodes)
        ]

    if not nodes_at_level:
        return pd.DataFrame()

    rows = []
    for node in nodes_at_level:
        # Все потомки данного узла среди feature_columns
        descendant_cols = [c for c in feature_columns if is_descendant_of(c, node)]
        if not descendant_cols:
            continue

        label = classifier_labels.get(node, "")
        row: Dict = {"Код": node, "Раздел": label}

        for school in school_order:
            dataset = datasets.get(school)
            if dataset is None or dataset.empty:
                row[school] = None
                continue
            available = [c for c in descendant_cols if c in dataset.columns]
            if not available:
                row[school] = None
                continue
            # Среднее по потомкам для каждой диссертации, затем среднее по школе
            per_diss = dataset[available].fillna(0.0).mean(axis=1)
            row[school] = round(per_diss.mean(), 2)

        rows.append(row)

    return pd.DataFrame(rows)


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def create_comparison_summary(
    datasets: Dict[str, pd.DataFrame],
    feature_columns: List[str],
    school_order: List[str],
) -> pd.DataFrame:
    """Создаёт сводную таблицу общей статистики по школам."""
    summary_data = []

    for school in school_order:
        if school not in datasets:
            continue

        data = datasets[school]
        if data.empty:
            continue

        available_cols = [c for c in feature_columns if c in data.columns]
        numeric_data = data[available_cols].fillna(0.0)
        row_sums = numeric_data.sum(axis=1)

        summary_data.append({
            "Научная школа": school,
            "Количество диссертаций": len(data),
            "Средняя сумма профиля": round(row_sums.mean(), 2),
            "Медиана суммы профиля": round(row_sums.median(), 2),
            "Стд. отклонение": round(row_sums.std(), 2),
            "Ненулевых признаков (среднее)": round(
                (numeric_data > 0).sum(axis=1).mean(), 1
            ),
        })

    return pd.DataFrame(summary_data)


def interpret_silhouette_score(score: float) -> str:
    """Возвращает текстовую интерпретацию коэффициента силуэта."""
    if score >= 0.71:
        return "🟢 Отличное разделение: школы имеют чётко различающиеся тематические профили"
    elif score >= 0.51:
        return "🟢 Хорошее разделение: школы достаточно хорошо различаются по тематике"
    elif score >= 0.26:
        return "🟡 Умеренное разделение: есть частичное пересечение тематических профилей"
    elif score >= 0:
        return "🟠 Слабое разделение: школы имеют схожие тематические профили"
    else:
        return "🔴 Плохое разделение: тематические профили перемешаны"
