"""지표 계산 — 설계서 「3. 나타낼 지표 10가지」 중 플랜과 별개로 계산하는 것들.

(곡선·플랜·컷오프·잔량·수면 감소는 pk / effect / optimizer가 이미 계산한다)
  7  오늘 누적 섭취 / 상한
  8  목표 구간 커버율 (위험선 이상인 시간 비율)
  9  수면 부채
  10 일·주·월 리포트
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from . import params
from .effect import curve_with_caffeine
from .fatigue import SleepEpisode, alertness_curve
from .optimizer import Window
from .pk import Dose


def _m(name: str):
    return params.value("metrics", name)


# ── 7. 누적 섭취 / 상한 ─────────────────────────
@dataclass(frozen=True)
class CapStatus:
    total_mg: float
    cap_mg: float
    level: str  # ok / warning(80%+) / over(100%+)

    @property
    def ratio(self) -> float:
        return self.total_mg / self.cap_mg


def cap_status(doses: Iterable[Dose], cap_mg: float) -> CapStatus:
    total = sum(d.mg for d in doses)
    warn, over = _m("cap_warning_levels")
    ratio = total / cap_mg
    level = "over" if ratio >= over else "warning" if ratio >= warn else "ok"
    return CapStatus(total, cap_mg, level)


# ── 8. 목표 구간 커버율 ─────────────────────────
@dataclass(frozen=True)
class Coverage:
    kind: str
    start_h: float
    end_h: float
    with_caffeine: float     # 위험선 이상인 시간 비율 (0~1)
    without_caffeine: float


def window_coverage(sleeps: Sequence[SleepEpisode], windows: Sequence[Window], doses: Sequence[Dose],
                    chronotype: str = "neutral") -> List[Coverage]:
    """구간마다 '졸음 위험선(7) 이상으로 버틴 시간' 비율. 기상 직후 멍함은 뺀다."""
    danger = params.value("fatigue", "danger_threshold")
    step = params.value("optimizer", "time_step_h")
    out = []
    for w in windows:
        points = [p for p in alertness_curve(sleeps, w.start_h, w.end_h, step, chronotype) if p.t < w.end_h]
        lifted = curve_with_caffeine(points, doses)
        awake = [(p, s) for p, s in zip(points, lifted) if not p.asleep]
        if not awake:
            continue
        ok_with = sum(s + p.w >= danger for p, s in awake) / len(awake)
        ok_without = sum(p.score + p.w >= danger for p, _ in awake) / len(awake)
        out.append(Coverage(w.kind, w.start_h, w.end_h, ok_with, ok_without))
    return out


# ── 9. 수면 부채 ───────────────────────────────
def sleep_debt_h(sleeps: Sequence[SleepEpisode], days: Optional[int] = None,
                 need_h: Optional[float] = None) -> float:
    """최근 days일 동안 (필요 수면 − 실제 수면)의 합. 더 잔 날은 0으로 본다."""
    days = days or _m("sleep_debt_days")
    need = need_h if need_h is not None else _m("sleep_need_h")
    recent = sorted(sleeps, key=lambda e: e.end_h)[-days:]
    return sum(max(0.0, need - (e.end_h - e.start_h)) for e in recent)


# ── 10. 일·주·월 리포트 ─────────────────────────
@dataclass(frozen=True)
class PeriodReport:
    start: date
    end: date
    total_mg: float
    days_with_caffeine: int
    daily_average_mg: float      # 기간 전체 일수로 나눈 평균
    max_day: Optional[date]
    max_day_mg: float
    days_over_cap: int


def period_report(intake_by_day: Dict[date, Sequence[Dose]], start: date, end: date,
                  cap_mg: Optional[float] = None) -> PeriodReport:
    """start~end(포함) 기간의 섭취 요약. intake_by_day: 날짜 → 그날 마신 잔 목록."""
    cap = cap_mg if cap_mg is not None else params.value("limits", "daily_mg_adult")
    n_days = (end - start).days + 1
    totals = {start + timedelta(i): sum(d.mg for d in intake_by_day.get(start + timedelta(i), ()))
              for i in range(n_days)}
    total = sum(totals.values())
    max_day = max(totals, key=totals.get) if total > 0 else None
    return PeriodReport(
        start=start, end=end, total_mg=total,
        days_with_caffeine=sum(1 for v in totals.values() if v > 0),
        daily_average_mg=total / n_days,
        max_day=max_day, max_day_mg=totals[max_day] if max_day else 0.0,
        days_over_cap=sum(1 for v in totals.values() if v > cap),
    )


def weekly_report(intake_by_day, week_end: date, cap_mg: Optional[float] = None) -> PeriodReport:
    return period_report(intake_by_day, week_end - timedelta(days=6), week_end, cap_mg)


def monthly_report(intake_by_day, year: int, month: int, cap_mg: Optional[float] = None) -> PeriodReport:
    first = date(year, month, 1)
    last = (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)
    return period_report(intake_by_day, first, last, cap_mg)
