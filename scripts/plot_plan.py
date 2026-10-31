"""Step 1-4 확인용: 최적화 엔진이 추천한 플랜을 그래프로.

실행: .venv/bin/python scripts/plot_plan.py
결과: figures/step1-4_plan_bed23.png (23시 취침), figures/step1-4_plan_bed01.png (01시 취침)
"""
from daychart import render

from caffeine_engine.fatigue import SleepEpisode
from caffeine_engine.optimizer import Window, optimize
from caffeine_engine.timeutil import h_to_hhmm, hhmm_to_h

sleeps = [  # 최근 3일 6~7시간 수면, 오늘 08:00 기상
    SleepEpisode(hhmm_to_h("00:30") - 48, hhmm_to_h("07:30") - 48),
    SleepEpisode(hhmm_to_h("01:00") - 24, hhmm_to_h("07:00") - 24),
    SleepEpisode(hhmm_to_h("01:30"), hhmm_to_h("08:00")),
]
wake = hhmm_to_h("08:00")
exam = (hhmm_to_h("14:00"), hhmm_to_h("17:00"))

for name, bed in [("bed23", hhmm_to_h("23:00")), ("bed01", hhmm_to_h("01:00", next_day=True))]:
    windows = [Window(wake, bed, "stay_awake"), Window(*exam, "must_not_sleep"),
               Window(hhmm_to_h("15:00"), hhmm_to_h("16:00"), "focus")]
    plan = optimize(sleeps, windows, bed_h=bed, now_h=wake)
    r = render(f"step1-4_plan_{name}.png", sleeps, plan.all_doses, bed, start=wake,
               highlight=exam, highlight_label="시험 14:00–17:00 (집중 15–16시)",
               title=f"엔진 추천 플랜 — {h_to_hhmm(bed)} 취침", cutoff=plan.cutoff_h,
               planned=plan.new_doses)
    print(f"\n[{h_to_hhmm(bed)} 취침] 저장: {r['out']}")
    print("  추천:", ", ".join(f"{h_to_hhmm(d.time_h)} {d.mg:g}mg" for d in plan.new_doses) or "없음")
    print(f"  잠든 뒤 최대 잔량 {plan.max_residual_mg:.1f}mg · 예상 수면 감소 {plan.sleep_loss_min:.1f}분"
          f" · 절대 컷오프 {h_to_hhmm(plan.cutoff_h) if plan.cutoff_h else '없음'}")
    print(f"  목표 구간 졸림 {plan.sleepiness_reduction * 100:.1f}% 감소 · 위험 시간"
          f" {plan.danger_hours_without:g}h → {plan.danger_hours:g}h")
    for w in plan.warnings:
        print("  ⚠️", w)
