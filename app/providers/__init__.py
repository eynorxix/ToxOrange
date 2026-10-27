"""Registro de providers de scraping."""
from __future__ import annotations

from providers.base import ScraperProvider
from providers.lamovie import LaMovieProvider
from providers.tioplus import TioPlusProvider


def build_registry() -> dict[str, ScraperProvider]:
    providers: list[ScraperProvider] = [TioPlusProvider(), LaMovieProvider()]
    return {p.id: p for p in providers}
