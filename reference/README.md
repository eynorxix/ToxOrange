# reference/ — plantilla (snapshot del widget de notas)

Copia congelada del widget de notas que sirve de **ejemplo canónico** para
rehacer Gonty en GTK4. Fuente viva (puede evolucionar):

- `~/.local/share/noteswidget/` → `widget.py`, `notes_core.py`,
  `moodle_module.py`, `style.css`
- `~/.local/bin/notes-widget` → launcher

| Archivo aquí | Rol |
|---|---|
| `widget.py` | App GTK4 completa: temas, `SidePanel` + `Gtk.Stack`, franja, atajos, launcher D-Bus, resize Wayland. |
| `style.css` | Estética completa (tokens `@bg/@fg/@accent/...` + clases). Reutilizar tal cual. |
| `notes_core.py` | Modelo de datos `@dataclass` + persistencia a markdown/JSON. |
| `moodle_module.py` | Provider de red → cache JSON en hilo de fondo + `GLib.idle_add`. |
| `notes-widget-launcher` | Bash: instancia única por D-Bus, reinicio si cambia el código. |

> No editar aquí para el widget real (eso vive en `~/.local/share/noteswidget`).
> Esta carpeta es solo referencia/plantilla para el proyecto Gonty.
