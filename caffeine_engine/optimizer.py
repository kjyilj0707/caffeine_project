"""④ 최적화 엔진 — '언제, 얼마나 마실까'를 찾는다 (앱의 두뇌).

벌점(작을수록 좋은 플랜) = Vital-Lopez 2018 구조 + 우리 앱 항목
  졸림 면적   Σ 구간 가중치 × 졸림(14 − 점수) × 시간
  최악 졸림   목표 구간에서 가장 졸린 순간
  위험 벌점   졸면 안 되는·깨어 있어야 하는 구간에서 위험선 7 아래인 시간
  섭취량      같은 효과면 덜 마시는 쪽

후보에서 아예 빼는 플랜 (지켜야 할 규칙)
  하루 상한 · 1회 용량 · 잔 사이 2시간 · 몸속 최고치가 400mg 1회 복용 최고치 이하
  잠든 뒤 2시간 최대 잔량 ≤ 허용치(30mg) · 예상 수면 감소 < 20분 (Gardiner 2023)

찾는 방법: 아무것도 안 마시는 플랜에서 시작해, '한 잔 추가 · 시각 옮기기 ·
양 바꾸기 · 빼기' 중 벌점을 가장 많이 줄이는 변경을 반복 (더 못 줄이면 끝).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import params
from .effect import dose_effect
from .fatigue import SleepEpisode, alertness_curve
from .pk import Dose, amount_from_dose

KINDS = ("stay_awake", "must_not_sleep", "focus")


@dataclass(frozen=True)
class Window:
    start_h: float
    end_h: float
    kind: str  # stay_awake / must_not_sleep / focus

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"구간 종류는 {KINDS} 중 하나: {self.kind}")


@dataclass
class Plan:
    new_doses: List[Dose]
    all_doses: List[Dose]
    cost: float
    total_mg: float
    max_residual_mg: float          # 잠든 뒤 2시간 동안 최대 몸속 카페인
    sleep_loss_min: float           # Gardiner 예상 수면 감소 (마지막 잔 기준)
    last_dose_h: Optional[float]    # 플랜의 마지막 잔 시각 → 이후엔 플랜 외 카페인 금지
    cutoff_h: Optional[float]       # 절대 컷오프: 이미 마신 것 기준, 이 시각부터는 25mg도 수면 기준 위반
    sleepiness_reduction: float     # 목표 구간 졸림 면적이 아무것도 안 마실 때보다 몇 % 줄었나
    danger_hours: float             # 플랜대로 해도 위험선 아래인 시간 (졸면 안 되는·깨어 있어야 하는 구간)
    danger_hours_without: float     # 새로 안 마실 때 위험선 아래인 시간
    warnings: List[str] = field(default_factory=list)


def _o(name: str):
    return params.value("optimizer", name)


def gardiner_sleep_loss_min(dose: Dose, bed_h: float) -> float:
    """Gardiner 2023 메타회귀: 마지막 잔 기준 예상 수면 감소(분)."""
    model = params.load()["sleep_protection"]["sleep_loss_model"]
    minutes_before = (bed_h - dose.time_h) * 60
    return model["intercept_min"] + model["per_min_before_bed"] * minutes_before + model["per_mg"] * dose.mg


class _Problem:
    """후보 시각·용량별 효과/잔량을 미리 계산해 두고 플랜 벌점을 빠르게 매긴다."""

    def __init__(self, sleeps, windows, bed_h, now_h, already, daily_cap_mg, single_cap_mg,
                 residual_limit_mg, half_life_h, chronotype):
        self.bed_h = bed_h
        self.already = list(already)
        self.daily_cap = daily_cap_mg
        self.residual_limit = residual_limit_mg
        self.half_life = half_life_h
        step = _o("time_step_h")
        reference = params.value("caffeine_effect", "reference_score")
        danger = params.value("fatigue", "danger_threshold")

        # 평가 시간축: 목표 구간들을 덮는 15분 격자
        t0 = min(w.start_h for w in windows)
        t1 = max(w.end_h for w in windows)
        points = alertness_curve(sleeps, t0, t1, step, chronotype)
        self.t = np.array([p.t for p in points])
        # 기상 직후 멍함(W)은 뺀다: 1~2시간이면 저절로 사라지고, Ramakrishnan 2016 모델도
        # 수면 관성은 다루지 않는다. 넣으면 '일어나자마자 최대 용량'만 추천하게 된다.
        self.base = np.array([p.score + p.w for p in points])
        self.awake = np.array([not p.asleep for p in points])
        self.reference, self.danger, self.dt = reference, danger, step

        weights = _o("window_weights")
        self.weight = np.zeros_like(self.t)
        self.guard = np.zeros_like(self.t, dtype=bool)  # 위험선을 지켜야 하는 구간
        for w in windows:
            inside = (self.t >= w.start_h - 1e-9) & (self.t < w.end_h - 1e-9)
            self.weight = np.where(inside, np.maximum(self.weight, weights[w.kind]), self.weight)
            if w.kind in ("stay_awake", "must_not_sleep"):
                self.guard |= inside
        self.weight *= self.awake

        # 잔량 검사 시간축: 잠든 뒤 residual_window_h 동안
        self.t_sleep = np.arange(bed_h, bed_h + _o("residual_window_h") + 1e-9, step)
        # 400mg 1회 복용 최고치 (Vital-Lopez 안전 기준)
        probe = np.arange(0, 12, 1 / 12)
        self.cmax = max(amount_from_dose(Dose(0.0, 400), x, half_life_h) for x in probe)
        self.t_body = np.arange(min([now_h] + [d.time_h for d in self.already]), bed_h + 1e-9, step)

        # 후보: 지금부터 취침 전까지 15분마다 × 용량
        first = np.ceil((now_h - 1e-9) / step) * step
        self.slots = [round(x, 4) for x in np.arange(first, bed_h - 1e-9, step)]
        self.doses_mg = [mg for mg in _o("dose_options_mg") if mg <= single_cap_mg]

        self._cache: Dict[Tuple[float, float], Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self.base_effect = self._sum(self.already)[0]

    def _vectors(self, dose: Dose):
        key = (dose.time_h, dose.mg)
        if key not in self._cache:
            effect = np.array([dose_effect(dose, x) for x in self.t])
            sleep_amount = np.array([amount_from_dose(dose, x, self.half_life) for x in self.t_sleep])
            body = np.array([amount_from_dose(dose, x, self.half_life) for x in self.t_body])
            self._cache[key] = (effect, sleep_amount, body)
        return self._cache[key]

    def _sum(self, doses):
        effect = np.zeros_like(self.t)
        sleep_amount = np.zeros_like(self.t_sleep)
        body = np.zeros_like(self.t_body)
        for d in doses:
            e, s, b = self._vectors(d)
            effect, sleep_amount, body = effect + e, sleep_amount + s, body + b
        return effect, sleep_amount, body

    def scores(self, new_doses) -> np.ndarray:
        effect = self.base_effect + self._sum(new_doses)[0]
        g = 1 / (1 + effect)
        lifted = self.reference - (self.reference - self.base) * g
        return np.where(self.awake & (self.base < self.reference), lifted, self.base)

    def violations(self, new_doses) -> List[str]:
        all_doses = sorted(self.already + list(new_doses), key=lambda d: d.time_h)
        problems = []
        if sum(d.mg for d in all_doses) > self.daily_cap + 1e-9:
            problems.append("하루 상한 초과")
        times = [d.time_h for d in all_doses]
        if any(b - a < _o("min_interval_h") - 1e-9 for a, b in zip(times, times[1:])):
            problems.append("잔 사이 간격 2시간 미만")
        _, sleep_amount, body = self._sum(all_doses)
        if sleep_amount.max(initial=0) > self.residual_limit + 1e-9:
            problems.append(f"잠든 뒤 몸속 카페인 {sleep_amount.max():.0f}mg > {self.residual_limit:g}mg")
        if all_doses and gardiner_sleep_loss_min(all_doses[-1], self.bed_h) >= params.value(
                "sleep_protection", "meaningful_sleep_loss_min"):
            problems.append("예상 수면 감소 20분 이상")
        if body.max(initial=0) > self.cmax + 1e-9:
            problems.append("몸속 최고치가 400mg 1회 복용보다 높음")
        return problems

    def deficit(self, scores: np.ndarray) -> np.ndarray:
        return np.clip(self.reference - scores, 0, None)

    def danger_hours(self, scores: np.ndarray) -> float:
        # scores는 이미 멍함을 뺀 점수 (fatigue.first_time_below와 같은 기준)
        below = (scores < self.danger) & self.guard & self.awake
        return float(below.sum() * self.dt)

    def cost(self, new_doses) -> float:
        s = self.scores(new_doses)
        weighted = self.weight * self.deficit(s)
        area = weighted.sum() * self.dt
        worst = weighted.max(initial=0)
        return (area + _o("worst_point_weight") * worst
                + _o("danger_penalty_per_h") * self.danger_hours(s)
                + _o("mg_penalty") * sum(d.mg for d in new_doses))


def _neighbors(problem: _Problem, plan: List[Dose]):
    if len(plan) < _o("max_new_doses"):
        for t in problem.slots:
            for mg in problem.doses_mg:
                yield plan + [Dose(t, mg)]
    for i, d in enumerate(plan):
        rest = plan[:i] + plan[i + 1:]
        yield rest
        for mg in problem.doses_mg:
            if mg != d.mg:
                yield rest + [Dose(d.time_h, mg)]
        for shift in (-4, -2, -1, 1, 2, 4):
            t = round(d.time_h + shift * _o("time_step_h"), 4)
            if t in problem.slots:
                yield rest + [Dose(t, d.mg)]


def cutoff_time(problem: _Problem) -> Optional[float]:
    """절대 컷오프: 이미 마신 것에 25mg만 더해도 수면 기준을 어기기 시작하는 시각.

    플랜은 수면 기준을 거의 다 쓰도록 짜이므로, 플랜까지 넣고 계산하면 늘 '지금'이
    나온다. 그래서 이미 마신 것만 기준으로 '이 시각 이후엔 한 모금도 안 됨'을 구한다.
    """
    probe = _o("cutoff_probe_mg")
    sleep_rules = ("잠든 뒤", "예상 수면")
    for t in problem.slots:
        if any(p.startswith(sleep_rules) for p in problem.violations([Dose(t, probe)])):
            return t
    return None


def optimize(sleeps: Sequence[SleepEpisode], windows: Sequence[Window], bed_h: float, now_h: float,
             already: Sequence[Dose] = (), daily_cap_mg: Optional[float] = None,
             single_cap_mg: Optional[float] = None, residual_limit_mg: Optional[float] = None,
             half_life_h: Optional[float] = None, chronotype: str = "neutral") -> Plan:
    """오늘 남은 시간의 최적 섭취 플랜."""
    if not windows:
        raise ValueError("목표 구간(깨어 있어야 하는 시간 등)이 최소 1개 필요합니다")
    daily_cap = daily_cap_mg if daily_cap_mg is not None else params.value("limits", "daily_mg_adult")
    single_cap = single_cap_mg if single_cap_mg is not None else params.value("limits", "single_dose_mg")
    limit = residual_limit_mg if residual_limit_mg is not None else params.value(
        "sleep_protection", "bedtime_residual_mg")
    half_life = half_life_h if half_life_h is not None else params.value("pk", "half_life_h")

    problem = _Problem(sleeps, windows, bed_h, now_h, already, daily_cap, single_cap, limit,
                       half_life, chronotype)
    warnings = []
    already_problems = problem.violations([])
    if already_problems:
        warnings.append("이미 마신 카페인만으로 기준을 넘음: " + ", ".join(already_problems)
                        + " → 오늘은 더 마시지 않기")

    plan: List[Dose] = []
    best = problem.cost(plan)
    if not already_problems:
        while True:
            candidates = [(problem.cost(c), c) for c in _neighbors(problem, plan) if not problem.violations(c)]
            if not candidates:
                break
            cost, choice = min(candidates, key=lambda x: x[0])
            if cost >= best - 1e-9:
                break
            best, plan = cost, sorted(choice, key=lambda d: d.time_h)

    all_doses = sorted(problem.already + plan, key=lambda d: d.time_h)
    s_plan, s_none = problem.scores(plan), problem.scores([])
    area_plan = (problem.weight * problem.deficit(s_plan)).sum()
    area_none = (problem.weight * problem.deficit(s_none)).sum()
    reduction = 1 - area_plan / area_none if area_none > 0 else 0.0
    danger_plan = problem.danger_hours(s_plan)
    if danger_plan > 0:
        warnings.append(f"카페인으로도 위험선 아래인 시간이 {danger_plan:g}시간 남음 → 수면·휴식이 필요")

    _, sleep_amount, _ = problem._sum(all_doses)
    return Plan(
        new_doses=plan,
        all_doses=all_doses,
        cost=best,
        total_mg=sum(d.mg for d in all_doses),
        max_residual_mg=float(sleep_amount.max(initial=0)),
        sleep_loss_min=gardiner_sleep_loss_min(all_doses[-1], bed_h) if all_doses else 0.0,
        last_dose_h=plan[-1].time_h if plan else None,
        cutoff_h=cutoff_time(problem) if not already_problems else now_h,
        sleepiness_reduction=reduction,
        danger_hours=danger_plan,
        danger_hours_without=problem.danger_hours(s_none),
        warnings=warnings,
    )
