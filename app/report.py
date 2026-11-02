"""📊 리포트 계산 (Step 4-6) — 서버 원자료(store.report_rows) → 날짜별 기록 → 기간 요약.

하루 = 그날 새벽 4시 ~ 다음 날 새벽 4시 (밤늦게 마신 것도 그날). 잠은 깬 날짜 기준.
'추천대로 마셨나'·'금지 시각'은 사용자가 기록한 '마신 것'만으로 판단한다 (기록 안 한 잔은 모름).
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from caffeine_engine import params
from caffeine_engine.metrics import period_report
from caffeine_engine.notify import local_tz
from caffeine_engine.pk import Dose
from caffeine_engine.timeutil import hhmm_to_h

MATCH_MIN = 30          # 추천 시각 ±30분 안에 마셨으면 '추천대로'
ROLLOVER_H = 4


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(local_tz())


def _day_of(t: datetime) -> date:
    return (t - timedelta(hours=ROLLOVER_H)).date()


def _hours_since_midnight(t: datetime, day: date) -> float:
    """그날 0시부터 지난 시간 (다음 날 새벽이면 24 이상) — 엔진 시각과 같은 기준."""
    return (t - datetime(day.year, day.month, day.day, tzinfo=local_tz())).total_seconds() / 3600


@dataclass
class DayStat:
    day: date
    intakes: List[Dose] = field(default_factory=list)     # 기록한 마신 것 (엔진 시각)
    planned: List[Dose] = field(default_factory=list)     # 그날 마지막으로 저장한 추천
    cutoff_h: Optional[float] = None
    sleep_h: Optional[float] = None
    latency_min: Optional[int] = None
    quality: Optional[int] = None
    kss: List[int] = field(default_factory=list)

    @property
    def mg(self) -> float:
        return sum(d.mg for d in self.intakes)

    @property
    def matched(self) -> int:
        """추천 잔 중 ±30분 안에 실제로 마신 잔 수 (한 번 마신 기록은 한 추천에만 대응)."""
        left = sorted(d.time_h for d in self.intakes)
        n = 0
        for p in self.planned:
            hit = next((t for t in left if abs(t - p.time_h) <= MATCH_MIN / 60), None)
            if hit is not None:
                left.remove(hit)
                n += 1
        return n

    @property
    def cutoff_kept(self) -> Optional[bool]:
        """금지 시각 이후 기록이 없으면 True. 추천이나 기록이 없으면 판단 못 함(None)."""
        if self.cutoff_h is None or not self.intakes:
            return None
        return all(d.time_h < self.cutoff_h for d in self.intakes)


def _cutoff_h(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    h = hhmm_to_h(text)
    return h + 24 if h < ROLLOVER_H else h      # 새벽 시각은 다음 날


def day_stats(rows: Dict[str, List], first: date, last: date) -> List[DayStat]:
    days = {first + timedelta(i): DayStat(first + timedelta(i)) for i in range((last - first).days + 1)}
    for r in rows.get("intakes", []):
        t = _ts(r["taken_at"])
        if (d := days.get(_day_of(t))) is not None:
            d.intakes.append(Dose(_hours_since_midnight(t, d.day), float(r["mg"])))
    for r in rows.get("plans", []):            # 오래된 것부터 → 같은 날은 마지막 저장이 남음
        d = days.get(date.fromisoformat(r["plan_date"]))
        result = r.get("result") or {}
        if d is not None:
            d.planned = [Dose(x["time_h"], x["mg"]) for x in result.get("doses", [])]
            d.cutoff_h = _cutoff_h(result.get("cutoff"))
    for r in rows.get("sleeps", []):
        woke, slept = _ts(r["woke_at"]), _ts(r["slept_at"])
        if (d := days.get(woke.date())) is not None:
            d.sleep_h = (woke - slept).total_seconds() / 3600
            d.latency_min, d.quality = r.get("sleep_latency_min"), r.get("quality")
    for r in rows.get("kss", []):
        if (d := days.get(_day_of(_ts(r["at"])))) is not None:
            d.kss.append(int(r["kss"]))
    return list(days.values())


def _mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


@dataclass(frozen=True)
class Summary:
    total_mg: float
    daily_average_mg: float
    days_with_caffeine: int
    max_day: Optional[date]
    max_day_mg: float
    days_over_cap: int
    cap_mg: float
    planned_cups: int
    matched_cups: int
    cutoff_days: int          # 금지 시각을 판단할 수 있었던 날
    cutoff_kept_days: int
    sleep_h: Optional[float]
    latency_min: Optional[float]
    kss_count: int
    kss_mean: Optional[float]


def summarize(stats: List[DayStat], cap_mg: Optional[float] = None) -> Summary:
    cap = cap_mg or params.value("limits", "daily_mg_adult")
    pr = period_report({s.day: s.intakes for s in stats}, stats[0].day, stats[-1].day, cap)
    judged = [s.cutoff_kept for s in stats if s.cutoff_kept is not None]
    kss = [k for s in stats for k in s.kss]
    return Summary(
        total_mg=pr.total_mg, daily_average_mg=pr.daily_average_mg, days_with_caffeine=pr.days_with_caffeine,
        max_day=pr.max_day, max_day_mg=pr.max_day_mg, days_over_cap=pr.days_over_cap, cap_mg=cap,
        planned_cups=sum(len(s.planned) for s in stats), matched_cups=sum(s.matched for s in stats),
        cutoff_days=len(judged), cutoff_kept_days=sum(judged),
        sleep_h=_mean(s.sleep_h for s in stats), latency_min=_mean(s.latency_min for s in stats),
        kss_count=len(kss), kss_mean=_mean(kss),
    )
