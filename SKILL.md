---
name: kde-gonty
description: >
  Use when building "Gonty" (the TioPlus streaming / Nostr-forum Android app)
  as a native KDE/Linux desktop app. Trigger keywords: gonty, KDE_gonty,
  gonty desktop, portar gonty, gonty en KDE, reproductor GTK4, scraping GTK4.
  Recipe: Python + GTK4 (PyGObject) + CSS, same style/architecture as the
  notes widget at ~/.local/share/noteswidget.
---

# Skill: Gonty para escritorio (KDE) — GTK4 + Python + CSS

## Qué es esto

Rehacer **Gonty** (app Android de streaming tipo "TioPlus" + foro Nostr,
escrita en Kotlin + Jetpack Compose) como una **app nativa de escritorio para
Linux/KDE**, usando **el mismo enfoque que el widget de notas** que ya hicimos:

> **Python 3 + GTK4 (PyGObject) + CSS, sin Compose, sin frameworks pesados.**

El objetivo es una app **liviana** (~120–250 MB RAM, ~0 % CPU en reposo),
**responsiva** (se adapta al ancho de ventana) y con el **mismo estilo
terminal/transparencia** del widget.

La carpeta `reference/` contiene el **proyecto widget completo** como ejemplo
canónico de arquitectura y estilo. **Cópialo como base y adáptalo.**

## Reglas duras (no negociables)

1. **Stack:** `Python 3` + `GTK4` + `PyGObject` (`Gdk, Gio, GLib, Gtk, Pango`).
   **NO** usar `libadwaita`. **NO** usar Qt/Compose/Electron/WebView para la UI.
2. **Estilo:** reutilizar el sistema de temas del widget (dict `THEMES` +
   `@define-color` inyectado a un `CssProvider` + `style.css`). Mismo look:
   monoespaciado, `border-radius`, transparencia por `rgba`, franja `.frame`.
3. **Sin ventanas separadas:** todo vive en una sola ventana; los "módulos" son
   páginas de un `Gtk.Stack` dentro de un panel lateral (patrón `SidePanel`).
4. **Estado en JSON** (como `state.json` / `moodle.json` del widget), no SQLite.
5. **Rutas portables:** usar `Path.home()`, no `/home/eynor/...` hardcodeado.
6. **Verificar siempre**: `python3 -m py_compile` + un test headless (ver Test).
7. **No comentar en exceso** el código; sí usar docstrings de una línea.

## Template canónico: `reference/`

| Archivo | Qué copiar de él |
|---|---|
| `reference/widget.py` | Arquitectura: `Gtk.Application`, ventana sin marco, `SidePanel` con páginas (`home`/`editor`/`json`), `Gtk.Stack`, sistema de temas, `_load_css`, atajos de teclado, launcher por D-Bus (instancia única). |
| `reference/style.css` | **Toda la estética.** Tokens: `@bg, @bg_soft, @bg_hover, @panel_bg, @input_bg, @fg, @muted, @accent, @accent_hover, @on_accent, @green, @yellow, @red, @border`. Clases base: `.card`, `.frame`, `.titlebar`, `.note-row`, `button.icon-btn`, `button.primary`, `button.flat`, `.module-row`, `.json-*`. |
| `reference/notes_core.py` | Patrón de modelo de datos: `@dataclass` + `as_dict/from_dict` + persistencia a `.md`/JSON. |
| `reference/moodle_module.py` | Patrón de "provider" que baja datos de red y los cachea a JSON. |
| `reference/notes-widget-launcher` | Launcher bash: instancia única por D-Bus (`gdbus`), reinicio si el código cambió. |

**Antes de escribir código, lee `reference/widget.py` y `reference/style.css`.**
Copia el sistema de temas y el `_load_css` **tal cual**; solo cambian las
pantallas.

## Sistema de estilo (copiar de `reference/widget.py`)

- `THEMES`: dict `nombre -> paleta` con las 14 claves de color (ver
  `reference/widget.py` líneas ~43-156). Temas incluidos: Tokyo Night, Matte
  Black, Ghost Pastel, Gruvbox, Nord, Catppuccin Mocha, Dracula.
