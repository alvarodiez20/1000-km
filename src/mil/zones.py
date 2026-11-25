"""Zonas de frecuencia cardíaca y ritmos de entrenamiento.

Ritmos: modelo VDOT de Jack Daniels (fórmulas de Daniels y Gilbert, 1979).
Zonas de FC: por umbral (LTHR, estilo Friel) si se conoce; si no, por reserva
cardíaca (Karvonen); si tampoco, estimación provisional con Tanaka.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------- VDOT / ritmos


def vo2_at_speed(v_m_min: float) -> float:
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min**2


def pct_vo2max(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_race(dist_m: float, secs: float) -> float:
    t = secs / 60.0
    return vo2_at_speed(dist_m / t) / pct_vo2max(t)


def speed_at_vo2(vo2: float) -> float:
    a, b, c = 0.000104, 0.182258, -(4.60 + vo2)
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def pace_at_fraction(vdot: float, frac: float) -> float:
    """Segundos por km a una fracción del VO2max (VDOT)."""
    return 1000.0 / speed_at_vo2(vdot * frac) * 60.0


# (rápido, lento) como fracción del VO2max
INTENSIDADES = {
    "E": (0.70, 0.62),   # fácil
    "T": (0.88, 0.85),   # umbral
    "I": (1.00, 0.97),   # intervalos (VO2max)
    "R": (1.10, 1.05),   # repeticiones / rectas
}


def pace_table(vdot: float) -> dict[str, tuple[float, float]]:
    """{'E': (s/km rápido, s/km lento), ...}"""
    return {k: (pace_at_fraction(vdot, f), pace_at_fraction(vdot, s)) for k, (f, s) in INTENSIDADES.items()}


def mid(pair: tuple[float, float]) -> float:
    return (pair[0] + pair[1]) / 2.0


# ---------------------------------------------------------------- Zonas de FC


@dataclass
class HRZones:
    method: str
    floors: list[int]   # límite inferior de Z1..Z5 (Z1 empieza en 0)
    max_hr: int
    provisional: bool = False

    def ranges(self) -> list[tuple[int, int]]:
        out = []
        for i, lo in enumerate(self.floors):
            hi = self.floors[i + 1] - 1 if i < 4 else self.max_hr
            out.append((lo, hi))
        return out

    @property
    def easy_ceiling(self) -> int:
        """Techo de los rodajes fáciles: tope de Z2."""
        return self.floors[2] - 1

    def label(self, z: int) -> str:
        lo, hi = self.ranges()[z - 1]
        return f"Z{z} ({'<' + str(hi + 1) if z == 1 else str(lo) + '-' + str(hi)} lpm)"


def hr_zones(max_hr=None, rest_hr=None, lthr=None, age=None) -> HRZones:
    provisional = False
    if max_hr is None:
        age = age or 35
        max_hr = round(208 - 0.7 * age)
        provisional = True
    max_hr = int(round(max_hr))
    if lthr:
        lthr = float(lthr)
        floors = [0] + [round(f * lthr) for f in (0.85, 0.90, 0.95, 1.03)]
        return HRZones("umbral (LTHR)", floors, max_hr, provisional)
    if rest_hr is None:
        rest_hr = 60
        provisional = True
    reserve = max_hr - rest_hr
    floors = [0] + [round(rest_hr + f * reserve) for f in (0.60, 0.70, 0.80, 0.90)]
    return HRZones("reserva cardíaca (Karvonen)", floors, max_hr, provisional)
