"""Sincronización con Garmin Connect (Forerunner 255) usando python-garminconnect.

Notas de diseño:
- Garmin cambió su autenticación en marzo de 2026 y protege Connect con Cloudflare, que bloquea
  muchas IP de centros de datos. Por eso la sincronización está pensada para ejecutarse en TU
  ordenador (IP residencial) con tokens guardados en ~/.garminconnect, no en GitHub Actions.
- Solo se descargan métricas: nunca coordenadas GPS ni el nombre de la actividad.
- Las funciones de extracción son defensivas: Garmin cambia los JSON sin avisar. Si algo no
  aparece, `mil sync --probe` guarda las respuestas crudas en data/_probe/ para ajustarlo.
"""

from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path
from typing import Any, Callable

TOKENSTORE_DEFAULT = "~/.garminconnect"
PAUSA_S = 0.8  # pausa entre llamadas para no disparar límites de uso

TIPOS_DEFECTO = {"running", "trail_running", "treadmill_running", "track_running", "virtual_run", "indoor_running"}


# ---------------------------------------------------------------- helpers de extracción


def find_key(obj: Any, names: list[str]) -> Any:
    """Busca recursivamente la primera clave (sin distinguir mayúsculas) de `names`."""
    wanted = {n.lower() for n in names}
    stack = [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if str(k).lower() in wanted and v is not None and not isinstance(v, (dict, list)):
                    return v
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(x for x in cur if isinstance(x, (dict, list)))
    return None


def _num(x) -> float | None:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def normalize_activity(a: dict, valid_types: set[str] | None = None) -> dict | None:
    """Convierte una actividad de Garmin al esquema propio. Devuelve None si no es carrera."""
    valid = valid_types or TIPOS_DEFECTO
    tkey = ((a.get("activityType") or {}).get("typeKey") or "").lower()
    if tkey not in valid:
        return None
    dist_m = _num(a.get("distance")) or 0.0
    dur = _num(a.get("duration")) or 0.0
    if dist_m < 100:
        return None
    start = str(a.get("startTimeLocal") or "")
    km = dist_m / 1000.0
    return {
        "id": f"garmin:{a.get('activityId')}",
        "source": "garmin",
        "date": start[:10],
        "start": start[:19].replace(" ", "T"),
        "type": tkey,
        "distance_km": round(km, 3),
        "duration_s": round(dur, 1),
        "pace_s_km": round(dur / km, 1) if km > 0 else None,
        "avg_hr": _num(a.get("averageHR")),
        "max_hr": _num(a.get("maxHR")),
        "elev_gain_m": _num(a.get("elevationGain")),
        "calories": _num(a.get("calories")),
        "training_effect": _num(a.get("aerobicTrainingEffect")),
        "anaerobic_te": _num(a.get("anaerobicTrainingEffect")),
        "vo2max": _num(a.get("vO2MaxValue")),
        "hr_zone_s": None,
    }


def parse_hr_zones(resp: Any) -> list[float] | None:
    """Segundos en Z1..Z5 a partir de get_activity_hr_in_timezones."""
    if not isinstance(resp, list):
        resp = resp.get("zones") if isinstance(resp, dict) else None
    if not resp:
        return None
    out = [0.0] * 5
    for z in resp:
        n = z.get("zoneNumber")
        secs = _num(z.get("secsInZone"))
        if n and 1 <= int(n) <= 5 and secs is not None:
            out[int(n) - 1] = secs
    return out if sum(out) > 0 else None


def parse_wellness(day: str, rhr=None, hrv=None, sleep=None, stats=None) -> dict:
    rec: dict[str, Any] = {}
    rv = find_key(rhr, ["restingHeartRate", "currentDayRestingHeartRate", "value"]) if rhr else None
    rec["rhr"] = _num(rv)
    if hrv:
        summ = hrv.get("hrvSummary") if isinstance(hrv, dict) else None
        summ = summ or hrv
        rec["hrv_last_night"] = _num(find_key(summ, ["lastNightAvg"]))
        rec["hrv_weekly_avg"] = _num(find_key(summ, ["weeklyAvg"]))
        st = find_key(summ, ["status"])
        rec["hrv_status"] = str(st) if st else None
    if sleep:
        dto = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
        dto = dto or sleep
        s = _num(find_key(dto, ["sleepTimeSeconds"]))
        rec["sleep_h"] = round(s / 3600, 2) if s else None
        rec["sleep_score"] = _num(find_key(dto, ["value"]))
    if stats:
        rec["body_battery_high"] = _num(find_key(stats, ["bodyBatteryHighestValue"]))
        rec["body_battery_low"] = _num(find_key(stats, ["bodyBatteryLowestValue"]))
    return rec


def parse_profile(settings=None, hr_zones=None, max_metrics=None, race=None, lactate=None) -> dict:
    out: dict[str, Any] = {}
    out["vo2max"] = _num(find_key(max_metrics, ["vo2MaxPreciseValue", "vo2MaxValue"])) if max_metrics else None
    if out["vo2max"] is None and settings:
        out["vo2max"] = _num(find_key(settings, ["vo2MaxRunning"]))
    out["fc_umbral"] = _num(find_key(lactate, ["heartRate", "lactateThresholdHeartRate"])) if lactate else None
    if out["fc_umbral"] is None and settings:
        out["fc_umbral"] = _num(find_key(settings, ["lactateThresholdHeartRate"]))
    out["fc_max"] = _num(find_key(hr_zones, ["maxHeartRateUsed", "maxHeartRate"])) if hr_zones else None
    out["fc_reposo_zonas"] = _num(find_key(hr_zones, ["restingHeartRateUsed"])) if hr_zones else None
    out["race_5k_s"] = _num(find_key(race, ["time5K", "fiveK", "5K"])) if race else None
    for k in ("vo2max", "fc_umbral", "fc_max"):
        if out[k] is not None:
            out[k] = round(out[k])
    return {k: v for k, v in out.items() if v is not None}


# ---------------------------------------------------------------- conexión


def tokenstore() -> str:
    return os.environ.get("GARMINTOKENS") or TOKENSTORE_DEFAULT


def login_interactive() -> None:
    """Primer inicio de sesión (una sola vez). La contraseña no se guarda; solo los tokens."""
    import getpass
    from garminconnect import Garmin

    email = input("Email de Garmin Connect: ").strip()
    password = getpass.getpass("Contraseña (no se muestra): ")
    g = Garmin(email, password, prompt_mfa=lambda: input("Código MFA (si lo pide): ").strip())
    g.login(os.path.expanduser(tokenstore()))
    print(f"Sesión guardada en {tokenstore()}. Ya no hace falta volver a poner la contraseña.")
    print("Aviso: no repitas intentos fallidos seguidos; Garmin puede bloquear la cuenta unas horas (error 429).")


def connect():
    from garminconnect import Garmin

    g = Garmin()
    g.login(os.path.expanduser(tokenstore()))
    return g


# ---------------------------------------------------------------- sincronización


def _safe(fn: Callable, *a, log: list[str] | None = None, **kw):
    try:
        out = fn(*a, **kw)
        time.sleep(PAUSA_S)
        return out
    except Exception as e:  # noqa: BLE001 - queremos seguir con el resto de métricas
        msg = str(e)
        if "429" in msg or "Too Many" in msg:
            raise RuntimeError("Garmin devolvió 429 (límite de uso). Espera unas horas y no reintentes el login.") from e
        if log is not None:
            log.append(f"{getattr(fn, '__name__', fn)}: {type(e).__name__}")
        return None


def sync(client, days: int, valid_types: set[str], with_zones: bool = True, probe_dir: Path | None = None,
         known_ids: set[str] | None = None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    start = today - dt.timedelta(days=days)
    log: list[str] = []
    known_ids = known_ids or set()

    raw_acts = _safe(client.get_activities_by_date, start.isoformat(), today.isoformat(), log=log) or []
    activities = []
    for a in raw_acts:
        n = normalize_activity(a, valid_types)
        if not n:
            continue
        if with_zones and n["id"] not in known_ids:
            z = _safe(client.get_activity_hr_in_timezones, str(a.get("activityId")), log=log)
            n["hr_zone_s"] = parse_hr_zones(z)
        activities.append(n)

    wellness: dict[str, dict] = {}
    for i in range(min(days, 7) + 1):
        d = (today - dt.timedelta(days=i)).isoformat()
        rhr = _safe(client.get_rhr_day, d, log=log)
        hrv = _safe(client.get_hrv_data, d, log=log)
        sl = _safe(client.get_sleep_data, d, log=log)
        st = _safe(client.get_stats, d, log=log)
        wellness[d] = parse_wellness(d, rhr, hrv, sl, st)
        if probe_dir and i == 1:
            _dump_probe(probe_dir, {"rhr": rhr, "hrv": hrv, "sleep": sl, "stats": st})

    settings = _safe(client.get_userprofile_settings, log=log)
    hrz = _safe(client.get_heart_rate_zones, log=log)
    mm = _safe(client.get_max_metrics_latest, log=log)
    race = _safe(client.get_race_predictions, log=log)
    lact = _safe(client.get_lactate_threshold, log=log)
    profile = parse_profile(settings, hrz, mm, race, lact)
    if probe_dir:
        _dump_probe(probe_dir, {"settings": settings, "hr_zones": hrz, "max_metrics": mm, "race": race, "lactate": lact,
                                "activities_sample": raw_acts[:2]})
    return {"activities": activities, "wellness": wellness, "profile": profile, "log": log}


def _dump_probe(d: Path, payload: dict) -> None:
    import json

    d.mkdir(parents=True, exist_ok=True)
    for k, v in payload.items():
        # quita coordenadas por privacidad antes de guardar
        txt = json.dumps(v, ensure_ascii=False, indent=2, default=str)
        (d / f"{k}.json").write_text(_scrub(txt), encoding="utf-8")


def _scrub(txt: str) -> str:
    import re

    return re.sub(r'("(?:startLatitude|startLongitude|endLatitude|endLongitude|latitude|longitude|locationName|activityName)"\s*:\s*)[^,\n]+', r'\1null', txt)
