"""Página Catálogo: grid responsivo con posters, búsqueda y cache JSON."""
from __future__ import annotations

import hashlib
import threading
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

from models import ContentItem  # noqa: E402
from providers import build_registry  # noqa: E402
from providers.base import DEFAULT_HEADERS  # noqa: E402
from store import Store  # noqa: E402

POSTER_DIR = Path.home() / ".cache" / "gonty" / "posters"
CARD_WIDTH = 148
POSTER_HEIGHT = 222
MAX_PAGES = 50
TODO_PAGES = 4
TYPE_LABELS = {
    "": "Todo",
    "pelicula": "Películas",
    "serie": "Series",
    "anime": "Animes",
    "dorama": "Doramas",
}


def _poster_cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return POSTER_DIR / f"{digest}.jpg"


def _download_poster(url: str) -> Path | None:
    path = _poster_cache_path(url)
    if path.exists() and path.stat().st_size > 0:
        return path
    request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read()
    except Exception:
        return None
    if not data:
        return None
    try:
        POSTER_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        return None
    return path


def _load_texture(path: Path, width: int = CARD_WIDTH,
                  height: int = POSTER_HEIGHT) -> Gdk.Texture | None:
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(path), width, height, True)
    except Exception:
        return None
    return Gdk.Texture.new_for_pixbuf(pixbuf)


