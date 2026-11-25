from mil import zones as Z
from mil.util import fmt_pace


def test_vdot_reference_values():
    assert abs(Z.vdot_from_race(5000, 19 * 60 + 57) - 50.0) < 0.2


def test_daniels_threshold_pace_vdot50():
    fast, slow = Z.pace_table(50)["T"]
    assert fmt_pace(fast) == "4:15"
    assert fast < slow


def test_pace_order():
    t = Z.pace_table(40)
    assert t["R"][0] < t["I"][0] < t["T"][0] < t["E"][0]


def test_hr_zones_reserve_and_lthr():
    z = Z.hr_zones(max_hr=190, rest_hr=60)
    assert z.easy_ceiling == 150 and not z.provisional
    z2 = Z.hr_zones(max_hr=190, lthr=165)
    assert z2.method.startswith("umbral") and z2.easy_ceiling == 147
    assert Z.hr_zones().provisional
    r = z.ranges()
    assert all(r[i][1] + 1 == r[i + 1][0] for i in range(4))
