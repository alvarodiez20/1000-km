"""Datos sintéticos para previsualizar el panel sin tocar los datos reales."""

from __future__ import annotations

import datetime as dt
import random
import shutil
from pathlib import Path

from . import analysis, store
from .planner import generate_plan
from .util import to_date, write_json


def fake_activities(plan: dict, today: dt.date, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    acts = []
    for i, d in enumerate(plan["days"]):
        day = to_date(d["date"])
        if day > today or d["type"] != "run":
            continue
        if rng.random() < 0.08:
            continue  # sesión saltada
        km = max(1.5, d["km"] * rng.uniform(0.9, 1.08))
        pace = 395 * rng.uniform(0.96, 1.04) - 0.03 * (i)  # mejora lenta
        dur = km * pace
        total = dur
        z_easy = 0.80 if d["zone"] == "Z2" else 0.60
        z = [total * 0.10, total * (z_easy - 0.10), total * 0.10, total * (0.9 - z_easy) * 0.7, total * (0.9 - z_easy) * 0.3 + total * 0.1 - total * 0.1]
        acts.append({
            "id": f"demo:{i}", "source": "demo", "date": d["date"], "start": d["date"] + "T07:30:00", "type": "running",
            "distance_km": round(km, 2), "duration_s": round(dur, 1), "pace_s_km": round(pace, 1),
            "avg_hr": round(rng.uniform(140, 158)), "max_hr": 172, "elev_gain_m": 20, "calories": None,
            "training_effect": 2.8, "anaerobic_te": 0.2, "vo2max": None, "hr_zone_s": [round(x, 1) for x in z],
        })
    return acts


def build_demo(root: Path, cfg: dict, site_src: Path, today: dt.date) -> Path:
    plan = generate_plan(cfg, {})
    acts = fake_activities(plan, today)
    wellness = {}
    rng = random.Random(3)
    for i in range(40):
        d = (today - dt.timedelta(days=i)).isoformat()
        wellness[d] = {"rhr": 54 + rng.randint(-2, 3), "hrv_last_night": 48 + rng.randint(-6, 6), "hrv_status": "BALANCED",
                       "sleep_h": round(7 + rng.uniform(-0.8, 0.8), 2), "sleep_score": 78, "body_battery_high": 85}
    s = analysis.summarize(cfg, plan, acts, wellness, {"vo2max": 44, "last_sync": today.isoformat() + "T08:00:00"}, today, include_wellness=True)
    out = root / "docs-demo"
    out.mkdir(exist_ok=True)
    shutil.copy(site_src / "index.html", out / "index.html")
    write_json(out / "summary.json", s)
    return out
