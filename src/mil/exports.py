"""Exporta el plan a CSV y a iCalendar (.ics) para importarlo en Google Calendar, Apple Calendar, etc."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path


def to_csv(plan: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["date", "weekday", "week", "phase_name", "week_kind", "type", "title", "km", "duration_min", "zone", "description", "cum_plan_km"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in plan["days"]:
            w.writerow(d)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 74:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (74 if not out else 73):
            out.append(cur.decode("utf-8"))
            cur = b
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def to_ics(plan: dict, path: Path, include_rest: bool = False) -> int:
    name = plan["meta"]["proyecto"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{name}//ES", "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{_esc(name)}"]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n = 0
    for d in plan["days"]:
        if d["type"] == "rest" and not include_rest:
            continue
        if d["type"] == "reserve" and d["role"] != "M0":
            continue
        day = dt.date.fromisoformat(d["date"])
        nxt = day + dt.timedelta(days=1)
        icon = {"run": "Correr", "strength": "Fuerza", "reserve": "Margen"}.get(d["type"], "Descanso")
        km = f" {d['km']:g} km" if d["km"] else ""
        summary = f"{icon}: {d['title']}{km}"
        desc = f"Semana {d['week']} ({d['phase_name']}). {d['description']}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{d['date']}-{d['type']}@{name.lower().replace(' ', '-')}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{nxt.strftime('%Y%m%d')}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
        n += 1
    lines.append("END:VCALENDAR")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(_fold(l) for l in lines) + "\r\n", encoding="utf-8")
    return n
