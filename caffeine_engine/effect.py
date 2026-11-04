"""카페인 → 각성 효과 (Ramakrishnan 2016, 2B-Alert 모델의 식 1·6).

카페인을 마셨을 때의 졸림(결손) = 카페인 없을 때의 졸림 × g
    g = 1 / (1 + Σ Mc·ka/(ka−kc)·(e^(−kc·τ) − e^(−ka·τ)))
    Mc = M0·c,  kc = k0·e^(−z·c),  c = 한 잔 용량(g),  τ = 마신 뒤 시간(h)
g = 1이면 효과 없음, 0이면 졸림이 완전히 사라짐.

우리 각성 점수(Åkerstedt 1~21)로 옮기는 방법:
    졸림(결손) = 기준 점수(14) − 각성 점수
    카페인 반영 점수 = 14 − (14 − 원래 점수) × g
"""
import math
from typing import Iterable, List, Optional

from . import params
from .fatigue import AlertnessPoint
from .pk import Dose, pieces


def _p(name: str):
    return params.value("caffeine_effect", name)


def _metric(metric: Optional[str]) -> str:
    return metric or _p("default_metric")


def dose_effect(dose: Dose, t: float, metric: Optional[str] = None) -> float:
    """한 잔이 시각 t에 만드는 효과 크기 (g 분모에 더해지는 값, 0 이상)."""
    if dose.duration_h > 0:     # 나눠 마시기: 조금씩 마신 잔들의 효과를 더함
        return sum(dose_effect(p, t, metric) for p in pieces(dose))
    tau = t - dose.time_h
    if tau <= 0 or dose.mg <= 0:
        return 0.0
    grams = dose.mg / 1000
    ka = params.value("pk", "absorption_rate_per_h")
    mc = _p("m0_per_g")[_metric(metric)] * grams
    kc = _p("k0_per_h") * math.exp(-_p("z_per_g") * grams)
    return mc * ka / (ka - kc) * (math.exp(-kc * tau) - math.exp(-ka * tau))


def caffeine_factor(t: float, doses: Iterable[Dose], metric: Optional[str] = None) -> float:
    """g(t): 졸림에 곱하는 계수. 1 = 효과 없음, 작을수록 효과 큼."""
    return 1 / (1 + sum(dose_effect(d, t, metric) for d in doses))


def sleepiness_reduction(t: float, doses: Iterable[Dose], metric: Optional[str] = None) -> float:
    """졸림이 몇 % 줄었나 (0~1)."""
    return 1 - caffeine_factor(t, doses, metric)


def score_with_caffeine(point: AlertnessPoint, doses: Iterable[Dose],
                        metric: Optional[str] = None, include_inertia: bool = True) -> float:
    """카페인을 반영한 각성 점수. 자는 동안·이미 기준보다 또렷하면 그대로."""
    score = point.score if include_inertia else point.score + point.w
    reference = _p("reference_score")
    if point.asleep or score >= reference:
        return score
    return reference - (reference - score) * caffeine_factor(point.t, doses, metric)


def curve_with_caffeine(points: Iterable[AlertnessPoint], doses: Iterable[Dose],
                        metric: Optional[str] = None) -> List[float]:
    doses = list(doses)
    return [score_with_caffeine(p, doses, metric) for p in points]
