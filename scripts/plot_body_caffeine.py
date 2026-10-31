"""Step 1-1 확인용 그래프: 설계서 예시 하루의 체내 카페인 곡선.

실행: .venv/bin/python scripts/plot_body_caffeine.py
결과: figures/step1-1_body_caffeine.png
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from caffeine_engine import params
from caffeine_engine.pk import Dose, amount_at, curve
from caffeine_engine.timeutil import h_to_hhmm, hhmm_to_h

# 색: dataviz 기준 팔레트 (단일 계열 → series-1 파랑, 글자·기준선은 텍스트 색)
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
WINDOW_FILL = "#f1f0ec"

plt.rcParams.update({
    "font.family": "AppleGothic",
    "axes.unicode_minus": False,
    "font.size": 10,
})

# 설계서 예시 하루
doses = [Dose(hhmm_to_h("09:00"), 100), Dose(hhmm_to_h("13:15"), 75)]
bed = hhmm_to_h("01:00", next_day=True)
exam = (hhmm_to_h("14:00"), hhmm_to_h("17:00"))
limit = params.value("sleep_protection", "bedtime_residual_mg")

points = curve(doses, start_h=7.0, end_h=bed + 1)
xs = [t for t, _ in points]
ys = [mg for _, mg in points]
residual = amount_at(bed, doses)

fig, ax = plt.subplots(figsize=(9, 4.2), dpi=160)
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)

ax.axvspan(*exam, color=WINDOW_FILL, zorder=0)
ax.text(sum(exam) / 2, max(ys) * 1.12, "시험 14:00–17:00", ha="center",
        color=TEXT_SECONDARY, fontsize=9)

ax.axhline(limit, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
ax.text(17.3, limit - 9, f"취침 허용 잔량 {limit}mg", color=TEXT_SECONDARY, fontsize=9)

ax.axvline(bed, color=TEXT_SECONDARY, linewidth=1, zorder=1)
ax.text(bed - 0.1, max(ys) * 1.12, "취침 01:00", ha="right", color=TEXT_SECONDARY, fontsize=9)

ax.plot(xs, ys, color=SERIES, linewidth=2, zorder=3)

for d in doses:
    ax.annotate(f"{h_to_hhmm(d.time_h)} {d.mg:.0f}mg", xy=(d.time_h, 0), xytext=(d.time_h, -22),
                ha="center", color=TEXT_PRIMARY, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=TEXT_SECONDARY, linewidth=0.8))
    ax.plot(d.time_h, 0, marker="v", markersize=8, color=SERIES, zorder=4, clip_on=False)

ax.plot(bed, residual, marker="o", markersize=8, color=SERIES, markeredgecolor=SURFACE,
        markeredgewidth=2, zorder=5)
ax.annotate(f"취침 때 {residual:.1f}mg", xy=(bed, residual), xytext=(bed - 0.3, residual + 22),
            ha="right", color=TEXT_PRIMARY, fontsize=9)

ticks = list(range(8, int(bed) + 2, 2))
ax.set_xticks(ticks)
ax.set_xticklabels([h_to_hhmm(t) for t in ticks], color=TEXT_SECONDARY)
ax.set_xlim(7, bed + 1)
ax.set_ylim(-30, max(ys) * 1.22)
ax.set_ylabel("몸속 카페인 (mg)", color=TEXT_SECONDARY)
ax.tick_params(colors=TEXT_SECONDARY, length=0)
ax.grid(axis="y", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.set_yticks([t for t in ax.get_yticks() if t >= 0])

half_life = params.value("pk", "half_life_h")
ax.set_title(f"몸속 카페인 — 예시 하루 (반감기 {half_life:g}시간)", loc="left",
             color=TEXT_PRIMARY, fontsize=12, pad=14)

out = ROOT / "figures" / "step1-1_body_caffeine.png"
out.parent.mkdir(exist_ok=True)
fig.tight_layout()
fig.savefig(out, facecolor=SURFACE)
print(f"저장: {out}")
print(f"취침 01:00 몸속 카페인: {residual:.1f}mg (기준 {limit}mg)")
