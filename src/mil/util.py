"""Utilidades pequeñas: fechas, ritmos, E/S de JSON."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def dia_idx(nombre: str) -> int:
    return DIAS.index(nombre.strip().lower()[:3].replace("é", "e"))


def to_date(x) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


def monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def parse_mmss(text) -> float | None:
    """'24:10' -> 1450.0 segundos; '1:02:30' -> 3750.0."""
    if text is None or text == "":
        return None
    parts = [float(p) for p in str(text).split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def fmt_pace(sec_per_km: float) -> str:
    s = int(round(sec_per_km))
    return f"{s // 60}:{s % 60:02d}"


def fmt_hms(secs: float) -> str:
    s = int(round(secs))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
