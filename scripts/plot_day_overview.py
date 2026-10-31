"""확인용 그래프: 설계서 예시 하루 (정해진 섭취)의 각성 점수와 몸속 카페인.

실행: .venv/bin/python scripts/plot_day_overview.py
결과: figures/step1-3_day_overview.png
"""
from daychart import render

from caffeine_engine.fatigue import SleepEpisode
from caffeine_engine.pk import Dose
from caffeine_engine.timeutil import h_to_hhmm, hhmm_to_h

sleeps = [  # 최근 3일 수면, 오늘 08:00 기상 (6.5시간)
    SleepEpisode(hhmm_to_h("00:30") - 48, hhmm_to_h("07:30") - 48),
    SleepEpisode(hhmm_to_h("01:00") - 24, hhmm_to_h("07:00") - 24),
    SleepEpisode(hhmm_to_h("01:30"), hhmm_to_h("08:00")),
]
doses = [Dose(hhmm_to_h("09:00"), 100), Dose(hhmm_to_h("13:15"), 75)]
exam = (hhmm_to_h("14:00"), hhmm_to_h("17:00"))
bed = hhmm_to_h("01:00", next_day=True)

r = render("step1-3_day_overview.png", sleeps, doses, bed, start=hhmm_to_h("08:00"),
           highlight=exam, highlight_label="시험 14:00–17:00")
in_exam = [i for i, p in enumerate(r["alert"]) if exam[0] <= p.t <= exam[1]]
before = [r["alert"][i].score for i in in_exam]
after = [r["alert_caf"][i] for i in in_exam]
print(f"저장: {r['out']}")
print(f"시험 중 각성 점수: 카페인 없이 {min(before):.1f}~{max(before):.1f} → 반영 {min(after):.1f}~{max(after):.1f}")
print(f"위험선 아래로 (카페인 없이): {h_to_hhmm(r['crossing']) if r['crossing'] else '없음'}")
print(f"취침 때 몸속 카페인: {r['residual']:.1f}mg")
