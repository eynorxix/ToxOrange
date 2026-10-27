#!/usr/bin/env python3
"""Widget de notas / recordatorios para el escritorio (GTK4 + Wayland).

- Guarda cada recordatorio como .md (frontmatter JSON) en ~/Documents/Notes.
- Cada fila tiene 4 columnas: [check]=borrar  [tarea]  [expandir]  [editar].
- Cada fila muestra: titulo, luego fecha+hora y lo que falta (color segun
  urgencia), luego la materia (Moodle). Al expandir (Enter o clic) se revela
  la descripcion.
- La fecha limite se elige con un calendario y la hora con un reloj (spin).
- Estetica terminal transparente estilo Omarchy, con temas y control de
  transparencia (botones en la barra superior).
"""
from __future__ import annotations

import json
import re
import sys
import threading
from datetime import date, datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moodle_module as moodle  # noqa: E402
import notes_core as core  # noqa: E402

BASE = Path(__file__).resolve().parent
CSS_PATH = BASE / "style.css"
APP_ID = "org.eynor.noteswidget"
STATE_PATH = Path.home() / ".config" / "noteswidget" / "state.json"
PANEL_WIDTH = 300

# --------------------------------------------------------------------------- #
# Temas (paletas). Cada tema define los colores que style.css consume via
# @define-color. El conjunto completo se inyecta en un solo CssProvider para
# que los nombres de color resuelvan correctamente.
# --------------------------------------------------------------------------- #
THEMES = {
    "Tokyo Night": {
        "bg": "rgba(20, 22, 34, 0.82)",
        "bg_soft": "rgba(30, 33, 48, 0.55)",
        "bg_hover": "rgba(41, 46, 66, 0.72)",
        "panel_bg": "rgba(20, 22, 34, 0.97)",
        "input_bg": "rgba(15, 17, 26, 0.75)",
        "fg": "#c8d3f5",
        "muted": "#7f87a7",
        "accent": "#7aa2f7",
        "accent_hover": "#93b4f9",
        "on_accent": "#1a1b26",
        "green": "#9ece6a",
        "yellow": "#e0af68",
        "red": "#f7768e",
        "border": "rgba(122, 162, 247, 0.25)",
    },
    "Matte Black": {
        "bg": "rgba(18, 18, 18, 0.88)",
        "bg_soft": "rgba(28, 28, 28, 0.60)",
        "bg_hover": "rgba(38, 38, 38, 0.75)",
        "panel_bg": "rgba(16, 16, 16, 0.98)",
        "input_bg": "rgba(10, 10, 10, 0.85)",
        "fg": "#e8e8e8",
        "muted": "#8c8c8c",
        "accent": "#c8c8c8",
        "accent_hover": "#e6e6e6",
        "on_accent": "#111111",
        "green": "#8fbf8f",
        "yellow": "#d6b26a",
        "red": "#d16d6d",
        "border": "rgba(255, 255, 255, 0.14)",
    },
    "Ghost Pastel": {
        "bg": "rgba(28, 26, 38, 0.86)",
        "bg_soft": "rgba(40, 38, 54, 0.60)",
        "bg_hover": "rgba(50, 47, 68, 0.75)",
        "panel_bg": "rgba(28, 26, 38, 0.97)",
        "input_bg": "rgba(20, 18, 28, 0.85)",
        "fg": "#e8e2f4",
        "muted": "#9a92b3",
        "accent": "#c5a3ff",
        "accent_hover": "#d6bcff",
        "on_accent": "#221f2e",
        "green": "#a8e6cf",
        "yellow": "#ffe29a",
        "red": "#ffb3ba",
        "border": "rgba(197, 163, 255, 0.28)",
    },
    "Gruvbox": {
        "bg": "rgba(40, 40, 40, 0.85)",
        "bg_soft": "rgba(50, 48, 47, 0.60)",
        "bg_hover": "rgba(60, 56, 54, 0.75)",
        "panel_bg": "rgba(40, 40, 40, 0.97)",
        "input_bg": "rgba(29, 32, 33, 0.85)",
        "fg": "#ebdbb2",
        "muted": "#a89984",
        "accent": "#fabd2f",
        "accent_hover": "#ffd45e",
        "on_accent": "#282828",
        "green": "#b8bb26",
        "yellow": "#fabd2f",
        "red": "#fb4934",
        "border": "rgba(250, 189, 47, 0.28)",
    },
    "Nord": {
        "bg": "rgba(46, 52, 64, 0.85)",
        "bg_soft": "rgba(59, 66, 82, 0.60)",
        "bg_hover": "rgba(67, 76, 94, 0.75)",
        "panel_bg": "rgba(46, 52, 64, 0.97)",
        "input_bg": "rgba(40, 45, 55, 0.85)",
        "fg": "#d8dee9",
        "muted": "#7b88a1",
        "accent": "#88c0d0",
        "accent_hover": "#9fd0dd",
        "on_accent": "#2e3440",
        "green": "#a3be8c",
        "yellow": "#ebcb8b",
        "red": "#bf616a",
        "border": "rgba(136, 192, 208, 0.28)",
    },
    "Catppuccin Mocha": {
        "bg": "rgba(30, 30, 46, 0.86)",
        "bg_soft": "rgba(49, 50, 68, 0.60)",
        "bg_hover": "rgba(59, 60, 80, 0.75)",
        "panel_bg": "rgba(30, 30, 46, 0.97)",
        "input_bg": "rgba(24, 24, 37, 0.85)",
        "fg": "#cdd6f4",
        "muted": "#7f849c",
        "accent": "#89b4fa",
        "accent_hover": "#a3c6ff",
        "on_accent": "#1e1e2e",
        "green": "#a6e3a1",
        "yellow": "#f9e2af",
        "red": "#f38ba8",
        "border": "rgba(137, 180, 250, 0.28)",
    },
    "Dracula": {
        "bg": "rgba(40, 42, 54, 0.86)",
        "bg_soft": "rgba(50, 52, 66, 0.60)",
        "bg_hover": "rgba(60, 63, 80, 0.75)",
        "panel_bg": "rgba(40, 42, 54, 0.97)",
        "input_bg": "rgba(33, 34, 44, 0.85)",
        "fg": "#f8f8f2",
        "muted": "#6272a4",
        "accent": "#bd93f9",
        "accent_hover": "#cfaefc",
        "on_accent": "#21222c",
        "green": "#50fa7b",
        "yellow": "#f1fa8c",
        "red": "#ff5555",
        "border": "rgba(189, 147, 249, 0.28)",
    },
}
DEFAULT_THEME = "Tokyo Night"

# Escala global del tamano de fuente (ajustable desde la barra superior).
DEFAULT_FONT_SCALE = 1.0
MIN_FONT_SCALE = 0.8
MAX_FONT_SCALE = 2.0

# Franja/marco de color estilo "Zen Browser" (solido o degradado de 3 colores).
DEFAULT_BAND = {
    "mode": "gradient",
    "c1": "#7aa2f7",
    "c2": "#bb9af7",
    "c3": "#f7768e",
    "width": 8,
}

_PALETTE_TEMPLATE = """\
@define-color bg {bg};
@define-color bg_soft {bg_soft};
@define-color bg_hover {bg_hover};
@define-color panel_bg {panel_bg};
@define-color input_bg {input_bg};
@define-color fg {fg};
@define-color muted {muted};
@define-color accent {accent};
@define-color accent_hover {accent_hover};
@define-color on_accent {on_accent};
@define-color green {green};
@define-color yellow {yellow};
@define-color red {red};
@define-color border {border};
"""

# Ratios de opacidad de los fondos respecto al fondo principal (bg).
_BG_RATIOS = {"bg": 1.0, "bg_soft": 0.68, "bg_hover": 0.90, "input_bg": 0.92}


