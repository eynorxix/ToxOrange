#!/usr/bin/env python3
"""Gonty para escritorio: app de streaming / foro Nostr (GTK4 + Python).

Fase 1 (esqueleto): ventana sin marco, temas, Gtk.Stack con paginas
home/about y panel lateral de modulos (patron SidePanel del widget).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

BASE = Path(__file__).resolve().parent
CSS_PATH = BASE / "style.css"
APP_ID = "org.eynor.gonty"
STATE_PATH = Path.home() / ".config" / "gonty" / "state.json"
PANEL_WIDTH = 300

sys.path.insert(0, str(BASE))
import theme as themes  # noqa: E402
from store import Store  # noqa: E402
from ui.catalog import CatalogPage  # noqa: E402
from ui.detail import DetailPage  # noqa: E402
from ui.player_page import PlayerPage  # noqa: E402


def _load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(data):
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _edge(name):
    enum = getattr(Gdk, "SurfaceEdge", None) or getattr(Gdk, "WindowEdge", None)
    return getattr(enum, name)


def _clear(box):
    child = box.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


# --------------------------------------------------------------------------- #
# Panel lateral de modulos
# --------------------------------------------------------------------------- #
class SidePanel(Gtk.Box):
    """Lista de modulos que navega el Gtk.Stack principal de la ventana."""

    def __init__(self, on_navigate, on_hide):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.on_navigate = on_navigate
        self.on_hide = on_hide
        self.add_css_class("editor-panel")
        self.set_size_request(PANEL_WIDTH, -1)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("titlebar")
        title = Gtk.Label(label="MÓDULOS")
        title.add_css_class("titlebar-title")
        title.set_xalign(0)
        bar.append(title)
        sp = Gtk.Box()
        sp.set_hexpand(True)
        bar.append(sp)
        close = Gtk.Button(label="✕")
        close.add_css_class("icon-btn")
        close.set_tooltip_text("Ocultar (Ctrl+S)")
        close.connect("clicked", lambda *_: self.request_hide())
        bar.append(close)
        self.append(bar)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(14)
        box.set_margin_end(14)

        hint = Gtk.Label(label="Selecciona un módulo")
        hint.add_css_class("module-hint")
        hint.set_xalign(0)
        box.append(hint)

        self.module_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.module_list)
        self._add_module("⌂", "Inicio", "Panel principal de Gonty", "home")
        self._add_module("▶", "Catálogo",
                         "Películas, series y animes", "catalog")
        self._add_module("☰", "Foro Nostr",
                         "Feed y publicaciones (próximamente)", "nostr")
        self._add_module("?", "Acerca de", "Versión y créditos", "about")
        self.append(box)

    def _add_module(self, icon, name, subtitle, page):
        row = Gtk.Button()
        row.add_css_class("module-row")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ic = Gtk.Label(label=icon)
        ic.add_css_class("module-icon")
        inner.append(ic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        t = Gtk.Label(label=name)
        t.add_css_class("module-title")
        t.set_xalign(0)
        t.set_ellipsize(Pango.EllipsizeMode.END)
        t.set_max_width_chars(24)
        col.append(t)
        s = Gtk.Label(label=subtitle)
        s.add_css_class("module-sub")
        s.set_xalign(0)
        s.set_wrap(True)
        s.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        s.set_max_width_chars(30)
        col.append(s)
        inner.append(col)
        arrow = Gtk.Label(label="›")
        arrow.add_css_class("module-arrow")
        inner.append(arrow)
        row.set_child(inner)
        row.connect("clicked", self._on_clicked, page)
        self.module_list.append(row)
        return row

    def _on_clicked(self, _btn, page):
        self.on_navigate(page)

    def request_hide(self):
        self.set_visible(False)
        if self.on_hide:
            self.on_hide()


# --------------------------------------------------------------------------- #
# Aplicacion principal
# --------------------------------------------------------------------------- #
class GontyApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.stack = None
        self.panel = None
        self.catalog = None
        self.detail = None
        self.player = None
        self.store = Store()
        self.css_provider_holder = None
        state = _load_state()
        self.theme = state.get("theme", themes.DEFAULT_THEME)
        if self.theme not in themes.THEMES:
            self.theme = themes.DEFAULT_THEME
        self.transparent = bool(state.get("transparent", True))
        self.transparency = min(0.9, max(0.0, float(state.get("transparency", 0.18))))
        self.band = themes.normalize_band(state.get("band"))
        self.font_scale = min(themes.MAX_FONT_SCALE, max(
            themes.MIN_FONT_SCALE, float(state.get("font_scale", themes.DEFAULT_FONT_SCALE))))
        self.tm = themes.ThemeManager(CSS_PATH)
        self._trans_switch = None
        self._trans_scale = None
        self._font_scale = None
        self._font_value = None
        self._band_color_btns = {}
        self._band_solid = None
        self._band_gradient = None
        self._band_scale = None

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        self._sync_theme_manager()
        self._load_css()
        self.window = self._build_window()
        self.window.present()

    def _sync_theme_manager(self):
        self.tm.theme = self.theme
        self.tm.transparent = self.transparent
        self.tm.transparency = self.transparency
        self.tm.font_scale = self.font_scale
        self.tm.band = self.band

    def _load_css(self):
        self._sync_theme_manager()
        self.tm.load()

    def _set_theme(self, name):
        if name not in themes.THEMES:
            return
        self.theme = name
        state = _load_state()
        state["theme"] = name
        _save_state(state)
        self._load_css()

    # -- ventana ------------------------------------------------------------
    def _build_window(self):
        win = Gtk.ApplicationWindow(application=self, title="Gonty")
        state = _load_state()
        win.set_default_size(int(state.get("width", 960)), int(state.get("height", 620)))
        win.set_decorated(False)
        win.add_css_class("gonty-window")
        win.connect("close-request", self._on_window_close)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("card")
        root.set_vexpand(True)
        root.set_hexpand(True)
        root.append(self._build_header())

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.add_named(self._build_home_page(), "home")
        self.catalog = CatalogPage(self.store, on_open=self._open_detail)
        self.stack.add_named(self.catalog, "catalog")
        self.detail = DetailPage(self.store, on_back=lambda: self._navigate("catalog"))
        self.detail.on_server_selected = self._play_server
        self.stack.add_named(self.detail, "detail")
        self.player = PlayerPage(self.store, on_back=self._back_from_player)
        self.stack.add_named(self.player, "player")
        self.stack.add_named(self._build_about_page(), "about")
        body.append(self.stack)

        self.panel = SidePanel(self._navigate, self._on_panel_hide)
        self.panel.set_visible(False)
        body.append(self.panel)

        root.append(body)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("frame")
        frame.set_vexpand(True)
        frame.set_hexpand(True)
        frame.append(root)

        outer = Gtk.Overlay()
        outer.set_child(frame)
        self._add_resize_handles(outer)
        win.set_child(outer)

        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_key)
        win.add_controller(key)
        return win

    def _add_resize_handles(self, overlay):
        edges = [
            ("WEST", 5, -1, Gtk.Align.START, Gtk.Align.FILL, "ew-resize"),
            ("EAST", 5, -1, Gtk.Align.END, Gtk.Align.FILL, "ew-resize"),
            ("NORTH", -1, 6, Gtk.Align.FILL, Gtk.Align.START, "ns-resize"),
            ("SOUTH", -1, 6, Gtk.Align.FILL, Gtk.Align.END, "ns-resize"),
            ("NORTH_WEST", 14, 14, Gtk.Align.START, Gtk.Align.START, "nwse-resize"),
            ("NORTH_EAST", 14, 14, Gtk.Align.END, Gtk.Align.START, "nesw-resize"),
            ("SOUTH_WEST", 14, 14, Gtk.Align.START, Gtk.Align.END, "nesw-resize"),
            ("SOUTH_EAST", 14, 14, Gtk.Align.END, Gtk.Align.END, "nwse-resize"),
        ]
        for name, w, h, halign, valign, cursor_name in edges:
            handle = Gtk.Box()
            handle.set_size_request(w, h)
            handle.set_halign(halign)
            handle.set_valign(valign)
            try:
                handle.set_cursor(Gdk.Cursor.new_from_name(cursor_name, None))
            except Exception:
                pass
            gesture = Gtk.GestureClick()
            gesture.set_button(1)
            gesture.connect("pressed", self._on_resize_pressed, name)
            handle.add_controller(gesture)
            overlay.add_overlay(handle)

    def _on_resize_pressed(self, gesture, _n_press, x, y, edge_name):
        surface = self.window.get_surface()
        if surface is None or not hasattr(surface, "begin_resize"):
            return
        device = gesture.get_current_event_device()
        if device is None:
            return
        button = gesture.get_current_button() or 1
        try:
            ts = gesture.get_current_event_time()
        except Exception:
            ts = 0
        surface.begin_resize(_edge(edge_name), device, button, int(x), int(y), ts)

    # -- paginas ------------------------------------------------------------
    def _build_home_page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        logo = Gtk.Label(label="▶  GONTY")
        logo.add_css_class("home-logo")
        logo.set_xalign(0)
        box.append(logo)

        sub = Gtk.Label(label="Streaming y foro Nostr · versión de escritorio")
        sub.add_css_class("home-sub")
        sub.set_xalign(0)
        box.append(sub)

        status = Gtk.Label(label="Fase 4 · reproductor GStreamer embebido. "
                                 "El foro Nostr llegará en la Fase 6.")
        status.add_css_class("module-hint")
        status.set_xalign(0)
        status.set_wrap(True)
        status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.append(status)

        open_catalog = Gtk.Button(label="Abrir catálogo")
        open_catalog.add_css_class("primary")
        open_catalog.set_halign(Gtk.Align.START)
        open_catalog.connect("clicked", lambda *_: self._navigate("catalog"))
        box.append(open_catalog)

        open_modules = Gtk.Button(label="Módulos (Ctrl+S)")
        open_modules.add_css_class("flat")
        open_modules.set_halign(Gtk.Align.START)
        open_modules.connect("clicked", lambda *_: self._show_panel())
        box.append(open_modules)

        scroll.set_child(box)
        return scroll

    def _build_about_page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        title = Gtk.Label(label="ACERCA DE")
        title.add_css_class("titlebar-title")
        title.set_xalign(0)
        box.append(title)

        for line in (
            "Gonty — app de escritorio para KDE/Linux",
            "Python 3 + GTK4 (PyGObject) + CSS",
            "Basada en el patrón del widget de notas",
            "Stack: catálogo con scraping, reproductor GStreamer, foro Nostr",
        ):
            lbl = Gtk.Label(label=line)
            lbl.add_css_class("json-string")
            lbl.set_xalign(0)
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            box.append(lbl)

        version = Gtk.Label(label="v0.1.0-fase4")
        version.add_css_class("days-none")
        version.set_xalign(0)
        box.append(version)

        scroll.set_child(box)
        return scroll

    # -- header -------------------------------------------------------------
    def _build_header(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("titlebar")

        dot = Gtk.Label(label="●")
        dot.add_css_class("titlebar-dot")
        bar.append(dot)

        title = Gtk.Label(label="GONTY")
        title.add_css_class("titlebar-title")
        title.set_xalign(0)
        bar.append(title)

        sp = Gtk.Box()
        sp.set_hexpand(True)
        bar.append(sp)

        bar.append(self._build_font_button())
        bar.append(self._build_band_button())
        bar.append(self._build_transparency_button())
        bar.append(self._build_theme_button())

        modules = Gtk.Button(label="☰")
        modules.add_css_class("icon-btn")
        modules.set_tooltip_text("Módulos (Ctrl+S)")
        modules.connect("clicked", lambda *_: self._toggle_panel())
        bar.append(modules)

        help_btn = Gtk.Button(label="?")
        help_btn.add_css_class("icon-btn")
        help_btn.set_tooltip_text(
            "Atajos de teclado\n"
            "Ctrl+S   abrir / cerrar módulos\n"
            "Esc      volver (reproductor → detalle → catálogo → inicio)\n"
            "Espacio  reproducir / pausar\n"
            "←  →     retroceder / avanzar 10 s\n"
            "Ctrl+Q   salir del todo"
        )
        bar.append(help_btn)

        close = Gtk.Button(label="✕")
        close.add_css_class("icon-btn")
        close.set_tooltip_text("Cerrar")
        close.connect("clicked", lambda *_: self.window.close())
        bar.append(close)

        handle = Gtk.WindowHandle()
        handle.set_child(bar)
        return handle

    def _build_theme_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Cambiar tema")
        menu.set_child(Gtk.Label(label="◑"))
        menu.set_popover(self._build_theme_popover())
        return menu

    def _build_theme_popover(self):
        popover = Gtk.Popover()
        popover.add_css_class("theme-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for margin in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{margin}")(6)
        for name in themes.THEMES:
            btn = Gtk.Button(label=name)
            btn.add_css_class("theme-item")
            if name == self.theme:
                btn.add_css_class("theme-item-active")
            btn.connect("clicked", self._on_theme_clicked, name, box, popover)
            box.append(btn)
        popover.set_child(box)
        return popover

    def _on_theme_clicked(self, btn, name, box, popover):
        self._set_theme(name)
        child = box.get_first_child()
        while child is not None:
            child.remove_css_class("theme-item-active")
            child = child.get_next_sibling()
        btn.add_css_class("theme-item-active")
        popover.popdown()

    def _build_transparency_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Transparencia")
        menu.set_child(Gtk.Label(label="◌"))
        menu.set_popover(self._build_transparency_popover())
        return menu

    def _build_transparency_popover(self):
        popover = Gtk.Popover()
        popover.add_css_class("theme-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_size_request(220, -1)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label="Transparente")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        row.append(lbl)
        self._trans_switch = Gtk.Switch()
        self._trans_switch.set_active(self.transparent)
        self._trans_switch.set_valign(Gtk.Align.CENTER)
        self._trans_switch.connect("state-set", self._on_transparent_toggle)
        row.append(self._trans_switch)
        box.append(row)

        scale_lbl = Gtk.Label(label="NIVEL DE TRANSPARENCIA")
        scale_lbl.add_css_class("field-label")
        scale_lbl.set_xalign(0)
        box.append(scale_lbl)

        self._trans_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 90, 1)
        self._trans_scale.set_digits(0)
        self._trans_scale.set_draw_value(True)
        self._trans_scale.set_hexpand(True)
        self._trans_scale.set_value(round(self.transparency * 100))
        self._trans_scale.set_sensitive(self.transparent)
        self._trans_scale.connect("value-changed", self._on_transparency_changed)
        box.append(self._trans_scale)

        popover.set_child(box)
        return popover

    def _on_transparent_toggle(self, _switch, state):
        self.transparent = bool(state)
        if self._trans_scale is not None:
            self._trans_scale.set_sensitive(self.transparent)
        self._save_visual()
        self._load_css()
        return False

    def _on_transparency_changed(self, scale):
        self.transparency = min(0.9, max(0.0, scale.get_value() / 100.0))
        self._save_visual()
        self._load_css()

    def _build_font_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Tamaño de fuente")
        menu.set_child(Gtk.Label(label="A"))
        menu.set_popover(self._build_font_popover())
        return menu

    def _build_font_popover(self):
        popover = Gtk.Popover()
        popover.add_css_class("theme-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_size_request(230, -1)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label="TAMAÑO DE FUENTE")
        lbl.add_css_class("field-label")
        lbl.set_xalign(0)
        lbl.set_hexpand(True)
        head.append(lbl)
        self._font_value = Gtk.Label(label=f"{round(self.font_scale * 100)}%")
        self._font_value.set_xalign(1)
        head.append(self._font_value)
        box.append(head)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        smaller = Gtk.Button(label="A-")
        smaller.add_css_class("flat")
        smaller.connect("clicked", lambda *_: self._nudge_font(-0.1))
        row.append(smaller)
        self._font_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            themes.MIN_FONT_SCALE * 100, themes.MAX_FONT_SCALE * 100, 5)
        self._font_scale.set_digits(0)
        self._font_scale.set_draw_value(False)
        self._font_scale.set_hexpand(True)
        self._font_scale.set_valign(Gtk.Align.CENTER)
        self._font_scale.set_value(round(self.font_scale * 100))
        self._font_scale.connect("value-changed", self._on_font_scale_changed)
        row.append(self._font_scale)
        bigger = Gtk.Button(label="A+")
        bigger.add_css_class("flat")
        bigger.connect("clicked", lambda *_: self._nudge_font(0.1))
        row.append(bigger)
        box.append(row)

        reset = Gtk.Button(label="Restablecer")
        reset.add_css_class("flat")
        reset.connect(
            "clicked", lambda *_: self._set_font_scale(themes.DEFAULT_FONT_SCALE))
        box.append(reset)

        popover.set_child(box)
        return popover

    def _nudge_font(self, delta):
        self._set_font_scale(round(self.font_scale + delta, 2))

    def _set_font_scale(self, value):
        value = min(themes.MAX_FONT_SCALE, max(themes.MIN_FONT_SCALE, value))
        self.font_scale = value
        if self._font_scale is not None:
            self._font_scale.set_value(round(value * 100))
        if self._font_value is not None:
            self._font_value.set_text(f"{round(value * 100)}%")
        self._save_visual()
        self._load_css()

    def _on_font_scale_changed(self, scale):
        value = min(themes.MAX_FONT_SCALE, max(
            themes.MIN_FONT_SCALE, scale.get_value() / 100.0))
        self.font_scale = round(value, 2)
        if self._font_value is not None:
            self._font_value.set_text(f"{round(self.font_scale * 100)}%")
        self._save_visual()
        self._load_css()

    def _build_band_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Margen / franja de color")
        menu.set_child(Gtk.Label(label="▣"))
        menu.set_popover(self._build_band_popover())
        return menu

    def _build_band_popover(self):
        popover = Gtk.Popover()
        popover.add_css_class("theme-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_size_request(240, -1)

        box.append(self._field_label("ESTILO"))
        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._band_solid = Gtk.ToggleButton(label="Sólido")
        self._band_gradient = Gtk.ToggleButton(label="Degradado")
        self._band_gradient.set_group(self._band_solid)
        self._band_solid.set_active(self.band["mode"] == "solid")
        self._band_gradient.set_active(self.band["mode"] == "gradient")
        self._band_solid.connect("toggled", self._on_band_mode, "solid")
        self._band_gradient.connect("toggled", self._on_band_mode, "gradient")
        mode_row.append(self._band_solid)
        mode_row.append(self._band_gradient)
        box.append(mode_row)

        for key, text in (("c1", "COLOR 1"), ("c2", "COLOR 2"), ("c3", "COLOR 3")):
            box.append(self._field_label(text))
            btn = Gtk.ColorDialogButton.new(Gtk.ColorDialog())
            btn.set_rgba(themes.hex_to_rgba(self.band[key]))
            btn.connect("notify::rgba", self._on_band_color, key)
            box.append(btn)
            self._band_color_btns[key] = btn

        box.append(self._field_label("GROSOR (px)"))
        self._band_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 30, 1)
        self._band_scale.set_value(self.band["width"])
        self._band_scale.set_digits(0)
        self._band_scale.set_draw_value(True)
        self._band_scale.set_hexpand(True)
        self._band_scale.connect("value-changed", self._on_band_width)
        box.append(self._band_scale)

        self._update_band_sensitivity()
        popover.set_child(box)
        return popover

    @staticmethod
    def _field_label(text):
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("field-label")
        lbl.set_xalign(0)
        return lbl

    def _update_band_sensitivity(self):
        gradient = self.band["mode"] == "gradient"
        for key, btn in self._band_color_btns.items():
            btn.set_sensitive(True if key == "c1" else gradient)

    def _on_band_mode(self, btn, mode):
        if not btn.get_active():
            return
        self.band["mode"] = mode
        self._update_band_sensitivity()
        self._save_visual()
        self._load_css()

    def _on_band_color(self, btn, _pspec, key):
        self.band[key] = themes.rgba_to_hex(btn.get_rgba())
        self._save_visual()
        self._load_css()

    def _on_band_width(self, scale):
        self.band["width"] = int(round(scale.get_value()))
        self._save_visual()
        self._load_css()

    def _save_visual(self):
        state = _load_state()
        state.update(
            theme=self.theme,
            transparent=self.transparent,
            transparency=round(self.transparency, 3),
            font_scale=round(self.font_scale, 3),
            band=dict(self.band),
        )
        _save_state(state)

    # -- navegacion / panel --------------------------------------------------
    def _open_detail(self, item):
        if self.player is not None:
            self.player.stop_playback()
        self.stack.set_visible_child_name("detail")
        self.detail.load_item(item)

    def _play_server(self, item, server):
        if item is None or server is None:
            return
        self.stack.set_visible_child_name("player")
        self.player.play_item(item, server)

    def _back_from_player(self):
        self.player.stop_playback()
        self._navigate("detail")

    def _navigate(self, page):
        if page == "nostr":
            page = "home"  # Fase 6
        if page != "player" and self.player is not None:
            self.player.stop_playback()
        self.stack.set_visible_child_name(page)
        if page == "catalog" and self.catalog is not None:
            self.catalog.ensure_data()
        self._remember_size()

    def _toggle_panel(self):
        if self.panel.get_visible():
            self.panel.request_hide()
        else:
            self._show_panel()

    def _show_panel(self):
        self.panel.set_visible(True)

    def _on_panel_hide(self):
        self._remember_size()

    # -- teclado ------------------------------------------------------------
    def _on_key(self, _ctrl, keyval, _code, state):
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        lower = Gdk.keyval_to_lower(keyval)
        panel_visible = self.panel is not None and self.panel.get_visible()

        if ctrl and lower == Gdk.KEY_s:
            self._toggle_panel()
            return True
        if ctrl and lower == Gdk.KEY_q:
            self._quit()
            return True
        page = self.stack.get_visible_child_name()
        if page == "player" and not ctrl:
            if keyval == Gdk.KEY_space:
                self.player.toggle()
                return True
            if lower == Gdk.KEY_f:
                self.player.toggle_fullscreen()
                return True
            if keyval == Gdk.KEY_Left:
                self.player.engine.seek_relative(-10)
                return True
            if keyval == Gdk.KEY_Right:
                self.player.engine.seek_relative(10)
                return True
        if keyval == Gdk.KEY_Escape:
            if self.player is not None and self.player.is_fullscreen():
                self.player.exit_fullscreen()
                return True
            if self.window.is_fullscreen():
                self.window.unfullscreen()
                return True
            if panel_visible:
                self.panel.request_hide()
                return True
            if page == "player":
                self._back_from_player()
            elif page == "detail":
                self._navigate("catalog")
            elif page == "catalog":
                self._navigate("home")
            return True
        _ = shift
        return False

    # -- ciclo de vida --------------------------------------------------------
    def _remember_size(self):
        if self.window is None:
            return
        if self.window.is_maximized() or self.window.is_fullscreen():
            return
        width = self.window.get_width()
        height = self.window.get_height()
        if width < 200 or height < 200:
            return
        state = _load_state()
        state["width"] = width
        state["height"] = height
        _save_state(state)

    def _on_window_close(self, *_args):
        self._remember_size()
        if self.player is not None:
            self.player.stop_playback()
        if self.window is not None:
            self.window.set_visible(False)
        return True

    def _quit(self):
        self._remember_size()
        if self.player is not None:
            self.player.stop_playback()
        self.quit()


def main():
    app = GontyApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
