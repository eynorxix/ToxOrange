"""Modelos de datos de Gonty (port de scraper/model/Models.kt)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerInfo:
    name: str = ""
    base64: str = ""
    player_url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "base64": self.base64, "player_url": self.player_url}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerInfo:
        return cls(
            name=str(data.get("name", "")),
            base64=str(data.get("base64", "")),
            player_url=str(data.get("player_url", "")),
        )


@dataclass
class SeasonEpisode:
    title: str = ""
    image: str = ""
    season: int = 0
    episode: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "image": self.image,
            "season": self.season,
            "episode": self.episode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeasonEpisode:
        return cls(
            title=str(data.get("title", "")),
            image=str(data.get("image", "")),
            season=int(data.get("season", 0) or 0),
            episode=int(data.get("episode", 0) or 0),
        )


@dataclass
class ContentItem:
    slug: str = ""
    title: str = ""
    poster: str = ""
    type: str = ""
    original_url: str = ""
    description: str = ""
    year: str = ""
    rating: str = ""
    genres: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    duration: str = ""
    original_title: str = ""
    servers: list[ServerInfo] = field(default_factory=list)
    default_player_url: str = ""
    seasons: dict[str, list[SeasonEpisode]] = field(default_factory=dict)
    detail_scraped: bool = False
    added_at: int = 0
    provider: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "poster": self.poster,
            "type": self.type,
            "original_url": self.original_url,
            "description": self.description,
            "year": self.year,
            "rating": self.rating,
            "genres": list(self.genres),
            "countries": list(self.countries),
            "actors": list(self.actors),
            "duration": self.duration,
            "original_title": self.original_title,
            "servers": [s.as_dict() for s in self.servers],
            "default_player_url": self.default_player_url,
            "seasons": {
                k: [e.as_dict() for e in v] for k, v in self.seasons.items()
            },
            "detail_scraped": self.detail_scraped,
            "added_at": self.added_at,
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentItem:
        seasons: dict[str, list[SeasonEpisode]] = {}
        raw_seasons = data.get("seasons") or {}
        if isinstance(raw_seasons, dict):
            for key, eps in raw_seasons.items():
                seasons[str(key)] = [
                    SeasonEpisode.from_dict(e) for e in (eps or [])
                    if isinstance(e, dict)
                ]
        return cls(
            slug=str(data.get("slug", "")),
            title=str(data.get("title", "")),
            poster=str(data.get("poster", "")),
            type=str(data.get("type", "")),
            original_url=str(data.get("original_url", "")),
            description=str(data.get("description", "")),
            year=str(data.get("year", "")),
            rating=str(data.get("rating", "")),
            genres=[str(g) for g in (data.get("genres") or [])],
            countries=[str(c) for c in (data.get("countries") or [])],
            actors=[str(a) for a in (data.get("actors") or [])],
            duration=str(data.get("duration", "")),
            original_title=str(data.get("original_title", "")),
            servers=[
                ServerInfo.from_dict(s) for s in (data.get("servers") or [])
                if isinstance(s, dict)
            ],
            default_player_url=str(data.get("default_player_url", "")),
            seasons=seasons,
            detail_scraped=bool(data.get("detail_scraped", False)),
            added_at=int(data.get("added_at", 0) or 0),
            provider=str(data.get("provider", "")),
        )
