"""Provider lamovie.org (port de LaMovieProvider.kt, usa su API wp-api/v1)."""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Callable

from models import ContentItem, SeasonEpisode, ServerInfo
from providers.base import abs_url, fetch_json

log = logging.getLogger(__name__)

BASE_URL = "https://lamovie.org"
API_URL = f"{BASE_URL}/wp-api/v1"
UPLOADS_URL = f"{BASE_URL}/wp-content/uploads"

TYPE_TO_POST_TYPE = {
    "pelicula": "movies",
    "serie": "tvshows",
    "anime": "animes",
}
POST_TYPE_TO_TYPE = {v: k for k, v in TYPE_TO_POST_TYPE.items()}
SECTION_PATH = {
    "pelicula": "peliculas",
    "serie": "series",
    "anime": "animes",
}

GENRE_ID_TO_NAME = {
    17: "Drama", 18: "Comedia", 33: "Suspense", 32: "Acción",
    520: "Animación", 96: "Terror", 180: "Crimen", 130: "Aventura",
    115: "Romance", 398: "Familia", 97: "Misterio", 131: "Ciencia ficción",
    229: "Fantasía", 704: "Sci-Fi & Fantasy", 705: "Action & Adventure",
    164: "Documental", 165: "Historia", 8: "Música", 6787: "Película de TV",
    3056: "Bélica", 674: "Western", 703: "Kids", 786: "War & Politics",
    12485: "Reality", 19824: "Soap",
}

AD_BLOCK_DOMAINS = [
    "popads.net", "popadscdn.net", "propellerads.com", "propellerclick.com",
    "adsterra.com", "adsterra.net", "adsterra.co", "adsterra.org", "adtng.com",
    "1xbet.com", "1xbet.xyz", "1xbet.club", "1xbet.info", "1xbet.vip",
    "exoclick.com", "exosrv.com", "juicyads.com", "onclickads.net",
    "popcash.net", "trafficfactory.biz", "mgid.com", "adf.ly",
]


