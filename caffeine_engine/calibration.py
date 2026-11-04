"""Step 5 개인화 ① — 엔진의 예측과 사용자의 실제 기록을 비교한다 (추천은 아직 바꾸지 않음).

1) 졸림: 기록한 시각의 '카페인 반영 각성 점수' → KSS로 바꿔 사용자가 남긴 KSS(1~9)와 비교
       예측 KSS = 10.6 − 0.6 × 각성 점수   (Ingre 2014 식 1.9, 3-프로세스 모델 기본 변환)
       차이 = 실제 − 예측  (+면 모델보다 더 졸림, −면 덜 졸림)
2) 잠들기: 잠든 시각의 몸속 카페인이 기준(취침 허용 잔량)보다 많았던 밤과 적었던 밤의
       '잠드는 데 걸린 시간' 평균을 비교 → 기준이 이 사람에게 맞는지 보는 단서
"""
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from . import params
from .effect import score_with_caffeine
from .fatigue import SleepEpisode, alertness_curve
from .pk import Dose, amount_at


def _c(name: str):
    return params.value("calibration", name)


def kss_from_score(score: float) -> float:
    """각성 점수 → 예측 KSS (1~9 범위로 자름)."""
    k = _c("kss_from_alertness")
    return min(9.0, max(1.0, k["intercept"] + k["slope"] * score))


# ── 1) 졸림: 예측 vs 실제 ─────────────────────────
@dataclass(frozen=True)
class KssPair:
    t: float          # 엔진 시각 (기준 날짜 0시부터)
    observed: int
    predicted: float

    @property
    def diff(self) -> float:
        return self.observed - self.predicted


def kss_pairs(sleeps: Sequence[SleepEpisode], doses: Iterable[Dose], records: Iterable[tuple],
              chronotype: str = "neutral") -> List[KssPair]:
    """records: [(엔진 시각, KSS), ...]. 잠자는 중이거나 첫 수면 기록 이전 기록은 건너뛴다."""
    sleeps = sorted(sleeps, key=lambda e: e.start_h)
    doses = list(doses)
    out = []
    for t, kss in records:
        if not sleeps or t <= sleeps[0].end_h or any(e.start_h <= t < e.end_h for e in sleeps):
            continue
        point = alertness_curve(sleeps, t, t, chronotype=chronotype)[0]
        out.append(KssPair(t, int(kss), kss_from_score(score_with_caffeine(point, doses))))
    return out


@dataclass(frozen=True)
class KssBias:
    n: int
    mean_diff: Optional[float]   # 실제 − 예측 평균
    enough: bool                 # 기록 수가 판단할 만큼 쌓였나
    level: str                   # unknown / matches / sleepier / more_alert

    @property
    def message(self) -> str:
        need = _c("min_kss_records")
        if not self.enough:
            return f"졸림 기록 {self.n}/{need}개 — {need}개가 쌓이면 모델 예측과 비교해 드려요"
        d = self.mean_diff
        return {
            "matches": f"모델 예측과 비슷해요 (평균 차이 {d:+.1f}점)",
            "sleepier": f"모델 예측보다 평균 {d:.1f}점 더 졸려요 — 실제 피로가 모델보다 커요",
            "more_alert": f"모델 예측보다 평균 {-d:.1f}점 덜 졸려요 — 모델이 졸림을 크게 보고 있어요",
        }[self.level]


def kss_bias(pairs: Sequence[KssPair]) -> KssBias:
    n = len(pairs)
    if n == 0:
        return KssBias(0, None, False, "unknown")
    mean = sum(p.diff for p in pairs) / n
    if n < _c("min_kss_records"):
        return KssBias(n, mean, False, "unknown")
    th = _c("meaningful_kss_bias")
    level = "sleepier" if mean >= th else "more_alert" if mean <= -th else "matches"
    return KssBias(n, mean, True, level)


# ── 2) 잠들기 시간 vs 잠들 때 몸속 카페인 ─────────────
@dataclass(frozen=True)
class NightCheck:
    onset_h: float           # 잠든 시각 (엔진 시각)
    residual_mg: float       # 그때 몸속 카페인
    latency_min: int


def residual_at_onset(onset_h: float, doses: Iterable[Dose], half_life_h: float) -> float:
    return amount_at(onset_h, doses, half_life_h)


@dataclass(frozen=True)
class LatencyCompare:
    high_n: int
    low_n: int
    high_mean: Optional[float]   # 기준보다 많았던 밤의 평균 잠들기(분)
    low_mean: Optional[float]
    enough: bool

    @property
    def message(self) -> str:
        need = _c("min_nights_per_group")
        if not self.enough:
            return (f"잠들 때 카페인이 기준보다 많았던 밤 {self.high_n}일 · 적었던 밤 {self.low_n}일 — "
                    f"각각 {need}일 이상 쌓이면 비교해 드려요")
        gap = self.high_mean - self.low_mean
        return (f"카페인이 기준보다 많았던 밤엔 잠들기까지 평균 {self.high_mean:.0f}분, "
                f"적었던 밤엔 {self.low_mean:.0f}분 ({gap:+.0f}분)")


def latency_compare(nights: Sequence[NightCheck], limit_mg: float) -> LatencyCompare:
    high = [n.latency_min for n in nights if n.residual_mg > limit_mg]
    low = [n.latency_min for n in nights if n.residual_mg <= limit_mg]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    need = _c("min_nights_per_group")
    return LatencyCompare(len(high), len(low), mean(high), mean(low), len(high) >= need and len(low) >= need)
