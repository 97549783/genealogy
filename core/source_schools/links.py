"""Постоянные ссылки на школы универсального формата и карточки их участников."""
from __future__ import annotations

from urllib.parse import urlencode, urlsplit, urlunsplit


_SOURCE_SCHOOL_VIEWS = {"tree", "table", "together", "person"}


def build_source_school_url(
    school_id: str, *, person_id: str | None = None,
    view: str | None = None, base_url: str | None = None,
) -> str:
    """Формирует ссылку школы без переноса фильтров и участника другой школы.

    Значение None использует настроенный адрес для публикации ссылок. Явный адрес
    или путь подходит для локального просмотра; ``base_url=""`` создаёт относительный
    запрос к текущей странице. Параметры и фрагмент явного базового URL заменяются.
    """
    if not str(school_id).strip():
        raise ValueError("Ссылка школы требует непустой идентификатор.")
    if view is not None and view not in _SOURCE_SCHOOL_VIEWS:
        raise ValueError(f"Неизвестный вид школы: {view}.")
    params = {"tab": "source_schools", "school": str(school_id)}
    if person_id is not None:
        if not str(person_id).strip():
            raise ValueError("Карточка требует непустой идентификатор персоны.")
        params["person"] = str(person_id)
    if view is not None:
        params["view"] = view
    if base_url is None:
        # core.ui.__init__ импортирует общие визуализаторы, использующие нашу SVG-иконку.
        # Откладываем импорт до завершения инициализации этого модуля.
        from core.ui.links import build_share_url_from_params

        return build_share_url_from_params(params)
    if "\\" in base_url or any(ord(char) <= 32 or ord(char) == 127 for char in base_url):
        raise ValueError("Недопустимый базовый URL.")
    base = urlsplit(base_url)
    if base.scheme or base.netloc:
        if base.scheme not in {"http", "https"} or not base.netloc or base.username or base.password:
            raise ValueError("Базовый URL должен использовать HTTP или HTTPS.")
    elif base.path and not (base.path.startswith("/") and not base.path.startswith("//")):
        raise ValueError("Относительный базовый путь должен начинаться с /.")
    return urlunsplit((base.scheme, base.netloc, base.path, urlencode(params), ""))


def _safe_link_url(href: str, *, allow_relative: bool = False) -> str:
    """Отбрасывает исполняемые URL, адреса без схемы, учётные данные и управляющие символы."""
    raw = str(href or "")
    if not raw or "\\" in raw or any(ord(char) <= 32 or ord(char) == 127 for char in raw):
        return ""
    try:
        parsed = urlsplit(raw)
        if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.username and not parsed.password:
            return raw
        if allow_relative and not parsed.scheme and not parsed.netloc and (raw.startswith("?") or (raw.startswith("/") and not raw.startswith("//"))):
            return raw
    except ValueError:
        pass
    return ""


def tree_icon_link(href: str, title: str = "Открыть дерево научного руководства") -> str:
    """Создаёт небольшую доступную SVG-ссылку для дерева источниковой школы, таблицы и карточек."""
    from html import escape

    href = _safe_link_url(href, allow_relative=True)
    if not href:
        return ""
    label = escape(str(title), quote=True)
    return (
        f'<a class="markmap-lineage-link source-school-tree-icon" href="{escape(href, quote=True)}" '
        f'target="_blank" rel="noopener noreferrer" title="{label}" aria-label="{label}" '
        'style="display:inline-flex;vertical-align:middle;align-items:center;justify-content:center;'
        'width:1.35em;height:1.35em;margin-left:.3em;color:inherit;text-decoration:none">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" '
        'fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" focusable="false">'
        '<path d="M12 7v5M5 17v-5h14v5"/><rect x="9" y="2" width="6" height="5" rx="1"/>'
        '<rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/>'
        '</svg></a>'
    )