def _parse_rgb(color):
    color = color.strip()
    if color.startswith("#"):
        h = color[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    if color.startswith("rgb"):
        inside = color[color.find("(") + 1:color.find(")")]
        parts = [p.strip() for p in inside.split(",")]
        return tuple(int(float(parts[i])) for i in range(3))
    return (0, 0, 0)


def _rgba(color, alpha):
    r, g, b = _parse_rgb(color)
    return f"rgba({r}, {g}, {b}, {round(alpha, 3)})"


def _hex_to_rgba(value):
    c = Gdk.RGBA()
    if not c.parse(value or ""):
        c.parse("#7aa2f7")
    return c


def _rgba_to_hex(c):
    return "#%02x%02x%02x" % (
        round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def normalize_band(band):
    band = band if isinstance(band, dict) else {}
    return {
        "mode": band.get("mode", DEFAULT_BAND["mode"]),
        "c1": band.get("c1", DEFAULT_BAND["c1"]),
        "c2": band.get("c2", DEFAULT_BAND["c2"]),
        "c3": band.get("c3", DEFAULT_BAND["c3"]),
        "width": max(0, int(band.get("width", DEFAULT_BAND["width"]))),
    }


def _band_css(band):
    """CSS del marco de color (se inyecta despues de style.css)."""
    width = band["width"]
    if band["mode"] == "gradient":
        background = (
            f"background-image: linear-gradient(135deg, {band['c1']} 0%, "
            f"{band['c2']} 50%, {band['c3']} 100%); background-color: transparent;")
    else:
        background = f"background-image: none; background-color: {band['c1']};"
    return (
        f".frame {{ {background} }}\n"
        f".frame > .card {{ margin: {width}px; }}\n"
    )


def _palette_css(theme_name, transparent, transparency):
    """Genera el bloque @define-color aplicando el nivel de transparencia."""
    base = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    main = 1.0 if not transparent else max(0.05, 1.0 - transparency)
    pal = dict(base)
    for key, ratio in _BG_RATIOS.items():
        pal[key] = _rgba(base[key], min(1.0, main * ratio))
    pal["panel_bg"] = _rgba(base["panel_bg"], min(1.0, main + 0.16))
    return _PALETTE_TEMPLATE.format(**pal)


def _scale_font_css(css, scale):
    """Multiplica todos los 'font-size: Npx' del CSS por la escala dada."""
    if abs(scale - 1.0) < 1e-6:
        return css

    def repl(match):
        value = float(match.group(1)) * scale
        return f"font-size: {round(value, 1)}px"

    return re.sub(r"font-size:\s*([0-9.]+)px", repl, css)


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
    """Devuelve el valor del enum de borde (GdkSurfaceEdge / GdkWindowEdge)."""
    enum = getattr(Gdk, "SurfaceEdge", None) or getattr(Gdk, "WindowEdge", None)
    return getattr(enum, name)


def _clear(box):
    child = box.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


def _parse_local_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _note_deadline(note):
    """datetime local de vencimiento de una nota propia (fecha [+ hora]).

    Devuelve None si no hay fecha valida. Si no hay hora, usa 23:59.
    """
    parsed = core.parse_date(getattr(note, "date", ""))
    if parsed is None:
        return None
    clock = core.format_time(getattr(note, "time", ""))
    hour, minute = (23, 59)
    if clock:
        hour, minute = (int(clock[:2]), int(clock[3:5]))
    return datetime(parsed.year, parsed.month, parsed.day, hour, minute)


def _format_hours_left(end_dt):
    """Devuelve (texto, clase-urgencia) para una fecha de cierre local."""
    if end_dt is None:
        return "", "none"
    now = datetime.now(end_dt.tzinfo) if end_dt.tzinfo else datetime.now()
    minutes = int(round((end_dt - now).total_seconds() / 60))
    past = minutes < 0
    minutes = abs(minutes)
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    if days:
        txt = f"{days}d {hours}h"
    elif hours:
        txt = f"{hours}h {mins}m" if mins else f"{hours}h"
    else:
        txt = f"{mins}m"
    if past:
        return f"cerr\u00f3 hace {txt}", "overdue"
    if minutes <= 24 * 60:
        cls = "danger"
    elif minutes <= 72 * 60:
        cls = "warn"
    else:
        cls = "ok"
    return f"faltan {txt}", cls


def _bucket_for(cls):
    """Agrupa por color segun la urgencia: red | yellow | green."""
    if cls in ("danger", "overdue"):
        return "red"
    if cls == "warn":
        return "yellow"
    return "green"


def _textview_text(view):
    buf = view.get_buffer()
    start, end = buf.get_bounds()
    return buf.get_text(start, end, True)


def _set_textview_text(view, text):
    view.get_buffer().set_text(text or "")


def _cap_width(scroll):
    """Evita que un ScrolledWindow con contenido ancho (p. ej. un TextView con
    wrap NONE) estire el panel. Su ancho natural deja de propagarse."""
    try:
        scroll.set_propagate_natural_width(False)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Vista "estetica" del JSON (como el preview de VS Code): sin llaves ni
# comillas, con las claves resaltadas y los valores legibles.
# --------------------------------------------------------------------------- #
def _json_scalar_label(value):
    if value is None:
        text, cls = "\u2014", "json-null"
    elif isinstance(value, bool):
        text, cls = ("true" if value else "false"), "json-bool"
    elif isinstance(value, (int, float)):
        text, cls = str(value), "json-num"
    else:
        text, cls = str(value), "json-string"
    lbl = Gtk.Label(label=text)
    lbl.add_css_class(cls)
    lbl.set_xalign(0)
    lbl.set_wrap(True)
    lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lbl.set_max_width_chars(1)
    lbl.set_selectable(True)
    return lbl


def _json_empty_label():
    lbl = Gtk.Label(label="(vacio)")
    lbl.add_css_class("json-empty")
    lbl.set_xalign(0)
    return lbl


def _json_preview_into(box, data, depth):
    if isinstance(data, dict):
        if not data:
            box.append(_json_empty_label())
            return
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                group.set_margin_top(6)
                key_lbl = Gtk.Label(label=str(key))
                key_lbl.add_css_class("json-key")
                key_lbl.set_xalign(0)
                group.append(key_lbl)
                inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                inner.add_css_class("json-block")
                _json_preview_into(inner, value, depth + 1)
                group.append(inner)
                box.append(group)
            else:
                box.append(_json_key_value(str(key), value))
    elif isinstance(data, list):
        if not data:
            box.append(_json_empty_label())
            return
        for item in data:
            if isinstance(item, (dict, list)):
                group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                group.add_css_class("json-item")
                group.set_margin_top(6)
                _json_preview_into(group, item, depth + 1)
                box.append(group)
            else:
                box.append(_json_scalar_label(item))
    else:
        box.append(_json_scalar_label(data))


def _json_key_value(key, value):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("json-row")
    key_lbl = Gtk.Label(label=key)
    key_lbl.add_css_class("json-key")
    key_lbl.set_xalign(0)
    key_lbl.set_valign(Gtk.Align.START)
    key_lbl.set_size_request(96, -1)
    row.append(key_lbl)
    val_lbl = _json_scalar_label(value)
    val_lbl.set_hexpand(True)
    row.append(val_lbl)
    return row


def _json_preview(data):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    box.add_css_class("json-preview")
    _json_preview_into(box, data, 0)
    return box


# --------------------------------------------------------------------------- #
# Panel de edicion embebido (formulario + JSON) en la columna derecha
# --------------------------------------------------------------------------- #
class SidePanel(Gtk.Box):
    """Panel derecho estilo editor: una lista de modulos y, dentro, cada
    modulo (Recordatorio / Tareas Moodle JSON). Todo vive en la ventana
    principal; no se abren ventanas aparte."""

    def __init__(self, store, on_saved, on_hide, on_sync=None,
                 row_builder=None, notes_provider=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.on_saved = on_saved
        self.on_hide = on_hide
        self.on_sync = on_sync
        # Constructor de filas y proveedor de tareas (viven en NotesApp); el
        # modulo Calendario los reutiliza para dibujar las tareas de un dia.
        self._row_builder = row_builder
        self._notes_provider = notes_provider
        self.note = core.Note()
        self.is_new = True

        self.add_css_class("editor-panel")
        self.set_size_request(PANEL_WIDTH, -1)

        # estado del editor
        self._prev_page = "json"
        # calendario / reloj (formato 12 horas, guardado como HH:MM)
        self._has_date = False
        self._loading_form = False
        self._hour24 = 12
        self._minute = 0
        self.calendar = None
        self.hour_field = None
        self.minute_field = None
        self.ampm_btn = None
        self.date_summary = None
        # estado del modulo JSON
        self._json_view = None
        self._json_view_box = None
        self._json_entry = None
        self._json_status = None
        self._json_stack = None
        self._json_busy = False
        # estado del modulo Calendario
        self.cal_view = None
        self.cal_list = None
        self.cal_summary = None
        self._cal_by_date = {}

        self.append(self._build_header())
        self.nav_stack = Gtk.Stack()
        self.nav_stack.set_vexpand(True)
        self.nav_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.nav_stack.add_named(self._build_home_page(), "home")
        self.nav_stack.add_named(self._build_editor_module(), "editor")
        self.nav_stack.add_named(self._build_json_module(), "json")
        self.nav_stack.add_named(self._build_calendar_module(), "calendario")
        self.append(self.nav_stack)

        self.show_home()
        self._moodle_start()

    # -- cabecera / navegacion ---------------------------------------------
    def _build_header(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("titlebar")
        self.back_btn = Gtk.Button(label="\u2190")
        self.back_btn.add_css_class("icon-btn")
        self.back_btn.set_tooltip_text("Volver a m\u00f3dulos (Esc)")
        self.back_btn.connect("clicked", lambda *_: self.show_home())
        bar.append(self.back_btn)
        self.header_title = Gtk.Label(label="M\u00d3DULOS")
        self.header_title.add_css_class("titlebar-title")
        self.header_title.set_xalign(0)
        bar.append(self.header_title)
        bar.append(self._spacer())
        close = Gtk.Button(label="\u2715")
        close.add_css_class("icon-btn")
        close.set_tooltip_text("Ocultar (Ctrl+S)")
        close.connect("clicked", lambda *_: self.request_hide())
        bar.append(close)
        return bar

    def _build_home_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(14)
        box.set_margin_end(14)

        intro = Gtk.Label(label="Selecciona un m\u00f3dulo")
        intro.add_css_class("module-hint")
        intro.set_xalign(0)
        box.append(intro)

        self.module_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.module_list)
        self._add_module_button(
            "\u270e", "Recordatorio",
            "Crear y editar tus propias tareas", self.new_note)
        self._add_module_button(
            "\U0001f4c5", "Calendario",
            "Ver todas las tareas por fecha",
            lambda: self.open_module("calendario"))
        self._add_module_button(
            "{}", "Tareas Moodle \u00b7 JSON",
            "Ver datos, vista y sincronizar", lambda: self.open_module("json"))
        box.append(self._spacer())
        return box

    def _add_module_button(self, icon, title, subtitle, action):
        row = Gtk.Button()
        row.add_css_class("module-row")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ic = Gtk.Label(label=icon)
        ic.add_css_class("module-icon")
        inner.append(ic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        t = Gtk.Label(label=title)
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
        arrow = Gtk.Label(label="\u203a")
        arrow.add_css_class("module-arrow")
        inner.append(arrow)
        row.set_child(inner)
        row.connect("clicked", lambda *_: action())
        self.module_list.append(row)
        return row

    # -- modulo: calendario de tareas --------------------------------------
    def _build_calendar_module(self):
        """Vista mensual: marca los dias con tareas y lista las del dia."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(14)
        box.set_margin_end(14)

        self.cal_view = Gtk.Calendar()
        self.cal_view.add_css_class("date-calendar")
        self.cal_view.set_halign(Gtk.Align.CENTER)
        now = datetime.now()
        self.cal_view.set_year(now.year)
        # Gtk.Calendar usa meses 0-based (0 = enero).
        self.cal_view.set_month(now.month - 1)
        self.cal_view.set_day(now.day)
        self.cal_view.connect("day-selected", self._on_cal_changed)
        self.cal_view.connect("notify::month", self._on_cal_changed)
        self.cal_view.connect("notify::year", self._on_cal_changed)
        box.append(self.cal_view)

        self.cal_summary = Gtk.Label(label="")
        self.cal_summary.add_css_class("calendar-summary")
        self.cal_summary.set_xalign(0)
        box.append(self.cal_summary)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        _cap_width(scroll)
        self.cal_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.cal_list.add_css_class("note-list")
        scroll.set_child(self.cal_list)
        box.append(scroll)
        return box

    def _calendar_entries_by_date(self):
        """Agrupa TODAS las tareas (propias + Moodle) por fecha."""
        entries = self._notes_provider() if self._notes_provider else []
        by_date = {}
        for note, read_only in entries:
            if not getattr(note, "date", ""):
                continue
            parsed = core.parse_date(note.date)
            if parsed is None:
                continue
            by_date.setdefault(parsed, []).append((note, read_only))
        return by_date

    def refresh_calendar(self):
        """Recarga todas las tareas y vuelve a pintar el calendario."""
        if self.cal_view is None:
            return
        self._cal_by_date = self._calendar_entries_by_date()
        self._mark_calendar_days()
        self._render_calendar_day()

    def _mark_calendar_days(self):
        self.cal_view.clear_marks()
        year = self.cal_view.get_year()
        month = self.cal_view.get_month() + 1
        for day in self._cal_by_date:
            if day.year == year and day.month == month:
                self.cal_view.mark_day(day.day)

    def _on_cal_changed(self, *_args):
        self._mark_calendar_days()
        self._render_calendar_day()

    def _current_cal_date(self):
        return date(self.cal_view.get_year(),
                    self.cal_view.get_month() + 1,
                    self.cal_view.get_day())

    def _render_calendar_day(self):
        if self.cal_list is None:
            return
        _clear(self.cal_list)
        day = self._current_cal_date()
        items = self._cal_by_date.get(day, [])
        if self.cal_summary is not None:
            stamp = core.format_date(day)
            self.cal_summary.set_text(
                f"{stamp}  \u00b7  {len(items)} tarea(s)"
                if items else f"{stamp}  \u00b7  sin tareas")
        if not items:
            empty = Gtk.Label(label="Sin tareas este d\u00eda")
            empty.add_css_class("empty-state")
            self.cal_list.append(empty)
            return
        items.sort(key=lambda it: (it[0].title or "").lower())
        for note, read_only in items:
            if self._row_builder is not None:
                self.cal_list.append(self._row_builder(note, read_only=read_only))

    def show_home(self):
        self.nav_stack.set_visible_child_name("home")
        self.header_title.set_text("M\u00d3DULOS")
        self.back_btn.set_visible(False)

    def open_module(self, key):
        self.nav_stack.set_visible_child_name(key)
        self.back_btn.set_visible(True)
        if key == "json":
            self.header_title.set_text("TAREAS MOODLE")
            self.refresh_json()
        elif key == "editor":
            self.header_title.set_text("RECORDATORIO")
        elif key == "calendario":
            self.header_title.set_text("CALENDARIO")
            self.refresh_calendar()

    def go_back(self):
        """Esc: vuelve a la lista de modulos; si ya estas ahi, oculta el panel."""
        if self.nav_stack.get_visible_child_name() == "home":
            self.request_hide()
        else:
            self.show_home()

    def close_or_save(self):
        """Ctrl+S: guarda si estamos en el editor; si no, oculta el panel."""
        if self.nav_stack.get_visible_child_name() == "editor":
            self.save_and_hide()
        else:
            self.request_hide()

    def request_hide(self):
        self.set_visible(False)
        if self.on_hide:
            self.on_hide()

    @staticmethod
    def _spacer():
        sp = Gtk.Box()
        sp.set_hexpand(True)
        return sp

    @staticmethod
    def _label(text):
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("field-label")
        lbl.set_xalign(0)
        return lbl

    # -- modulo: editor de recordatorio ------------------------------------
    def _build_editor_module(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        switcher_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        switcher_bar.set_margin_start(14)
        switcher_bar.set_margin_end(14)
        switcher_bar.set_margin_top(6)
        self.mode_switcher = Gtk.StackSwitcher()
        self.mode_switcher.set_stack(self._build_stack())
        self.mode_switcher.add_css_class("mode-switcher")
        self.mode_switcher.set_halign(Gtk.Align.START)
        switcher_bar.append(self.mode_switcher)
        box.append(switcher_bar)
        box.append(self.stack)
        box.append(self._build_editor_footer())
        return box

    def _build_stack(self):
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(self._build_form_page(), "form", "Form")
        self.stack.add_titled(self._build_json_page(), "json", "C\u00f3digo")
        self.stack.add_titled(self._build_view_page(), "view", "Vista")
        self._prev_page = "form"
        self.stack.connect("notify::visible-child", self._on_page_changed)
        return self.stack

    def _build_view_page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        _cap_width(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(14)
        box.set_margin_end(14)
        self.view_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(self.view_box)
        scroll.set_child(box)
        return scroll

    def _build_form_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(14)
        box.set_margin_end(14)

        box.append(self._label("TITULO"))
        self.title_entry = Gtk.Entry()
        self.title_entry.set_placeholder_text("Titulo del recordatorio")
        box.append(self.title_entry)

        box.append(self._label("DESCRIPCION"))
        self.desc_view = Gtk.TextView()
        self.desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.desc_view.set_monospace(True)
        desc_scroll = Gtk.ScrolledWindow()
        desc_scroll.set_vexpand(True)
        _cap_width(desc_scroll)
        desc_scroll.set_min_content_height(120)
        desc_scroll.set_child(self.desc_view)
        box.append(desc_scroll)

        box.append(self._label("FECHA Y HORA LIMITE"))
        box.append(self._build_datetime_picker())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        _cap_width(scroll)
        scroll.set_child(box)
        return scroll

    def _build_datetime_picker(self):
        """Fila con (1) calendario y a su derecha (2) el reloj, en vez de
        escribir la fecha a mano."""
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        wrap.add_css_class("datetime-picker")

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.date_summary = Gtk.Label(label="Sin fecha")
        self.date_summary.add_css_class("date-summary")
        self.date_summary.set_xalign(0)
        self.date_summary.set_hexpand(True)
        self.date_summary.set_ellipsize(Pango.EllipsizeMode.END)
        head.append(self.date_summary)
        now_btn = Gtk.Button(label="Ahora")
        now_btn.add_css_class("flat")
        now_btn.set_tooltip_text("Fijar fecha y hora actuales")
        now_btn.connect("clicked", lambda *_: self._set_datetime_now())
        head.append(now_btn)
        clear_btn = Gtk.Button(label="Limpiar")
        clear_btn.add_css_class("flat")
        clear_btn.set_tooltip_text("Quitar la fecha limite")
        clear_btn.connect("clicked", lambda *_: self._clear_datetime())
        head.append(clear_btn)
        wrap.append(head)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_halign(Gtk.Align.CENTER)

        # Izquierda: calendario. Flechas mueven dia/semana, Page Up/Down los
        # meses; con el cursor se hace clic en las flechas del encabezado.
        self.calendar = Gtk.Calendar()
        self.calendar.add_css_class("date-calendar")
        self.calendar.set_valign(Gtk.Align.START)
        self.calendar.connect("day-selected", self._on_calendar_day)
        ckey = Gtk.EventControllerKey()
        ckey.connect("key-pressed", self._on_calendar_key)
        self.calendar.add_controller(ckey)
        row.append(self.calendar)

        # Derecha: reloj compacto en formato 12 horas (13 -> 1 PM).
        row.append(self._build_clock())
        wrap.append(row)
        return wrap

    def _build_clock(self):
        """Columna vertical al lado derecho del calendario.

        Hora arriba y minuto abajo, cada uno con flechas arriba/abajo; debajo
        el botón AM/PM. Todo se puede tocar con el cursor o con el teclado."""
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.add_css_class("clock-col")
        col.set_halign(Gtk.Align.CENTER)
        col.set_valign(Gtk.Align.START)

        self.hour_field = self._clock_field("hour", "HORA")
        col.append(self.hour_field["box"])
        sep = Gtk.Label(label=":")
        sep.add_css_class("clock-colon")
        col.append(sep)
        self.minute_field = self._clock_field("minute", "MIN")
        col.append(self.minute_field["box"])

        self.ampm_btn = Gtk.Button(label="AM")
        self.ampm_btn.add_css_class("clock-ampm")
        self.ampm_btn.set_tooltip_text("Alternar AM / PM (clic)")
        self.ampm_btn.connect("clicked", lambda *_: self._toggle_ampm())
        col.append(self.ampm_btn)

        col.set_focusable(True)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_clock_key)
        col.add_controller(key)
        return col

    def _clock_field(self, kind, header):
        """Campo [flecha arriba / valor / flecha abajo] para hora o minuto."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("clock-field")
        head = Gtk.Label(label=header)
        head.add_css_class("clock-head")
        box.append(head)
        up = Gtk.Button(label="\u25b2")
        up.add_css_class("clock-step")
        up.connect("clicked", self._step_clock, kind, 1)
        box.append(up)
        val = Gtk.Label(label="--")
        val.add_css_class("clock-value")
        val.set_focusable(True)
        box.append(val)
        down = Gtk.Button(label="\u25bc")
        down.add_css_class("clock-step")
        down.connect("clicked", self._step_clock, kind, -1)
        box.append(down)
        return {"box": box, "val": val}

    # -- calendario / reloj -------------------------------------------------
    def _on_calendar_day(self, _calendar):
        if self._loading_form:
            return
        self._has_date = True
        self._update_date_summary()

    def _on_calendar_key(self, _ctrl, keyval, _code, _state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.hour_field is not None:
                self.hour_field["val"].grab_focus()
            return True
        return False

    def _step_clock(self, _btn, kind, delta):
        if kind == "hour":
            self._hour24 = (self._hour24 + delta) % 24
        else:
            self._minute = (self._minute + delta) % 60
        self._update_clock()

    def _toggle_ampm(self):
        self._hour24 = (self._hour24 + 12) % 24
        self._update_clock()

    def _on_clock_key(self, _ctrl, keyval, _code, _state):
        """Teclado: arriba/abajo cambia la hora, izq/derecha el minuto."""
        if keyval == Gdk.KEY_Up:
            self._step_clock(None, "hour", 1)
            return True
        if keyval == Gdk.KEY_Down:
            self._step_clock(None, "hour", -1)
            return True
        if keyval == Gdk.KEY_Right:
            self._step_clock(None, "minute", 1)
            return True
        if keyval == Gdk.KEY_Left:
            self._step_clock(None, "minute", -1)
            return True
        return False

    def _update_clock(self):
        """Pinta el reloj en formato 12 horas (13 -> 1 PM)."""
        if self.hour_field is None or self.minute_field is None:
            return
        hour12 = self._hour24 % 12 or 12
        self.hour_field["val"].set_text(f"{hour12:02d}")
        self.minute_field["val"].set_text(f"{self._minute:02d}")
        if self.ampm_btn is not None:
            self.ampm_btn.set_label("AM" if self._hour24 < 12 else "PM")
        if not self._loading_form and self._has_date:
            self._update_date_summary()

    def _set_datetime_now(self):
        now = datetime.now()
        self._loading_form = True
        self.calendar.set_year(now.year)
        # Gtk.Calendar usa meses 0-based (0 = enero); datetime es 1-based.
        self.calendar.set_month(now.month - 1)
        self.calendar.set_day(now.day)
        self._hour24 = now.hour
        self._minute = now.minute
        self._loading_form = False
        self._has_date = True
        self._update_clock()
        self._update_date_summary()

    def _clear_datetime(self):
        self._has_date = False
        self._update_date_summary()

    def _selected_date(self):
        return core.format_date(
            date(self.calendar.get_year(),
                 self.calendar.get_month() + 1,
                 self.calendar.get_day()))

    def _selected_time(self):
        return f"{self._hour24:02d}:{self._minute:02d}"

    def _update_date_summary(self):
        if self.date_summary is None:
            return
        if self._has_date:
            self.date_summary.set_text(
                f"{self._selected_date()}  {self._selected_time()}")
        else:
            self.date_summary.set_text("Sin fecha")

    def _build_json_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(14)
        box.set_margin_end(14)
        box.append(self._label("JSON (editable como texto)"))
        self.json_view = Gtk.TextView()
        self.json_view.set_monospace(True)
        self.json_view.set_wrap_mode(Gtk.WrapMode.NONE)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        _cap_width(scroll)
        scroll.set_child(self.json_view)
        box.append(scroll)
        return box

    def _build_editor_footer(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_top(6)
        bar.set_margin_bottom(12)
        bar.set_margin_start(14)
        bar.set_margin_end(14)

        self.error_label = Gtk.Label(label="")
        self.error_label.add_css_class("error-text")
        self.error_label.set_xalign(0)
        bar.append(self.error_label)

        bar.append(self._spacer())

        cancel = Gtk.Button(label="Volver")
        cancel.add_css_class("flat")
        cancel.set_tooltip_text("Volver a m\u00f3dulos (Esc)")
        cancel.connect("clicked", lambda *_: self.show_home())
        bar.append(cancel)

        save = Gtk.Button(label="Guardar")
        save.add_css_class("primary")
        save.set_tooltip_text("Guardar (Enter)")
        save.connect("clicked", lambda *_: self.save_and_hide())
        bar.append(save)

        return bar

    # -- modulo: tareas Moodle (JSON) --------------------------------------
    def _build_json_module(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        switcher_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        switcher_bar.set_margin_start(14)
        switcher_bar.set_margin_end(14)
        switcher_bar.set_margin_top(6)
        self._json_stack = Gtk.Stack()
        self._json_stack.set_vexpand(True)
        self._json_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._json_stack.add_titled(self._build_json_code_page(), "code", "C\u00f3digo")
        self._json_stack.add_titled(self._build_json_view_page(), "view", "Vista")
        self._json_switcher = Gtk.StackSwitcher()
        self._json_switcher.set_stack(self._json_stack)
        self._json_switcher.add_css_class("mode-switcher")
        self._json_switcher.set_halign(Gtk.Align.START)
        switcher_bar.append(self._json_switcher)
        box.append(switcher_bar)
        box.append(self._json_stack)
        box.append(self._build_json_footer())
        return box

    def _build_json_code_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(14)
        box.set_margin_end(14)
        self._json_view = Gtk.TextView()
        self._json_view.set_monospace(True)
        self._json_view.set_wrap_mode(Gtk.WrapMode.NONE)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        _cap_width(scroll)
        scroll.set_child(self._json_view)
        box.append(scroll)
        return box

    def _build_json_view_page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        _cap_width(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(14)
        box.set_margin_end(14)
        self._json_view_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(self._json_view_box)
        scroll.set_child(box)
        return scroll

    def _build_json_footer(self):
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        wrap.set_margin_top(6)
        wrap.set_margin_bottom(12)
        wrap.set_margin_start(14)
        wrap.set_margin_end(14)

        wrap.append(self._label("URL DEL CALENDARIO MOODLE"))
        self._json_entry = Gtk.Entry()
        self._json_entry.set_placeholder_text("https://.../calendar/export_execute.php?...")
        self._json_entry.set_max_width_chars(24)
        self._json_entry.set_hexpand(True)
        wrap.append(self._json_entry)

        self._json_status = Gtk.Label(label="")
        self._json_status.add_css_class("moodle-status")
        self._json_status.set_xalign(0)
        self._json_status.set_wrap(True)
        self._json_status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._json_status.set_max_width_chars(30)
        wrap.append(self._json_status)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_top(4)
        bar.append(self._spacer())

        save_url = Gtk.Button(label="Guardar URL")
        save_url.add_css_class("flat")
        save_url.connect("clicked", self._on_json_save_url)
        bar.append(save_url)

        refresh = Gtk.Button(label="\u21bb Actualizar")
        refresh.add_css_class("primary")
        refresh.set_tooltip_text("Sincronizar ahora (Ctrl+Shift+R)")
        refresh.connect("clicked", self._on_json_refresh)
        bar.append(refresh)
        wrap.append(bar)
        return wrap

    # -- sincronizacion Moodle ---------------------------------------------
    def _moodle_start(self):
        try:
            GLib.timeout_add_seconds(moodle.REFRESH_HOURS * 3600, self._moodle_timer)
            if moodle.get_url() and moodle.is_stale():
                self._moodle_fetch_async()
        except Exception:
            pass
        self._load_json_from_disk()

    def _load_json_from_disk(self):
        try:
            data = moodle.load_data()
        except Exception:
            data = {}
        self._on_json_loaded(data, None)

    def _moodle_timer(self):
        if not self._json_busy:
            self._moodle_fetch_async()
        return True

    def _global_json(self):
        try:
            moodle_data = moodle.load_data()
        except Exception:
            moodle_data = {}
        tasks = []
        for note in self.store.list_notes():
            tasks.append(note.as_dict())
        return {"tareas": tasks, "moodle": moodle_data}

    def _global_json_text(self):
        return json.dumps(self._global_json(), ensure_ascii=False, indent=2)

    def refresh_json(self):
        try:
            data = self._global_json()
        except Exception:
            return
        if self._json_view is not None:
            _set_textview_text(self._json_view, self._global_json_text())
        if self._json_view_box is not None:
            _clear(self._json_view_box)
            self._json_view_box.append(_json_preview(data))
        if self._json_entry is not None:
            url = moodle.get_url()
            if url and self._json_entry.get_text() != url:
                self._json_entry.set_text(url)
        self._update_json_status()

    def _update_json_status(self, message=None):
        if self._json_status is None:
            return
        if message:
            self._json_status.set_text(message)
            return
        try:
            data = moodle.load_data()
        except Exception:
            data = {}
        count = data.get("count", len(data.get("events", [])))
        fetched = data.get("fetched_at", "")
        stamp = fetched[11:16] if len(fetched) >= 16 else (fetched or "\u2014")
        tasks = sum(1 for e in data.get("events", []) if e.get("is_task"))
        self._json_status.set_text(
            f"{tasks} tareas \u00b7 {count} eventos \u00b7 actualizado: {stamp}")

    def _on_json_save_url(self, _btn):
        url = self._json_entry.get_text().strip()
        moodle.set_url(url)
        self._update_json_status("URL guardada \u00b7 sincronizando\u2026")
        self._moodle_fetch_async()

    def _on_json_refresh(self, _btn):
        if self._json_busy:
            return
        self._moodle_fetch_async()

    def sync_now(self):
        """Dispara una sincronizacion de Moodle (usado por el boton superior)."""
        self._moodle_fetch_async()

    def _moodle_fetch_async(self):
        if self._json_busy:
            return
        if not moodle.get_url():
            self._update_json_status("Configura la URL del calendario")
            return
        self._json_busy = True
        self._update_json_status("Sincronizando\u2026")
        thread = threading.Thread(target=self._moodle_thread, daemon=True)
        thread.start()

    def _moodle_thread(self):
        try:
            data = moodle.refresh()
            error = None
        except Exception as exc:
            data = None
            error = str(exc)
        GLib.idle_add(self._on_json_loaded, data, error)

    def _on_json_loaded(self, data, error):
        self._json_busy = False
        if error:
            self._update_json_status(f"Error: {error}")
        self.refresh_json()
        if self.on_sync:
            self.on_sync()

    # -- logica del editor --------------------------------------------------
    def new_note(self):
        self.load(None)

    def load(self, note):
        self.is_new = note is None
        self.note = note if note is not None else core.Note()
        self.title_entry.set_text(self.note.title or "")
        _set_textview_text(self.desc_view, self.note.description or "")
        # Calendario + reloj: reflejan la fecha/hora de la nota (o "ahora").
        self._loading_form = True
        parsed = core.parse_date(self.note.date) if self.note.date else None
        base = parsed or datetime.now().date()
        self.calendar.set_year(base.year)
        self.calendar.set_month(base.month - 1)
        self.calendar.set_day(base.day)
        clock = core.format_time(self.note.time) if self.note.time else ""
        if clock:
            self._hour24 = int(clock[:2])
            self._minute = int(clock[3:5])
        else:
            now = datetime.now()
            self._hour24 = now.hour
            self._minute = now.minute
        self._has_date = parsed is not None
        self._loading_form = False
        self._update_clock()
        self._update_date_summary()
        _set_textview_text(self.json_view, self.note.as_json())
        self._prev_page = "form"
        self.stack.set_visible_child_name("form")
        self._refresh_view()
        self._set_error("")
        self.open_module("editor")
        self.header_title.set_text("NUEVA NOTA" if self.is_new else "EDITAR NOTA")
        self.title_entry.grab_focus()

    def _focused_field_index(self, fields):
        root = self.get_root()
        focus = root.get_focus() if root is not None else None
        if focus is None:
            return -1
        for i, field in enumerate(fields):
            if focus is field or focus.is_ancestor(field):
                return i
        return -1

    def focus_next(self):
        """Ctrl+Enter: pasa al siguiente campo; en el ultimo, guarda."""
        if self.stack.get_visible_child_name() != "form":
            self.save_and_hide()
            return
        fields = [self.title_entry, self.desc_view, self.calendar,
                  self.hour_field["val"], self.minute_field["val"]]
        idx = self._focused_field_index(fields)
        if idx < 0 or idx >= len(fields) - 1:
            self.save_and_hide()
            return
        fields[idx + 1].grab_focus()

    def focus_prev(self):
        """Ctrl+Shift+Enter: vuelve al campo anterior."""
        if self.stack.get_visible_child_name() != "form":
            return
        fields = [self.title_entry, self.desc_view, self.calendar,
                  self.hour_field["val"], self.minute_field["val"]]
        idx = self._focused_field_index(fields)
        if idx <= 0:
            self.title_entry.grab_focus()
            return
        fields[idx - 1].grab_focus()

    def _collect_form(self):
        title = self.title_entry.get_text().strip()
        desc = _textview_text(self.desc_view).strip()
        date_txt = self._selected_date() if self._has_date else ""
        time_txt = self._selected_time() if self._has_date else ""
        if date_txt and core.parse_date(date_txt) is None:
            return None
        return title, desc, date_txt, time_txt

    def _set_error(self, message):
        self.error_label.set_text(message or "")

    def _on_page_changed(self, _stack, _pspec):
        page = self.stack.get_visible_child_name()
        # Al salir del formulario, vuelca los campos al JSON editable.
        if self._prev_page == "form" and page != "form":
            collected = self._collect_form()
            if collected is not None:
                title, desc, date_txt, time_txt = collected
                data = self.note.as_dict()
                data.update(title=title, description=desc, date=date_txt,
                            time=time_txt)
                _set_textview_text(
                    self.json_view, json.dumps(data, ensure_ascii=False, indent=2))
                self._set_error("")
        if page == "view":
            self._refresh_view()
        self._prev_page = page

    def _refresh_view(self):
        """Rellena la pestana Vista renderizando el JSON actual (sin simbolos)."""
        if self.view_box is None:
            return
        _clear(self.view_box)
        try:
            data = json.loads(_textview_text(self.json_view) or "{}")
        except Exception:
            data = self.note.as_dict()
        if not isinstance(data, dict):
            data = {"valor": data}
        self.view_box.append(_json_preview(data))

    def save(self):
        """Guarda el contenido del panel. Devuelve True si se guardo."""
        if self.stack.get_visible_child_name() == "form":
            collected = self._collect_form()
            if collected is None:
                self._set_error("Fecha invalida (usa dd/mm/aa)")
                return False
            title, desc, date_txt, time_txt = collected
            note = self.note
            note.title = title
            note.description = desc
            note.date = date_txt
            note.time = time_txt
        else:
            # "json" (editor de texto) o "view": se guarda el JSON actual.
            try:
                data = json.loads(_textview_text(self.json_view) or "{}")
                note = core.Note.from_dict(data)
            except Exception as exc:
                self._set_error(f"JSON invalido: {exc}")
                return False
            if note.date and core.parse_date(note.date) is None:
                self._set_error("Fecha invalida (usa dd/mm/aa)")
                return False
            note.file = self.note.file
            note.id = note.id or self.note.id

        if self.is_new and not note.title and not note.description and not note.date:
            return True  # nota nueva vacia: no crear archivo

        self.store.save(note)
        if self.on_saved:
            self.on_saved()
        return True

    def save_and_hide(self):
        if self.save():
            self.request_hide()


# --------------------------------------------------------------------------- #
# Aplicacion principal
# --------------------------------------------------------------------------- #
class NotesApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.store = core.NotesStore()
        self.window = None
        self.list_box = None
        self.count_label = None
        self.scrolled = None
        self.rows = []
        self.selected = 0
        self.paned = None
        self.panel = None
        state = _load_state()
        self.theme = state.get("theme", DEFAULT_THEME)
        if self.theme not in THEMES:
            self.theme = DEFAULT_THEME
        self.transparent = bool(state.get("transparent", True))
        self.transparency = min(0.9, max(0.0, float(state.get("transparency", 0.18))))
        self.band = normalize_band(state.get("band"))
        self.font_scale = min(MAX_FONT_SCALE, max(
            MIN_FONT_SCALE, float(state.get("font_scale", DEFAULT_FONT_SCALE))))
        self.css_provider = None
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
        self._load_css()
        self.window = self._build_window()
        self.refresh()
        self.window.present()

    def _load_css(self):
        try:
            base = CSS_PATH.read_text(encoding="utf-8")
        except OSError:
            base = ""
        base = _scale_font_css(base, self.font_scale)
        # Escala tambien el texto que no fija un tamano explicito (hereda).
        font_rule = f"window.notes-window {{ font-size: {self.font_scale}em; }}\n"
        css = (_palette_css(self.theme, self.transparent, self.transparency)
               + "\n" + base + "\n" + _band_css(self.band) + "\n" + font_rule)

        if self.css_provider is None:
            self.css_provider = Gtk.CssProvider()
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display, self.css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        if hasattr(self.css_provider, "load_from_string"):
            self.css_provider.load_from_string(css)
        else:
            self.css_provider.load_from_data(css.encode("utf-8"))

    def _set_theme(self, name):
        if name not in THEMES:
            return
        self.theme = name
        state = _load_state()
        state["theme"] = name
        _save_state(state)
        self._load_css()

    # -- ventana ------------------------------------------------------------
    def _build_window(self):
        win = Gtk.ApplicationWindow(application=self, title="Notas")
        state = _load_state()
        win.set_default_size(int(state.get("width", 440)), int(state.get("height", 600)))
        win.set_decorated(False)
        win.add_css_class("notes-window")
        win.connect("close-request", self._on_window_close)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("card")
        root.set_vexpand(True)
        root.set_hexpand(True)

        root.append(self._build_header())

        # Cuerpo: lista + panel a la derecha. Es un Box (no un Overlay) para
        # que al abrir el panel la lista se reacomode (responsive) y no quede
        # tapada por encima.
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.set_hexpand(True)
        self.left_box = left

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.list_box.add_css_class("note-list")

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self.list_box)
        left.append(scrolled)
        self.scrolled = scrolled

        left.append(self._build_footer())
        body.append(left)

        self.panel = SidePanel(
            self.store, self.refresh, self._on_panel_hide,
            on_sync=self.refresh,
            row_builder=self._build_row,
            notes_provider=self._calendar_notes)
        self.panel.set_visible(False)
        body.append(self.panel)

        root.append(body)

        # Marco de color estilo "Zen Browser": el .frame pinta la franja y el
        # .card queda dentro con un margen (grosor de la franja).
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("frame")
        frame.set_vexpand(True)
        frame.set_hexpand(True)
        frame.append(root)

        # Envolvemos en un Overlay para poner los bordes de redimensionado
        # (la ventana es sin marco; en Wayland, sin esto no se cambia el tamano).
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

    def _build_header(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("titlebar")

        dot = Gtk.Label(label="\u25cf")
        dot.add_css_class("titlebar-dot")
        bar.append(dot)

        title = Gtk.Label(label="NOTAS")
        title.add_css_class("titlebar-title")
        title.set_xalign(0)
        bar.append(title)

        sp = Gtk.Box()
        sp.set_hexpand(True)
        bar.append(sp)

        refresh = Gtk.Button(label="\u21bb")
        refresh.add_css_class("icon-btn")
        refresh.set_tooltip_text("Sincronizar Moodle ahora (Ctrl+Shift+R)")
        refresh.connect("clicked", lambda *_: self._refresh_moodle())
        bar.append(refresh)

        bar.append(self._build_font_button())
        bar.append(self._build_band_button())
        bar.append(self._build_transparency_button())
        bar.append(self._build_theme_button())

        moodle_btn = Gtk.Button(label="{}")
        moodle_btn.add_css_class("icon-btn")
        moodle_btn.set_tooltip_text("M\u00f3dulo de tareas Moodle (Ctrl+Shift+J)")
        moodle_btn.connect("clicked", lambda *_: self._open_json_module())
        bar.append(moodle_btn)

        help_btn = Gtk.Button(label="?")
        help_btn.add_css_class("icon-btn")
        help_btn.set_tooltip_text(
            "Atajos de teclado\n"
            "\u2191 \u2193   mover seleccion\n"
            "Enter   expandir / contraer\n"
            "Ctrl+Shift+N   nuevo recordatorio\n"
            "Ctrl+Shift+M   editar\n"
            "Ctrl+Shift+L   eliminar (solo tareas rojas)\n"
            "Ctrl+Shift+J   m\u00f3dulo tareas Moodle\n"
            "Ctrl+Shift+R   sincronizar Moodle\n"
            "Ctrl+S   abrir / cerrar panel\n"
            "Esc   volver a m\u00f3dulos / cerrar panel\n"
            "Ctrl+Q   salir del todo\n"
            "En el editor: Ctrl+Enter pasa de campo,\n"
            "Enter en titulo/fecha guarda"
        )
        bar.append(help_btn)

        add = Gtk.Button(label="\uff0b")
        add.add_css_class("icon-btn")
        add.set_tooltip_text("Nuevo recordatorio (Ctrl+Shift+N)")
        add.connect("clicked", lambda *_: self.new_note())
        bar.append(add)

        close = Gtk.Button(label="\u2715")
        close.add_css_class("icon-btn")
        close.set_tooltip_text("Cerrar")
        close.connect("clicked", lambda *_: self.window.close())
        bar.append(close)

        handle = Gtk.WindowHandle()
        handle.set_child(bar)
        return handle

    def _build_font_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Tamano de fuente")
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
        lbl = Gtk.Label(label="TAMA\u00d1O DE FUENTE")
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
            Gtk.Orientation.HORIZONTAL, MIN_FONT_SCALE * 100, MAX_FONT_SCALE * 100, 5)
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
        reset.connect("clicked", lambda *_: self._set_font_scale(DEFAULT_FONT_SCALE))
        box.append(reset)

        popover.set_child(box)
        return popover

    def _nudge_font(self, delta):
        self._set_font_scale(round(self.font_scale + delta, 2))

    def _set_font_scale(self, value):
        value = min(MAX_FONT_SCALE, max(MIN_FONT_SCALE, value))
        self.font_scale = value
        if self._font_scale is not None:
            self._font_scale.set_value(round(value * 100))
        if self._font_value is not None:
            self._font_value.set_text(f"{round(value * 100)}%")
        self._save_font()
        self._load_css()

    def _on_font_scale_changed(self, scale):
        value = min(MAX_FONT_SCALE, max(MIN_FONT_SCALE, scale.get_value() / 100.0))
        self.font_scale = round(value, 2)
        if self._font_value is not None:
            self._font_value.set_text(f"{round(self.font_scale * 100)}%")
        self._save_font()
        self._load_css()

    def _save_font(self):
        state = _load_state()
        state["font_scale"] = round(self.font_scale, 3)
        _save_state(state)

    def _build_theme_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Cambiar tema")
        menu.set_child(Gtk.Label(label="\u25d1"))
        menu.set_popover(self._build_theme_popover())
        return menu

    def _build_theme_popover(self):
        popover = Gtk.Popover()
        popover.add_css_class("theme-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        for name in THEMES:
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
        menu.set_child(Gtk.Label(label="\u25cc"))
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
        self._save_transparency()
        self._load_css()
        return False

    def _on_transparency_changed(self, scale):
        self.transparency = min(0.9, max(0.0, scale.get_value() / 100.0))
        self._save_transparency()
        self._load_css()

    def _save_transparency(self):
        state = _load_state()
        state["transparent"] = self.transparent
        state["transparency"] = round(self.transparency, 3)
        _save_state(state)

    # -- franja de color (estilo Zen Browser) -------------------------------
    def _build_band_button(self):
        menu = Gtk.MenuButton()
        menu.add_css_class("icon-btn")
        menu.set_always_show_arrow(False)
        menu.set_tooltip_text("Margen / franja de color")
        menu.set_child(Gtk.Label(label="\u25a3"))
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
        self._band_solid = Gtk.ToggleButton(label="S\u00f3lido")
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
            btn.set_rgba(_hex_to_rgba(self.band[key]))
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
        self._save_band()
        self._load_css()

    def _on_band_color(self, btn, _pspec, key):
        self.band[key] = _rgba_to_hex(btn.get_rgba())
        self._save_band()
        self._load_css()

    def _on_band_width(self, scale):
        self.band["width"] = int(round(scale.get_value()))
        self._save_band()
        self._load_css()

    def _save_band(self):
        state = _load_state()
        state["band"] = dict(self.band)
        _save_state(state)

    # -- Moodle (atajos) ----------------------------------------------------
    def _open_json_module(self):
        self._show_panel()
        self.panel.open_module("json")

    def _refresh_moodle(self):
        self.panel.sync_now()

    def _build_footer(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.set_margin_top(4)
        bar.set_margin_bottom(10)
        bar.set_margin_start(14)
        bar.set_margin_end(14)

        self.count_label = Gtk.Label(label="")
        self.count_label.add_css_class("days-none")
        self.count_label.set_xalign(0)
        self.count_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.count_label.set_max_width_chars(14)
        bar.append(self.count_label)

        sp = Gtk.Box()
        sp.set_hexpand(True)
        bar.append(sp)

        new = Gtk.Button(label="+ nueva")
        new.add_css_class("flat")
        new.connect("clicked", lambda *_: self.new_note())
        bar.append(new)

        return bar

    # -- lista --------------------------------------------------------------
    def refresh(self):
        if self.list_box is None:
            return
        _clear(self.list_box)
        self.rows = []
        notes = self.store.list_notes()
        moodle_notes = self._moodle_notes()
        if not notes and not moodle_notes:
            empty = Gtk.Label(label="Sin recordatorios.\nPresiona \uff0b para crear uno.")
            empty.add_css_class("empty-state")
            empty.set_justify(Gtk.Justification.CENTER)
            empty.set_wrap(True)
            empty.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            empty.set_max_width_chars(1)
            self.list_box.append(empty)
            self.selected = -1
        else:
            built = [self._build_row(note) for note in notes]
            built += [self._build_row(note, read_only=True) for note in moodle_notes]
            self.rows = built
            self._relayout()
            self.selected = max(0, min(self.selected, len(self.rows) - 1))
            GLib.idle_add(self._apply_selection)
        if self.count_label is not None:
            extra = f" \u00b7 {len(moodle_notes)} de Moodle" if moodle_notes else ""
            self.count_label.set_text(f"{len(notes)} recordatorio(s){extra}")
        # Mantiene los modulos JSON y Calendario sincronizados con la lista.
        if self.panel is not None:
            self.panel.refresh_json()
            self.panel.refresh_calendar()

    def _calendar_notes(self):
        """Todas las tareas para el calendario: (nota, solo_lectura)."""
        entries = [(note, False) for note in self.store.list_notes()]
        entries += [(note, True) for note in self._moodle_notes()]
        return entries

    def _relayout(self):
        """Reparte las filas en grupos por color.

        Ventana ancha (panel oculto): 3 columnas verde | amarillo | rojo.
        Lista apretada (panel visible): 1 columna rojo -> amarillo -> verde."""
        if self.list_box is None or not self.rows:
            return
        selected_row = None
        if 0 <= self.selected < len(self.rows):
            selected_row = self.rows[self.selected]
        rows = list(self.rows)
        # Desprende las filas de su contenedor actual (grupo o lista) para
        # poder reubicarlas sin perder el estado de expansion.
        for row in rows:
            row.unparent()
        _clear(self.list_box)
        wide = self.panel is None or not self.panel.get_visible()
        order = ["green", "yellow", "red"] if wide else ["red", "yellow", "green"]
        groups = {"green": [], "yellow": [], "red": []}
        for row in rows:
            groups[getattr(row, "_bucket", "green")].append(row)
        visual = []
        cols = None
        if wide:
            cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            cols.add_css_class("task-columns")
            cols.set_valign(Gtk.Align.START)
            # Reparte el ancho en partes iguales: ninguna columna crece mas
            # que otra aunque un titulo sea largo (las letras envuelven).
            cols.set_homogeneous(True)
        for bucket in order:
            members = groups[bucket]
            if not members:
                continue
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.add_css_class("task-group")
            box.add_css_class(f"group-{bucket}")
            box.set_valign(Gtk.Align.START)
            if wide:
                box.set_hexpand(True)
            for row in members:
                box.append(row)
                visual.append(row)
            if wide:
                cols.append(box)
            else:
                self.list_box.append(box)
        if wide:
            self.list_box.append(cols)
        self.rows = visual
        if selected_row is not None and selected_row in self.rows:
            self.selected = self.rows.index(selected_row)

    def _moodle_notes(self):
        """Tareas del calendario de Moodle como notas de solo lectura.

        Las tareas marcadas como hechas (Ctrl+Shift+L) se ocultan y no
        vuelven a aparecer al sincronizar."""
        done = moodle.done_uids()
        events = [
            e for e in moodle.load_data().get("events", [])
            if e.get("is_task") and e.get("uid") not in done
        ]
        events.sort(key=lambda e: (e.get("start") or "", e.get("title", "").lower()))
        notes = []
        for event in events:
            note = core.Note(
                id=event.get("uid", ""),
                title=event.get("title", ""),
                description=event.get("description", ""),
                date=event.get("date", ""),
                done=False,
            )
            note._end_time = event.get("end_time", "")  # type: ignore[attr-defined]
            note._end_dt = _parse_local_dt(  # type: ignore[attr-defined]
                event.get("end_local") or "")
            note._course = event.get("course", "")  # type: ignore[attr-defined]
            note._career = event.get("career", "")  # type: ignore[attr-defined]
            notes.append(note)
        return notes

    def _build_row(self, note, read_only=False):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("note-row")
        if read_only:
            row.add_css_class("moodle-row")
        row._read_only = read_only  # type: ignore[attr-defined]

        # Columna 1: checkbox -> al marcar se elimina el recordatorio.
        # En filas de Moodle (solo lectura) se muestra una marca de nube.
        if read_only:
            marker = Gtk.Label(label="\u2601")
            marker.add_css_class("moodle-mark")
            marker.set_valign(Gtk.Align.CENTER)
            marker.set_tooltip_text("Tarea de Moodle (sincronizada)")
            row.append(marker)
        else:
            check = Gtk.CheckButton()
            check.add_css_class("note-check")
            check.set_active(note.done)
            check.set_valign(Gtk.Align.CENTER)
            check.set_tooltip_text("Marcar para eliminar")
            check.connect("toggled", self._on_check, note)
            row.append(check)

        # Columna 2: la tarea. Siempre visibles, en este orden:
        #   1) titulo
        #   2) fecha + hora + lo que falta (limite/dias/horas restantes)
        #   3) materia (Moodle)
        # Al expandir (Enter / boton) se revela la descripcion.
        task = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        task.set_hexpand(True)
        task.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label=note.title or "(sin titulo)")
        title.add_css_class("task-title")
        title.set_xalign(0)
        title.set_wrap(True)
        title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title.set_max_width_chars(1)
        # Oculta el exceso: el titulo usa como maximo 3 lineas.
        title.set_lines(3)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        task.append(title)

        # Linea de fecha/hora/lo que falta: siempre visible (deba del titulo),
        # asi no se pierde al acortarse la lista.
        if read_only:
            hours_txt, hours_cls = _format_hours_left(
                getattr(note, "_end_dt", None))
            end_time = getattr(note, "_end_time", "")
            parts = []
            if note.date:
                parts.append(core.format_date(note.date))
            if end_time:
                parts.append(f"cierra {end_time}")
            if hours_txt:
                parts.append(hours_txt)
            meta_text = " \u00b7 ".join(parts) or "\u2014"
            meta_cls = hours_cls
        else:
            days = core.days_left(note.date)
            if note.date:
                stamp = core.format_stamp(note.date, getattr(note, "time", ""))
                meta_text = f"{stamp} \u00b7 {core.days_label(days)}"
            else:
                meta_text = core.days_label(days)
            meta_cls = core.urgency(days)
        meta_lbl = Gtk.Label(label=meta_text)
        meta_lbl.add_css_class("task-meta")
        meta_lbl.add_css_class(f"days-{meta_cls}")
        meta_lbl.set_xalign(0)
        meta_lbl.set_wrap(True)
        meta_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        meta_lbl.set_max_width_chars(1)
        # Como maximo 2 lineas: la altura de la cajita no depende del texto.
        meta_lbl.set_lines(2)
        meta_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        task.append(meta_lbl)

        # Materia de la tarea: debajo de la fecha. Se crea siempre (aunque no
        # haya materia) para reservar su linea y que todas las cajitas midan
        # igual de alto.
        course_lbl = Gtk.Label()
        course_lbl.add_css_class("task-course")
        course_lbl.set_xalign(0)
        course_lbl.set_wrap(True)
        course_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        course_lbl.set_max_width_chars(1)
        # Una sola linea: la materia nunca cambia la altura de la cajita.
        course_lbl.set_lines(1)
        course_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        if read_only and getattr(note, "_course", ""):
            course = note._course
            career = getattr(note, "_career", "")
            course_lbl.set_text(
                f"\U0001f4da {course}" + (f"  \u00b7  {career}" if career else ""))
        else:
            course_lbl.set_text("\u00a0")
        task.append(course_lbl)

        desc = Gtk.Label(label=note.description or "(sin descripcion)")
        desc.add_css_class("task-desc")
        desc.set_xalign(0)
        # WORD_CHAR: corta tambien palabras largas -> la ventana se adapta
        desc.set_wrap(True)
        desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        desc.set_max_width_chars(1)
        desc.set_visible(False)
        try:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_line_height_new(1.5))
            desc.set_attributes(attrs)
        except Exception:
            pass
        task.append(desc)

        row.append(task)

        # Clic sobre la fila: selecciona y abre/cierra (igual que Enter o ▸).
        # Cursor tipo mano + tooltip para dejar claro que es cliqueable.
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_row_pressed, row)
        task.add_controller(click)
        try:
            task.set_cursor_from_name("pointer")
        except Exception:
            pass
        task.set_tooltip_text("Clic para abrir / cerrar")

        state = {"expanded": False}
        row._state = state  # type: ignore[attr-defined]
        row._note = note  # type: ignore[attr-defined]
        row._desc = desc  # type: ignore[attr-defined]
        row._meta = meta_lbl  # type: ignore[attr-defined]
        row._course_lbl = course_lbl  # type: ignore[attr-defined]
        row._bucket = _bucket_for(meta_cls)  # type: ignore[attr-defined]
        # Solo las tareas de la seccion ROJA (vencidas / urgentes) se pueden
        # eliminar; las amarillas y verdes quedan protegidas.
        deletable = row._bucket == "red"  # type: ignore[attr-defined]
        row._deletable = deletable  # type: ignore[attr-defined]
        if not read_only:
            check.set_sensitive(deletable)
            check.set_tooltip_text(
                "Marcar para eliminar" if deletable
                else "Solo las tareas rojas se pueden eliminar")
        row.set_focusable(True)

        # Columna 3: expandir / contraer
        expand = Gtk.Button(label="\u25b8")
        expand.add_css_class("icon-btn")
        expand.set_valign(Gtk.Align.CENTER)
        expand.set_tooltip_text("Expandir / contraer")
        expand.connect("clicked", self._on_expand, note, desc, expand, state)
        row.append(expand)

        # Columna 4: editar (no aplica a filas de Moodle, solo lectura)
        if not read_only:
            edit = Gtk.Button(label="\u270e")
            edit.add_css_class("icon-btn")
            edit.set_valign(Gtk.Align.CENTER)
            edit.set_tooltip_text("Editar")
            edit.connect("clicked", lambda *_: self.edit_note(note))
            row.append(edit)

        row._expand_btn = expand  # type: ignore[attr-defined]
        return row

    # -- seleccion ----------------------------------------------------------
    def _select_row(self, row):
        if row in self.rows:
            self.selected = self.rows.index(row)
            self._apply_selection()

    def _on_row_pressed(self, _gesture, _n_press, _x, _y, row):
        """Clic del mouse sobre una fila: la selecciona y la abre/cierra."""
        self._select_row(row)
        btn = getattr(row, "_expand_btn", None)
        if btn is not None:
            self._on_expand(btn, row._note, row._desc, btn, row._state)

    def _apply_selection(self):
        for i, row in enumerate(self.rows):
            if i == self.selected:
                row.add_css_class("selected")
            else:
                row.remove_css_class("selected")
        if 0 <= self.selected < len(self.rows):
            row = self.rows[self.selected]
            row.grab_focus()
            GLib.idle_add(self._scroll_to, row)
        return False

    def _scroll_to(self, row):
        if self.scrolled is None:
            return False
        ok, rect = row.compute_bounds(self.list_box)
        if not ok:
            return False
        adj = self.scrolled.get_vadjustment()
        top = rect.get_y()
        bottom = top + rect.get_height()
        if top < adj.get_value():
            adj.set_value(top)
        elif bottom > adj.get_value() + adj.get_page_size():
            adj.set_value(bottom - adj.get_page_size())
        return False

    def _move_selection(self, delta):
        if not self.rows:
            return
        self.selected = max(0, min(self.selected + delta, len(self.rows) - 1))
        self._apply_selection()

    # -- teclado ------------------------------------------------------------
    def _on_key(self, _ctrl, keyval, _code, state):
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        lower = Gdk.keyval_to_lower(keyval)
        panel_visible = self.panel is not None and self.panel.get_visible()

        # Ctrl+S: abre/cierra el panel. Al abrir muestra la lista de modulos.
        if ctrl and lower == Gdk.KEY_s:
            if panel_visible:
                self.panel.close_or_save()
            else:
                self._show_panel()
                self.panel.show_home()
            return True
        if ctrl and lower == Gdk.KEY_q:
            self._quit()
            return True
        if ctrl and lower == Gdk.KEY_n:  # Ctrl+N y Ctrl+Shift+N
            self.new_note()
            return True
        if ctrl and shift and lower == Gdk.KEY_m:
            self._edit_selected()
            return True
        if ctrl and shift and lower == Gdk.KEY_l:
            self._delete_selected()
            return True
        if ctrl and shift and lower == Gdk.KEY_j:
            self._open_json_module()
            return True
        if ctrl and shift and lower == Gdk.KEY_r:
            self._refresh_moodle()
            return True

        if panel_visible:
            if keyval == Gdk.KEY_Escape:
                self.panel.go_back()
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                if ctrl and shift:
                    self.panel.focus_prev()
                    return True
                if ctrl:
                    self.panel.focus_next()
                    return True
                focus = self.window.get_focus()
                is_entry = focus is not None and focus.get_ancestor(Gtk.Entry) is not None
                if is_entry:
                    self.panel.save_and_hide()
                    return True
                # Enter dentro del area de texto: nueva linea (GTK por defecto)
                return False
            # flechas / Tab los maneja GTK dentro del panel
            return False

        # Panel oculto: navegacion de la lista
        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._move_selection(-1)
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._move_selection(1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._toggle_selected()
            return True
        return False

    def _selected_row(self):
        if 0 <= self.selected < len(self.rows):
            return self.rows[self.selected]
        return None

    def _toggle_selected(self):
        row = self._selected_row()
        if row is None:
            return
        self._on_expand(row._expand_btn, row._note, row._desc,
                        row._expand_btn, row._state)

    def _edit_selected(self):
        row = self._selected_row()
        if row is not None and not getattr(row, "_read_only", False):
            self.edit_note(row._note)

    def _delete_selected(self):
        row = self._selected_row()
        if row is None:
            return
        # Solo se eliminan las tareas de la seccion roja.
        if getattr(row, "_bucket", "green") != "red":
            return
        if getattr(row, "_read_only", False):
            # Tarea de Moodle: se marca como hecha (oculta, persistida local).
            moodle.mark_done(row._note.id)
            GLib.idle_add(self.refresh)
            return
        self.store.delete(row._note)
        GLib.idle_add(self.refresh)

    # -- callbacks ----------------------------------------------------------
    def _on_check(self, check, note):
        if check.get_active():
            self.store.delete(note)
            GLib.idle_add(self.refresh)

    def _on_expand(self, _btn, note, desc, button, state):
        state["expanded"] = not state["expanded"]
        expanded = state["expanded"]
        desc.set_label(note.description or "(sin descripcion)")
        desc.set_visible(expanded)
        if expanded:
            desc.add_css_class("expanded")
        else:
            desc.remove_css_class("expanded")
        button.set_label("\u25be" if expanded else "\u25b8")

    def _show_panel(self):
        self.panel.set_visible(True)
        # El panel aprieta la lista: pasa a una sola columna.
        GLib.idle_add(self._relayout)

    def _on_panel_hide(self):
        self._remember_size()
        # El panel se oculta: vuelve a repartir en columnas por color.
        self._relayout()
        if self.rows:
            GLib.idle_add(self._apply_selection)

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
        # Oculta en vez de destruir: la app queda residente y el atajo de
        # teclado la vuelve a mostrar al instante (sin arrancar Python+GTK).
        self._remember_size()
        if self.window is not None:
            self.window.set_visible(False)
        return True

    def _quit(self):
        self._remember_size()
        self.quit()

    def new_note(self):
        self.panel.load(None)
        self._show_panel()

    def edit_note(self, note):
        self.panel.load(note)
        self._show_panel()


def main():
    app = NotesApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
