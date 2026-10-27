#!/usr/bin/env python3
"""Modulo Moodle: descarga el calendario (iCal), lo convierte a JSON y lo
guarda localmente. El widget lo muestra en un visor JSON.

Archivo de datos: ~/.config/noteswidget/moodle.json

    {
      "url": "https://.../calendar/export_execute.php?...",
      "fetched_at": "2026-10-14T13:20:00-04:00",
      "count": 16,
      "events": [
        {
          "uid": "140831@aula-virtual.unifranz.edu.bo",
          "title": "Tarea 3 - Pruebas API y UI",
          "summary": "Vencimiento de Tarea 3 - Pruebas API y UI",
          "description": "...",
          "is_task": true,
          "start": "2026-10-11T03:59:00+00:00",
          "start_local": "2026-10-10T23:59:00-04:00",
          "end": "2026-10-11T03:59:00+00:00",
          "end_local": "2026-10-10T23:59:00-04:00",
          "end_time": "23:59",
          "date": "10/10/26",
          "days_left": -4,
          "hours_left": -102.0
        }
      ]
    }

Uso (CLI, para el timer):
    python3 moodle_module.py --update          # descarga y guarda el JSON
    python3 moodle_module.py --url <URL>       # guarda la URL
    python3 moodle_module.py --print           # imprime el JSON actual
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_PATH = Path.home() / ".config" / "noteswidget" / "moodle.json"
DONE_PATH = Path.home() / ".config" / "noteswidget" / "moodle_done.json"
REFRESH_HOURS = 12
TASK_PREFIX_RE = re.compile(r"^vencimiento\s+de\s+", re.I)

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("America/La_Paz")
except Exception:  # pragma: no cover
    LOCAL_TZ = timezone(timedelta(hours=-4))

EMPTY = {"url": "", "fetched_at": "", "count": 0, "events": []}


# --------------------------------------------------------------------------- #
# Persistencia
# --------------------------------------------------------------------------- #
def load_data() -> dict:
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(EMPTY)
        data.setdefault("url", "")
        data.setdefault("fetched_at", "")
        data.setdefault("events", [])
        data.setdefault("count", len(data["events"]))
        return data
    except (OSError, ValueError):
        return dict(EMPTY)


def save_data(data: dict):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_url() -> str:
    return load_data().get("url", "")


def set_url(url: str) -> dict:
    data = load_data()
    data["url"] = (url or "").strip()
    save_data(data)
    return data


def pretty() -> str:
    return json.dumps(load_data(), ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Tareas marcadas como hechas / ocultas (local, por UID)
# --------------------------------------------------------------------------- #
def done_uids() -> set:
    try:
        data = json.loads(DONE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
    except (OSError, ValueError):
        pass
    return set()


def _save_done(uids: set):
    DONE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DONE_PATH.write_text(
        json.dumps(sorted(uids), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def mark_done(uid: str):
    uids = done_uids()
    uids.add(str(uid))
    _save_done(uids)


def unmark_done(uid: str):
    uids = done_uids()
    uids.discard(str(uid))
    _save_done(uids)


def clear_done():
    _save_done(set())


def is_done(uid: str) -> bool:
    return str(uid) in done_uids()


# --------------------------------------------------------------------------- #
# Red / parseo iCal
# --------------------------------------------------------------------------- #
def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def _unfold(raw: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", raw)


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_events(ics: str):
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", _unfold(ics), re.S):
        def get(prop):
            m = re.search(r"^" + prop + r"(?:;[^:\n]*)?:(.*)$", block, re.M)
            return m.group(1).strip() if m else ""

        events.append(
            {
                "uid": get("UID"),
                "summary": _unescape(get("SUMMARY")),
                "description": _unescape(get("DESCRIPTION")),
                "categories": _unescape(get("CATEGORIES")),
                "dtstart": get("DTSTART"),
                "dtend": get("DTEND"),
            }
        )
    return events


def _course_from_categories(value: str):
    """De '02/2026/EAT/SIS/TQA-711 (P)/P1/CHID30245' saca (materia, carrera)."""
    value = (value or "").strip()
    if not value:
        return "", ""
    parts = [p.strip() for p in value.split("/") if p.strip()]
    career = parts[3] if len(parts) > 3 else ""
    course = parts[4] if len(parts) > 4 else (parts[-1] if parts else value)
    return course, career


def _parse_dt(value: str):
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", value or "")
    if not m:
        return None
    y, mo, d, h, mi, s = map(int, m.groups())
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def _event_json(event: dict, now) -> dict:
    start = _parse_dt(event["dtstart"])
    end = _parse_dt(event["dtend"])
    local = start.astimezone(LOCAL_TZ) if start else None
    local_end = end.astimezone(LOCAL_TZ) if end else local
    is_task = bool(TASK_PREFIX_RE.match(event["summary"]))
    title = event["summary"].strip()
    if is_task:
        title = TASK_PREFIX_RE.sub("", title).strip()
    course, career = _course_from_categories(event.get("categories", ""))
    return {
        "uid": event["uid"],
        "title": title,
        "summary": event["summary"],
        "description": event["description"],
        "course": course,
        "career": career,
        "categories": event.get("categories", ""),
        "is_task": is_task,
        "start": start.isoformat() if start else "",
        "start_local": local.isoformat() if local else "",
        "end": end.isoformat() if end else "",
        "end_local": local_end.isoformat() if local_end else "",
        "end_time": local_end.strftime("%H:%M") if local_end else "",
        "date": local.strftime("%d/%m/%y") if local else "",
        "days_left": (local.date() - now.date()).days if local else None,
        "hours_left": round((local_end - now).total_seconds() / 3600, 2)
        if local_end
        else None,
    }


def refresh(url: str | None = None) -> dict:
    data = load_data()
    url = (url or data.get("url", "")).strip()
    if not url:
        raise ValueError("Falta la URL del calendario")

    ics = _fetch(url)
    if "BEGIN:VCALENDAR" not in ics:
        snippet = ics.strip()[:120] or "(vacio)"
        raise ValueError(f"Respuesta no valida del servidor: {snippet}")

    now = datetime.now(LOCAL_TZ)
    events = [_event_json(e, now) for e in _parse_events(ics)]
    events.sort(key=lambda e: (e["start"] or "", e["title"].lower()))

    data = {
        "url": url,
        "fetched_at": now.isoformat(timespec="seconds"),
        "count": len(events),
        "events": events,
    }
    save_data(data)
    return data


def is_stale(hours: int = REFRESH_HOURS) -> bool:
    fetched = load_data().get("fetched_at")
    if not fetched:
        return True
    try:
        dt = datetime.fromisoformat(fetched)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return True
    return (datetime.now(LOCAL_TZ) - dt) > timedelta(hours=hours)


# --------------------------------------------------------------------------- #
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sincronizacion de Moodle a JSON")
    parser.add_argument("--update", action="store_true", help="descargar y guardar")
    parser.add_argument("--url", help="guardar la URL del calendario")
    parser.add_argument("--print", dest="do_print", action="store_true",
                        help="imprimir el JSON actual")
    args = parser.parse_args()

    if args.url is not None:
        set_url(args.url)
        print("[moodle] URL guardada")

    if args.update:
        try:
            data = refresh()
            print(f"[moodle] actualizado: {data['count']} eventos")
        except Exception as exc:
            print(f"[moodle] error: {exc}")
            return 1

    if args.do_print:
        print(pretty())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
