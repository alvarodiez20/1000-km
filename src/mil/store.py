"""Almacén JSON de actividades, bienestar y perfil. Idempotente: fusiona por id o fecha."""

from __future__ import annotations

from pathlib import Path

from .util import read_json, write_json

ROOT = Path(".")


def paths(root: Path | None = None) -> dict[str, Path]:
    r = Path(root) if root else ROOT
    return {
        "activities": r / "data" / "activities.json",
        "wellness": r / "data" / "wellness.json",
        "profile": r / "data" / "profile.json",
        "plan": r / "plan" / "plan.json",
        "summary": r / "data" / "summary.json",
    }


def load_activities(root=None) -> list[dict]:
    return read_json(paths(root)["activities"], []) or []


def merge_activities(new: list[dict], root=None) -> tuple[int, int]:
    """Devuelve (añadidas, actualizadas)."""
    cur = {a["id"]: a for a in load_activities(root)}
    added = updated = 0
    for a in new:
        if a["id"] in cur:
            if cur[a["id"]] != a:
                cur[a["id"]] = {**cur[a["id"]], **{k: v for k, v in a.items() if v is not None}}
                updated += 1
        else:
            cur[a["id"]] = a
            added += 1
    write_json(paths(root)["activities"], sorted(cur.values(), key=lambda a: (a["date"], a.get("start", ""))))
    return added, updated


def load_wellness(root=None) -> dict[str, dict]:
    return read_json(paths(root)["wellness"], {}) or {}


def merge_wellness(new: dict[str, dict], root=None) -> int:
    cur = load_wellness(root)
    n = 0
    for day, rec in new.items():
        clean = {k: v for k, v in rec.items() if v is not None}
        if not clean:
            continue
        cur[day] = {**cur.get(day, {}), **clean}
        n += 1
    write_json(paths(root)["wellness"], dict(sorted(cur.items())))
    return n


def load_profile(root=None) -> dict:
    return read_json(paths(root)["profile"], {}) or {}


def update_profile(fields: dict, root=None) -> dict:
    prof = load_profile(root)
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(prof.get(k), dict):
            prof[k] = {**prof[k], **v}
        else:
            prof[k] = v
    write_json(paths(root)["profile"], prof)
    return prof
