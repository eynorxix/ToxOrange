"""Página Detalle: info del título, temporadas/episodios y servidores."""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from models import ContentItem, SeasonEpisode, ServerInfo  # noqa: E402
from providers import build_registry  # noqa: E402
from store import Store  # noqa: E402
from ui.catalog import (  # noqa: E402
    TYPE_LABELS, _download_poster, _load_texture,
)

POSTER_W = 180
POSTER_H = 270


class DetailPage(Gtk.Box):
    """Pagina del Stack con el detalle scrapeado de un titulo."""

    def __init__(self, store: Store, on_back=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.store = store
        self.on_back = on_back
        self.providers = build_registry()
        self.item: ContentItem | None = None
        self.selected_server: ServerInfo | None = None
        self.busy = False
        self._generation = 0

        self.append(self._build_header())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._build_body())
        self.append(scroll)

        self.status = Gtk.Label(label="")
        self.status.add_css_class("catalog-status")
        self.status.set_xalign(0)
        self.status.set_margin_start(14)
        self.status.set_margin_end(14)
        self.status.set_margin_bottom(10)
        self.append(self.status)

        self._set_seasons({})

    # -- cabecera ------------------------------------------------------------
    def _build_header(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("titlebar")
        back = Gtk.Button(label="←")
        back.add_css_class("icon-btn")
        back.set_tooltip_text("Volver al catálogo (Esc)")
        back.connect("clicked", lambda *_: self._go_back())
        bar.append(back)
        self.header_title = Gtk.Label(label="DETALLE")
        self.header_title.add_css_class("titlebar-title")
        self.header_title.set_xalign(0)
        self.header_title.set_ellipsize(Pango.EllipsizeMode.END)
        bar.append(self.header_title)
        sp = Gtk.Box()
        sp.set_hexpand(True)
        bar.append(sp)
        self.fav_btn = Gtk.Button(label="☆")
        self.fav_btn.add_css_class("icon-btn")
        self.fav_btn.set_tooltip_text("Favorito")
        self.fav_btn.connect("clicked", self._on_fav_clicked)
        bar.append(self.fav_btn)
        refresh = Gtk.Button(label="↻")
        refresh.add_css_class("icon-btn")
        refresh.set_tooltip_text("Re-scrapear detalle")
        refresh.connect("clicked", lambda *_: self._load_remote(force=True))
        bar.append(refresh)
        return bar

    def _go_back(self):
        if self.on_back:
            self.on_back()

    # -- cuerpo --------------------------------------------------------------
    def _build_body(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)
        outer.set_margin_start(14)
        outer.set_margin_end(14)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        top.set_valign(Gtk.Align.START)

        self.poster = Gtk.Picture()
        self.poster.set_size_request(POSTER_W, POSTER_H)
        self.poster.add_css_class("poster")
        if hasattr(self.poster, "set_content_fit"):
            self.poster.set_content_fit(Gtk.ContentFit.CONTAIN)
        top.append(self.poster)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        info.set_hexpand(True)
        self.title_lbl = Gtk.Label(label="")
        self.title_lbl.add_css_class("home-logo")
        self.title_lbl.set_xalign(0)
        self.title_lbl.set_wrap(True)
        self.title_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        info.append(self.title_lbl)

        self.original_lbl = Gtk.Label(label="")
        self.original_lbl.add_css_class("module-sub")
        self.original_lbl.set_xalign(0)
        self.original_lbl.set_wrap(True)
        info.append(self.original_lbl)

        self.meta_lbl = Gtk.Label(label="")
        self.meta_lbl.add_css_class("card-meta")
        self.meta_lbl.set_xalign(0)
        self.meta_lbl.set_wrap(True)
        info.append(self.meta_lbl)

        self.genres_lbl = Gtk.Label(label="")
        self.genres_lbl.add_css_class("task-course")
        self.genres_lbl.set_xalign(0)
        self.genres_lbl.set_wrap(True)
        info.append(self.genres_lbl)

        self.actors_lbl = Gtk.Label(label="")
        self.actors_lbl.add_css_class("module-sub")
        self.actors_lbl.set_xalign(0)
        self.actors_lbl.set_wrap(True)
        info.append(self.actors_lbl)

        top.append(info)
        outer.append(top)

        self.description_lbl = Gtk.Label(label="")
        self.description_lbl.add_css_class("json-string")
        self.description_lbl.set_xalign(0)
        self.description_lbl.set_wrap(True)
        self.description_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        outer.append(self.description_lbl)

        # Temporadas + episodios (rejillas de botones, 5 por fila)
        self.seasons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        seasons_label = Gtk.Label(label="TEMPORADAS")
        seasons_label.add_css_class("field-label")
        seasons_label.set_xalign(0)
        self.seasons_box.append(seasons_label)

        self.seasons_grid = Gtk.FlowBox()
        self.seasons_grid.add_css_class("season-grid")
        self.seasons_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.seasons_grid.set_homogeneous(True)
        self.seasons_grid.set_min_children_per_line(5)
        self.seasons_grid.set_max_children_per_line(5)
        self.seasons_grid.set_column_spacing(8)
        self.seasons_grid.set_row_spacing(8)
        self.seasons_box.append(self.seasons_grid)

        self.episodes_label = Gtk.Label(label="EPISODIOS")
        self.episodes_label.add_css_class("field-label")
        self.episodes_label.set_xalign(0)
        self.seasons_box.append(self.episodes_label)

        self.episodes_grid = Gtk.FlowBox()
        self.episodes_grid.add_css_class("episode-grid")
        self.episodes_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.episodes_grid.set_homogeneous(True)
        self.episodes_grid.set_min_children_per_line(5)
        self.episodes_grid.set_max_children_per_line(5)
        self.episodes_grid.set_column_spacing(6)
        self.episodes_grid.set_row_spacing(6)
        self.episodes_grid.set_margin_top(2)
        self.seasons_box.append(self.episodes_grid)
        outer.append(self.seasons_box)

        # Servidores
        servers_head = Gtk.Label(label="SERVIDORES")
        servers_head.add_css_class("field-label")
        servers_head.set_xalign(0)
        outer.append(servers_head)
        self.servers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.append(self.servers_box)

        return outer

    # -- carga ---------------------------------------------------------------
    def load_item(self, item: ContentItem):
        self.item = item
        self.selected_server = None
        self._generation += 1
        self.header_title.set_text((item.title or "DETALLE").upper()[:40])
        self.title_lbl.set_text(item.title or "(sin título)")
        self.original_lbl.set_text(item.original_title or "")
        self.original_lbl.set_visible(bool(item.original_title))
        self._fill_meta(item)
        self.genres_lbl.set_text(" · ".join(item.genres))
        self.actors_lbl.set_text(", ".join(item.actors[:8]))
        self.description_lbl.set_text(item.description or "")
        self._update_fav()
        self._clear_servers()
        self._set_seasons(item.seasons)
        self._set_status("")

        if item.poster:
            self._load_poster_async(item.poster, self._generation)

        cached = self.store.load_detail(item.provider, item.slug)
        if cached and self.store.detail_fresh(item.provider, item.slug):
            self._apply_detail(cached)
            return
        self._load_remote()

    def _fill_meta(self, item: ContentItem):
        parts = [TYPE_LABELS.get(item.type, item.type)]
        if item.year:
            parts.append(item.year)
        if item.duration:
            parts.append(item.duration)
        if item.rating:
            parts.append(f"★ {item.rating}")
        if item.countries:
            parts.append(" · ".join(item.countries[:3]))
        self.meta_lbl.set_text(" · ".join(p for p in parts if p))

    def _load_remote(self, force: bool = False):
        item = self.item
        if item is None or self.busy:
            return
        provider = self.providers.get(item.provider)
        if provider is None:
            self._set_status(f"Proveedor desconocido: {item.provider}")
            return
        self.busy = True
        self._set_status(f"Scraping detalle de {item.slug}…")
        generation = self._generation

        def worker():
            try:
                detail = provider.scrape_detail(item.slug, item.type)
                error = None
            except Exception as exc:
                detail = None
                error = str(exc)
            GLib.idle_add(self._on_remote_done, detail, error, generation)

        threading.Thread(target=worker, daemon=True).start()

    def _on_remote_done(self, detail, error, generation):
        self.busy = False
        if generation != self._generation:
            return False
        if error:
            self._set_status(f"Error: {error}")
            return False
        if detail is None:
            self._set_status("Sin resultados del proveedor")
            return False
        self._apply_detail(detail)
        return False

    def _apply_detail(self, detail: ContentItem):
        if self.item is None:
            return
        # Conserva el slug/tipo locales; mezcla lo scrapeado.
        base = self.item
        base.description = detail.description or base.description
        base.original_title = detail.original_title or base.original_title
        base.year = detail.year or base.year
        base.rating = detail.rating or base.rating
        base.duration = detail.duration or base.duration
        base.genres = detail.genres or base.genres
        base.countries = detail.countries or base.countries
        base.actors = detail.actors or base.actors
        base.poster = base.poster or detail.poster
        base.servers = detail.servers
        base.default_player_url = detail.default_player_url
        base.seasons = detail.seasons or base.seasons
        base.detail_scraped = detail.detail_scraped

        self.title_lbl.set_text(base.title or "(sin título)")
        self._fill_meta(base)
        self.genres_lbl.set_text(" · ".join(base.genres))
        self.actors_lbl.set_text(", ".join(base.actors[:8]))
        self.description_lbl.set_text(base.description or "")
        self._set_seasons(base.seasons)
        self._render_servers(base.servers)
        self.store.save_detail(base)
        count = len(base.servers)
        seasons = len(base.seasons)
        extra = f" · {seasons} temporada(s)" if seasons else ""
        self._set_status(f"{count} servidor(es){extra} · cache 72 h")

    # -- temporadas / episodios ----------------------------------------------
    def _set_seasons(self, seasons: dict[str, list[SeasonEpisode]]):
        self.episode_seasons = dict(seasons)
        keys = sorted(seasons.keys(), key=lambda k: int(k) if k.isdigit() else 0)
        self.season_keys = keys
        self.active_season = keys[0] if keys else ""
        self.seasons_box.set_visible(bool(keys))

        child = self.seasons_grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.seasons_grid.remove(child)
            child = nxt
        self._season_btns: dict[str, Gtk.Button] = {}
        for key in keys:
            btn = Gtk.Button(label=f"T{key}")
            btn.add_css_class("season-btn")
            btn.set_tooltip_text(f"Temporada {key}")
            btn.connect("clicked", self._select_season, key)
            self.seasons_grid.append(btn)
            self._season_btns[key] = btn
        self._update_season_buttons()
        if keys:
            self._fill_episodes(keys[0])
        else:
            self._clear_episodes()

    def _select_season(self, _btn, season_key: str):
        self.active_season = season_key
        self._update_season_buttons()
        self._fill_episodes(season_key)

    def _update_season_buttons(self):
        for key, btn in getattr(self, "_season_btns", {}).items():
            if key == self.active_season:
                btn.add_css_class("season-btn-active")
            else:
                btn.remove_css_class("season-btn-active")

    def _clear_episodes(self):
        child = self.episodes_grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.episodes_grid.remove(child)
            child = nxt

    def _fill_episodes(self, season_key: str):
        self._clear_episodes()
        episodes = self.episode_seasons.get(season_key, [])
        self.episodes_label.set_visible(bool(episodes))
        for ep in episodes:
            btn = Gtk.Button(label=str(ep.episode))
            btn.add_css_class("episode-btn")
            btn.set_tooltip_text(ep.title or f"Episodio {ep.episode}")
            btn.connect("clicked", self._on_episode_clicked, season_key, ep)
            self.episodes_grid.append(btn)

    def _on_episode_clicked(self, _btn, season_key: str, ep: SeasonEpisode):
        item = self.item
        if item is None or self.busy:
            return
        provider = self.providers.get(item.provider)
        if provider is None:
            return
        self.busy = True
        self._set_status(f"Cargando servidores · T{season_key}E{ep.episode}…")
        generation = self._generation

        def worker():
            try:
                servers, default_url = provider.scrape_episode_servers(
                    item.type, item.slug, season_key, str(ep.episode))
                error = None
            except Exception as exc:
                servers, default_url = [], ""
                error = str(exc)
            GLib.idle_add(self._on_episode_servers, servers, default_url,
                          error, generation, ep)

        threading.Thread(target=worker, daemon=True).start()

    def _on_episode_servers(self, servers, default_url, error, generation, ep):
        self.busy = False
        if generation != self._generation:
            return False
        if error:
            self._set_status(f"Error: {error}")
            return False
        if not servers and default_url:
            servers = [ServerInfo(name="Embed", player_url=default_url)]
        if self.item is not None:
            self.item.servers = servers
        self._render_servers(servers)
        season_label = self.active_season or str(ep.season)
        self._set_status(
            f"T{season_label}E{ep.episode} · {len(servers)} servidor(es)")
        return False

    # -- servidores ----------------------------------------------------------
    def _clear_servers(self):
        child = self.servers_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.servers_box.remove(child)
            child = nxt

    def _render_servers(self, servers: list[ServerInfo]):
        self._clear_servers()
        if not servers:
            empty = Gtk.Label(label="Sin servidores disponibles")
            empty.add_css_class("module-hint")
            empty.set_xalign(0)
            self.servers_box.append(empty)
            return
        for server in servers:
            row = Gtk.Button()
            row.add_css_class("module-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            ic = Gtk.Label(label="▶")
            ic.add_css_class("module-icon")
            inner.append(ic)
            name = Gtk.Label(label=server.name or "Servidor")
            name.add_css_class("module-title")
            name.set_xalign(0)
            name.set_hexpand(True)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            inner.append(name)
            arrow = Gtk.Label(label="›")
            arrow.add_css_class("module-arrow")
            inner.append(arrow)
            row.set_child(inner)
            row.connect("clicked", self._on_server_clicked, server)
            self.servers_box.append(row)

    def _on_server_clicked(self, _btn, server: ServerInfo):
        self.selected_server = server
        self._set_status(f"Seleccionado: {server.name} · {server.player_url}")
        if self.on_server_selected:
            self.on_server_selected(self.item, server)

    # -- utilidades ----------------------------------------------------------
    on_server_selected = None  # phase 4: reproductor

    def _update_fav(self):
        if self.item is None:
            self.fav_btn.set_label("☆")
            return
        fav = self.store.is_favorite(self.item.provider, self.item.slug)
        self.fav_btn.set_label("★" if fav else "☆")

    def _on_fav_clicked(self, *_args):
        if self.item is None:
            return
        fav = self.store.toggle_favorite(self.item)
        self._update_fav()
        self._set_status(("★ Añadido a favoritos" if fav
                          else "☆ Eliminado de favoritos"))

    def _load_poster_async(self, url: str, generation: int):
        def worker():
            path = _download_poster(url)
            if path is None or generation != self._generation:
                return
            texture = _load_texture(path, POSTER_W, POSTER_H)
            if texture is None or generation != self._generation:
                return
            GLib.idle_add(self._apply_poster, texture)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_poster(self, texture: Gdk.Texture):
        self.poster.set_paintable(texture)
        return False

    def _set_status(self, text):
        self.status.set_text(text or "")
