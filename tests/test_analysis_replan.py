import datetime as dt

import pytest

from mil import analysis, exports, planner as P, store
from mil.demo import fake_activities
from mil.replan import replan


def act(i, day, km, hr_z=None):
    return {"id": f"t:{i}", "date": day.isoformat(), "start": day.isoformat() + "T08:00:00", "type": "running", "distance_km": km,
            "duration_s": km * 400, "pace_s_km": 400, "avg_hr": 150, "hr_zone_s": hr_z}


def test_summary_and_spike_alert(cfg):
    plan = P.generate_plan(cfg)
    acts = [act(1, dt.date(2026, 11, 24), 4), act(2, dt.date(2026, 11, 26), 4), act(3, dt.date(2026, 11, 29), 6, [0, 600, 100, 50, 0])]
    s = analysis.summarize(cfg, plan, acts, {}, {}, dt.date(2026, 11, 30))
    assert s["hecho_km"] == 14.0 and s["faltan_km"] == 986.0
    assert any("más que tu carrera más larga" in a["texto"] for a in s["alertas"])
    assert s["semanas"][0]["shares"]["easy"] == pytest.approx(600 / 750)
    assert len(s["proximos_7_dias"]) == 7


def test_status_before_start(cfg):
    plan = P.generate_plan(cfg)
    s = analysis.summarize(cfg, plan, [], {}, {}, dt.date(2026, 11, 1))
    assert s["estado"]["codigo"] == "pendiente"


def test_wellness_flags():
    today = dt.date(2027, 3, 1)
    w = {(today - dt.timedelta(days=i)).isoformat(): {"rhr": 50 if i > 6 else 58, "hrv_status": "UNBALANCED" if i < 2 else "BALANCED", "sleep_h": 5.5} for i in range(30)}
    texts = " ".join(f["texto"] for f in analysis.wellness_flags(w, today))
    assert "FC en reposo" in texts and "VFC" in texts and "sueño" in texts


def test_replan_hits_goal_when_behind(cfg):
    plan = P.generate_plan(cfg)
    today = dt.date(2027, 3, 3)
    acts = [a for a in fake_activities(plan, today) if a["date"] < "2027-03-01"]
    for a in acts:  # el corredor va al 70% del plan
        a["distance_km"] = round(a["distance_km"] * 0.7, 2)
    new = replan(cfg, plan, acts, {}, today)
    done = sum(a["distance_km"] for a in acts)
    future = sum(d["km"] for d in new["days"] if d["date"] >= "2027-03-08")
    assert done + future == pytest.approx(1000.0, abs=0.6)
    assert new["days"][-1]["cum_plan_km"] == pytest.approx(1000.0, abs=0.6)
    assert new["meta"]["replan"]["desde"] == "2027-03-08"
    # los días anteriores se conservan
    assert [d["date"] for d in new["days"]] == sorted(d["date"] for d in new["days"])
    runs = [{"date": dt.date.fromisoformat(d["date"]), "km": d["km"]} for d in new["days"] if d["type"] == "run" and d["date"] >= "2027-03-08"]
    longest = max(a["distance_km"] for a in acts if a["date"] >= "2027-02-06")
    assert runs[0]["km"] <= P.max_run(longest) + 0.5


def test_replan_consumes_margin_when_late(cfg):
    plan = P.generate_plan(cfg)
    today = dt.date(2027, 9, 28)
    acts = [a for a in fake_activities(plan, today) if a["date"] < "2027-10-01"]
    for a in acts:
        a["distance_km"] = round(a["distance_km"] * 0.9, 2)
    new = replan(cfg, plan, acts, {}, today)
    assert new["meta"]["fin_plan"] == "2027-11-23" and "margen" in new["meta"]["aviso"]
    assert any(d["type"] == "run" and d["date"] > "2027-10-10" for d in new["days"])
    done = sum(a["distance_km"] for a in acts)
    assert done + sum(d["km"] for d in new["days"] if d["date"] >= "2027-10-04") == pytest.approx(1000.0, abs=0.6)


def test_replan_keeps_margin_when_early(cfg):
    plan = P.generate_plan(cfg)
    today = dt.date(2027, 3, 3)
    acts = [a for a in fake_activities(plan, today) if a["date"] < "2027-03-01"]
    new = replan(cfg, plan, acts, {}, today)
    assert new["meta"]["fin_plan"] == "2027-10-10" and new["meta"]["margen_semanas"] == 6


def test_status_margin(cfg):
    plan = P.generate_plan(cfg)
    s = analysis.summarize(cfg, plan, [act(1, dt.date(2027, 10, 9), 5)], {}, {}, dt.date(2027, 10, 20))
    assert s["estado"]["codigo"] == "margen" and s["margen"]["semanas"] == 6


def test_replan_errors(cfg):
    plan = P.generate_plan(cfg)
    with pytest.raises(ValueError):
        replan(cfg, plan, [], {}, dt.date(2027, 11, 22))


def test_store_idempotent(tmp_path):
    a = act(1, dt.date(2026, 11, 24), 4)
    assert store.merge_activities([a], tmp_path) == (1, 0)
    assert store.merge_activities([a], tmp_path) == (0, 0)
    assert len(store.load_activities(tmp_path)) == 1


def test_exports(cfg, tmp_path):
    plan = P.generate_plan(cfg)
    n = exports.to_ics(plan, tmp_path / "x.ics")
    txt = (tmp_path / "x.ics").read_bytes()
    assert txt.startswith(b"BEGIN:VCALENDAR") and txt.count(b"BEGIN:VEVENT") == n > 250
    assert all(len(l) <= 75 for l in txt.split(b"\r\n"))
    exports.to_csv(plan, tmp_path / "x.csv")
    assert (tmp_path / "x.csv").read_text(encoding="utf-8").count("\n") == 367
