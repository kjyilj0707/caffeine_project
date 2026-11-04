"""전체 실행기 — 입력을 받아 ①~⑤와 지표를 순서대로 계산한다.

  ① profile → ②③ fatigue·pk (optimizer 안에서) → ④ optimizer → ⑤ convert → metrics
"""
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from . import params
from .convert import Beverage, Serving, default_beverages, to_serving
from .fatigue import SleepEpisode
from .metrics import CapStatus, Coverage, cap_status, sleep_debt_h, window_coverage
from .optimizer import Plan, Window, optimize
from .pk import Dose
from .profile import PersonalParams, Profile, personal_params
from .timeutil import h_to_hhmm


@dataclass
class DayResult:
    personal: PersonalParams
    plan: Optional[Plan]
    servings: List[Serving] = field(default_factory=list)
    cap: Optional[CapStatus] = None
    coverage: List[Coverage] = field(default_factory=list)
    sleep_debt_h: float = 0.0
    notes: List[str] = field(default_factory=list)


def run_day(profile: Profile, sleeps: Sequence[SleepEpisode], windows: Sequence[Window], bed_h: float,
            now_h: float, already: Sequence[Dose] = (), beverage: Optional[Beverage] = None,
            sip_ml: Optional[float] = None) -> DayResult:
    personal = personal_params(profile)
    beverage = beverage or default_beverages()["coffee"]
    notes = list(personal.notes)
    debt = sleep_debt_h(sleeps)

    if personal.blocked:
        return DayResult(personal, None, sleep_debt_h=debt, notes=notes)

    plan = optimize(sleeps, windows, bed_h=bed_h, now_h=now_h, already=already,
                    daily_cap_mg=personal.daily_cap_mg, single_cap_mg=personal.single_cap_mg,
                    residual_limit_mg=personal.residual_limit_mg, half_life_h=personal.half_life_h,
                    chronotype=personal.chronotype)
    notes += plan.warnings
    if debt >= params.value("metrics", "sleep_need_h"):
        notes.append(f"최근 1주 수면 부채 {debt:.1f}시간 — 1주 이상 이어진 수면 부족은 모델이 실제보다 가볍게"
                     " 볼 수 있어요 (Van Dongen 2003)")
    return DayResult(
        personal=personal,
        plan=plan,
        servings=[to_serving(d.mg, beverage, sip_ml, d.duration_h) for d in plan.new_doses],
        cap=cap_status(plan.all_doses, personal.daily_cap_mg),
        coverage=window_coverage(sleeps, windows, plan.all_doses, personal.chronotype),
        sleep_debt_h=debt,
        notes=notes,
    )


_KIND_LABEL = {"stay_awake": "깨어 있기", "must_not_sleep": "졸면 안 됨", "focus": "집중"}
_CAP_LABEL = {"ok": "", "warning": " 상한 80% 이상", "over": " 상한 초과"}


def format_card(result: DayResult) -> str:
    """앱 홈 화면에 보여줄 요약 카드 (텍스트)."""
    lines = ["오늘의 카페인 플랜", ""]
    plan = result.plan
    if plan is None:
        lines.append("플랜을 만들지 않았어요.")
    else:
        already = [d for d in plan.all_doses if d not in plan.new_doses]
        if already:
            lines.append("  이미 마심: " + ", ".join(f"{h_to_hhmm(d.time_h)} {d.mg:.0f}mg" for d in already))
        if result.servings:
            for d, s in zip(plan.new_doses, result.servings):
                lines.append(f"  {h_to_hhmm(d.time_h)}~{h_to_hhmm(d.end_h)}  {s.beverage.name} {s.cup}"
                             f" (약 {s.ml:.0f}ml · {s.mg_actual:.0f}mg) · {s.minutes}분 동안 나눠서, {s.pace}")
        else:
            lines.append("  오늘은 더 마시지 않는 게 좋아요")
        if plan.last_dose_h is not None:
            lines.append(f"  {h_to_hhmm(plan.last_dose_h)} 이후엔 플랜 외 카페인 금지")
        if plan.cutoff_h is not None:
            lines.append(f"  {h_to_hhmm(plan.cutoff_h)}부터는 한 모금도 금지 (수면 보호)")
        lines += [
            "",
            f"오늘 총 {result.cap.total_mg:.0f}mg / 상한 {result.cap.cap_mg:.0f}mg"
            f" ({result.cap.ratio * 100:.0f}%){_CAP_LABEL[result.cap.level]}",
            # 소수점 한 자리: 19.8을 '20 (기준 20)'으로 반올림하면 기준을 넘은 것처럼 보임
            f"잠든 뒤 몸속 카페인 최대 {plan.max_residual_mg:.1f}mg (기준 {result.personal.residual_limit_mg:.0f})"
            f" · 예상 수면 감소 {max(plan.sleep_loss_min, 0):.1f}분 (기준 20)",
            f"목표 구간 졸림 {plan.sleepiness_reduction * 100:.0f}% 감소",
        ]
        for c in result.coverage:
            if c.kind == "focus":
                continue
            lines.append(f"  {_KIND_LABEL[c.kind]} {h_to_hhmm(c.start_h)}–{h_to_hhmm(c.end_h)}:"
                         f" 위험선 위 {c.without_caffeine * 100:.0f}% → {c.with_caffeine * 100:.0f}%")
    lines.append(f"최근 1주 수면 부채 {result.sleep_debt_h:.1f}시간")
    if result.notes:
        lines.append("")
        lines += [f"{n}" for n in result.notes]
    lines += ["", "※ 의학적 조언이 아니에요. 평균적인 성인 기준 예측입니다."]
    return "\n".join(lines)
