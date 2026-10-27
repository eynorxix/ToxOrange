"""Base de providers: Protocol + HTTP (port de ScraperProvider.kt)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol, runtime_checkable

from models import ContentItem, ServerInfo

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
    "Chrome/126.0.0.0 Mobile Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


@runtime_checkable
class ScraperProvider(Protocol):
    id: str
    name: str
    supported_types: list[str]

    def scrape_section(
        self, type_: str, on_progress: Callable[[str], None] | None = None,
    ) -> list[ContentItem]: ...

    def search(self, query: str) -> list[ContentItem]: ...

    def scrape_detail(self, slug: str, type_: str) -> ContentItem | None: ...

    def scrape_episode_servers(
        self, type_: str, slug: str, season: str, episode: str,
    ) -> tuple[list[ServerInfo], str]: ...

    def get_embed_url(self, player_url: str) -> str: ...


def fetch_url(url: str, headers: dict[str, str] | None = None,
              timeout: int = 15) -> str | None:
    """GET simple; devuelve el texto o None si falla."""
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def fetch_json(url: str, headers: dict[str, str] | None = None,
               timeout: int = 20) -> dict[str, Any] | None:
    text = fetch_url(url, headers=headers, timeout=timeout)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def abs_url(base: str, path: str) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def normalize_title(title: str) -> str:
    """Port de TextNormalizer.kt: sin acentos ni numeros ni puntuacion."""
    import unicodedata

    no_marks = unicodedata.normalize("NFD", title or "")
    no_marks = re.sub(r"[\u0300-\u036f]", "", no_marks)
    text = no_marks.lower()
    text = re.sub(r"\b\d{4}\b", "", text)
    text = re.sub(r"\b\d+\b", " ", text)
    text = re.sub(r"[^a-zñ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
