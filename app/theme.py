"""Sistema de temas de Gonty: paletas + CSS inyectado (patron del widget)."""
from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

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

DEFAULT_FONT_SCALE = 1.0
MIN_FONT_SCALE = 0.8
MAX_FONT_SCALE = 2.0

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


def hex_to_rgba(value):
    c = Gdk.RGBA()
    if not c.parse(value or ""):
        c.parse("#7aa2f7")
    return c


def rgba_to_hex(c):
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


def band_css(band):
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


def palette_css(theme_name, transparent, transparency):
    base = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
    main = 1.0 if not transparent else max(0.05, 1.0 - transparency)
    pal = dict(base)
    for key, ratio in _BG_RATIOS.items():
        pal[key] = _rgba(base[key], min(1.0, main * ratio))
    pal["panel_bg"] = _rgba(base["panel_bg"], min(1.0, main + 0.16))
    return _PALETTE_TEMPLATE.format(**pal)


def scale_font_css(css, scale):
    if abs(scale - 1.0) < 1e-6:
        return css

    def repl(match):
        value = float(match.group(1)) * scale
        return f"font-size: {round(value, 1)}px"

    return re.sub(r"font-size:\s*([0-9.]+)px", repl, css)


class ThemeManager:
    """Carga style.css + paleta del tema activo en un solo CssProvider."""

    def __init__(self, css_path):
        self.css_path = css_path
        self.theme = DEFAULT_THEME
        self.transparent = True
        self.transparency = 0.18
        self.font_scale = DEFAULT_FONT_SCALE
        self.band = normalize_band(None)
        self.provider = None

    def load(self):
        try:
            base = self.css_path.read_text(encoding="utf-8")
        except OSError:
            base = ""
        base = scale_font_css(base, self.font_scale)
        font_rule = f"window.gonty-window {{ font-size: {self.font_scale}em; }}\n"
        css = (palette_css(self.theme, self.transparent, self.transparency)
               + "\n" + base + "\n" + band_css(self.band) + "\n" + font_rule)

        if self.provider is None:
            self.provider = Gtk.CssProvider()
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display, self.provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        if hasattr(self.provider, "load_from_string"):
            self.provider.load_from_string(css)
        else:
            self.provider.load_from_data(css.encode("utf-8"))