def genres_from(obj: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for genre_id in obj.get("genres") or []:
        name = GENRE_ID_TO_NAME.get(int(genre_id))
        if name and name not in names:
            names.append(name)
    return names


def post_to_item(obj: dict[str, Any], fallback_type: str) -> ContentItem | None:
    slug = str(obj.get("slug", "")).strip()
    if not slug:
        return None
    raw_type = str(obj.get("type", ""))
    if raw_type:
        content_type = POST_TYPE_TO_TYPE.get(raw_type)
        if not content_type:
            return None
    else:
        content_type = fallback_type
    images = obj.get("images") or {}
    poster = abs_url(UPLOADS_URL, str(images.get("poster", "")))
    return ContentItem(
        slug=slug,
        title=str(obj.get("title", "")).strip(),
        poster=poster,
        type=content_type,
        original_url=f"{BASE_URL}/{SECTION_PATH.get(content_type, 'peliculas')}/{slug}",
        description=str(obj.get("overview", "")),
        year=str(obj.get("release_date", ""))[:4],
        rating=str(obj.get("rating", "")),
        duration=_runtime_str(obj.get("runtime")),
        original_title=str(obj.get("original_title", "")),
        genres=genres_from(obj),
        provider="lamovie",
    )


def _runtime_str(runtime: Any) -> str:
    try:
        value = float(runtime)
    except (TypeError, ValueError):
        return ""
    return f"{int(value)} min" if value > 0 else ""


_HOST_FIRST = ("videoapp.",)
_HOST_LAST = ("hls2.goodstream.", "goodstream.one", "hlswish.", "voe.sx")


def _server_rank(url: str) -> int:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(h in host for h in _HOST_FIRST):
        return 0
    if any(h in host for h in _HOST_LAST):
        return 100
    return 50


def parse_embeds(data: dict[str, Any] | None) -> list[ServerInfo]:
    if not data:
        return []
    embeds = data.get("embeds") or []
    servers: list[ServerInfo] = []
    for embed in embeds:
        if not isinstance(embed, dict):
            continue
        url = str(embed.get("url", "")).strip()
        if not url:
            continue
        parts = [
            str(embed.get("server", "")),
            str(embed.get("lang", "")),
            str(embed.get("quality", "")),
        ]
        name = " · ".join(p for p in parts if p)
        servers.append(ServerInfo(
            name=name or f"Servidor {len(servers) + 1}", player_url=url))
    servers.sort(key=lambda s: _server_rank(s.player_url))
    return servers


class LaMovieProvider:
    """Scraper de lamovie.org via API JSON."""

    id = "lamovie"
    name = "lamovie"
    supported_types = ["pelicula", "serie", "anime"]
    ad_block_domains = AD_BLOCK_DOMAINS

    def __init__(self, fetch_json_fn=fetch_json):
        self._fetch_json = fetch_json_fn

    def _api(self, path: str) -> dict[str, Any] | None:
        return self._fetch_json(
            f"{API_URL}{path}",
            headers={"Accept": "application/json", "Referer": BASE_URL},
        )

    def _fetch_season_episodes(self, show_id: int, season: int) -> list[SeasonEpisode]:
        result: list[SeasonEpisode] = []
        page = 1
        while page <= 20:
            data = self._api(
                f"/single/episodes/list?_id={show_id}&season={season}"
                f"&page={page}&postsPerPage=100")
            if not data:
                break
            payload = data.get("data") or {}
            posts = payload.get("posts") or []
            for post in posts:
                if not isinstance(post, dict):
                    continue
                result.append(SeasonEpisode(
                    title=str(post.get("title", "")),
                    image=abs_url(UPLOADS_URL, str(post.get("still_path", ""))),
                    season=season,
                    episode=int(post.get("episode_number", 0) or 0),
                ))
            last_page = int((payload.get("pagination") or {}).get("last_page", 0) or 0)
            if last_page <= 0 or page >= last_page:
                break
            page += 1
        return sorted((e for e in result if e.episode > 0), key=lambda e: e.episode)

    def _fetch_season_numbers(self, show_id: int) -> list[int]:
        data = self._api(
            f"/single/episodes/list?_id={show_id}&season=1&page=1&postsPerPage=1")
        if not data:
            return []
        seasons = (data.get("data") or {}).get("seasons") or []
        numbers = []
        for value in seasons:
            try:
                numbers.append(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(numbers)

    def scrape_section(self, type_: str,
                       on_progress: Callable[[str], None] | None = None,
                       max_pages: int = 100,
                       on_page: Callable[[list[ContentItem], int], None] | None = None,
                       ) -> list[ContentItem]:
        post_type = TYPE_TO_POST_TYPE.get(type_)
        if not post_type:
            return []
        result: list[ContentItem] = []
        page = 1
        while page <= max_pages:
            if on_progress:
                on_progress(f"Página {page}...")
            data = self._api(
                f"/listing/{post_type}?page={page}&orderBy=latest&order=asc"
                f"&postType={post_type}&postsPerPage=24")
            if not data:
                break
            payload = data.get("data") or {}
            posts = payload.get("posts") or []
            if not posts:
                break
            batch = []
            for post in posts:
                if isinstance(post, dict):
                    item = post_to_item(post, type_)
                    if item:
                        batch.append(item)
            result.extend(batch)
            if on_page and batch:
                on_page(batch, page)
            last_page = int((payload.get("pagination") or {}).get("last_page", 0) or 0)
            if last_page <= 0 or page >= last_page:
                break
            page += 1
        return result

    def search(self, query: str) -> list[ContentItem]:
        encoded = urllib.parse.quote(query)
        data = self._api(f"/search?postType=any&q={encoded}&postsPerPage=24")
        if not data:
            return []
        posts = (data.get("data") or {}).get("posts") or []
        result = []
        for post in posts:
            if isinstance(post, dict):
                item = post_to_item(post, "pelicula")
                if item:
                    result.append(item)
        return result

    def scrape_detail(self, slug: str, type_: str) -> ContentItem | None:
        post_type = TYPE_TO_POST_TYPE.get(type_)
        if not post_type:
            return None
        data = self._api(f"/single/{post_type}?slug={slug}&postType={post_type}")
        if not data:
            return None
        payload = data.get("data") or {}
        base = post_to_item(payload, type_)
        if base is None:
            return None
        show_id = int(payload.get("_id", 0) or 0)

        seasons: dict[str, list[SeasonEpisode]] = {}
        if show_id and type_ != "pelicula":
            numbers = self._fetch_season_numbers(show_id) or [1]
            for s in numbers:
                episodes = self._fetch_season_episodes(show_id, s)
                if episodes:
                    seasons[str(s)] = episodes

        servers: list[ServerInfo] = []
        if show_id:
            player = self._api(f"/player?postId={show_id}&demo=0")
            servers = parse_embeds((player or {}).get("data"))
        if seasons:
            servers = [s for s in servers if "embed.html" not in s.player_url]

        base.servers = servers
        base.default_player_url = servers[0].player_url if servers else ""
        base.seasons = seasons
        base.detail_scraped = bool(servers or seasons or base.default_player_url)
        return base

    def scrape_episode_servers(self, type_: str, slug: str,
                               season: str, episode: str,
                               ) -> tuple[list[ServerInfo], str]:
        post_type = TYPE_TO_POST_TYPE.get(type_)
        if not post_type:
            return [], ""
        show_json = self._api(f"/single/{post_type}?slug={slug}&postType={post_type}")
        show_id = int(((show_json or {}).get("data") or {}).get("_id", 0) or 0)
        if not show_id:
            return [], ""
        try:
            ep_number = int(episode)
        except ValueError:
            return [], ""
        list_json = self._api(
            f"/single/episodes/list?_id={show_id}&season={season}&page=1&postsPerPage=100")
        posts = ((list_json or {}).get("data") or {}).get("posts") or []
        ep_id = 0
        for post in posts:
            if isinstance(post, dict) and int(post.get("episode_number", 0) or 0) == ep_number:
                ep_id = int(post.get("_id", 0) or 0)
                break
        if not ep_id:
            return [], ""
        player = self._api(f"/player?postId={ep_id}&demo=0")
        servers = parse_embeds((player or {}).get("data"))
        default_url = servers[0].player_url if servers else ""
        return servers, default_url

    def get_embed_url(self, player_url: str) -> str:
        return player_url