- `DEFAULT_THEME` y `_palette_css(theme, transparency)` generan el bloque
  `@define-color ... ;` y se cargan en **un solo** `CssProvider`
  (`Gtk.StyleContext.add_provider_for_display(display, provider,
  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)`), junto con `style.css`.
- `_scale_font_css(css, scale)`: escala los `font-size:Npx` para el control de
  tamaño de fuente. Añade además `window.notes-window { font-size: Nem; }`.
- Transparencia: `window { background-color: transparent; }` + `.card { background-color: @bg; }`
  donde `@bg` es un `rgba(...)` con alpha. En Wayland da transparencia real;
  en X11 necesita un compositor (xfwm4 la tiene).
- Ventana sin marco: `win.set_decorated(False)`; para redimensionar en Wayland,
  usar handles con `Gtk.Overlay` + `surface.begin_resize(...)` (ver
  `reference/widget.py` `_add_resize_handles`), protegido con
  `hasattr(surface, "begin_resize")`.

## Estructura de proyecto propuesta

```
KDE_gonty/
  SKILL.md
  reference/                # ejemplo widget (no tocar, es la plantilla)
  app/
    main.py                 # Gtk.Application, una sola ventana
    theme.py                # THEMES + _palette_css + _load_css (copiados)
    style.css               # copiado de reference/style.css
    models.py               # ContentItem, ServerInfo, SeasonEpisode (dataclasses)
    providers/              # scrapers (uno por sitio), ver "Scraping"
      __init__.py
      base.py               # Protocolo ScraperProvider
      tioplus.py
      lamovie.py
    store.py                # cache JSON (catálogo, favoritos, historial)
    nostr/                  # cliente Nostr (websockets + secp256k1)
    player/                 # reproductor de video (ver "Video")
    ui/
      home.py               # páginas del Gtk.Stack
      catalog.py
      detail.py
      player_page.py
      profile.py
  bin/gonty                 # launcher (copiar de reference/notes-widget-launcher)
```

## ScraperProvider en Python

El contrato Kotlin (`scraper/.../ScraperProvider.kt`) se traduce a un `Protocol`:

```python
class ScraperProvider(Protocol):
    id: str
    name: str
    supported_types: list[str]

    def scrape_section(self, type_: str, on_progress=...) -> list[ContentItem]: ...
    def search(self, query: str) -> list[ContentItem]: ...
    def scrape_detail(self, slug: str, type_: str) -> ContentItem | None: ...
    def scrape_episode_servers(self, type_, slug, season, episode) -> tuple[list[ServerInfo], str]: ...
    def get_embed_url(self, player_url: str) -> str: ...
```

- HTTP: `urllib.request` (stdlib) o `requests`. **Hacer red SIEMPRE en un hilo**
  (`threading.Thread` + `GLib.idle_add` para volver al hilo de UI), igual que
  hace `moodle_module.py`. **Nunca** bloquear el bucle de GTK.
- Parsing: `beautifulsoup4` + `lxml` (equivalente a Jsoup). Manejar **base64**
  de servidores (`ServerInfo.base64`) con `base64.b64decode`.
- Cachear el catálogo a JSON en `~/.config/gonty/` (patrón `moodle.json`).
- Aislamiento de fallos: cada provider en su propio try/except; un sitio caído
  no debe romper la app.

## Video (el punto difícil) — SOLUCIÓN REAL: híbrido WebKitGTK 6.0

La app Android usa un **WebView que carga la página embed tal cual** (no
reproduce el m3u8 directo). Los CDN bloquean el m3u8 fuera de su página
(referer/hotlink), así que **en escritorio hay que imitar eso con un WebKit
embebido**, no con GStreamer.

**Requiere `webkitgtk-6.0`** (namespace `WebKit`, versión `"6.0"`), NO
`webkit2gtk-4.1` (ese es GTK3 e incompatible con GTK4). En Arch:
`sudo pacman -S webkitgtk-6.0`. Además **`gst-plugins-good`** (si falta,
WebKit no encuentra `autoaudiosink`/`autovideosink`/`vp8dec`/`vp9dec` → el
video no arranca; ver `pipeline` de salida con `GST_DEBUG`).

