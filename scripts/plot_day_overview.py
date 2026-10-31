"""확인용 그래프: 예시 하루의 각성 점수(② + 카페인 효과)와 몸속 카페인(③)을 위아래로.

실행: .venv/bin/python scripts/plot_day_overview.py
결과: figures/step1-3_day_overview.png
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from caffeine_engine import params
from caffeine_engine.effect import curve_with_caffeine
from caffeine_engine.fatigue import SleepEpisode, alertness_curve, first_time_below
from caffeine_engine.pk import Dose, amount_at, curve
from caffeine_engine.timeutil import h_to_hhmm, hhmm_to_h

SURFACE = "#fcfcfb"
SERIES_ALERT = "#2a78d6"     # categorical slot 1
SERIES_CAFFEINE = "#eb6834"  # categorical slot 2
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
WINDOW_FILL = "#f1f0ec"

plt.rcParams.update({"font.family": "AppleGothic", "axes.unicode_minus": False, "font.size": 10})

# 예시 하루: 최근 3일 수면 기록, 오늘 08:00 기상(6.5시간 수면)
sleeps = [
    SleepEpisode(hhmm_to_h("00:30") - 48, hhmm_to_h("07:30") - 48),
    SleepEpisode(hhmm_to_h("01:00") - 24, hhmm_to_h("07:00") - 24),
    SleepEpisode(hhmm_to_h("01:30"), hhmm_to_h("08:00")),
]
doses = [Dose(hhmm_to_h("09:00"), 100), Dose(hhmm_to_h("13:15"), 75)]
bed = hhmm_to_h("01:00", next_day=True)
exam = (hhmm_to_h("14:00"), hhmm_to_h("17:00"))
start, end = hhmm_to_h("08:00"), bed + 1

danger = params.value("fatigue", "danger_threshold")
focus_target = params.value("targets", "peak_focus")
residual_limit = params.value("sleep_protection", "bedtime_residual_mg")

alert = alertness_curve(sleeps, start, end)
alert_caf = curve_with_caffeine(alert, doses)
crossing = first_time_below(alert)
caffeine = curve(doses, start, end)
residual = amount_at(bed, doses)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6.4), dpi=160, sharex=True,
                               gridspec_kw={"height_ratios": [1.1, 1], "hspace": 0.32})
fig.patch.set_facecolor(SURFACE)


def style(ax, ylabel):
    ax.set_facecolor(SURFACE)
    ax.axvspan(*exam, color=WINDOW_FILL, zorder=0)
    ax.axvline(bed, color=TEXT_SECONDARY, linewidth=1, zorder=1)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


# ── 위: 각성 점수 ─────────────────────────────
style(ax1, "각성 점수 (1–21)")
ts = [p.t for p in alert]
ax1.plot(ts, [p.score for p in alert], color=TEXT_SECONDARY, linewidth=1.2,
         linestyle=(0, (2, 2)), zorder=2, label="카페인 없을 때")
ax1.plot(ts, alert_caf, color=SERIES_ALERT, linewidth=2, zorder=3, label="카페인 반영")
ax1.legend(loc="lower center", frameon=False, fontsize=9, labelcolor=TEXT_PRIMARY,
           bbox_to_anchor=(0.36, 0.0), ncol=2)
ax1.axhline(danger, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
ax1.text(17.3, danger - 1.1, f"졸음 위험선 {danger}", color=TEXT_SECONDARY, fontsize=9)
ax1.hlines(focus_target, *exam, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (1, 2)), zorder=1)
ax1.text(exam[1] + 0.15, focus_target - 0.3, f"시험 목표 {focus_target}", color=TEXT_SECONDARY, fontsize=9)
ax1.text(sum(exam) / 2, 15.6, "시험 14:00–17:00", ha="center", color=TEXT_SECONDARY, fontsize=9)
ax1.text(bed - 0.1, 15.6, "취침 01:00", ha="right", color=TEXT_SECONDARY, fontsize=9)
ax1.annotate("기상 직후 멍함", xy=(start, alert[0].score), xytext=(start + 0.6, 4.2),
             color=TEXT_SECONDARY, fontsize=9,
             arrowprops=dict(arrowstyle="-", color=TEXT_SECONDARY, linewidth=0.8))
if crossing is not None:
    crossing_score = next(p.score for p in alert if p.t == crossing)
    ax1.plot(crossing, crossing_score, marker="o", markersize=8, color=SERIES_ALERT,
             markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)
    ax1.annotate(f"{h_to_hhmm(crossing)} 위험선 아래로 (카페인 있어도 15분 차이)",
                 xy=(crossing, crossing_score),
                 xytext=(crossing - 0.4, crossing_score - 2.6), ha="right",
                 color=TEXT_PRIMARY, fontsize=9)
ax1.set_ylim(2, 16.5)
ax1.set_title("각성 점수 — 수면 기록 + 카페인 효과 (반응 속도 기준)", loc="left",
              color=TEXT_PRIMARY, fontsize=11, pad=10)

# ── 아래: 몸속 카페인 ─────────────────────────
style(ax2, "몸속 카페인 (mg)")
ax2.plot([t for t, _ in caffeine], [mg for _, mg in caffeine], color=SERIES_CAFFEINE,
         linewidth=2, zorder=3)
ax2.axhline(residual_limit, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
ax2.text(17.3, residual_limit - 11, f"취침 허용 잔량 {residual_limit}mg", color=TEXT_SECONDARY, fontsize=9)
for d in doses:
    ax2.plot(d.time_h, 0, marker="v", markersize=8, color=SERIES_CAFFEINE, zorder=4, clip_on=False)
    ax2.text(d.time_h, -24, f"{h_to_hhmm(d.time_h)} {d.mg:.0f}mg", ha="center",
             color=TEXT_PRIMARY, fontsize=9)
ax2.plot(bed, residual, marker="o", markersize=8, color=SERIES_CAFFEINE, markeredgecolor=SURFACE,
         markeredgewidth=2, zorder=5)
ax2.annotate(f"취침 때 {residual:.1f}mg", xy=(bed, residual), xytext=(bed - 0.3, residual + 24),
             ha="right", color=TEXT_PRIMARY, fontsize=9)
ax2.set_ylim(-32, 135)
ax2.set_yticks([0, 40, 80, 120])
ax2.set_title("몸속 카페인 (반감기 5시간)", loc="left", color=TEXT_PRIMARY, fontsize=11, pad=10)

ticks = list(range(8, int(bed) + 2, 2))
ax2.set_xticks(ticks)
ax2.set_xticklabels([h_to_hhmm(t) for t in ticks], color=TEXT_SECONDARY)
ax2.set_xlim(start, end)

out = ROOT / "figures" / "step1-3_day_overview.png"
fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
print(f"저장: {out}")
in_exam = [i for i, p in enumerate(alert) if exam[0] <= p.t <= exam[1]]
before = [alert[i].score for i in in_exam]
after = [alert_caf[i] for i in in_exam]
print(f"시험 중 각성 점수: 카페인 없이 {min(before):.1f}~{max(before):.1f} → 반영 {min(after):.1f}~{max(after):.1f} (목표 {focus_target})")
print(f"위험선 아래로 (카페인 없이): {h_to_hhmm(crossing) if crossing else '없음'}")
caf_cross = next((p.t for p, s in zip(alert, alert_caf) if not p.asleep and s + p.w < danger), None)
print(f"위험선 아래로 (카페인 반영): {h_to_hhmm(caf_cross) if caf_cross else '없음'}")
print(f"취침 때 몸속 카페인: {residual:.1f}mg")
