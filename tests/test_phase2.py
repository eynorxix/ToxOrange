"""Test de la Fase 2: providers con fixtures, store y UI del catálogo."""
import base64
import json
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("GDK_BACKEND", "wayland")
ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(APP_DIR))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import main  # noqa: E402
from models import ContentItem  # noqa: E402
from providers import tioplus  # noqa: E402
from providers.lamovie import LaMovieProvider, post_to_item  # noqa: E402
from store import Store  # noqa: E402

failures = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- tioplus: parseo de seccion --------------------------------------------
section_html = (FIXTURES / "tioplus_section.html").read_text(encoding="utf-8")
items = tioplus.parse_articles(section_html, "pelicula")
check("tioplus: 3 articulos", len(items) == 3, str(len(items)))
check("tioplus: slug correcto", items[0].slug == "avatar-2", items[0].slug)
check("tioplus: type forzado", all(i.type == "pelicula" for i in items))
check("tioplus: poster absoluto",
      items[0].poster == "https://tioplus.app/uploads/posters/avatar2.jpg",
      items[0].poster)
items_auto = tioplus.parse_articles(section_html)
check("tioplus: type por href",
      [i.type for i in items_auto] == ["pelicula", "serie", "anime"],
      str([i.type for i in items_auto]))

# --- tioplus: decode de servidores ------------------------------------------
raw = base64.b64encode(b"localhost/embed/abc").decode()
decoded = tioplus.decode_server_b64(raw)
single = base64.b64encode(b"localhost/embed/abc").decode()
double = base64.b64encode(single.encode()).decode()
check("tioplus: decode server", decoded.endswith("/player/" + double), decoded)

# --- tioplus: scrape_detail con fetch falso ---------------------------------
detail_html = (FIXTURES / "tioplus_detail.html").read_text(encoding="utf-8")


def fake_detail_fetch(url):
    if "/pelicula/avatar-2" in url:
        return detail_html
    return None  # players: sin resolucion remota


provider = tioplus.TioPlusProvider(fetch=fake_detail_fetch)
detail = provider.scrape_detail("avatar-2", "pelicula")
check("tioplus: detail no nulo", detail is not None)
check("tioplus: detail titulo", detail.title == "Avatar 2", detail.title)
check("tioplus: detail anio", detail.year == "2022", detail.year)
check("tioplus: detail rating", detail.rating == "8.1", detail.rating)
check("tioplus: detail duracion", detail.duration == "192 min", detail.duration)
check("tioplus: NetU filtrado",
      all("NetU" not in s.name for s in detail.servers),
      str([s.name for s in detail.servers]))
check("tioplus: 2 servidores", len(detail.servers) == 2,
      str([s.name for s in detail.servers]))
check("tioplus: temporadas",
      "1" in detail.seasons and detail.seasons["1"][0].title == "Piloto")
check("tioplus: default player", bool(detail.default_player_url))

# seccion con fetch falso: pagina 1 ok, pagina 2 vacia
calls = []


def fake_section_fetch(url):
    calls.append(url)
    return section_html if len(calls) == 1 else None


sec_provider = tioplus.TioPlusProvider(fetch=fake_section_fetch)
section_items = sec_provider.scrape_section("pelicula")
check("tioplus: seccion corta en pagina vacia",
      len(section_items) == 3 and len(calls) == 2,
      f"items={len(section_items)} calls={len(calls)}")

# --- lamovie: listing y detail ----------------------------------------------
listing = json.loads((FIXTURES / "lamovie_listing.json").read_text(encoding="utf-8"))


def fake_json(url, headers=None):
    if "/listing/movies" in url:
        return listing
    if "/search" in url:
        return listing
    return None


lm = LaMovieProvider(fetch_json_fn=fake_json)
lm_items = lm.scrape_section("pelicula")
check("lamovie: 2 posts", len(lm_items) == 2, str(len(lm_items)))
check("lamovie: slug", lm_items[0].slug == "dune-2", lm_items[0].slug)
check("lamovie: poster relativo a absoluto",
      lm_items[0].poster
      == "https://lamovie.org/wp-content/uploads/uploads/2024/dune2.jpg",
      lm_items[0].poster)
