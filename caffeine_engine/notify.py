"""Step 3 알림 — 플랜을 '언제 · 무슨 알림'으로 바꾸고 실제 날짜·시각을 붙인다.

보내는 일(인터넷)은 app/ntfy.py가 한다. 여기는 계산만 해서 테스트하기 쉽게 둔다.

엔진 시각(그날 0시부터 지난 시간, 자정 넘으면 24+)을 실제 시각으로 바꾸는 법:
  '그날 0시' = 지금 실제 시각 − 입력한 '지금 시각'(now_h)을 가장 가까운 자정으로 맞춘 것
  → 새벽 0:30에 '24:30'으로 입력해도 전날 0시가 기준이 되어 시각이 어긋나지 않는다.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from . import params
from .convert import Serving
from .optimizer import Plan
from .timeutil import h_to_hhmm


@dataclass(frozen=True)
class Notification:
    time_h: float          # 엔진 시각
    kind: str              # drink / stop / test / feedback
    title: str
    message: str
    tags: tuple = ()
    priority: int = 3      # ntfy 1(최저)~5(최고)


def _n(name: str):
    return params.value("notify", name)


def local_tz() -> timezone:
    return timezone(timedelta(hours=_n("utc_offset_h")), "KST")


def day_start(now_h: float, real_now: Optional[datetime] = None) -> datetime:
    """엔진 시각 0h에 해당하는 실제 시각(그날 0시, 한국 시간)."""
    tz = local_tz()
    real_now = (real_now or datetime.now(tz)).astimezone(tz)
    guess = real_now - timedelta(hours=now_h)
    midnight = guess.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=1) if guess - midnight >= timedelta(hours=12) else midnight


def to_datetime(time_h: float, start: datetime) -> datetime:
    return start + timedelta(minutes=round(time_h * 60))


def plan_notifications(plan: Plan, servings: Sequence[Serving], bed_h: float) -> List[Notification]:
    """마실 시각마다 1개 + 절대 컷오프 1개."""
    out: List[Notification] = []
    for i, (dose, s) in enumerate(zip(plan.new_doses, servings)):
        last = i == len(plan.new_doses) - 1
        tail = " · 오늘 마지막 잔이에요" if last else ""
        out.append(Notification(
            time_h=dose.time_h, kind="drink",
            title=f"{h_to_hhmm(dose.time_h)} {s.beverage.name} {s.cup} · {s.minutes}분 동안",
            message=f"약 {s.ml:.0f}ml · {s.mg_actual:.0f}mg · {s.pace}{tail}",
            tags=("coffee",), priority=4))
    if plan.cutoff_h is not None:
        out.append(Notification(
            time_h=plan.cutoff_h, kind="stop",
            title="지금부터 카페인 금지",
            message=f"{h_to_hhmm(bed_h)} 취침 · 수면 보호를 위해 한 모금도 마시지 마세요",
            tags=("no_entry",), priority=3))
    return sorted(out, key=lambda n: n.time_h)


def feedback_notifications(windows) -> List[Notification]:
    """'졸면 안 되는 시간' 한가운데에 '지금 얼마나 졸려요?' — 예측과 실제를 비교할 정답 데이터 모으기."""
    return [Notification(time_h=(w.start_h + w.end_h) / 2, kind="feedback", title="지금 얼마나 졸려요?",
                         message="앱을 열어 1~9점으로 남겨 주세요 (10초)", tags=("memo",), priority=3)
            for w in windows if w.kind == "must_not_sleep"]


def make_test_notification(now_h: float, minutes: int = 1) -> Notification:
    return Notification(time_h=now_h + minutes / 60, kind="test", title="카페인 측정기 테스트 알림",
                        message=f"{minutes}분 전에 예약한 알림이에요. 이게 보이면 알림 설정 완료!",
                        tags=("bell",), priority=3)


@dataclass(frozen=True)
class Scheduled:
    notification: Notification
    at: datetime            # 보낼 실제 시각 (한국 시간)
    send: bool              # False면 건너뜀
    reason: str = ""        # 건너뛴 이유


def schedule(notifications: Sequence[Notification], now_h: float,
             real_now: Optional[datetime] = None) -> List[Scheduled]:
    """실제 시각을 붙이고, 이미 지났거나 너무 먼 알림은 건너뛴다."""
    tz = local_tz()
    real_now = (real_now or datetime.now(tz)).astimezone(tz)
    start = day_start(now_h, real_now)
    out = []
    for n in notifications:
        at = to_datetime(n.time_h, start)
        lead = (at - real_now).total_seconds()
        if lead < _n("min_lead_s"):
            out.append(Scheduled(n, at, False, "이미 지난 시각"))
        elif lead > _n("max_ahead_h") * 3600:
            out.append(Scheduled(n, at, False, "3일 넘게 남음 (ntfy 예약 한도)"))
        else:
            out.append(Scheduled(n, at, True))
    return out


def schedule_test(minutes: int = 1, real_now: Optional[datetime] = None) -> Scheduled:
    """테스트 알림은 입력한 '지금 시각'이 아니라 실제 현재 시각 + minutes분에 보낸다."""
    tz = local_tz()
    real_now = (real_now or datetime.now(tz)).astimezone(tz)
    at = (real_now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    if (at - real_now).total_seconds() < _n("min_lead_s"):
        at += timedelta(minutes=1)
    hours = at.hour + at.minute / 60
    return Scheduled(make_test_notification(hours - minutes / 60, minutes), at, True)


def current_time_h(real_now: Optional[datetime] = None) -> float:
    """실제 현재 한국 시각을 15분 단위로 내림한 값 (화면의 '실제 현재 시각으로' 버튼용)."""
    tz = local_tz()
    real_now = (real_now or datetime.now(tz)).astimezone(tz)
    return real_now.hour + (real_now.minute // 15) * 15 / 60
