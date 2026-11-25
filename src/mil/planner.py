"""Generador del plan: periodización en bloques de 4 semanas que suma exactamente el objetivo.

Principios (ver README, sección Ciencia):
- Bloques 3 semanas de carga + 1 de descarga (o test).
- Ninguna carrera supera el 110% de la más larga de los 30 días previos (Frandsen et al., BJSM 2025).
- Distribución 80/20: el trabajo duro (umbral, VO2max) no pasa del 18% del tiempo semanal.
- Frecuencia 3 carreras/semana al inicio y 4 desde la semana 13.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

from . import zones as Z
from .util import DIAS, DIAS_LARGO, dia_idx, fmt_pace, monday_of, to_date

PASO = 0.5                # los km se redondean a 0,5
LOAD_FACTORS = (0.90, 0.95, 1.00)
DELOAD_FACTOR = 0.75
TEST_FACTOR = 0.85
HARD_TIME_CAP = 0.18      # fracción del tiempo semanal a intensidad umbral o mayor
SPIKE = 1.10              # tope de una carrera sobre la más larga de los últimos 30 días
MIN_RUN_KM = 2.5
TEST_WEEKS = {12: "test30", 24: "test5k", 36: "test30", 48: "test5k"}

# (tipo, repeticiones, minutos por repetición, minutos de recuperación)
Q_SPECS: dict[int, tuple[str, int, int, float]] = {
    3: ("strides", 4, 20, 0), 4: ("strides", 4, 20, 0),
    5: ("strides", 6, 20, 0), 6: ("strides", 6, 20, 0), 7: ("strides", 6, 20, 0), 8: ("strides", 6, 20, 0),
    9: ("hills", 6, 8, 0), 10: ("hills", 7, 8, 0), 11: ("hills", 8, 8, 0),
    13: ("T", 3, 4, 1.5), 14: ("T", 3, 5, 2), 15: ("T", 3, 6, 2), 16: ("strides", 6, 20, 0),
    17: ("T", 4, 5, 1.5), 18: ("T", 3, 7, 2), 19: ("T", 2, 10, 3), 20: ("strides", 6, 20, 0),
    21: ("T", 4, 6, 2), 22: ("T", 3, 8, 2), 23: ("T", 2, 12, 3),
    25: ("I", 4, 3, 3), 26: ("T", 3, 8, 2), 27: ("I", 5, 3, 2.5), 28: ("strides", 6, 20, 0),
    29: ("I", 5, 3, 2.5), 30: ("T", 2, 12, 3), 31: ("I", 6, 3, 2.5), 32: ("strides", 6, 20, 0),
    33: ("I", 4, 4, 3), 34: ("T", 3, 10, 2), 35: ("I", 5, 4, 3),
    37: ("T", 2, 15, 3), 38: ("I", 5, 3, 2.5), 39: ("I", 4, 5, 3), 40: ("strides", 6, 20, 0),
    41: ("T", 3, 10, 2), 42: ("I", 5, 4, 3), 43: ("T", 2, 15, 3), 44: ("strides", 6, 20, 0),
    45: ("I", 5, 4, 3), 46: ("Tc", 1, 20, 0), 47: ("I", 6, 3, 2.5),
    49: ("T", 3, 8, 2), 50: ("I", 5, 3, 2.5), 51: ("Tc", 1, 20, 0), 52: ("strides", 6, 20, 0),
}

FASES = [
    (12, "A", "Base aeróbica"),
    (24, "B", "Desarrollo del umbral"),
    (36, "C", "Potencia aeróbica"),
    (48, "D", "Específica y consolidación"),
    (10_000, "E", "Cierre"),
]

FUERZA = {
    "A": ("Fuerza A: base", "Sentadilla goblet 3x10, peso muerto rumano 3x10, elevación de talones lenta (3 s bajando) 3x15, puente de glúteo a una pierna 3x12, plancha lateral 3x30 s."),
    "B": ("Fuerza B: carga", "Sentadilla o prensa 3x6-8, peso muerto rumano 3x6-8, elevación de talones con peso 3x8 (rodilla recta) y 3x10 (rodilla flexionada), zancada búlgara 3x8, plancha 3x45 s."),
    "C": ("Fuerza C: potencia", "Sentadilla pesada 3x5, peso muerto 3x5, elevación de talones pesada 3x6, saltos de pogo 3x20 s, escalón con salto 3x6. Todo con técnica limpia."),
}


def rnd(x: float) -> float:
    return round(x / PASO) * PASO


def floor_half(x: float) -> float:
    return math.floor(x / PASO + 1e-9) * PASO


def max_run(ref: float) -> float:
    """Distancia máxima de una carrera dada la más larga de los últimos 30 días.

    110% de la referencia, o un paso de 0,5 km si el 10% queda por debajo de la resolución
    del plan (así un corredor de tiradas cortas puede progresar).
    """
    return max(floor_half(SPIKE * ref), ref + PASO)


def fase(week: int) -> tuple[str, str]:
    for lim, code, name in FASES:
        if week <= lim:
            return code, name
    return "E", "Cierre"


def week_kind(week: int, closing: bool, taper: bool = False) -> str:
    if closing:
        return "cierre"
    if taper and week not in TEST_WEEKS:
        return "descarga"
    if week in TEST_WEEKS:
        return "test"
    if (week - 1) % 4 == 3:
        return "descarga"
    return "carga"


def runs_per_week(week: int) -> int:
    return 3 if week <= 12 else 4


# ---------------------------------------------------------------- calendario


def make_weeks(start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    """Semanas lunes-domingo recortadas al rango; la última puede ser parcial."""
    weeks = []
    m = monday_of(start)
    i = 1
    while m <= end:
        days = [m + dt.timedelta(days=k) for k in range(7)]
        days = [d for d in days if start <= d <= end]
        weeks.append({"week": i, "monday": m, "days": days, "full": len(days) == 7, "taper": False})
        m += dt.timedelta(days=7)
        i += 1
    fulls = [w for w in weeks if w["full"]]
    if fulls:
        fulls[-1]["taper"] = True   # la última semana completa del plan es de descarga
    return weeks


def default_plan_end(cfg: dict, end: dt.date) -> dt.date:
    """Último día del plan: `margen_semanas` antes del fin del reto, ajustado al domingo anterior."""
    margen = int(cfg.get("margen_semanas") or 0)
    if margen <= 0:
        return end
    e = end - dt.timedelta(weeks=margen)
    return e - dt.timedelta(days=(e.weekday() + 1) % 7)


# ---------------------------------------------------------------- volumen semanal


def weekly_targets(weeks, v0: float, g: float, grow_blocks: int) -> list[float]:
    """Volumen objetivo (km) de cada semana. g es el crecimiento por bloque.

    En un replan (semana inicial > 1) el crecimiento se cuenta desde el bloque actual.
    """
    out = []
    offset = weeks[0]["week"] - 1
    b0 = offset // 4
    first_factor = LOAD_FACTORS[0] if offset == 0 else 0.95
    p0 = v0 / first_factor
    last_full_peak = p0
    for w in weeks:
        n = w["week"]
        b, pos = divmod(n - 1, 4)
        # crecimiento continuo (por semana) para que ningun salto choque con el tope del 110%
        x = min(max((n - 1 - 4 * b0) / 4.0, 0.0), grow_blocks - 1)
        peak = p0 * (1 + g) ** x
        if not w["full"]:
            out.append(0.0)
            continue
        last_full_peak = peak
        kind = week_kind(n, False, w.get("taper", False))
        if kind == "carga":
            out.append(peak * LOAD_FACTORS[pos])
        elif kind == "test":
            out.append(peak * TEST_FACTOR)
        else:
            out.append(peak * DELOAD_FACTOR)
    # semanas parciales (cierre): proporcional al pico
    for i, w in enumerate(weeks):
        if not w["full"]:
            out[i] = last_full_peak * 0.35 * len(w["days"]) / 2.0
    return out


# ---------------------------------------------------------------- composición


class History:
    """Carreras previas para aplicar la regla del 110% sobre los últimos 30 días."""

    def __init__(self, seed: list[tuple[dt.date, float]] | None = None):
        self.runs: list[tuple[dt.date, float]] = list(seed or [])

    def longest30(self, d: dt.date) -> float:
        lo = d - dt.timedelta(days=30)
        vals = [km for (rd, km) in self.runs if lo <= rd < d]
        return max(vals) if vals else 0.0

    def cap(self, d: dt.date) -> float:
        base = self.longest30(d)
        return max_run(base) if base > 0 else 1e9

    def add(self, d: dt.date, km: float) -> None:
        self.runs.append((d, km))


def shares_for(n: int, kind: str) -> list[tuple[str, float]]:
    if n >= 4:
        if kind == "test":
            return [("Q", 0.34), ("E", 0.22), ("E2", 0.16), ("L", 0.28)]
        return [("Q", 0.26), ("E", 0.22), ("E2", 0.18), ("L", 0.34)]
    if n == 3:
        if kind == "test":
            return [("Q", 0.42), ("E", 0.30), ("L", 0.28)]
        return [("Q", 0.30), ("E", 0.30), ("L", 0.40)]
    if n == 2:
        return [("E", 0.45), ("F", 0.55)]
    return [("F", 1.0)]


def run_days_for(cfg: dict, n: int, days: list[dt.date], full: bool) -> list[dt.date]:
    if not full:
        return days[-n:]
    key = "correr_4" if n >= 4 else "correr_3"
    idx = sorted(dia_idx(x) for x in cfg["dias"][key])
    by_idx = {d.weekday(): d for d in days}
    return [by_idx[i] for i in idx if i in by_idx]


def fit_spec(spec, q_km: float, week_min: float, paces) -> tuple[str, int, int, float]:
    kind, reps, dur, rec = spec
    if kind not in ("T", "I", "Tc"):
        return spec
    hard_pace = Z.mid(paces["T" if kind in ("T", "Tc") else "I"])
    easy_pace = Z.mid(paces["E"])
    while True:
        hard = reps * dur
        rec_min = max(reps - 1, 0) * rec
        main_km = hard * 60 / hard_pace + rec_min * 60 / easy_pace
        if hard <= HARD_TIME_CAP * week_min and q_km - main_km >= 2.0:
            return (kind, reps, dur, rec)
        if kind == "Tc":
            if dur > 10:
                dur -= 2
                continue
        elif reps > 2:
            reps -= 1
            continue
        elif dur > 3:
            dur -= 1
            continue
        return ("strides", 6, 20, 0)


def compose_week(cfg, w, vol, hist: History, paces) -> list[dict]:
    n_week = w["week"]
    kind = week_kind(n_week, not w["full"], w.get("taper", False))
    n = runs_per_week(n_week) if w["full"] else min(2, len(w["days"]))
    shares = shares_for(n, kind)
    days = run_days_for(cfg, len(shares), w["days"], w["full"])
    shares = shares[: len(days)]
    raw = [rnd(vol * s) for _, s in shares]
    runs = []
    excess = 0.0
    local = History(hist.runs)
    for (role, _), d, km in zip(shares, days, raw):
        cap = local.cap(d)
        km = max(MIN_RUN_KM if vol >= 8 else 1.5, km)
        if km > cap:
            excess += km - cap
            km = cap
        local.add(d, km)
        runs.append({"date": d, "role": role, "km": km, "week": n_week, "kind": kind})
    # redistribuir el exceso por la regla del 110%
    for r in runs:
        if excess <= 0:
            break
        if r["role"] in ("L", "F"):
            continue
        room = max_run(max(x["km"] for x in runs if x["date"] <= r["date"])) - r["km"]
        add = min(excess, max(0.0, room))
        r["km"] += add
        excess -= add
    # especificación de calidad
    for r in runs:
        r["spec"] = None
        if r["role"] == "Q":
            if n_week in TEST_WEEKS:
                r["spec"] = (TEST_WEEKS[n_week], 1, 30 if TEST_WEEKS[n_week] == "test30" else 25, 0)
            else:
                spec = Q_SPECS.get(n_week, ("none", 0, 0, 0))
                if w.get("taper") and spec[0] in ("T", "I", "Tc"):
                    spec = ("strides", 6, 20, 0)
                week_min = vol * Z.mid(paces["E"]) / 60
                r["spec"] = fit_spec(spec, r["km"], week_min, paces)
    for r in runs:
        hist.add(r["date"], r["km"])
    return runs


def build_runs(cfg, weeks, v0, g, grow_blocks, paces, seed_longest):
    first_day = weeks[0]["days"][0]
    hist = History([(first_day - dt.timedelta(days=3), seed_longest)])
    targets = weekly_targets(weeks, v0, g, grow_blocks)
    all_runs = []
    for w, vol in zip(weeks, targets):
        all_runs.extend(compose_week(cfg, w, vol, hist, paces))
    return all_runs, targets


def total_for(cfg, weeks, v0, g, grow_blocks, paces, seed_longest) -> float:
    runs, _ = build_runs(cfg, weeks, v0, g, grow_blocks, paces, seed_longest)
    return sum(r["km"] for r in runs)


def solve(cfg, weeks, total_km, v0, grow_blocks, paces, seed_longest):
    """Devuelve (g, v0 usado, aviso)."""
    aviso = None
    t0 = total_for(cfg, weeks, v0, 0.0, grow_blocks, paces, seed_longest)
    if t0 > total_km:
        lo, hi = 3.0, v0
        for _ in range(40):
            mid_v = (lo + hi) / 2
            if total_for(cfg, weeks, mid_v, 0.0, grow_blocks, paces, mid_v * 0.4) > total_km:
                hi = mid_v
            else:
                lo = mid_v
        return 0.0, lo, "El objetivo exige menos volumen que tu nivel actual: se ha reducido el punto de partida."
    gmax = 0.30
    if total_for(cfg, weeks, v0, gmax, grow_blocks, paces, seed_longest) < total_km:
        return gmax, v0, "El objetivo no se alcanza con una progresión prudente: amplía la fecha o reduce los km."
    lo, hi = 0.0, gmax
    for _ in range(50):
        mid_g = (lo + hi) / 2
        if total_for(cfg, weeks, v0, mid_g, grow_blocks, paces, seed_longest) < total_km:
            lo = mid_g
        else:
            hi = mid_g
    g = (lo + hi) / 2
    if g > 0.15:
        aviso = f"Crecimiento por bloque de {g * 100:.0f}%: exigente. Valora ampliar plazo."
    return g, v0, aviso


def spike_violations(runs) -> list[dict]:
    """Carreras que superan el 110% de la más larga de los 30 días previos."""
    runs = sorted(runs, key=lambda r: r["date"])
    bad = []
    for i, r in enumerate(runs):
        lo = r["date"] - dt.timedelta(days=30)
        prev = [x["km"] for x in runs[:i] if lo <= x["date"] < r["date"]]
        if prev and r["km"] > max_run(max(prev)) + 1e-9:
            bad.append({"date": r["date"], "km": r["km"], "ref": max(prev)})
    return bad


def reconcile(runs, total_km, seed_longest, start):
    """Ajusta de 0,5 en 0,5 km carreras fáciles hasta sumar exactamente el objetivo."""
    def total():
        return round(sum(r["km"] for r in runs), 3)

    def ok_add(r, delta):
        r["km"] += delta
        seed = [(start - dt.timedelta(days=3), seed_longest)]
        viol = spike_violations([{"date": d, "km": k} for d, k in seed] + runs)
        r["km"] -= delta
        return not viol

    cands = [r for r in runs if r["role"] in ("E", "E2") and r["kind"] in ("carga",)]
    if not cands:
        cands = [r for r in runs if r["role"] in ("E", "E2", "F")]
    guard = 0
    i = 0
    while abs(total() - total_km) > PASO / 2 + 1e-9 and guard < 5000:
        guard += 1
        diff = total_km - total()
        delta = PASO if diff > 0 else -PASO
        for _ in range(len(cands)):
            r = cands[i % len(cands)]
            i += 1
            if delta < 0 and r["km"] + delta < MIN_RUN_KM:
                continue
            if delta > 0 and not ok_add(r, delta):
                continue
            r["km"] += delta
            break
        else:
            break
    return runs


# ---------------------------------------------------------------- textos


def easy_text(km, paces, zones) -> str:
    f, s = paces["E"]
    return (
        f"{km:g} km en zona 2 (FC hasta {zones.easy_ceiling} lpm) o a ritmo de conversación. "
        f"Ritmo orientativo {fmt_pace(f)} a {fmt_pace(s)} /km: manda la FC y las sensaciones, el ritmo es una consecuencia."
    )


def describe_run(r, paces, zones) -> dict:
    easy_mid = Z.mid(paces["E"])
    km = r["km"]
    role = r["role"]
    spec = r.get("spec")
    out = {"zone": "Z2", "title": "Rodaje fácil"}
    if role in ("L",):
        out.update(title="Tirada larga", zone="Z2")
        out["description"] = easy_text(km, paces, zones) + " Constante, sin acelerar al final. Lleva agua si pasas de 75 min."
    elif role == "F":
        out.update(title="Tirada larga" if r["kind"] != "cierre" else "Kilómetro final")
        out["description"] = easy_text(km, paces, zones)
        if r["kind"] == "cierre":
            out["description"] += " Último día del reto: cierra el kilómetro 1000 a gusto."
    elif role == "Q" and spec and spec[0] in ("T", "I", "Tc"):
        kind, reps, dur, rec = spec
        hp = paces["T" if kind in ("T", "Tc") else "I"]
        hard_mid = Z.mid(hp)
        main_km = reps * dur * 60 / hard_mid + max(reps - 1, 0) * rec * 60 / easy_mid
        left = max(km - main_km, 2.0)
        wu = round(left * 0.6 * easy_mid / 60)
        cd = round(left * 0.4 * easy_mid / 60)
        name = "umbral" if kind in ("T", "Tc") else "intervalos de VO2max"
        zname = "Z4" if kind in ("T", "Tc") else "Z5"
        if kind == "Tc":
            core = f"{dur} min continuos a ritmo de umbral"
        else:
            core = f"{reps} x {dur} min a ritmo de {name}" + (f" con {rec:g} min de trote suave entre repeticiones" if reps > 1 else "")
        out.update(title=f"Calidad: {'umbral' if kind in ('T','Tc') else 'VO2max'}", zone=zname)
        out["description"] = (
            f"Calentamiento {wu} min fáciles, {core} ({fmt_pace(hp[0])} a {fmt_pace(hp[1])} /km, "
            f"FC {zones.ranges()[3 if zname == 'Z4' else 4][0]}+ lpm) y {cd} min de enfriamiento. Total {km:g} km."
        )
    elif role == "Q" and spec and spec[0] in ("test30", "test5k"):
        if spec[0] == "test30":
            out.update(title="Test de 30 minutos", zone="Test")
            out["description"] = (
                f"Calentamiento 15 min, 30 min al máximo ritmo sostenible y regular, enfriamiento 10 min (≈{km:g} km). "
                "La FC media de los últimos 20 min estima tu umbral (LTHR): anótala con `mil test --tipo 30min --fc N`."
            )
        else:
            out.update(title="Test de 5 km", zone="Test")
            out["description"] = (
                f"Calentamiento 15 min con 4 rectas, 5 km al máximo ritmo regular, enfriamiento 10 min (≈{km:g} km). "
                "Registra el tiempo con `mil test --tipo 5k --tiempo mm:ss` para recalibrar ritmos."
            )
    else:
        extra = ""
        if role == "Q" and spec:
            if spec[0] == "strides":
                extra = f" Al final, {spec[1]} rectas de {spec[2]} s rápidas pero relajadas, andando 60 a 90 s entre ellas."
            elif spec[0] == "hills":
                extra = f" Al final, {spec[1]} cuestas de {spec[2]} s a tope con salida explosiva, bajando andando."
        out["description"] = easy_text(km, paces, zones) + extra
        if role == "Q" and spec and spec[0] in ("strides", "hills"):
            out["title"] = "Rodaje fácil con rectas" if spec[0] == "strides" else "Rodaje fácil con cuestas"
    out["duration_min"] = round(km * easy_mid / 60) if out["zone"] in ("Z2",) else round(km * (easy_mid * 0.93) / 60)
    return out


def strength_session(week: int, kind: str, which: int) -> dict:
    code, _ = fase(week)
    key = {"A": "A", "B": "B"}.get(code, "C")
    title, desc = FUERZA[key]
    if kind in ("descarga", "test"):
        desc = "Descarga: mitad de series. " + desc
    return {"title": title, "description": desc, "duration_min": 25}


# ---------------------------------------------------------------- API principal


def resolve_profile(cfg, profile) -> dict:
    """Combina config.yaml y perfil sincronizado (Garmin). Devuelve valores efectivos y origen."""
    c = cfg.get("corredor", {}) or {}
    p = profile or {}
    force = bool(c.get("forzar"))

    def pick(key, pkey=None):
        pkey = pkey or key
        cv, pv = c.get(key), p.get(pkey)
        if force and cv is not None:
            return cv, "config"
        if pv is not None:
            return pv, "garmin"
        if cv is not None:
            return cv, "config"
        return None, "defecto"

    out = {}
    for k in ("fc_max", "fc_reposo", "fc_umbral"):
        out[k], out[k + "_src"] = pick(k)
    out["edad"] = c.get("edad")
    # VDOT: test reciente > config vdot > config 5K > predicción Garmin > defecto
    vdot, src = None, "defecto"
    tests = p.get("tests") or {}
    if tests.get("5k_s"):
        vdot, src = Z.vdot_from_race(5000, tests["5k_s"]), "test de 5 km"
    elif c.get("vdot"):
        vdot, src = float(c["vdot"]), "config"
    elif c.get("tiempo_5k"):
        from .util import parse_mmss
        vdot, src = Z.vdot_from_race(5000, parse_mmss(c["tiempo_5k"])), "config (5 km)"
    elif p.get("race_5k_s"):
        vdot, src = Z.vdot_from_race(5000, p["race_5k_s"]) * 0.97, "predicción Garmin (5 km, con descuento del 3%)"
    if vdot is None:
        vdot = 36.0
    out["vdot"], out["vdot_src"] = round(vdot, 1), src
    if tests.get("lthr"):
        out["fc_umbral"], out["fc_umbral_src"] = tests["lthr"], "test de 30 min"
    out["vo2max"] = p.get("vo2max")
    out["km_semana_actual"] = float(c.get("km_semana_actual") or 12)
    out["carrera_larga_reciente_km"] = c.get("carrera_larga_reciente_km")
    return out


def generate_plan(cfg, profile=None, *, start=None, end=None, plan_end=None, total_km=None, v0=None,
                  week_offset=0, base_cum=0.0, seed_longest=None) -> dict:
    start = to_date(start or cfg["inicio"])
    end = to_date(end or cfg["fin"])
    plan_end = to_date(plan_end) if plan_end else default_plan_end(cfg, end)
    total_km = float(total_km if total_km is not None else cfg["objetivo_km"])
    eff = resolve_profile(cfg, profile)
    v0 = float(v0 if v0 is not None else eff["km_semana_actual"])
    zones = Z.hr_zones(eff["fc_max"], eff["fc_reposo"], eff["fc_umbral"], eff["edad"])
    paces = Z.pace_table(eff["vdot"])

    weeks = make_weeks(start, plan_end)
    for w in weeks:
        w["week"] += week_offset
    n_full = sum(1 for w in weeks if w["full"])
    grow_blocks = max(1, int(round(n_full / 4 * 10 / 13)))
    seed_longest = seed_longest or eff["carrera_larga_reciente_km"] or max(3.0, round(0.40 * v0, 1))

    g, v0_used, aviso = solve(cfg, weeks, total_km, v0, grow_blocks, paces, seed_longest)
    if v0_used != v0:
        seed_longest = max(3.0, round(0.40 * v0_used, 1))
    runs, targets = build_runs(cfg, weeks, v0_used, g, grow_blocks, paces, seed_longest)
    reconcile(runs, total_km, seed_longest, weeks[0]["days"][0])
    for r in runs:
        r.update(describe_run(r, paces, zones))
    reserve_days = (end - plan_end).days
    last_run = max(runs, key=lambda r: r["date"])
    if reserve_days > 0:
        last_run["title"] = "Tirada larga final"
        last_run["description"] += f" Con esta tirada completas los {total_km + base_cum:g} km del plan. Después empieza tu margen de {reserve_days // 7} semanas."

    # días
    by_date = {r["date"]: r for r in runs}
    fuerza_idx = {dia_idx(x) for x in cfg["dias"]["fuerza"]}
    days = []
    cum = base_cum
    week_rows = []
    for w, vol in zip(weeks, targets):
        n = w["week"]
        kind = week_kind(n, not w["full"], w.get("taper", False))
        code, fname = fase(n)
        wk_km = 0.0
        nstr = 0
        for d in w["days"]:
            row = {"date": d.isoformat(), "weekday": DIAS_LARGO[d.weekday()], "week": n, "phase": code, "phase_name": fname, "week_kind": kind}
            if d in by_date:
                r = by_date[d]
                wk_km += r["km"]
                cum += r["km"]
                row.update(type="run", role=r["role"], title=r["title"], km=r["km"], duration_min=r["duration_min"],
                           zone=r["zone"], description=r["description"])
            elif w["full"] and d.weekday() in fuerza_idx and nstr < 2:
                s = strength_session(n, kind, nstr)
                nstr += 1
                row.update(type="strength", role="S", title=s["title"], km=0.0, duration_min=s["duration_min"], zone="", description=s["description"])
            else:
                row.update(type="rest", role="R", title="Descanso", km=0.0, duration_min=0, zone="", description="Descanso activo: paseo, movilidad suave y sueño largo.")
            row["cum_plan_km"] = round(cum, 1)
            days.append(row)
        week_rows.append({"week": n, "monday": w["monday"].isoformat(), "phase": code, "kind": kind,
                          "km": round(wk_km, 1), "runs": sum(1 for d in w["days"] if d in by_date)})

    # margen: semanas de reserva tras el último día del plan
    if reserve_days > 0:
        n_next = weeks[-1]["week"] + 1
        d = plan_end + dt.timedelta(days=1)
        cur_monday = None
        while d <= end:
            m = monday_of(d)
            if m != cur_monday:
                cur_monday = m
                week_rows.append({"week": n_next, "monday": m.isoformat(), "phase": "R", "kind": "margen", "km": 0.0, "runs": 0})
                n_next += 1
            first = d == plan_end + dt.timedelta(days=1)
            days.append({
                "date": d.isoformat(), "weekday": DIAS_LARGO[d.weekday()], "week": n_next - 1, "phase": "R", "phase_name": "Margen",
                "week_kind": "margen", "type": "reserve", "role": "M0" if first else "M",
                "title": f"Empieza el margen de {reserve_days // 7} semanas" if first else "Margen",
                "km": 0.0, "duration_min": 0, "zone": "",
                "description": ("Si ya tienes los km, corre suave a tu gusto o descansa: esto no cuenta para el plan. "
                                "Si te falta distancia por lesión, viaje o enfermedad, usa `mil replan` y el plan la reparte aquí.") if first else "",
                "cum_plan_km": round(cum, 1),
            })
            d += dt.timedelta(days=1)

    return {
        "meta": {
            "proyecto": cfg.get("proyecto", "MIL"),
            "inicio": start.isoformat(), "fin": end.isoformat(), "fin_plan": plan_end.isoformat(),
            "margen_semanas": reserve_days // 7, "objetivo_km": total_km,
            "total_plan_km": round(sum(r["km"] for r in runs), 1),
            "crecimiento_por_bloque": round(g, 4), "aviso": aviso,
            "vdot": eff["vdot"], "vdot_src": eff["vdot_src"],
            "zonas_fc": {"metodo": zones.method, "provisional": zones.provisional, "rangos": zones.ranges(), "techo_facil": zones.easy_ceiling},
            "ritmos": {k: [fmt_pace(a), fmt_pace(b)] for k, (a, b) in paces.items()},
            "perfil": {k: eff[k] for k in ("fc_max", "fc_reposo", "fc_umbral", "vo2max")},
        },
        "weeks": week_rows,
        "days": days,
    }
