"""Análisis de lo hecho frente al plan: km, semanas, intensidad, alertas y resumen para el panel."""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from typing import Any

from .planner import PASO, SPIKE
from .util import monday_of, to_date

HRV_MALO = {"UNBALANCED", "LOW", "POOR"}


def runs_in_range(acts: list[dict], start: dt.date, end: dt.date) -> list[dict]:
    return sorted(
        (a for a in acts if start <= to_date(a["date"]) <= end),
        key=lambda a: a.get("start") or a["date"],
    )


def plan_cum_at(plan: dict, d: dt.date) -> float:
    best = 0.0
    for row in plan["days"]:
        if to_date(row["date"]) <= d:
            best = row["cum_plan_km"]
        else:
            break
    return best


def weekly_actual(acts: list[dict]) -> dict[dt.date, dict]:
    out: dict[dt.date, dict] = defaultdict(lambda: {"km": 0.0, "runs": 0, "secs": 0.0, "z": [0.0] * 5, "hr_w": 0.0, "hr_t": 0.0})
    for a in acts:
        m = monday_of(to_date(a["date"]))
        w = out[m]
        w["km"] += a["distance_km"]
        w["runs"] += 1
        w["secs"] += a["duration_s"] or 0
        if a.get("hr_zone_s"):
            for i, v in enumerate(a["hr_zone_s"]):
                w["z"][i] += v
        if a.get("avg_hr"):
            w["hr_w"] += a["avg_hr"] * (a["duration_s"] or 0)
            w["hr_t"] += a["duration_s"] or 0
    return out


def intensity_shares(z: list[float]) -> dict[str, float] | None:
    tot = sum(z)
    if tot <= 0:
        return None
    return {"easy": (z[0] + z[1]) / tot, "moderate": z[2] / tot, "hard": (z[3] + z[4]) / tot}


def spike_alerts(acts: list[dict], since: dt.date) -> list[dict]:
    """Carreras reales que superan el 110% de la más larga de los 30 días previos."""
    acts = sorted(acts, key=lambda a: a.get("start") or a["date"])
    out = []
    for i, a in enumerate(acts):
        d = to_date(a["date"])
        if d < since:
            continue
        lo = d - dt.timedelta(days=30)
        prev = [x["distance_km"] for x in acts[:i] if lo <= to_date(x["date"]) <= d]
        if not prev:
            continue
        ref = max(prev)
        if a["distance_km"] > max(SPIKE * ref, ref + PASO) + 0.05:
            out.append({"date": a["date"], "km": round(a["distance_km"], 1), "ref_km": round(ref, 1),
                        "ratio": round(a["distance_km"] / ref, 2)})
    return out


def wellness_flags(wellness: dict[str, dict], today: dt.date) -> list[dict]:
    flags = []

    def series(key, days):
        vals = []
        for i in range(days):
            v = (wellness.get((today - dt.timedelta(days=i)).isoformat()) or {}).get(key)
            if v is not None:
                vals.append(v)
        return vals

    r7, r28 = series("rhr", 7), series("rhr", 28)
    if len(r7) >= 4 and len(r28) >= 14:
        diff = statistics.mean(r7) - statistics.mean(r28)
        if diff >= 5:
            flags.append({"nivel": "aviso", "texto": f"FC en reposo {diff:.0f} lpm por encima de tu media de 28 días: cambia la próxima sesión de calidad por rodaje fácil."})
    last2 = [(wellness.get((today - dt.timedelta(days=i)).isoformat()) or {}).get("hrv_status") for i in range(2)]
    if all(s and str(s).upper() in HRV_MALO for s in last2):
        flags.append({"nivel": "aviso", "texto": "VFC fuera de tu rango habitual dos días seguidos: prioriza sueño y rodajes fáciles."})
    sl = series("sleep_h", 3)
    if len(sl) == 3 and statistics.mean(sl) < 6:
        flags.append({"nivel": "aviso", "texto": "Menos de 6 h de sueño de media en 3 días: recorta la sesión dura de esta semana."})
    return flags


