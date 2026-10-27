"""Persistencia JSON: catálogo cacheado, favoritos e historial."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from models import ContentItem

DEFAULT_MAX_AGE_HOURS = 12


class Store:
    """Estado en ~/.config/gonty/ (patrón state.json del widget)."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path.home() / ".config" / "gonty")
        self.catalog_dir = self.base_dir / "catalog"
        self.details_dir = self.base_dir / "details"
        self.favorites_path = self.base_dir / "favorites.json"
        self.history_path = self.base_dir / "history.json"

    # -- cache de catalogo ---------------------------------------------------
    def _catalog_path(self, provider_id: str, type_: str) -> Path:
        return self.catalog_dir / f"{provider_id}.{type_}.json"

    def load_catalog(self, provider_id: str, type_: str) -> list[ContentItem]:
        try:
            data = json.loads(
                self._catalog_path(provider_id, type_).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("items") or []
        return [ContentItem.from_dict(i) for i in items if isinstance(i, dict)]

    def save_catalog(self, provider_id: str, type_: str,
                     items: list[ContentItem]) -> None:
        path = self._catalog_path(provider_id, type_)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "provider": provider_id,
                "type": type_,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "items": [i.as_dict() for i in items],
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def catalog_fresh(self, provider_id: str, type_: str,
                      max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> bool:
        try:
            data = json.loads(
                self._catalog_path(provider_id, type_).read_text(encoding="utf-8"))
            fetched = data.get("fetched_at", "")
            stamp = time.mktime(time.strptime(fetched, "%Y-%m-%dT%H:%M:%S"))
            return (time.time() - stamp) < max_age_hours * 3600
        except (OSError, ValueError):
            return False

    # -- cache de detalles ---------------------------------------------------
    def _detail_path(self, provider_id: str, slug: str) -> Path:
        safe = slug.replace("/", "_")
        return self.details_dir / f"{provider_id}.{safe}.json"

    def load_detail(self, provider_id: str, slug: str) -> ContentItem | None:
        try:
            data = json.loads(
                self._detail_path(provider_id, slug).read_text(encoding="utf-8"))
            item = data.get("item")
        except (OSError, ValueError):
            return None
        return ContentItem.from_dict(item) if isinstance(item, dict) else None

    def save_detail(self, item: ContentItem) -> None:
        path = self._detail_path(item.provider, item.slug)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "item": item.as_dict(),
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def detail_fresh(self, provider_id: str, slug: str,
                     max_age_hours: float = 72) -> bool:
        try:
            data = json.loads(
                self._detail_path(provider_id, slug).read_text(encoding="utf-8"))
            fetched = data.get("fetched_at", "")
            stamp = time.mktime(time.strptime(fetched, "%Y-%m-%dT%H:%M:%S"))
            return (time.time() - stamp) < max_age_hours * 3600
        except (OSError, ValueError):
            return False

    # -- favoritos -----------------------------------------------------------
    def _load_list(self, path: Path) -> list[dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [i for i in data if isinstance(i, dict)]
        except (OSError, ValueError):
            return []

    def _save_list(self, path: Path, items: list[dict[str, Any]]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def favorites(self) -> list[ContentItem]:
        return [ContentItem.from_dict(i) for i in self._load_list(self.favorites_path)]

    def is_favorite(self, provider_id: str, slug: str) -> bool:
        return any(
            f.get("provider") == provider_id and f.get("slug") == slug
            for f in self._load_list(self.favorites_path))

    def add_favorite(self, item: ContentItem) -> None:
        if self.is_favorite(item.provider, item.slug):
            return
        items = self._load_list(self.favorites_path)
        items.append(item.as_dict())
        self._save_list(self.favorites_path, items)

    def remove_favorite(self, provider_id: str, slug: str) -> None:
        items = [
            f for f in self._load_list(self.favorites_path)
            if not (f.get("provider") == provider_id and f.get("slug") == slug)]
        self._save_list(self.favorites_path, items)

    def toggle_favorite(self, item: ContentItem) -> bool:
        """Devuelve True si quedo como favorito."""
        if self.is_favorite(item.provider, item.slug):
            self.remove_favorite(item.provider, item.slug)
            return False
        self.add_favorite(item)
        return True

    # -- historial -----------------------------------------------------------
    def history(self) -> list[ContentItem]:
        return [ContentItem.from_dict(i) for i in self._load_list(self.history_path)]

    def push_history(self, item: ContentItem, limit: int = 100) -> None:
        items = [
            h for h in self._load_list(self.history_path)
            if not (h.get("provider") == item.provider and h.get("slug") == item.slug)]
        items.insert(0, item.as_dict())
        self._save_list(self.history_path, items[:limit])