class CatalogPage(Gtk.Box):
    """Pagina del Stack con el catalogo scrapeado."""

    def __init__(self, store: Store, on_open=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.store = store
        self.on_open = on_open
        self.providers = build_registry()
        self.provider_ids = list(self.providers.keys())
        self.items: list[ContentItem] = []
        self.busy = False
        self._generation = 0

        self.append(self._build_toolbar())

        self.status = Gtk.Label(label="")
        self.status.add_css_class("catalog-status")
        self.status.set_xalign(0)
        self.status.set_margin_start(14)
        self.status.set_margin_end(14)
        self.append(self.status)

        self.grid = Gtk.FlowBox()
        self.grid.set_valign(Gtk.Align.START)
        self.grid.set_homogeneous(True)
        self.grid.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.grid.set_min_children_per_line(1)
        self.grid.set_max_children_per_line(12)
        self.grid.set_column_spacing(10)
        self.grid.set_row_spacing(10)
        self.grid.set_margin_start(14)
        self.grid.set_margin_end(14)
        self.grid.set_margin_top(6)
        self.grid.set_margin_bottom(14)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.grid)
        self.append(scroll)

        self._set_status("Selecciona un proveedor y pulsa Actualizar.")

    # -- toolbar -------------------------------------------------------------
    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("catalog-toolbar")
        bar.set_margin_start(14)
        bar.set_margin_end(14)
        bar.set_margin_top(10)

        self.provider_down = Gtk.DropDown.new_from_strings(self.provider_ids)
        self.provider_down.set_valign(Gtk.Align.CENTER)
        self.provider_down.connect("notify::selected", self._on_provider_changed)
        bar.append(self.provider_down)

        self.type_down = Gtk.DropDown.new_from_strings(["Todo"])
        self.type_down.set_valign(Gtk.Align.CENTER)
        bar.append(self.type_down)

        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Buscar…")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("activate", self._on_search)
        bar.append(self.search_entry)

        search_btn = Gtk.Button(label="Buscar")
        search_btn.add_css_class("flat")
        search_btn.connect("clicked", self._on_search)
        bar.append(search_btn)

        refresh = Gtk.Button(label="↻ Actualizar")
        refresh.add_css_class("primary")
        refresh.connect("clicked", lambda *_: self.load_section(force=True))
        bar.append(refresh)

        self._sync_type_options()
        return bar

    def _current_provider_id(self) -> str:
        index = self.provider_down.get_selected()
        if 0 <= index < len(self.provider_ids):
            return self.provider_ids[index]
        return self.provider_ids[0]

    def _current_type(self) -> str:
        index = self.type_down.get_selected()
        strings = self._type_strings()
        if 0 <= index < len(strings):
            return strings[index]
        return ""

    def _type_strings(self) -> list[str]:
        provider = self.providers.get(self._current_provider_id())
        types = [""] + list(provider.supported_types) if provider else [""]
        return types

    def _sync_type_options(self):
        strings = [TYPE_LABELS.get(t, t) for t in self._type_strings()]
        self.type_down.set_model(Gtk.StringList.new(strings))
        self.type_down.set_selected(1 if len(strings) > 1 else 0)

    def _on_provider_changed(self, *_args):
        self._sync_type_options()
        self.load_section(force=True)

    # -- datos ---------------------------------------------------------------
    def ensure_data(self):
        """Muestra cache si es fresca; si no, scrapea."""
        provider_id = self._current_provider_id()
        type_ = self._current_type()
        cached = self.store.load_catalog(provider_id, type_)
        if cached and self.store.catalog_fresh(provider_id, type_):
            self.render(cached)
            self._set_status(f"{len(cached)} títulos · cache local")
            return
        if cached:
            self.render(cached)
        self.load_section()

    def load_section(self, force: bool = False):
        provider_id = self._current_provider_id()
        type_ = self._current_type()
        if not force and self.store.catalog_fresh(provider_id, type_):
            return
        provider = self.providers.get(provider_id)
        if provider is None:
            return
        self._generation += 1
        gen = self._generation
        self.busy = True
        self._clear_grid()
        self.items = []
        self._set_status(f"Scraping {provider_id}"
                         f"{' · ' + type_ if type_ else ''}…")
        types = list(provider.supported_types) if not type_ else [type_]
        pages = TODO_PAGES if not type_ else MAX_PAGES

        def on_page(items, page, t):
            GLib.idle_add(self._on_page_items, gen, provider_id, t, page,
                          list(items))

        def worker():
            collected: list[ContentItem] = []
            error = None
            try:
                for t in types:
                    def cb(items, page, _t=t):
                        collected.extend(items)
                        on_page(items, page, _t)
                    provider.scrape_section(t, max_pages=pages, on_page=cb)
            except Exception as exc:  # aislamiento de fallos por provider
                error = str(exc)
            GLib.idle_add(self._on_section_done, gen, provider_id, type_,
                          collected, error)

        threading.Thread(target=worker, daemon=True).start()

    def _on_page_items(self, gen, provider_id, type_, page, items):
        """Muestra cada pagina en cuanto llega (hilo de UI)."""
        if gen != self._generation:
            return False
        added = self._append_items(items, loading=True)
        self._save_cache(provider_id, type_)
        if added and page == 1:
            self._set_status(
                f"{len(self.items)} títulos · cargando el resto…")
        return False

    def _save_cache(self, provider_id, type_):
        if not self.items:
            return
        if type_:
            self.store.save_catalog(provider_id, type_, self.items)
            return
        self.store.save_catalog(provider_id, "", self.items)
        for t in {i.type for i in self.items}:
            subset = [i for i in self.items if i.type == t]
            if subset:
                self.store.save_catalog(provider_id, t, subset)

    def _on_section_done(self, gen, provider_id, type_, items, error):
        if gen != self._generation:
            return False
        self.busy = False
        self._save_cache(provider_id, type_)
        if not self.items and error:
            self._set_status(f"Error: {error}")
            return False
        note = f" · error: {error}" if error else ""
        self._set_status(f"{len(self.items)} títulos · {provider_id}{note}")
        return False

    def _on_search(self, *_args):
        query = self.search_entry.get_text().strip()
        if not query or self.busy:
            return
        provider = self.providers.get(self._current_provider_id())
        if provider is None:
            return
        self.busy = True
        self._set_status(f"Buscando «{query}»…")

        def worker():
            try:
                results = provider.search(query)
                error = None
            except Exception as exc:
                results = []
                error = str(exc)
            GLib.idle_add(self._on_search_done, results, error)

        threading.Thread(target=worker, daemon=True).start()

    def _on_search_done(self, results, error):
        self.busy = False
        if error:
            self._set_status(f"Error: {error}")
            return False
        self.render(results)
        self._set_status(f"{len(results)} resultados")
        return False

    def _set_status(self, text):
        self.status.set_text(text or "")

    # -- grid ----------------------------------------------------------------
    def render(self, items: list[ContentItem]):
        self._generation += 1
        self._clear_grid()
        self.items = []
        self._append_items(list(items), loading=False)
        if not self.items:
            self._set_status("Sin resultados")
        else:
            self._set_status(f"{len(self.items)} títulos")

    def _clear_grid(self):
        child = self.grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt

    def _append_items(self, items: list[ContentItem], loading: bool) -> int:
        """Anade tarjetas evitando duplicados; devuelve cuantas anadio."""
        seen = {(i.provider, i.slug) for i in self.items}
        jobs: dict[Gtk.Picture, str] = {}
        added = 0
        for item in items:
            key = (item.provider, item.slug)
            if key in seen:
                continue
            seen.add(key)
            self.items.append(item)
            child = self._build_card(item)
            self.grid.append(child)
            picture = getattr(child.get_child(), "_poster_picture", None)
            if picture is not None and item.poster:
                jobs[picture] = item.poster
            added += 1
        if jobs:
            self._load_posters_async(self._generation, jobs)
        if added and loading:
            self._set_status(f"{len(self.items)} títulos · cargando…")
        return added

    def _build_card(self, item: ContentItem) -> Gtk.FlowBoxChild:
        child = Gtk.FlowBoxChild()
        child.add_css_class("catalog-card")
        child.set_child(self._build_card_box(item))
        child.item = item  # type: ignore[attr-defined]
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_card_pressed, item)
        child.add_controller(click)
        try:
            child.set_cursor_from_name("pointer")
        except Exception:
            pass
        return child

    def _build_card_box(self, item: ContentItem) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(CARD_WIDTH, -1)

        picture = Gtk.Picture()
        picture.set_size_request(CARD_WIDTH, POSTER_HEIGHT)
        picture.add_css_class("poster")
        if hasattr(picture, "set_content_fit"):
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        box.append(picture)
        box._poster_picture = picture  # type: ignore[attr-defined]

        title = Gtk.Label(label=item.title or "(sin título)")
        title.add_css_class("card-title")
        title.set_xalign(0)
        title.set_wrap(True)
        title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title.set_max_width_chars(1)
        title.set_lines(2)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(title)

        parts = [TYPE_LABELS.get(item.type, item.type)]
        if item.year:
            parts.append(item.year)
        if item.rating:
            parts.append(f"★ {item.rating}")
        meta = Gtk.Label(label=" · ".join(p for p in parts if p))
        meta.add_css_class("card-meta")
        meta.set_xalign(0)
        meta.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(meta)

        return box

    def _on_card_pressed(self, _gesture, _n, _x, _y, item: ContentItem):
        if self.on_open is not None:
            self.on_open(item)
            return
        fav = self.store.toggle_favorite(item)
        mark = "★" if fav else "☆"
        self._set_status(f"{mark} {item.title} · {item.provider}/{item.slug}")

    def _load_posters_async(self, generation: int,
                            jobs: dict[Gtk.Picture, str] | None = None):
        jobs = dict(jobs if jobs is not None else {})
        if not jobs:
            return

        def worker():
            for picture, url in jobs.items():
                if generation != self._generation:
                    return
                path = _download_poster(url)
                if path is None or generation != self._generation:
                    continue
                texture = _load_texture(path)
                if texture is None or generation != self._generation:
                    continue
                GLib.idle_add(self._apply_texture, picture, texture)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_texture(self, picture: Gtk.Picture, texture: Gdk.Texture):
        picture.set_paintable(texture)
        return False
