"""Interfaz de línea de comandos: `mil`."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import statistics
import sys
from pathlib import Path

import yaml

from . import analysis, exports, store
from . import zones as Z
from .planner import generate_plan, resolve_profile
from .replan import replan as do_replan
from .util import fmt_pace, parse_mmss, read_json, to_date, write_json

SITE_SRC = Path(__file__).resolve().parents[2] / "site"


def load_cfg(root: Path) -> dict:
    p = root / "config.yaml"
    if not p.exists():
        sys.exit("No encuentro config.yaml. Ejecuta `mil` desde la raíz del repositorio (o usa --raiz).")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def write_plan_files(plan: dict, root: Path) -> None:
    P = store.paths(root)
    write_json(P["plan"], plan)
    exports.to_csv(plan, root / "plan" / "plan.csv")
    n = exports.to_ics(plan, root / "plan" / "mil-km.ics")
    print(f"Plan escrito: plan/plan.json, plan/plan.csv y plan/mil-km.ics ({n} eventos).")


def print_plan_header(plan: dict) -> None:
    m = plan["meta"]
    z = m["zonas_fc"]
    print(f"Total del plan: {m['total_plan_km']} km (objetivo {m['objetivo_km']:g}). Crecimiento por bloque: {m['crecimiento_por_bloque'] * 100:.1f}%.")
    if m.get("margen_semanas"):
        print(f"Plan completo el {m['fin_plan']}; margen de {m['margen_semanas']} semanas hasta el {m['fin']}.")
    print(f"VDOT {m['vdot']} ({m['vdot_src']}). Zonas de FC por {z['metodo']}{' (PROVISIONAL)' if z['provisional'] else ''}; techo de rodaje fácil {z['techo_facil']} lpm.")
    if m.get("aviso"):
        print("AVISO:", m["aviso"])


# ---------------------------------------------------------------- comandos


def cmd_plan(a, root: Path, cfg: dict) -> None:
    existing = read_json(store.paths(root)["plan"])
    if existing and existing["meta"].get("replan") and not a.forzar:
        sys.exit("Ya hay un replan guardado. Usa --forzar para regenerar el plan desde cero (se pierde el replan).")
    plan = generate_plan(cfg, store.load_profile(root))
    write_plan_files(plan, root)
    print_plan_header(plan)


def cmd_zonas(a, root: Path, cfg: dict) -> None:
    eff = resolve_profile(cfg, store.load_profile(root))
    z = Z.hr_zones(eff["fc_max"], eff["fc_reposo"], eff["fc_umbral"], eff["edad"])
    print(f"Zonas de FC por {z.method}{' (PROVISIONAL: faltan datos)' if z.provisional else ''}:")
    for i in range(1, 6):
        print("  ", z.label(i))
    print(f"VDOT {eff['vdot']} ({eff['vdot_src']}). Ritmos:")
    names = {"E": "Fácil", "T": "Umbral", "I": "Intervalos", "R": "Rectas"}
    for k, (f, s) in Z.pace_table(eff["vdot"]).items():
        print(f"   {names[k]:<11} {fmt_pace(f)} a {fmt_pace(s)} /km")


def cmd_garmin_login(a, root: Path, cfg: dict) -> None:
    from .sources import garmin
    garmin.login_interactive()


def cmd_sync(a, root: Path, cfg: dict) -> None:
    from .sources import garmin
    try:
        client = garmin.connect()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"No se pudo iniciar sesión con los tokens guardados ({type(e).__name__}). Ejecuta `mil garmin-login` una vez desde tu ordenador. Si ves 429, espera unas horas.")
    valid = set(cfg.get("tipos_actividad") or garmin.TIPOS_DEFECTO)
    known = {x["id"] for x in store.load_activities(root)}
    probe = root / "data" / "_probe" if a.probe else None
    try:
        res = garmin.sync(client, a.dias, valid, with_zones=not a.sin_zonas, probe_dir=probe, known_ids=known)
    except RuntimeError as e:
        sys.exit(str(e))
    added, updated = store.merge_activities(res["activities"], root)
    nw = store.merge_wellness(res["wellness"], root)
    rhr = [v["rhr"] for _, v in sorted(store.load_wellness(root).items())[-14:] if v.get("rhr")]
    fields = dict(res["profile"])
    if rhr:
        fields["fc_reposo"] = round(statistics.median(rhr))
    fields["last_sync"] = dt.datetime.now().replace(microsecond=0).isoformat()
    store.update_profile(fields, root)
    print(f"Garmin: {added} carreras nuevas, {updated} actualizadas, {nw} días de bienestar. Perfil: {sorted(res['profile'])}.")
    if res["log"]:
        print("Métricas no disponibles (normal si tu reloj no las genera):", "; ".join(sorted(set(res["log"]))))
    if a.probe:
        print("Respuestas crudas (sin GPS) en data/_probe/. No las subas a un repositorio público.")
    cmd_resumen(a, root, cfg)


def cmd_test(a, root: Path, cfg: dict) -> None:
    prof = store.load_profile(root)
    tests = dict(prof.get("tests") or {})
    if a.tipo == "5k":
        s = parse_mmss(a.tiempo)
        if not s:
            sys.exit("Indica el tiempo con --tiempo mm:ss")
        tests["5k_s"] = s
        tests["5k_fecha"] = (a.fecha or dt.date.today().isoformat())
        print(f"VDOT con tu 5K: {Z.vdot_from_race(5000, s):.1f}")
    else:
        if not a.fc:
            sys.exit("Indica la FC media de los últimos 20 min con --fc N")
        tests["lthr"] = int(a.fc)
        tests["lthr_fecha"] = (a.fecha or dt.date.today().isoformat())
        print(f"LTHR = {a.fc} lpm: zonas actualizadas.")
    store.update_profile({"tests": tests}, root)
    print("Ejecuta `mil replan` para recalcular ritmos y zonas de las semanas que quedan.")


def cmd_replan(a, root: Path, cfg: dict) -> None:
    old = read_json(store.paths(root)["plan"])
    if not old:
        sys.exit("Primero genera el plan con `mil plan`.")
    plan = do_replan(cfg, old, store.load_activities(root), store.load_profile(root), dt.date.today())
    write_plan_files(plan, root)
    print_plan_header(plan)
    r = plan["meta"]["replan"]
    print(f"Replan desde {r['desde']}: llevas {r['km_hechos']} km, faltan {r['km_restantes']} km; base semanal {r['km_semana_base']} km.")


def build_summary(root: Path, cfg: dict, private: bool, today: dt.date | None = None) -> dict:
    plan = read_json(store.paths(root)["plan"])
    if not plan:
        sys.exit("Primero genera el plan con `mil plan`.")
    include = private or bool(cfg.get("publicar_bienestar"))
    s = analysis.summarize(cfg, plan, store.load_activities(root), store.load_wellness(root), store.load_profile(root),
                           today or dt.date.today(), include_wellness=include)
    write_json(store.paths(root)["summary"], s)
    return s


def cmd_resumen(a, root: Path, cfg: dict) -> None:
    s = build_summary(root, cfg, private=getattr(a, "privado", False))
    print(f"Hecho {s['hecho_km']} / {s['objetivo_km']:g} km. Plan hasta hoy {s['plan_hasta_hoy_km']} km ({s['delta_km']:+.1f}). {s['estado']['texto']}")
    if s["proyeccion_km"] is not None:
        print(f"Proyección al ritmo de las últimas 4 semanas: {s['proyeccion_km']:.0f} km.")
    for al in s["alertas"]:
        print("!", al["texto"])


def cmd_build(a, root: Path, cfg: dict) -> None:
    s = build_summary(root, cfg, private=a.privado)
    out = root / "docs"
    out.mkdir(exist_ok=True)
    shutil.copy(SITE_SRC / "index.html", out / "index.html")
    write_json(out / "summary.json", s)
    print(f"Panel en {out}/ (con bienestar: {s['con_bienestar']}). Ábrelo con: python -m http.server -d docs 8000")


def cmd_demo(a, root: Path, cfg: dict) -> None:
    from .demo import build_demo
    out = build_demo(root, cfg, SITE_SRC, dt.date.fromisoformat(a.hoy))
    print(f"Demo con datos sintéticos en {out}/ (no toca tus datos reales).")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="mil", description="MIL: 1000 km en un año con tu Garmin")
    ap.add_argument("--raiz", default=".", help="raíz del repositorio (por defecto, el directorio actual)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="genera plan/plan.json, .csv y .ics")
    p.add_argument("--forzar", action="store_true")
    p.set_defaults(fn=cmd_plan)
    sub.add_parser("zonas", help="muestra zonas de FC y ritmos actuales").set_defaults(fn=cmd_zonas)
    sub.add_parser("garmin-login", help="primer inicio de sesión con Garmin (una vez)").set_defaults(fn=cmd_garmin_login)
    p = sub.add_parser("sync", help="descarga carreras y métricas de Garmin")
    p.add_argument("--dias", type=int, default=14, help="días hacia atrás (usa 60 o más la primera vez)")
    p.add_argument("--probe", action="store_true", help="guarda las respuestas crudas (sin GPS) en data/_probe/")
    p.add_argument("--sin-zonas", action="store_true", help="no pide el tiempo en zonas de FC (menos llamadas)")
    p.add_argument("--privado", action="store_true")
    p.set_defaults(fn=cmd_sync)
    p = sub.add_parser("test", help="registra un test (5K o 30 min) para recalibrar")
    p.add_argument("--tipo", choices=["5k", "30min"], required=True)
    p.add_argument("--tiempo")
    p.add_argument("--fc", type=int)
    p.add_argument("--fecha")
    p.set_defaults(fn=cmd_test)
    sub.add_parser("replan", help="redistribuye los km que faltan en las semanas que quedan").set_defaults(fn=cmd_replan)
    p = sub.add_parser("resumen", help="calcula data/summary.json y muestra el estado")
    p.add_argument("--privado", action="store_true")
    p.set_defaults(fn=cmd_resumen)
    p = sub.add_parser("build", help="construye el panel estático en docs/")
    p.add_argument("--privado", action="store_true", help="incluye sueño, VFC y FC en reposo (no lo publiques)")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("demo", help="panel de ejemplo con datos sintéticos en docs-demo/")
    p.add_argument("--hoy", default="2027-06-15")
    p.set_defaults(fn=cmd_demo)

    a = ap.parse_args(argv)
    root = Path(a.raiz).resolve()
    store.ROOT = root
    a.fn(a, root, load_cfg(root))


if __name__ == "__main__":
    main()