Arquitectura (`app/player/`):
- `webview.py`: `WebViewEngine` con `WebKit.WebView(user_content_manager=ucm)`.
  Cargar JS con `UserScript` (ALL_FRAMES): START neutraliza
  `window.open/alert/confirm/prompt`; END elimina iframes/overlays de ads,
  pinta negro y **fuerza `video.play()`** (con fallback a `muted` y reintentos
  en 0.6/1.5/2.5/4/6/9 s), más clic automático en botones de play (JW Player:
  `.jw-icon-playback`, `jwplayer().play()`). `create`→None (niega popups);
  `decide-policy` bloquea navegación a dominios de ads (`adblock.py`).
  Settings clave: `media_playback_requires_user_gesture=False`,
  `enable_mediasource=True`, `enable_media_stream=True`,
  `javascript_can_open_windows_automatically=False`.
- **Detección de reproducción:** `WebView.is_playing_audio()` (¡existe!). Usar
  eso, NO `evaluate_javascript_finish` (falla con "Unsupported result type").
- `engine.py`: GStreamer (`playbin`) o `Gtk.MediaFile` como alternativa con el
  botón `⇄`. Ojo: `Gtk.MediaFile.new_for_file(Gio.File.new_for_uri(uri))`.
- `stream.py`: `resolve_stream_url` resuelve redirecciones JS
  (`window.location.href`, meta refresh) de la página del provider.

**Auto-fallback de servidores (clave para UX):** los server-list tienen hosts
muertos (cert TLS inválido, 404, TLS EOF). Ordenar los buenos primero y, si a
los ~14 s `is_playing_audio()` sigue en False (o falla `load-failed` del frame
principal), **pasar automáticamente al siguiente servidor** (sin spamear el
historial). Ejemplo real: `videoapp.zip` y `vidhideplus.com` reproducen;
`goodstream.one` (cert no coincide), `hlswish.com` (TLS EOF) y `voe.sx` (404)
no. Verificar hosts con `curl -sSL -o /dev/null -w "%{http_code}"`.

GStreamer/mpv quedan como respaldo; el default es WebKit embed, como en Android.

**Pantalla completa del player del servidor:** los embeds tienen su propio
botón de fullscreen. En WebKitGTK hay que conectar `enter-fullscreen` /
`leave-fullscreen` en el `WebView` (existen en 6.0) y en el handler hacer
`window.fullscreen()` / `unfullscreen()`, ocultando la cabecera y los controles
propios para que el video llene la pantalla. Devolver `True` desde el handler.
Ojo: `window.is_fullscreen()` es **asíncrono** (devuelve el estado en el
siguiente frame) → llevar un flag propio de fullscreen, no basar el toggle en
`is_fullscreen()`. Añadir también botón `⛶` y tecla `F` propios, y que `Esc`
salga primero de pantalla completa (usar un `EventControllerKey` en fase
`CAPTURE` para que los atajos funcionen aunque el foco esté en el `WebView`).

## Nostr

Reimplementar en Python lo que hace `app/src/main/java/com/example/gonty/nostr/`:
- Transporte: `websockets` (o `websocket-client`) a los relays (`wss://`).
- Firma/verificación: `secp256k1` (`coincurve`) o `pip install nostr-sdk`
  (bindings) para no reinventar Schnorr/BIP-340.
- Modelos `NostrPost`/`NostrKeys` → dataclasses; guardar claves en
  `~/.config/gonty/nostr.json` (nunca en el repo).

## Responsividad (patrón del widget)

- Cuerpo = `Gtk.Box(HORIZONTAL)`: lista/catálogo (hexpand) + panel lateral
  (ancho fijo, oculto por defecto). Al abrir el panel, la lista se reacomoda
  (no queda tapada): **es un Box, no un Overlay.**
- Rejillas por columnas con `Gtk.Box.set_homogeneous(True)` para repartir ancho
  en partes iguales (evita que un texto largo ensanche su columna).
- Alturas uniformes: reservar con `min-height` en CSS (em) para títulos/meta,
  y `set_lines(N)` + `set_ellipsize(END)` para no depender del texto.
- Alternar 1 columna ↔ N columnas según `panel.get_visible()` (patrón
  `_relayout` del widget).
- `Gtk.Stack` con `SLIDE_LEFT_RIGHT` para navegar entre páginas (Home →
  Catálogo → Detalle → Reproductor), más un botón `←` (Esc = volver).

## Test / verificación (copiar el método del widget)

