"""Test headless de la Fase 1: esqueleto GTK4 de Gonty."""
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("GDK_BACKEND", "wayland")
APP_DIR = pathlib.Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import main  # noqa: E402

main.APP_ID = "net.local.gonty.test"
main.STATE_PATH = pathlib.Path(tempfile.mkdtemp()) / "state.json"

failures = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


app = main.GontyApp()


def run():
    app._load_css()
    app.window = app._build_window()
    app.window.present()

    def measure():
        check("ventana presente", app.window is not None)
        check("window class", app.window.has_css_class("gonty-window"))

        check("stack existe", app.stack is not None)
        check("pagina home activa",
              app.stack.get_visible_child_name() == "home",
              app.stack.get_visible_child_name())

        check("panel oculto al inicio", not app.panel.get_visible())

        # Ctrl+S equivalente: mostrar panel
        app._show_panel()
        check("panel visible tras mostrar", app.panel.get_visible())

        w = app.window.get_width()
        h = app.window.get_height()
        check("ancho minimo", w >= 200, str(w))
        check("alto minimo", h >= 200, str(h))

        # Navegar a About
        app._navigate("about")
        check("navega a about",
              app.stack.get_visible_child_name() == "about",
              app.stack.get_visible_child_name())

        # Modulos no implementados caen a home; catalog ahora existe (Fase 2)
        app._navigate("nostr")
        check("nostr -> home",
              app.stack.get_visible_child_name() == "home")
        # Catalogo (Fase 2): pagina existe; sin red en este test
        app.catalog.ensure_data = lambda: None
        app._navigate("catalog")
        check("catalog pagina real",
              app.stack.get_visible_child_name() == "catalog",
              app.stack.get_visible_child_name())
        app._navigate("home")

        # Tema: cambiar y verificar que el provider recarga sin error
        app._set_theme("Dracula")
        check("tema Dracula activo", app.theme == "Dracula")
        app._set_theme(main.themes.DEFAULT_THEME)
        check("tema por defecto restaurado",
              app.theme == main.themes.DEFAULT_THEME)

        check("css provider cargado", app.tm.provider is not None)

        check("state path aislado", str(main.STATE_PATH).startswith(tempfile.gettempdir()))
        check("state.json existe", main.STATE_PATH.exists())

        app.quit()
        return False

    GLib.timeout_add(300, measure)
    return False


GLib.idle_add(run)
app.run(["test"])

if failures:
    print(f"\n{len(failures)} fallo(s): {failures}")
    raise SystemExit(1)
print("\nFase 1: todos los checks OK")
