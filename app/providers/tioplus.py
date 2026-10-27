"""Provider tioplus.app (port de TioPlusProvider.kt)."""
from __future__ import annotations

import base64
import logging
import re
import urllib.parse
from typing import Callable

from bs4 import BeautifulSoup

from models import ContentItem, SeasonEpisode, ServerInfo
from providers.base import fetch_url, normalize_title

log = logging.getLogger(__name__)

BASE_URL = "https://tioplus.app"
SKIP_SERVERS_REGEX = re.compile(r"NetU|MobileFast|Plus", re.IGNORECASE)
LOW_PRIORITY_EMBED_HOSTS = ("vidhideplus.com", "strp2p.com")

SECTION_PATHS = {
    "pelicula": "/peliculas/",
    "serie": "/series/",
    "anime": "/animes/",
    "dorama": "/doramas/",
}


def _is_404(html: str) -> bool:
    return "<title>404" in html and len(html) < 2000


def _host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc
    except ValueError:
        return ""


def _is_low_priority_host(url: str) -> bool:
    host = _host_of(url)
    return any(host == h or host.endswith("." + h) for h in LOW_PRIORITY_EMBED_HOSTS)


def decode_server_b64(value: str) -> str:
    """Port de decodeTioPlusServer: doble encode + /player/."""
    try:
        padded = value + "=" * ((4 - len(value) % 4) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace")
        single = base64.b64encode(decoded.encode("utf-8")).decode("ascii")
        double = base64.b64encode(single.encode("utf-8")).decode("ascii")
        return f"{BASE_URL}/player/{double}"
    except Exception:
        log.exception("decode error")
        return ""


def _img_src(tag) -> str:
    src = (tag.get("data-src") or tag.get("src") or "").strip()
    if not src:
        return ""
    return src if src.startswith("http") else BASE_URL + src


def parse_articles(html: str, force_type: str = "") -> list[ContentItem]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    result: list[ContentItem] = []
    for article in soup.select("article.item"):
        link = article.select_one("a.itemA")
        if link is None:
            continue
        href = (link.get("href") or "").strip()
        img = article.select_one("img")
        poster = _img_src(img) if img else ""
        title = ""
        h2 = article.select_one("h2")
        if h2:
            title = h2.get_text(strip=True)
        elif img:
            title = (img.get("alt") or "").strip()
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        content_type = force_type or _type_from_href(href)
        if slug and slug not in seen:
            seen.add(slug)
            result.append(ContentItem(
                slug=slug,
                title=title,
                poster=poster,
                type=content_type,
                original_url=href if href.startswith("http") else BASE_URL + href,
                provider="tioplus",
            ))
    return result


def _type_from_href(href: str) -> str:
    if "/pelicula/" in href:
        return "pelicula"
    if "/serie/" in href:
        return "serie"
    if "/anime/" in href:
        return "anime"
    if "/dorama/" in href:
        return "dorama"
    return "serie"


def _parse_servers(doc: BeautifulSoup) -> list[ServerInfo]:
    servers: list[ServerInfo] = []
    for li in doc.select("li[data-server]"):
        b64 = (li.get("data-server") or "").strip()
        span = li.select_one("span")
        name = span.get_text(strip=True) if span else "Servidor"
        if SKIP_SERVERS_REGEX.search(name):
            continue
        if b64:
            servers.append(ServerInfo(
                name=name, base64=b64, player_url=decode_server_b64(b64)))
    return servers


def _parse_seasons(doc: BeautifulSoup) -> dict[str, list[SeasonEpisode]]:
    import json

    seasons: dict[str, list[SeasonEpisode]] = {}
    for script in doc.select("script"):
        text = script.string or script.get_text() or ""
        match = re.search(r"const\s+seasonsJson\s*=\s*(\{[\s\S]*?\});", text)
        if not match:
            continue
        try:
            obj = json.loads(match.group(1))
        except ValueError:
            continue
        for key, eps in obj.items():
            parsed = []
            for j, ep in enumerate(eps or []):
                if not isinstance(ep, dict):
                    continue
                parsed.append(SeasonEpisode(
                    title=str(ep.get("title", "")),
                    image=str(ep.get("image", "")),
                    season=int(ep.get("season", key) or 1),
                    episode=int(ep.get("episode", j + 1)),
                ))
            parsed.sort(key=lambda e: e.episode)
            seasons[str(key)] = parsed
    return seasons


def resolve_embed_target(player_url: str, fetch=fetch_url) -> str:
    html = fetch(player_url)
    if not html:
        return player_url
    match = re.search(r"""window\.location\.href\s*=\s*['"]([^'"]+)['"]""", html)
    return match.group(1) if match else player_url


def prioritize_servers(servers: list[ServerInfo],
                       fetch=fetch_url) -> tuple[list[ServerInfo], str]:
    if not servers:
        return [], ""
    good, bad = [], []
    for s in servers:
        target = resolve_embed_target(s.player_url, fetch)
        (bad if _is_low_priority_host(target) else good).append(s)
    ordered = good + bad
    default = (good[0].player_url if good else ordered[0].player_url)
    return ordered, default


class TioPlusProvider:
    """Scraper de tioplus.app (HTML + Jsoup->bs4)."""

    id = "tioplus"
    name = "tioplus"
    supported_types = ["pelicula", "serie", "anime", "dorama"]

    def __init__(self, fetch=fetch_url):
        self._fetch = fetch

    def scrape_section(self, type_: str,
                       on_progress: Callable[[str], None] | None = None,
                       max_pages: int = 50,
                       on_page: Callable[[list[ContentItem], int], None] | None = None,
                       ) -> list[ContentItem]:
        base_path = SECTION_PATHS.get(type_)
        if not base_path:
            return []
        result: list[ContentItem] = []
        for page in range(1, max_pages + 1):
            url = BASE_URL + base_path if page == 1 else f"{BASE_URL}{base_path}{page}"
            if on_progress:
                on_progress(f"Página {page}...")
            html = self._fetch(url)
            if not html or _is_404(html):
                break
            new_items = parse_articles(html, type_)
            if not new_items:
                break
            result.extend(new_items)
            if on_page:
                on_page(new_items, page)
        return result

    def search(self, query: str) -> list[ContentItem]:
        encoded = urllib.parse.quote(query.strip())
        html = self._fetch(f"{BASE_URL}/search/{encoded}")
        if not html:
            return []
        return parse_articles(html)

    def scrape_detail(self, slug: str, type_: str) -> ContentItem | None:
        type_path = {"anime": "anime", "serie": "serie", "dorama": "serie"}.get(
            type_, "pelicula")
        url = f"{BASE_URL}/{type_path}/{slug}"
        html = self._fetch(url)
        if not html or _is_404(html):
            return None
        soup = BeautifulSoup(html, "lxml")

        def _sel_text(selector: str) -> str:
            el = soup.select_one(selector)
            return el.get_text(strip=True) if el else ""

        title = _sel_text("h1.slugh1")
        if not title:
            og = soup.select_one('meta[property="og:title"]')
            title = og.get("content", "").strip() if og else ""
        original_title = _sel_text(".genres h2")
        description = _sel_text(".description p")
        if not description:
            meta = soup.select_one('meta[name="description"]')
            description = meta.get("content", "").strip() if meta else ""
        og_img = soup.select_one('meta[property="og:image"]')
        poster = og_img.get("content", "") if og_img else ""

        rating, duration = "", ""
        for span in soup.select(".genres.rating span"):
            text = span.get_text(strip=True)
            if text.startswith("Rating:"):
                rating = text.replace("Rating:", "").strip()
            elif text.startswith("Duración:"):
                duration = text.replace("Duración:", "").strip()
        year = _sel_text('.genres.rating a[href*="year"]')
        genres = [a.get_text(strip=True) for a in soup.select('.genres a[href*="/genero/"]')]
        countries = [a.get_text(strip=True) for a in soup.select('.genres a[href*="/paises/"]')]
        actors = [a.get_text(strip=True) for a in soup.select('.genres a[href*="/actor/"]')]

        servers = _parse_servers(soup)
        seasons = _parse_seasons(soup)

        default_player_url = ""
        player_tr = soup.select_one("#player-tr")
        if player_tr and (player_tr.get("data-tr") or "").strip():
            default_player_url = decode_server_b64(player_tr["data-tr"].strip())

        ordered, prioritized_default = prioritize_servers(servers, self._fetch)
        effective_default = prioritized_default or default_player_url

        return ContentItem(
            slug=slug,
            title=title,
            poster=poster,
            type=type_,
            original_url=url,
            description=description,
            year=year,
            rating=rating,
            genres=genres,
            countries=countries,
            actors=actors,
            duration=duration,
            original_title=original_title,
            servers=ordered,
            default_player_url=effective_default,
            seasons=seasons,
            detail_scraped=bool(ordered or default_player_url),
            provider=self.id,
        )

    def scrape_episode_servers(self, type_: str, slug: str,
                               season: str, episode: str,
                               ) -> tuple[list[ServerInfo], str]:
        type_path = "anime" if type_ == "anime" else "serie"
        url = f"{BASE_URL}/{type_path}/{slug}/season/{season}/episode/{episode}"
        html = self._fetch(url)
        if not html:
            return [], ""
        soup = BeautifulSoup(html, "lxml")
        servers = _parse_servers(soup)
        default_url = ""
        if not servers:
            iframe = soup.select_one("iframe[src]")
            default_url = iframe.get("src", "") if iframe else ""
        ordered, prioritized_default = prioritize_servers(servers, self._fetch)
        return ordered, prioritized_default or default_url

    def get_embed_url(self, player_url: str) -> str:
        html = self._fetch(player_url)
        if not html:
            return player_url
        soup = BeautifulSoup(html, "lxml")

        iframe = soup.select_one("iframe[src]")
        if iframe and iframe.get("src"):
            return iframe["src"]
        video = soup.select_one("video source[src], video[src]")
        if video and video.get("src"):
            return video["src"]
        text = html
        m3u8 = re.search(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", text)
        if m3u8:
            return m3u8.group(0)
        mp4 = re.search(r"https?://[^\s\"'<>]+\.mp4[^\s\"'<>]*", text)
        if mp4:
            return mp4.group(0)
        return player_url

    def scrape_genre(self, genre_slug: str, genre_name: str,
                     on_progress: Callable[[str], None] | None = None,
                     max_pages: int = 50) -> list[ContentItem]:
        result: list[ContentItem] = []
        for page in range(1, max_pages + 1):
            url = (f"{BASE_URL}/genero/{genre_slug}/" if page == 1
                   else f"{BASE_URL}/genero/{genre_slug}/{page}")
            if on_progress:
                on_progress(f"Género {genre_name} • página {page}...")
            html = self._fetch(url)
            if not html or _is_404(html):
                break
            new_items = parse_articles(html)
            if not new_items:
                break
            for item in new_items:
                item.genres = [genre_name]
            result.extend(new_items)
        return result

    def search_by_category(self, title: str, type_: str) -> ContentItem | None:
        base_path = SECTION_PATHS.get(type_)
        if not base_path:
            return None
        query_norm = normalize_title(title)
        for page in range(1, 11):
            url = BASE_URL + base_path if page == 1 else f"{BASE_URL}{base_path}{page}"
            html = self._fetch(url)
            if not html or _is_404(html):
                break
            articles = parse_articles(html, type_)
            for item in articles:
                if normalize_title(item.title) == query_norm:
                    return item
            for item in articles:
                n = normalize_title(item.title)
                if query_norm in n or n in query_norm:
                    return item
        return None