check("lamovie: year", lm_items[0].year == "2024", lm_items[0].year)
check("lamovie: runtime", lm_items[0].duration == "166 min", lm_items[0].duration)
check("lamovie: genres por id",
      lm_items[0].genres == ["Acción", "Ciencia ficción"],
      str(lm_items[0].genres))
check("lamovie: search usa type fallback",
      lm.search("dune")[0].type == "pelicula")

# --- store ------------------------------------------------------------------
tmp = pathlib.Path(tempfile.mkdtemp())
store = Store(tmp / "cfg")
store.save_catalog("tioplus", "pelicula", items)
loaded = store.load_catalog("tioplus", "pelicula")
check("store: catalog roundtrip",
      len(loaded) == 3 and loaded[0].slug == "avatar-2")
check("store: fresco recien guardado",
      store.catalog_fresh("tioplus", "pelicula"))
check("store: favorito add/toggle",
      store.toggle_favorite(items[0]) is True
      and store.is_favorite("tioplus", "avatar-2")
      and store.toggle_favorite(items[0]) is False
      and not store.is_favorite("tioplus", "avatar-2"))
store.push_history(items[0])
check("store: historial", store.history()[0].slug == "avatar-2")

# models roundtrip
item = ContentItem(slug="x", title="X", genres=["a"], servers=detail.servers,
                   seasons=detail.seasons)
rt = ContentItem.from_dict(item.as_dict())
check("models: roundtrip seasons", rt.seasons["1"][0].title == "Piloto")
check("models: roundtrip servers", len(rt.servers) == len(item.servers))

# --- UI headless ------------------------------------------------------------
main.APP_ID = "net.local.gonty.test2"
main.STATE_PATH = tmp / "state.json"
app = main.GontyApp()
app.store = Store(tmp / "cfg2")


def run():
    app._load_css()
    app.window = app._build_window()
    app.window.present()

    def measure():
        check("catalog en stack", app.stack.get_visible_child_name() == "home")
        app.catalog.ensure_data = lambda: None  # sin red en el test
        app._navigate("catalog")
        check("navega a catalog",
              app.stack.get_visible_child_name() == "catalog",
              app.stack.get_visible_child_name())

        # render con items de fixture (sin red)
        fixture_items = [
            ContentItem(slug="a1", title="Película Uno", type="pelicula",
                        year="2020", rating="7.1", poster="",
                        provider="tioplus"),
            ContentItem(slug="a2", title="Serie Dos", type="serie",
                        year="2021", provider="tioplus"),
            ContentItem(slug="a3", title="Anime Tres", type="anime",
                        provider="tioplus"),
        ]
        app.catalog.render(fixture_items)
        child = app.catalog.grid.get_first_child()
        count = 0
        while child is not None:
            count += 1
            child = child.get_next_sibling()
        check("grid con 3 cards", count == 3, str(count))

        # _on_section_done guarda cache + actualiza estado
        app.catalog._on_section_done(
            app.catalog._generation, "tioplus", "", fixture_items, None)
        check("status con datos", "3 títulos" in app.catalog.status.get_text(),
              app.catalog.status.get_text())
        check("cache guardada en store",
              len(app.store.load_catalog("tioplus", "pelicula")) == 1
              and len(app.store.load_catalog("tioplus", "serie")) == 1)

        # toggle favorito via store (sin on_open: click alterna fav)
        app.catalog.on_open = None
        app.catalog._on_card_pressed(None, 0, 0, 0, fixture_items[0])
        check("card click alterna favorito",
              app.store.is_favorite("tioplus", "a1"))
        check("status refleja favorito",
              app.catalog.status.get_text().startswith("★"),
              app.catalog.status.get_text())

        app.quit()
        return False

    GLib.timeout_add(300, measure)
    return False


GLib.idle_add(run)
app.run(["test"])

if failures:
    print(f"\n{len(failures)} fallo(s): {failures}")
    raise SystemExit(1)
print("\nFase 2: todos los checks OK")