def summarize(cfg: dict, plan: dict, acts: list[dict], wellness: dict, profile: dict, today: dt.date,
              include_wellness: bool = False) -> dict[str, Any]:
    start, end = to_date(cfg["inicio"]), to_date(cfg["fin"])
    goal = float(cfg["objetivo_km"])
    types = set(cfg.get("tipos_actividad") or [])
    acts = [a for a in acts if not types or a["type"] in types]
    mine = runs_in_range(acts, start, min(today, end))
    done = sum(a["distance_km"] for a in mine)
    planned = plan_cum_at(plan, min(today, end)) if today >= start else 0.0
    days_left = max((end - today).days, 0)
    fin_plan = plan["meta"].get("fin_plan")
    plan_end = to_date(fin_plan) if fin_plan else end

    wk_act = weekly_actual(mine)
    cur_monday = monday_of(min(today, end))
    full_weeks = sorted(m for m in wk_act if m < cur_monday)[-4:]
    recent_weekly = statistics.mean(wk_act[m]["km"] for m in full_weeks) if full_weeks else None
    remaining = max(goal - done, 0.0)
    weeks_left = days_left / 7 if days_left else 0
    required_weekly = remaining / weeks_left if weeks_left else None
    projection = done + recent_weekly * weeks_left if recent_weekly is not None else None

    delta = done - planned
    if today < start:
        status = {"codigo": "pendiente", "texto": "El reto aún no ha empezado."}
    elif done >= goal:
        status = {"codigo": "completado", "texto": "Reto completado. Mil kilómetros."}
    elif plan_end < today <= end:
        status = {"codigo": "margen", "texto": f"Estás usando el margen: faltan {remaining:.1f} km y {days_left} días. `mil replan` reparte lo que falta."}
    elif delta >= 3:
        status = {"codigo": "adelantado", "texto": f"Vas {delta:.1f} km por delante del plan."}
    elif delta <= -6:
        status = {"codigo": "atrasado", "texto": f"Vas {abs(delta):.1f} km por detrás del plan: ejecuta `mil replan` para redistribuir lo que falta."}
    else:
        status = {"codigo": "en_plan", "texto": "Vas al día con el plan."}

    weeks_out = []
    for w in plan["weeks"]:
        m = to_date(w["monday"])
        a = wk_act.get(m)
        shares = intensity_shares(a["z"]) if a else None
        weeks_out.append({
            "week": w["week"], "monday": w["monday"], "phase": w["phase"], "kind": w["kind"],
            "plan_km": w["km"], "km": round(a["km"], 1) if a else (0.0 if m <= today else None),
            "runs": a["runs"] if a else 0,
            "shares": {k: round(v, 3) for k, v in shares.items()} if shares else None,
        })

    cum = []
    run_total = 0.0
    by_week_end = {}
    for row in plan["days"]:
        by_week_end[monday_of(to_date(row["date"]))] = row
    for m in sorted(by_week_end):
        row = by_week_end[m]
        d = to_date(row["date"])
        actual = None
        if d <= today:
            actual = round(sum(a["distance_km"] for a in mine if to_date(a["date"]) <= d), 1)
        cum.append({"date": row["date"], "plan": row["cum_plan_km"], "actual": actual})
    if today >= start and cum and to_date(cum[-1]["date"]) > today:
        # punto de hoy para que la línea real llegue hasta el día actual
        cum.append({"date": today.isoformat(), "plan": planned, "actual": round(done, 1), "today": True})
        cum.sort(key=lambda r: r["date"])

    last4 = [m for m in sorted(wk_act) if m < cur_monday][-4:]
    z4 = [0.0] * 5
    for m in last4:
        for i, v in enumerate(wk_act[m]["z"]):
            z4[i] += v
    sh4 = intensity_shares(z4)

    upcoming = [r for r in plan["days"] if today <= to_date(r["date"]) <= today + dt.timedelta(days=6)]
    last_runs = [{"date": a["date"], "km": round(a["distance_km"], 2), "pace_s_km": a.get("pace_s_km"), "avg_hr": a.get("avg_hr")}
                 for a in mine[-8:][::-1]]

    alerts = [{"nivel": "aviso", "texto": f"El {s['date']} corriste {s['km']} km, un {int((s['ratio'] - 1) * 100)}% más que tu carrera más larga de los 30 días previos ({s['ref_km']} km). Por encima del 10% sube el riesgo de lesión."}
              for s in spike_alerts(mine, today - dt.timedelta(days=45))]
    if sh4 and (sh4["moderate"] + sh4["hard"]) > 0.25:
        alerts.append({"nivel": "aviso", "texto": f"Pasas el {int((sh4['moderate'] + sh4['hard']) * 100)}% del tiempo por encima de Z2 en las últimas 4 semanas. Objetivo 80/20: más fácil en los rodajes."})
    flags = wellness_flags(wellness, today) if include_wellness else []

    out = {
        "generado": dt.datetime.now().replace(microsecond=0).isoformat(),
        "hoy": today.isoformat(),
        "proyecto": cfg.get("proyecto", "MIL"),
        "inicio": start.isoformat(), "fin": end.isoformat(), "objetivo_km": goal,
        "hecho_km": round(done, 1), "plan_hasta_hoy_km": round(planned, 1), "delta_km": round(delta, 1),
        "faltan_km": round(remaining, 1), "dias_restantes": days_left,
        "media_4_semanas_km": round(recent_weekly, 1) if recent_weekly is not None else None,
        "necesario_semana_km": round(required_weekly, 1) if required_weekly is not None else None,
        "proyeccion_km": round(projection, 0) if projection is not None else None,
        "estado": status,
        "semanas": weeks_out, "acumulado": cum,
        "intensidad_4_semanas": {k: round(v, 3) for k, v in sh4.items()} if sh4 else None,
        "proximos_7_dias": [{k: r[k] for k in ("date", "weekday", "type", "title", "km", "duration_min", "zone", "description")} for r in upcoming],
        "ultimas_carreras": last_runs,
        "alertas": alerts + flags,
        "margen": ({"desde": (plan_end + dt.timedelta(days=1)).isoformat(), "hasta": end.isoformat(), "fin_plan": plan_end.isoformat(),
                    "semanas": (end - plan_end).days // 7} if plan_end < end else None),
        "plan": {k: plan["meta"][k] for k in ("vdot", "vdot_src", "zonas_fc", "ritmos", "aviso", "total_plan_km")},
        "perfil": {k: profile.get(k) for k in ("vo2max", "fc_umbral", "fc_max", "last_sync") if profile.get(k) is not None},
        "con_bienestar": bool(include_wellness),
    }
    if include_wellness:
        keys = sorted(wellness)[-30:]
        out["bienestar"] = [{"date": d, **{k: wellness[d].get(k) for k in ("rhr", "hrv_last_night", "hrv_weekly_avg", "hrv_status", "sleep_h", "sleep_score", "body_battery_high")}} for d in keys]
    return out
