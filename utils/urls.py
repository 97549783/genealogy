"""
utils/urls.py — формирование URL для функции «Поделиться».

Публичный API:
    build_share_url(names)   -> str
    share_button(names, key)        — Streamlit-кнопка «Поделиться»

Внутренние вспомогательные:
    _configured_base_url()
    _base_url_from_headers()
    _base_url_from_options()
    _clean_path(*parts)
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Union
from urllib.parse import urlencode, urlsplit

import streamlit as st

try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except Exception:
    get_script_run_ctx = None  # type: ignore

# Публичный адрес приложения. Можно переопределить через переменную окружения.
PUBLIC_APP_URL = os.environ.get(
    "PUBLIC_APP_URL",
    "https://academic-genealogy.streamlit.app/",
).strip().rstrip("/")


# ---------------------------------------------------------------------------
# Внутренние хелперы
# ---------------------------------------------------------------------------

def _clean_path(*parts: str) -> str:
    cleaned = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return f"/{cleaned}" if cleaned else ""


def _configured_base_url() -> Optional[str]:
    if PUBLIC_APP_URL:
        return PUBLIC_APP_URL
    keys = ("public_base_url", "base_url", "BASE_URL")
    for key in keys:
        try:
            val = st.secrets.get(key)  # type: ignore[attr-defined]
        except Exception:
            val = None
        if val:
            return str(val).rstrip("/")
    for key in ("PUBLIC_BASE_URL", "BASE_URL"):
        val = os.environ.get(key)
        if val:
            return val.rstrip("/")
    return None


def _base_url_from_headers() -> Optional[str]:
    if get_script_run_ctx is None:
        return None
    try:
        ctx = get_script_run_ctx()
    except Exception:
        ctx = None
    if not ctx:
        return None
    headers = getattr(ctx, "request_headers", None)
    if not headers:
        return None
    lowered = {str(k).lower(): str(v) for k, v in headers.items() if v}
    prefix = lowered.get("x-forwarded-prefix", "")
    base_path = st.get_option("server.baseUrlPath") or ""

    host = lowered.get("x-forwarded-host") or lowered.get("host")
    if host:
        proto = lowered.get("x-forwarded-proto")
        if proto:
            proto = proto.split(",")[0].strip()
        else:
            forwarded_port = lowered.get("x-forwarded-port")
            proto = (
                "https"
                if forwarded_port == "443" or host.endswith(":443")
                else "http"
            )
        path = _clean_path(prefix, base_path)
        return f"{proto}://{host}{path}".rstrip("/")

    referer = lowered.get("referer") or lowered.get("origin")
    if not referer:
        return None
    parsed = urlsplit(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    path = _clean_path(prefix or parsed.path, base_path)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}{path}".rstrip("/")


def _base_url_from_options() -> Optional[str]:
    try:
        addr = st.get_option("browser.serverAddress")
        port = st.get_option("browser.serverPort")
    except Exception:
        return None
    if not addr:
        return None
    base_path = st.get_option("server.baseUrlPath") or ""
    proto = "https" if str(port) == "443" else "http"
    if (proto == "https" and str(port) in ("", "443")) or (
        proto == "http" and str(port) in ("", "80")
    ):
        host = addr
    else:
        host = f"{addr}:{port}"
    path = _clean_path(base_path)
    return f"{proto}://{host}{path}".rstrip("/")


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

QueryValue = Union[str, int, float, List[Union[str, int, float]], tuple]


def _normalize_query_params(params: Dict[str, QueryValue]) -> List[tuple[str, str]]:
    normalized: List[tuple[str, str]] = []
    for key, raw_value in params.items():
        if raw_value is None:
            continue
        if isinstance(raw_value, (list, tuple)):
            values = [str(v).strip() for v in raw_value if str(v).strip()]
            for value in values:
                normalized.append((str(key), value))
            continue
        value = str(raw_value).strip()
        if value:
            normalized.append((str(key), value))
    return normalized


def build_share_url(names: List[str]) -> str:
    """Формирует URL с параметрами ?root=... для функции «Поделиться»."""
    params = urlencode([("root", n) for n in names])
    query = f"?{params}" if params else ""
    base_url = (
        _configured_base_url()
        or _base_url_from_headers()
        or _base_url_from_options()
    )
    return f"{base_url}{query}" if base_url else query


def build_share_url_from_params(params: Dict[str, QueryValue]) -> str:
    """Формирует URL с произвольными query-параметрами для шаринга результатов."""
    normalized = _normalize_query_params(params)
    encoded_params = urlencode(normalized)
    query = f"?{encoded_params}" if encoded_params else ""
    base_url = (
        _configured_base_url()
        or _base_url_from_headers()
        or _base_url_from_options()
    )
    return f"{base_url}{query}" if base_url else query


def share_params_button(params: Dict[str, QueryValue], key: str) -> None:
    """Кнопка «🔗 Поделиться» для произвольных query-параметров."""
    @st.dialog("Ссылка для доступа")
    def _show_dialog(url: str) -> None:
        st.text_input("URL", url, key=f"share_url_{key}")

    if st.button("🔗 Поделиться", key=key):
        normalized = _normalize_query_params(params)
        try:
            st.query_params.clear()
            grouped: Dict[str, List[str]] = {}
            for q_key, q_val in normalized:
                grouped.setdefault(q_key, []).append(q_val)
            for q_key, q_vals in grouped.items():
                st.query_params[q_key] = q_vals if len(q_vals) > 1 else q_vals[0]
        except Exception:
            pass
        _show_dialog(build_share_url_from_params(params))


def share_button(names: List[str], key: str) -> None:
    """Кнопка «🔗 Поделиться» — открывает диалог с URL."""
    share_params_button({"root": names}, key=key)