No hay que abrir la app a mano: escribir tests GTK headless-ish.

```python
import os, sys, tempfile, pathlib
os.environ.setdefault("GDK_BACKEND", "wayland")   # o "x11"/"headless"
sys.path.insert(0, "/ruta/al/proyecto")
import gi; gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib
import main  # tu app
main.APP_ID = "net.local.gonty.test"          # id único por test
main.STATE_PATH = pathlib.Path(tempfile.mkdtemp()) / "state.json"
app = main.GontyApp()
def run():
    app._load_css(); app.window = app._build_window(); app.window.present()
    def measure():
        # las medidas reales solo existen tras el layout: usar timeout_add
        ...
        app.quit(); return False
    GLib.timeout_add(300, measure); return False
GLib.idle_add(run); app.run(["test"])
```

Pitfalls (aprendidos en el widget):
- El layout solo se calcula tras el *frame clock* → medir dentro de
  `GLib.timeout_add(150-300ms)` después de `present()`.
- `get_allocation` está deprecado → usar `get_width()/get_height()`.
- `get_preferred_size()` devuelve 2 `Graphene.Rect` (`[0]`=min, `[1]`=natural).
- Filtrar ruido: `grep -viE "gtk_icon_theme|Gtk-WARNING|Gtk-CRITICAL|did not|Adwaita|Gdk-WARNING"`.
- `pgrep -af "gonty/main[.]py"` (el `[.]` evita auto-match).
- Para probar red/scraping: usar un fixture JSON local, no pegarle al sitio real.

## Empaquetado / integración KDE

- `bin/gonty`: copiar de `reference/notes-widget-launcher` y ajustar
  `APP_ID="org.eynor.gonty"`, `OBJ_PATH="/org/eynor/gonty"`, `PY_FILE`.
- Desktop entry en `~/.local/share/applications/gonty.desktop`
  (`Exec=` launcher, `Icon=`, `Categories=AudioVideo;Player;`).
- Autostart opcional en `~/.config/autostart/`.
- Sincronización periódica (si aplica): **reusar el patrón systemd user timer**
  (`moodle-sync.{service,timer}`) del proyecto widget.
- Atajo: crear entrada en KDE (ej. `Meta+Ctrl+G`).

## Mapeo Gonty (Android) → escritorio

| Android (Gonty) | Escritorio (esta app) |
|---|---|
| Jetpack Compose + Material3 | GTK4 + CSS (esta skill) |
| OkHttp | `urllib`/`requests` |
| Jsoup (`:scraper`) | `beautifulsoup4` + `lxml` |
| Media3 ExoPlayer (HLS) | GStreamer / mpv |
| Coil | `GdkPixbuf` / carga a disco |
| navigation-compose | `Gtk.Stack` + botón `←`/Esc |
| `MainActivity`/`Context` | `Gtk.Application` + una `ApplicationWindow` |
| `res/drawable/*.xml` | CSS + clases (glifos/emoji o SVG vía `Gtk.Image`) |
| NostrClient / NostrCrypto | `websockets` + `secp256k1` |
| State (SharedPreferences) | JSON en `~/.config/gonty/` |

## Plan por fases (sugerido)

1. **Esqueleto**: ventana GTK4 + temas + `Gtk.Stack` + panel lateral +
   `style.css` del widget. Módulos "Home" y "Acerca de".
2. **Catálogo (scraping)**: `provider` base + 1 sitio, cache JSON, grid
   responsivo con posters (`GdkPixbuf`), búsqueda.
3. **Detalle**: temporadas/episodios, lista de servidores.
4. **Reproductor**: WebKitGTK 6.0 embebido cargando el embed del servidor
   (default) + GStreamer como alternativa (`⇄`) + auto-fallback de servidores.
5. **Perfil / listas / historial** (JSON).
6. **Nostr**: feeds, posts, likes (último; más complejo).

Cada fase = correr test + `py_compile` + commit. No avanzar a la siguiente sin
la anterior verificada.

## Presupuesto de recursos (referencia)

- Widget de notas: ~160 MB RSS (~95 MB propio + ~70 MB GTK compartido), 0 % CPU
  en reposo. Gonty en GTK4 debería quedar en rango similar aun con listas
  grandes; vigilar **no** dejar bucles/timers despiertos.
```
