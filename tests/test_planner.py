import collections
import datetime as dt

import pytest

from mil import planner as P


@pytest.fixture(scope="module")
def plan(cfg):
    return P.generate_plan(cfg)


def runs_of(plan):
    return [{"date": dt.date.fromisoformat(d["date"]), "km": d["km"], "role": d["role"], "week": d["week"], "kind": d["week_kind"]}
            for d in plan["days"] if d["type"] == "run"]


def test_total_exact(plan):
    assert plan["meta"]["total_plan_km"] == 1000.0
    assert sum(d["km"] for d in plan["days"]) == pytest.approx(1000.0)
    assert plan["days"][-1]["cum_plan_km"] == pytest.approx(1000.0)


def test_dates_and_weeks(plan):
    assert plan["days"][0]["date"] == "2026-11-23"
    assert plan["days"][-1]["date"] == "2027-11-23"
    assert len(plan["days"]) == 366
    assert len(plan["weeks"]) == 53
    kinds = {w["week"]: w["kind"] for w in plan["weeks"]}
    for w in range(1, 47):
        if w in (12, 24, 36):
            assert kinds[w] == "test"
        elif w % 4 == 0 or w == 46:
            assert kinds[w] == "descarga"
        else:
            assert kinds[w] == "carga"
    assert all(kinds[w] == "margen" for w in range(47, 54))


def test_margin_six_weeks(plan):
    m = plan["meta"]
    assert m["fin_plan"] == "2027-10-10" and m["margen_semanas"] == 6 and m["fin"] == "2027-11-23"
    last_run = [d for d in plan["days"] if d["type"] == "run"][-1]
    assert last_run["date"] == "2027-10-10" and last_run["cum_plan_km"] == pytest.approx(1000.0)
    reserve = [d for d in plan["days"] if d["type"] == "reserve"]
    assert reserve[0]["date"] == "2027-10-11" and len(reserve) == 44
    assert all(d["km"] == 0 and d["cum_plan_km"] == pytest.approx(1000.0) for d in reserve)
    assert (dt.date(2027, 11, 23) - dt.date.fromisoformat(m["fin_plan"])).days >= 42


def test_no_margin_config_keeps_old_behaviour(cfg):
    p = P.generate_plan({**cfg, "margen_semanas": 0})
    assert p["meta"]["total_plan_km"] == 1000.0 and p["meta"]["fin_plan"] == "2027-11-23"
    assert not any(d["type"] == "reserve" for d in p["days"])


def test_no_single_run_spike(plan):
    seed = [{"date": dt.date(2026, 11, 20), "km": 4.8}]
    assert P.spike_violations(seed + runs_of(plan)) == []


def test_long_run_share_and_min_run(plan):
    by = collections.defaultdict(list)
    for r in runs_of(plan):
        by[r["week"]].append(r)
    for w, rs in by.items():
        tot = sum(r["km"] for r in rs)
        longest = max(r["km"] for r in rs)
        assert longest / tot <= 0.45, (w, longest, tot)
    assert min(r["km"] for r in runs_of(plan)) >= 2.5


def test_frequency(plan):
    n = collections.Counter(r["week"] for r in runs_of(plan))
    assert all(n[w] == 3 for w in range(1, 13))
    assert all(n[w] == 4 for w in range(13, 47))
    assert all(n[w] == 0 for w in range(47, 54))


def test_volume_trend(plan):
    vols = {w["week"]: w["km"] for w in plan["weeks"]}
    loads = [vols[w] for w in range(1, 53) if (w - 1) % 4 < 3]
    assert max(loads) < 35 and vols[46] < vols[45]
    for b in range(0, 11):
        block = [vols[4 * b + i] for i in (1, 2, 3, 4)]
        assert block[3] < max(block[:3])  # la descarga es la semana más baja del bloque


def test_hard_work_share(plan):
    # el trabajo duro (umbral/VO2max) no supera ~20% del tiempo semanal en semanas sin test
    by = collections.defaultdict(lambda: [0, 0])
    import re
    for d in plan["days"]:
        if d["type"] != "run":
            continue
        by[d["week"]][1] += d["duration_min"]
        m = re.search(r"(\d+) x (\d+) min a ritmo", d["description"])
        c = re.search(r"(\d+) min continuos", d["description"])
        if m:
            by[d["week"]][0] += int(m.group(1)) * int(m.group(2))
        elif c:
            by[d["week"]][0] += int(c.group(1))
    for w, (hard, tot) in by.items():
        if w in P.TEST_WEEKS:
            continue
        assert hard <= 0.21 * tot, (w, hard, tot)


@pytest.mark.parametrize("v0", [8, 12, 20])
def test_other_starting_levels(cfg, v0):
    p = P.generate_plan(cfg, v0=v0)
    assert p["meta"]["total_plan_km"] == 1000.0
    seed = [{"date": dt.date(2026, 11, 20), "km": max(3.0, round(0.4 * v0, 1))}]
    assert P.spike_violations(seed + runs_of(p)) == []


def test_unreachable_goal_warns(cfg):
    p = P.generate_plan(cfg, total_km=3000)
    assert p["meta"]["aviso"]


def test_vdot_priority(cfg):
    prof = {"tests": {"5k_s": 1500}, "race_5k_s": 1300}
    assert P.resolve_profile(cfg, prof)["vdot_src"] == "test de 5 km"
    assert P.resolve_profile(cfg, {"race_5k_s": 1500})["vdot_src"].startswith("predicción Garmin")
    assert P.resolve_profile(cfg, {})["vdot_src"] == "defecto"
