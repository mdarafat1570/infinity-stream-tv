"""Minimal, dependency-free i18n: dotted-key lookup with English fallback.

Translation files live in ``translations/<locale>.json`` as nested objects.
``t(key, **kwargs)`` performs a dotted-path lookup (e.g. ``"nav.home"``),
falling back to English when a key is missing in the active locale, and
finally to the key itself (with a logged warning) when it is missing from
both. It never raises, so a partial translation can never break a page.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from markupsafe import Markup

SUPPORTED_LOCALES = ("en", "ar")
DEFAULT_LOCALE = "en"
TEXT_DIRECTIONS = {"en": "ltr", "ar": "rtl"}

_TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"
_logger = logging.getLogger(__name__)

_cache: dict[str, dict] = {}
_cache_lock = Lock()


def _load_locale_file(locale: str) -> dict:
    path = _TRANSLATIONS_DIR / f"{locale}.json"
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def load_translations(force_reload: bool = False) -> dict[str, dict]:
    """Load (and cache) every supported locale's translation dictionary."""
    with _cache_lock:
        if not _cache or force_reload:
            _cache.clear()
            for locale in SUPPORTED_LOCALES:
                _cache[locale] = _load_locale_file(locale)
        return _cache


def _lookup(data: dict, dotted_key: str) -> Any:
    node: Any = data
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def translate(locale: str, key: str, **kwargs) -> str:
    """Look up ``key`` in ``locale``'s catalogue, falling back to English then the key itself."""
    translations = load_translations()
    locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    value = _lookup(translations.get(locale, {}), key)
    if value is None and locale != DEFAULT_LOCALE:
        value = _lookup(translations.get(DEFAULT_LOCALE, {}), key)
    if value is None:
        _logger.warning("Missing translation key %r (locale=%s)", key, locale)
        value = key
    text = str(value)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            _logger.warning("Translation key %r is missing format arguments %r", key, kwargs)
    return text


def make_translator(locale: str):
    """Return a ``t(key, **kwargs)`` callable bound to ``locale``.

    The returned value is wrapped in ``Markup`` so templates can embed
    trusted inline tags (e.g. ``<br>``) in translation strings without an
    explicit ``|safe`` filter. Translation content is developer-authored and
    never derived from user input, so this is safe.
    """

    def t(key: str, **kwargs) -> Markup:
        return Markup(translate(locale, key, **kwargs))

    return t


def text_direction(locale: str) -> str:
    return TEXT_DIRECTIONS.get(locale, "ltr")


def resolve_locale(*, query_lang: str | None = None, cookie_lang: str | None = None) -> str:
    """Resolve the active locale: explicit ``?lang=`` query, then the ``lang`` cookie, then English."""
    if query_lang and query_lang in SUPPORTED_LOCALES:
        return query_lang
    if cookie_lang and cookie_lang in SUPPORTED_LOCALES:
        return cookie_lang
    return DEFAULT_LOCALE


def localize(obj: dict, field: str, locale: str):
    """Return ``obj[f'{field}_ar']`` when Arabic and present, else ``obj[field]``."""
    if locale == "ar":
        ar_value = obj.get(f"{field}_ar")
        if ar_value is not None:
            return ar_value
    return obj.get(field)
