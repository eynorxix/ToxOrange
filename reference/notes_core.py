"""Nucleo de datos del widget de notas.

Cada recordatorio se guarda como un archivo Markdown (.md) en NOTE_DIR.
El archivo lleva un bloque de frontmatter con JSON (editable como texto)
y debajo el cuerpo en Markdown.

Formato del archivo .md:

    <!-- notes:data
    {
      "id": "...",
      "title": "...",
      "description": "...",
      "date": "dd/mm/aa",
      "time": "HH:MM",
      "done": false,
      "created": "...",
      "updated": "..."
    }
    -->

    # Titulo

    Descripcion completa.

    **Fecha limite:** dd/mm/aa HH:MM
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

NOTE_DIR = Path("/home/eynor/Documents/Notes")

# Descripcion: maximo de palabras antes de recortar con "..."
DESC_WORD_LIMIT = 15
# Si el texto viene "pegado" (una palabra sin espacios mas larga que esto),
# se recorta por caracteres en lugar de por palabras.
DESC_CHAR_LIMIT = 35

# Umbrales de urgencia (en dias) para el color de "dias restantes".
#   rojo    -> faltan DANGER_MAX_DAYS dias o menos (incluye hoy/vencido)
#   amarillo-> entre DANGER_MAX_DAYS y WARN_MAX_DAYS dias
#   verde   -> mas de WARN_MAX_DAYS dias (optimo)
DANGER_MAX_DAYS = 1
WARN_MAX_DAYS = 7

FRONT_RE = re.compile(r"<!--\s*notes:data\s*(?P<data>\{.*?\})\s*-->", re.DOTALL)
DATE_FORMATS = ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Fechas / urgencia
# --------------------------------------------------------------------------- #
def parse_date(value):
    """Convierte 'dd/mm/aa' (o 'dd/mm/aaaa') en date. Devuelve None si es invalida."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def format_date(value):
    """Normaliza a dd/mm/aa. Acepta str o date."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.strftime("%d/%m/%y")
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%y") if parsed else str(value).strip()


def format_time(value):
    """Normaliza 'HH:MM' (acepta 'H:MM', 'HH:MM:SS'). Devuelve '' si es invalida."""
    if value is None:
        return ""
    value = str(value).strip()
    if not value:
        return ""
    parts = value.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return ""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"


def format_stamp(note_date, note_time=""):
    """Une fecha y hora en 'dd/mm/aa HH:MM' (omite lo que falte)."""
    date_txt = format_date(note_date)
    time_txt = format_time(note_time)
    if date_txt and time_txt:
        return f"{date_txt} {time_txt}"
    return date_txt or time_txt


def days_left(note_date, today=None):
    """Dias que faltan hasta la fecha limite. None si no hay fecha valida."""
    parsed = parse_date(note_date)
    if parsed is None:
        return None
    today = today or date.today()
    return (parsed - today).days


def urgency(days):
    """Clasifica los dias restantes: none | overdue | danger | warn | ok."""
    if days is None:
        return "none"
    if days < 0:
        return "overdue"
    if days <= DANGER_MAX_DAYS:
        return "danger"
    if days <= WARN_MAX_DAYS:
        return "warn"
    return "ok"


def days_label(days):
    if days is None:
        return "sin fecha"
    if days < 0:
        return f"vencido hace {abs(days)}d"
    if days == 0:
        return "vence hoy"
    if days == 1:
        return "falta 1 dia"
    return f"faltan {days} dias"


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
def truncate_words(text, limit=DESC_WORD_LIMIT, char_limit=DESC_CHAR_LIMIT):
    """Recorta la descripcion y agrega ' ...' si sobra texto.

    - Texto normal: maximo `limit` palabras.
    - Texto "pegado" (palabras sin espacios mas largas que `char_limit`):
      se recorta a `char_limit` caracteres.
    """
    text = (text or "").strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    words = text.split()
    longest = max((len(w) for w in words[:limit]), default=0)
    if longest > char_limit:
        return text[:char_limit].rstrip() + " ..."
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]) + " ..."


def slugify(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text or "nota"


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #
@dataclass
class Note:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str = ""
    description: str = ""
    date: str = ""
    time: str = ""
    done: bool = False
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    file: str = ""  # ruta del .md en disco (no se serializa dentro del JSON)

    # -- JSON ---------------------------------------------------------------
    def as_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "date": self.date,
            "time": self.time,
            "done": self.done,
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data):
        note = cls()
        note.id = str(data.get("id") or note.id)
        note.title = data.get("title", "") or ""
        note.description = data.get("description", "") or ""
        note.date = data.get("date", "") or ""
        note.time = data.get("time", "") or ""
        note.done = bool(data.get("done", False))
        note.created = data.get("created", "") or note.created
        note.updated = data.get("updated", "") or note.updated
        return note

    def as_json(self):
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    # -- Markdown -----------------------------------------------------------
    def to_markdown(self):
        front = json.dumps(self.as_dict(), ensure_ascii=False, indent=2)
        body = f"# {self.title or 'Sin titulo'}\n\n"
        if self.description:
            body += self.description + "\n\n"
        stamp = format_stamp(self.date, self.time)
        if stamp:
            body += f"**Fecha limite:** {stamp}\n"
        return f"<!-- notes:data\n{front}\n-->\n\n{body}"

    @classmethod
    def from_markdown(cls, text, path=None):
        match = FRONT_RE.search(text or "")
        if not match:
            note = cls()
            note.title = _first_heading(text)
            note.description = _strip_heading(text)
        else:
            note = cls.from_dict(json.loads(match.group("data")))
        if path is not None:
            note.file = str(path)
        return note

    # -- Orden --------------------------------------------------------------
    def sort_key(self):
        parsed = parse_date(self.date)
        return (parsed is None, parsed or date.max, self.title.lower())


def _first_heading(text):
    for line in (text or "").splitlines():
        if line.strip().startswith("#"):
            return line.lstrip("#").strip()
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _strip_heading(text):
    out = []
    for line in (text or "").splitlines():
        if not out and line.lstrip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out).strip()


# --------------------------------------------------------------------------- #
# Almacen
# --------------------------------------------------------------------------- #
class NotesStore:
    def __init__(self, directory=None):
        self.dir = Path(directory) if directory else NOTE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def list_notes(self):
        notes = []
        for path in sorted(self.dir.glob("*.md")):
            try:
                notes.append(Note.from_markdown(path.read_text(encoding="utf-8"), path=path))
            except Exception:
                continue
        notes.sort(key=lambda n: n.sort_key())
        return notes

    def _target_path(self, note):
        return self.dir / f"{slugify(note.title)}--{note.id[:8]}.md"

    def save(self, note):
        note.updated = datetime.now().isoformat(timespec="seconds")
        if note.date:
            note.date = format_date(note.date)
        note.time = format_time(note.time) if note.time else ""
        target = self._target_path(note)
        old = Path(note.file) if note.file else None
        if old and old.exists() and old.resolve() != target.resolve():
            try:
                old.unlink()
            except OSError:
                pass
        target.write_text(note.to_markdown(), encoding="utf-8")
        note.file = str(target)
        return note

    def delete(self, note):
        path = Path(note.file) if note.file else None
        if path and path.exists():
            try:
                path.unlink()
            except OSError:
                pass
