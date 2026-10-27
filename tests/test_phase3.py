"""Test de la Fase 3: detalle, temporadas/episodios y servidores."""
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
from models import ContentItem, SeasonEpisode, ServerInfo  # noqa: E402
from providers import tioplus  # noqa: E402
from store import Store  # noqa: E402

failures = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- store: cache de detalles -----------------------------------------------
tmp = pathlib.Path(tempfile.mkdtemp())
store = Store(tmp / "cfg")
item = ContentItem(
    slug="avatar-2", title="Avatar 2", type="pelicula", provider="tioplus",
    description="Jake regresa.",
    servers=[ServerInfo(name="Fembed", player_url="https://p/1")],
    seasons={"1": [SeasonEpisode(title="Piloto", season=1, episode=1)]},
)
store.save_detail(item)
cached = store.load_detail("tioplus", "avatar-2")
check("store: detail roundtrip", cached is not None and cached.description == "Jake regresa.")
check("store: detail fresco", store.detail_fresh("tioplus", "avatar-2"))
check("store: detail servers roundtrip",
      cached is not None and cached.servers[0].name == "Fembed")
check("store: detail seasons roundtrip",
      cached is not None and cached.seasons["1"][0].title == "Piloto")

# --- provider tioplus con fixtures (detalle + episodio) ---------------------
detail_html = (FIXTURES / "tioplus_detail.html").read_text(encoding="utf-8")
episode_html = """<html><body>
<ul>
  <li data-server="bG9jYWxob3N0L2VwMSI=" data-lang="Lat"><span>Fembed</span></li>
  <li data-server="bG9jYWxob3N0L2VwMiI=" data-lang="Lat"><span>StreamTape</span></li>
</ul>
</body></html>"""


def fake_fetch(url):
    if "/pelicula/avatar-2" in url:
        return detail_html
    if "/episode/1" in url:
        return episode_html
    return None


fake_provider = tioplus.TioPlusProvider(fetch=fake_fetch)

# --- UI headless ------------------------------------------------------------
main.APP_ID = "net.local.gonty.test3"
main.STATE_PATH = tmp / "state.json"
app = main.GontyApp()
app.store = Store(tmp / "cfg2")


def run():
    app._load_css()
    app.window = app._build_window()
    app.window.present()
    app.detail.providers["tioplus"] = fake_provider
    app.catalog.ensure_data = lambda: None

    catalog_item = ContentItem(
        slug="avatar-2", title="Avatar 2", type="pelicula",
        poster="", provider="tioplus")

    def measure():
        # open_detail navega y arranca el scrape (thread)
        app._open_detail(catalog_item)
        check("navega a detail",
              app.stack.get_visible_child_name() == "detail",
              app.stack.get_visible_child_name())
        check("titulo en cabecera",
              "AVATAR" in app.detail.header_title.get_text(),
              app.detail.header_title.get_text())

        polls = {"n": 0}

        def wait_done():
            polls["n"] += 1
            status = app.detail.status.get_text()
            done = ("servidor" in status.lower()) or polls["n"] > 20
            if not done:
                return True
            check("detalle cargado (status)",
                  "servidor" in status.lower(), status)
            check("descripcion poblada",
                  "Pandora" in app.detail.description_lbl.get_text(),
                  app.detail.description_lbl.get_text())
            check("meta con rating",
                  "★ 8.1" in app.detail.meta_lbl.get_text(),
                  app.detail.meta_lbl.get_text())
            servers_child = app.detail.servers_box.get_first_child()
            check("lista de servidores no vacia", servers_child is not None)
            check("2 servidores renderizados",
                  app.store is not None
                  and len(app.detail.item.servers) == 2,
                  str(len(app.detail.item.servers)))
            check("cache de detalle guardada",
                  app.store.load_detail("tioplus", "avatar-2") is not None)

            # Temporadas: el fixture tiene la temporada 1 con Piloto
            check("temporadas visibles",
                  app.detail.season_keys == ["1"],
                  str(app.detail.season_keys))
            ep_row = app.detail.episodes_grid.get_first_child()
            check("episodio renderizado", ep_row is not None)

            # Clic en episodio → scrape_episode_servers del provider falso
            ep = SeasonEpisode(title="Piloto", season=1, episode=1)
            app.detail._on_episode_clicked(None, "1", ep)
            check("episodio dispara carga", app.detail.busy)

            def wait_episode():
                status = app.detail.status.get_text()
                if "E1" in status and "servidor" in status.lower():
                    check("servidores de episodio",
                          "2 servidor" in status, status)
                    # volver al catalogo via on_back del detail
                    app.detail._go_back()
                    check("vuelve a catalog",
                          app.stack.get_visible_child_name() == "catalog",
                          app.stack.get_visible_child_name())
                    app.quit()
                    return False
                if "E1" in status and app.detail.busy is False and "Error" in status:
                    check("servidores de episodio", False, status)
                    app.quit()
                    return False
                return True

            GLib.timeout_add(200, wait_episode)
            return False

        GLib.timeout_add(400, wait_done)
        return False

    GLib.timeout_add(300, measure)
    return False


GLib.idle_add(run)
app.run(["test"])

if failures:
    print(f"\n{len(failures)} fallo(s): {failures}")
    raise SystemExit(1)
print("\nFase 3: todos los checks OK")
