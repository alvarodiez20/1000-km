"""Replanificación: redistribuye los km que faltan en las semanas que quedan."""

from __future__ import annotations

import datetime as dt
import statistics

from .analysis import runs_in_range, weekly_actual
from .planner import default_plan_end, generate_plan
from .util import monday_of, to_date


def replan(cfg: dict, old_plan: dict, acts: list[dict], profile: dict, today: dt.date) -> dict:
    start = to_date(cfg["inicio"])
    end = to_date(cfg["fin"])
    nxt = monday_of(today) + dt.timedelta(days=7)
    if nxt > end:
        raise ValueError("No quedan semanas completas para replanificar.")
    types = set(cfg.get("tipos_actividad") or [])
    acts = [a for a in acts if not types or a["type"] in types]
    done_runs = runs_in_range(acts, start, nxt - dt.timedelta(days=1))
    done = sum(a["distance_km"] for a in done_runs)
    goal = float(cfg["objetivo_km"])
    remaining = goal - done
    if remaining <= 0:
        raise ValueError("El objetivo ya está cumplido.")

    wk = weekly_actual(done_runs)
    last4 = sorted(m for m in wk if m < monday_of(today))[-4:]
    if last4:
        v0 = max(6.0, statistics.mean(wk[m]["km"] for m in last4))
    else:
        v0 = max(6.0, float((cfg.get("corredor") or {}).get("km_semana_actual") or 12))
    lo = nxt - dt.timedelta(days=30)
    recent = [a["distance_km"] for a in done_runs if to_date(a["date"]) >= lo]
    seed = max(3.0, max(recent)) if recent else None

    offset = (nxt - monday_of(start)).days // 7
    default_end = default_plan_end(cfg, end)
    uses_margin = nxt + dt.timedelta(days=14) > default_end and default_end < end
    plan_end = end if uses_margin else default_end
    new = generate_plan(cfg, profile, start=nxt, end=end, plan_end=plan_end, total_km=remaining, v0=v0,
                        week_offset=offset, base_cum=done, seed_longest=seed)
    keep_days = [d for d in old_plan["days"] if to_date(d["date"]) < nxt]
    keep_weeks = [w for w in old_plan["weeks"] if to_date(w["monday"]) < nxt]
    meta = new["meta"]
    meta.update(inicio=start.isoformat(), objetivo_km=goal, total_plan_km=round(done + meta["total_plan_km"], 1))
    if uses_margin:
        extra = "Has consumido el margen: el plan ocupa ya hasta el último día del reto."
        meta["aviso"] = (meta["aviso"] + " " + extra) if meta.get("aviso") else extra
    meta["replan"] = {"fecha": today.isoformat(), "desde": nxt.isoformat(), "km_hechos": round(done, 1),
                      "km_restantes": round(remaining, 1), "km_semana_base": round(v0, 1)}
    return {"meta": meta, "weeks": keep_weeks + new["weeks"], "days": keep_days + new["days"]}
