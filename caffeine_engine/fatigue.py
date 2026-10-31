"""② 피로도 엔진 — Åkerstedt 3-프로세스 각성 모델 (2004).

각성 점수 = S(수면 압력) + C(생체 리듬) + U(오후 처짐) − W(기상 직후 멍함)
점수 해석: 14 = 매우 또렷 · 7 = 졸음 위험선 · 3 = 극도로 졸림

S는 수면 기록을 따라 시간 순서대로 시뮬레이션한다.
  깨어 있을 때: L을 향해 지수적으로 떨어짐
  자는 동안:   U_S를 향해 지수적으로 회복, 단 S < 12.5면 S=12.5일 때 속도로 제한
               (하룻밤에 수면 부채를 다 갚지 못함 → 며칠간 누적)
"""
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional

from . import params

_STEP_H = 1 / 60  # S 시뮬레이션 간격 (1분)


@dataclass(frozen=True)
class SleepEpisode:
    start_h: float  # 잠든 시각 (오늘 00:00 기준, 어제면 음수)
    end_h: float    # 깬 시각
    quality: Optional[int] = None  # 1~5, 없으면 5(정상)로 간주


@dataclass(frozen=True)
class AlertnessPoint:
    t: float
    s: float
    c: float
    u: float
    w: float
    asleep: bool

    @property
    def score(self) -> float:
        return self.s + self.c + self.u - self.w


def _p(name: str):
    return params.value("fatigue", name)


def _acrophase(chronotype: str) -> float:
    return _p("c_acrophase_h") + _p("chronotype_shift_h")[chronotype]


def circadian(t: float, chronotype: str = "neutral") -> float:
    """C: 24시간 주기, 오후에 높고 새벽에 낮다."""
    return _p("c_amplitude") * math.cos(2 * math.pi * (t - _acrophase(chronotype)) / 24)


def ultradian(t: float, chronotype: str = "neutral") -> float:
    """U: 12시간 주기 오후 처짐. C 정점 3시간 전이 골짜기."""
    trough = _acrophase(chronotype) + _p("u_phase_offset_h")
    return -_p("u_amplitude") * math.cos(2 * math.pi * (t - trough) / 12)


def inertia(hours_since_wake: float) -> float:
    """W: 일어난 직후 멍함. 1~2시간이면 거의 사라진다."""
    if hours_since_wake < 0:
        return 0.0
    return _p("w_initial") * math.exp(-_p("w_decay_per_h") * hours_since_wake)


def _wake_step(s: float, dt: float) -> float:
    low = _p("s_wake_lower_asymptote")
    return (s - low) * math.exp(-_p("s_wake_rate_per_h") * dt) + low


def _sleep_step(s: float, dt: float, quality_factor: float) -> float:
    upper = _p("s_sleep_upper_asymptote")
    rate = _p("s_sleep_rate_per_h") * quality_factor
    breakpoint = _p("s_recovery_breakpoint")
    if s < breakpoint:
        # 회복 속도 제한: S=12.5일 때의 속도로 직선 회복
        s_next = s + rate * (upper - breakpoint) * dt
        if s_next <= breakpoint:
            return s_next
        dt -= (breakpoint - s) / (rate * (upper - breakpoint))
        s = breakpoint
    return upper - (upper - s) * math.exp(-rate * dt)


def _quality_factor(episode: SleepEpisode) -> float:
    if episode.quality is None:
        return 1.0
    return _p("sleep_quality_recovery_factor")[episode.quality]


def alertness_curve(sleeps: Iterable[SleepEpisode], start_h: float, end_h: float,
                    step_h: float = 0.25, chronotype: str = "neutral") -> List[AlertnessPoint]:
    """start_h~end_h 구간의 각성 점수 곡선 (기본 15분 간격).

    수면 기록이 많을수록 정확하다(3~7일 권장). 첫 기록 이전 상태는
    논문 기본값(잠들 때 S = 7.96)으로 가정한다.
    """
    sleeps = sorted(sleeps, key=lambda e: e.start_h)
    if not sleeps:
        raise ValueError("수면 기록이 최소 1개 필요합니다")
    if start_h < sleeps[0].start_h:
        raise ValueError("곡선 시작 시각은 첫 수면 기록 이후여야 합니다")

    t0 = sleeps[0].start_h
    to_min = lambda hours: round(hours * 60)
    out_minutes = range(to_min(start_h - t0), to_min(end_h - t0) + 1, to_min(step_h))
    wanted = set(out_minutes)

    s = _p("s_at_retiring_default")
    out: List[AlertnessPoint] = []
    for minute in range(out_minutes[-1] + 1):
        t = t0 + minute / 60
        episode = next((e for e in sleeps if e.start_h <= t < e.end_h), None)
        if minute in wanted:
            last_wake = max((e.end_h for e in sleeps if e.end_h <= t), default=None)
            w = inertia(t - last_wake) if (episode is None and last_wake is not None) else 0.0
            out.append(AlertnessPoint(t=t, s=s, c=circadian(t, chronotype),
                                      u=ultradian(t, chronotype), w=w, asleep=episode is not None))
        if episode is None:
            s = _wake_step(s, _STEP_H)
        else:
            s = _sleep_step(s, _STEP_H, _quality_factor(episode))
    return out


def first_time_below(points: Iterable[AlertnessPoint], threshold: Optional[float] = None,
                     include_inertia: bool = False) -> Optional[float]:
    """깨어 있는 동안 점수가 처음으로 threshold(기본 위험선 7) 아래로 내려가는 시각.

    기본은 기상 직후 멍함(W)을 빼고 판단한다. 멍함은 잠깐 지나가는 것이라
    '피로가 쌓여 졸린 시각'을 찾을 때 넣으면 기상 직후가 잘못 잡힌다.
    """
    if threshold is None:
        threshold = _p("danger_threshold")
    for p in points:
        score = p.score if include_inertia else p.score + p.w
        if not p.asleep and score < threshold:
            return p.t
    return None
