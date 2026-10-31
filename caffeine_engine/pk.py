"""③ 체내 카페인 엔진 — 1구획 흡수·분해 모델.

한 잔(D mg)을 마시고 τ시간 뒤 몸에 남은 양:
    A(τ) = D · ka/(ka−ke) · (e^(−ke·τ) − e^(−ka·τ)),   ke = ln2 / 반감기
여러 잔이면 잔마다 계산해서 더한다.
"""
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from . import params


@dataclass(frozen=True)
class Dose:
    time_h: float  # 그날 00:00부터 지난 시간 (자정 넘으면 24+)
    mg: float


def elimination_rate(half_life_h: float) -> float:
    return math.log(2) / half_life_h


def _defaults(half_life_h: Optional[float], ka: Optional[float]) -> Tuple[float, float]:
    if half_life_h is None:
        half_life_h = params.value("pk", "half_life_h")
    if ka is None:
        ka = params.value("pk", "absorption_rate_per_h")
    return half_life_h, ka


def amount_from_dose(dose: Dose, t: float, half_life_h: Optional[float] = None,
                     ka: Optional[float] = None) -> float:
    """dose 한 잔이 시각 t에 몸에 남긴 양 (mg)."""
    half_life_h, ka = _defaults(half_life_h, ka)
    tau = t - dose.time_h
    if tau <= 0:
        return 0.0
    ke = elimination_rate(half_life_h)
    return dose.mg * ka / (ka - ke) * (math.exp(-ke * tau) - math.exp(-ka * tau))


def amount_at(t: float, doses: Iterable[Dose], half_life_h: Optional[float] = None,
              ka: Optional[float] = None) -> float:
    """시각 t의 몸속 카페인 총량 (mg)."""
    return sum(amount_from_dose(d, t, half_life_h, ka) for d in doses)


def curve(doses: Iterable[Dose], start_h: float, end_h: float, step_h: float = 0.25,
          half_life_h: Optional[float] = None, ka: Optional[float] = None) -> List[Tuple[float, float]]:
    """[(시각, mg), ...] — 그래프·지표용 시간 곡선 (기본 15분 간격)."""
    doses = list(doses)
    n = int(round((end_h - start_h) / step_h))
    return [(start_h + i * step_h, amount_at(start_h + i * step_h, doses, half_life_h, ka))
            for i in range(n + 1)]


def time_to_peak_h(half_life_h: Optional[float] = None, ka: Optional[float] = None) -> float:
    """한 잔 마신 뒤 몸속 양이 최고가 되는 시간 (h)."""
    half_life_h, ka = _defaults(half_life_h, ka)
    ke = elimination_rate(half_life_h)
    return math.log(ka / ke) / (ka - ke)
