"""Resolución de la URL de stream a partir del player_url del provider."""
from __future__ import annotations

import re

from providers.base import fetch_url

MEDIA_EXTS = (".m3u8", ".mp4", ".mpd", ".webm", ".mkv", ".m4v")
_MEDIA_RE = re.compile(
    r"https?://[^\s\"'<>\\]+?\.(?:m3u8|mp4|mpd|webm|mkv|m4v)(?:\?[^\s\"'<>\\]*)?")


def looks_like_media(url: str) -> bool:
    if not url:
        return False
    clean = url.split("?", 1)[0].lower()
    return clean.endswith(MEDIA_EXTS)


def find_media_in_html(html: str) -> str:
    if not html:
        return ""
    match = _MEDIA_RE.search(html)
    return match.group(0) if match else ""


def find_redirect(html: str) -> str:
    """Detecta redirects JS (window.location.href) y meta refresh."""
    if not html:
        return ""
    match = re.search(
        r"""window\.location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""", html)
    if match:
        return match.group(1).strip()
    meta = re.search(
        r"""<meta[^>]+http-equiv=['"]refresh['"][^>]+content=['"][^'"]*url=([^'";]+)""",
        html, re.IGNORECASE)
    if meta:
        return meta.group(1).strip()
    return ""


def resolve_stream_url(provider, player_url: str, fetch=fetch_url) -> str:
    """Cadena: player_url → get_embed_url → redirect → HTML → m3u8/mp4."""
    if not player_url:
        return ""
    if looks_like_media(player_url):
        return player_url
    try:
        resolved = provider.get_embed_url(player_url) or player_url
    except Exception:
        resolved = player_url
    if looks_like_media(resolved):
        return resolved
    html = fetch(resolved) if resolved else None
    found = find_media_in_html(html or "")
    if found:
        return found
    redirect = find_redirect(html or "")
    if redirect and redirect != resolved:
        if looks_like_media(redirect):
            return redirect
        inner = fetch(redirect) if redirect.startswith("http") else None
        inner_media = find_media_in_html(inner or "")
        return inner_media or redirect
    return resolved
