"""Test de la Fase 4: reproductor (resolución de stream + página GTK4)."""
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("GDK_BACKEND", "wayland")
ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import main  # noqa: E402
from models import ContentItem, ServerInfo  # noqa: E402
from player.stream import (  # noqa: E402
    find_media_in_html, looks_like_media, resolve_stream_url,
)
from store import Store  # noqa: E402

failures = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- resolucion de streams (unitario) ---------------------------------------
check("looks_like_media m3u8", looks_like_media("https://x/y/master.m3u8?t=1"))
check("looks_like_media mp4", looks_like_media("https://x/y/video.mp4"))
check("looks_like_media pagina falsa", not looks_like_media("https://x/embed/1"))
check("find_media_in_html",
      find_media_in_html('<iframe src="https://cdn.test/a.m3u8"></iframe>')
      == "https://cdn.test/a.m3u8")


class _FakeProvider:
    def __init__(self, embed):
        self._embed = embed

    def get_embed_url(self, _player_url):
        return self._embed


check("resolve directo",
      resolve_stream_url(_FakeProvider("x"), "https://cdn/live.mp4")
      == "https://cdn/live.mp4")
check("resolve via embed",
      resolve_stream_url(_FakeProvider("https://cdn/live/master.m3u8"),
                         "https://site.test/watch/1")
      == "https://cdn/live/master.m3u8")
check("resolve via probe HTML",
      resolve_stream_url(
          _FakeProvider("https://site.test/embed/1"),
          "https://site.test/watch/1",
          fetch=lambda url: '<video src="https://cdn.hls/master.m3u8?x=1"></video>')
      == "https://cdn.hls/master.m3u8?x=1")

# --- UI headless ------------------------------------------------------------
tmp = pathlib.Path(tempfile.mkdtemp())
main.APP_ID = "net.local.gonty.test4"
main.STATE_PATH = tmp / "state.json"
app = main.GontyApp()
app.store = Store(tmp / "cfg")


class _UiProvider(_FakeProvider):
    pass


ui_provider = _UiProvider("https://cdn.test/stream.m3u8")


def run():
    app._load_css()
    app.window = app._build_window()
    app.window.present()
    app.catalog.ensure_data = lambda: None
    app.player.providers["tioplus"] = ui_provider

    item = ContentItem(slug="avatar-2", title="Avatar 2", type="pelicula",
                       provider="tioplus")
    server = ServerInfo(name="Fembed", player_url="https://tioplus.app/player/abc")

    def measure():
        app._play_server(item, server)
        check("navega a player",
              app.stack.get_visible_child_name() == "player",
              app.stack.get_visible_child_name())
        check("historial registrado",
              any(h.slug == "avatar-2" for h in app.store.history()))
        check("widget de video embebido",
              app.player.video_stack.get_child_by_name("gst")
              is app.player.engine.widget)
        check("motor GStreamer listo",
              app.player.engine._using_paintable or isinstance(
                  app.player.engine.widget, Gtk.Video))
        if app.player.webview is not None:
            check("motor WebKit presente",
                  app.player.video_stack.get_child_by_name("web")
                  is app.player.webview.widget)
        uses_web = app.player.webview is not None
        check("controles presentes",
              app.player.play_btn is not None and app.player.seek is not None)

        polls = {"n": 0}

        def wait_done():
            polls["n"] += 1
            status = app.player.status.get_text().lower()
            done = ("reproduc" in status) or ("error" in status) or polls["n"] > 20
            if not done:
                return True
            if uses_web:
                check("embed cargado en WebKit",
                      "player/abc" in (app.player.webview.uri or ""),
                      app.player.webview.uri)
                check("seek deshabilitado en embed",
                      not app.player.seek.get_sensitive())
            else:
                check("seek habilitado tras resolver",
                      app.player.seek.get_sensitive())
                check("uri resuelto al stream",
                      app.player.engine.uri == "https://cdn.test/stream.m3u8",
                      app.player.engine.uri)
            check("boton externo habilitado",
                  app.player.external_btn.get_sensitive())
            check("url del stream guardada",
                  app.player.stream_url == "https://cdn.test/stream.m3u8")

            # Pantalla completa (boton propio / tecla F)
            app.player.toggle_fullscreen()
            check("fullscreen activa estado",
                  app.player.is_fullscreen())
            check("fullscreen oculta cromo",
                  not app.player.header.get_visible()
                  and not app.player.controls.get_visible())
            app.player.toggle_fullscreen()
            check("fullscreen sale y restaura cromo",
                  not app.player.is_fullscreen()
                  and app.player.header.get_visible()
                  and app.player.controls.get_visible())

            # Esc vuelve al detalle
            app._on_key(None, Gdk.KEY_Escape, 0, 0)
            check("Esc vuelve al detalle",
                  app.stack.get_visible_child_name() == "detail",
                  app.stack.get_visible_child_name())
            app.quit()
            return False

        GLib.timeout_add(200, wait_done)
        return False

    GLib.timeout_add(300, measure)
    return False


GLib.idle_add(run)
app.run(["test"])

if failures:
    print(f"\n{len(failures)} fallo(s): {failures}")
    raise SystemExit(1)
print("\nFase 4: todos los checks OK")
