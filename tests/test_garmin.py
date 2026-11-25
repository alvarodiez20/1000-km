import datetime as dt
import json

from mil.sources import garmin as G

ACT = {"activityId": 123, "activityName": "Casa", "startTimeLocal": "2026-11-24 07:30:00",
       "activityType": {"typeKey": "running"}, "distance": 5120.0, "duration": 1800.0, "averageHR": 148.0, "maxHR": 171.0,
       "elevationGain": 35.0, "startLatitude": 42.34, "startLongitude": -3.7, "aerobicTrainingEffect": 2.9, "vO2MaxValue": 45}


def test_normalize_activity_no_gps_and_pace():
    a = G.normalize_activity(ACT)
    assert a["id"] == "garmin:123" and a["date"] == "2026-11-24"
    assert a["pace_s_km"] == round(1800 / 5.12, 1)
    assert "startLatitude" not in json.dumps(a) and "Casa" not in json.dumps(a)


def test_normalize_filters_other_sports_and_tiny():
    assert G.normalize_activity({**ACT, "activityType": {"typeKey": "cycling"}}) is None
    assert G.normalize_activity({**ACT, "distance": 50}) is None
    assert G.normalize_activity({**ACT, "activityType": {"typeKey": "treadmill_running"}}) is not None


def test_parsers():
    z = G.parse_hr_zones([{"zoneNumber": i, "secsInZone": i * 100} for i in range(1, 6)])
    assert z == [100, 200, 300, 400, 500]
    w = G.parse_wellness("d", rhr={"allMetrics": {"metricsMap": {"WELLNESS_RESTING_HEART_RATE": [{"value": 52}]}}, "restingHeartRate": 52},
                         hrv={"hrvSummary": {"lastNightAvg": 48, "weeklyAvg": 50, "status": "BALANCED"}},
                         sleep={"dailySleepDTO": {"sleepTimeSeconds": 27000, "sleepScores": {"overall": {"value": 80}}}},
                         stats={"bodyBatteryHighestValue": 88})
    assert w["rhr"] == 52 and w["hrv_last_night"] == 48 and w["sleep_h"] == 7.5 and w["sleep_score"] == 80 and w["body_battery_high"] == 88
    p = G.parse_profile(settings={"userData": {"lactateThresholdHeartRate": 166, "vo2MaxRunning": 44.0}},
                        hr_zones=[{"maxHeartRateUsed": 189}], max_metrics=[{"generic": {"vo2MaxPreciseValue": 45.3}}],
                        race={"time5K": 1495}, lactate={"speed_and_heart_rate": {"heartRate": 165}})
    assert p == {"vo2max": 45, "fc_umbral": 165, "fc_max": 189, "race_5k_s": 1495.0}


class Fake:
    def get_activities_by_date(self, a, b): return [ACT, {**ACT, "activityId": 9, "activityType": {"typeKey": "cycling"}}]
    def get_activity_hr_in_timezones(self, i): return [{"zoneNumber": 2, "secsInZone": 1500}, {"zoneNumber": 3, "secsInZone": 300}]
    def get_rhr_day(self, d): return {"restingHeartRate": 53}
    def get_hrv_data(self, d): return None
    def get_sleep_data(self, d): raise RuntimeError("500 server error")
    def get_stats(self, d): return {"bodyBatteryHighestValue": 80}
    def get_userprofile_settings(self): return {"userData": {"lactateThresholdHeartRate": 166}}
    def get_heart_rate_zones(self): return []
    def get_max_metrics_latest(self): return {}
    def get_race_predictions(self): return {"time5K": 1500}
    def get_lactate_threshold(self): return {}


def test_sync_with_fake_client(monkeypatch):
    monkeypatch.setattr(G, "PAUSA_S", 0)
    res = G.sync(Fake(), 3, G.TIPOS_DEFECTO, today=dt.date(2026, 11, 26))
    assert len(res["activities"]) == 1 and res["activities"][0]["hr_zone_s"] == [0, 1500, 300, 0, 0]
    assert res["wellness"]["2026-11-26"]["rhr"] == 53
    assert res["profile"]["fc_umbral"] == 166 and res["profile"]["race_5k_s"] == 1500
    assert any("get_sleep_data" in x for x in res["log"])


def test_429_aborts(monkeypatch):
    monkeypatch.setattr(G, "PAUSA_S", 0)

    class Bad(Fake):
        def get_activities_by_date(self, a, b): raise RuntimeError("429 Too Many Requests")

    try:
        G.sync(Bad(), 3, G.TIPOS_DEFECTO)
        assert False
    except RuntimeError as e:
        assert "429" in str(e)
