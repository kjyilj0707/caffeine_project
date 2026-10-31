"""하루 그래프 공통 부분: 위 = 각성 점수(카페인 없을 때 / 반영), 아래 = 몸속 카페인.

색은 dataviz 기준 팔레트 (계열 1 파랑, 계열 2 주황, 글자·기준선은 텍스트 색).
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
from caffeine_engine.fatigue import alertness_curve, first_time_below
from caffeine_engine.pk import amount_at, curve
from caffeine_engine.timeutil import h_to_hhmm

SURFACE = "#fcfcfb"
SERIES_ALERT = "#2a78d6"
SERIES_CAFFEINE = "#eb6834"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
WINDOW_FILL = "#f1f0ec"

plt.rcParams.update({"font.family": "AppleGothic", "axes.unicode_minus": False, "font.size": 10})


def _style(ax, ylabel, highlight, bed):
    ax.set_facecolor(SURFACE)
    if highlight:
        ax.axvspan(*highlight, color=WINDOW_FILL, zorder=0)
    ax.axvline(bed, color=TEXT_SECONDARY, linewidth=1, zorder=1)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def render(out_name, sleeps, doses, bed, start, highlight=None, highlight_label="",
           title="", cutoff=None, planned=()):
    """그래프를 figures/out_name으로 저장하고, 계산한 값들을 돌려준다.

    planned: 엔진이 추천한 잔 (아래 그래프에 '추천'으로 표시)
    cutoff: 절대 컷오프 시각 (세로 점선)
    """
    end = bed + 1
    danger = params.value("fatigue", "danger_threshold")
    focus_target = params.value("targets", "peak_focus")
    residual_limit = params.value("sleep_protection", "bedtime_residual_mg")

    alert = alertness_curve(sleeps, start, end)
    alert_caf = curve_with_caffeine(alert, doses)
    crossing = first_time_below([p for p in alert if p.t < bed])  # 잠든 뒤는 보지 않음
    caffeine = curve(doses, start, end)
    residual = amount_at(bed, doses)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6.6), dpi=160, sharex=True,
                                   gridspec_kw={"height_ratios": [1.1, 1], "hspace": 0.34})
    fig.patch.set_facecolor(SURFACE)
    if title:
        fig.suptitle(title, x=0.075, ha="left", color=TEXT_PRIMARY, fontsize=12.5, y=0.985)

    # ── 위: 각성 점수 ──
    _style(ax1, "각성 점수 (1–21)", highlight, bed)
    ts = [p.t for p in alert]
    ax1.plot(ts, [p.score for p in alert], color=TEXT_SECONDARY, linewidth=1.2,
             linestyle=(0, (2, 2)), zorder=2, label="카페인 없을 때")
    ax1.plot(ts, alert_caf, color=SERIES_ALERT, linewidth=2, zorder=3, label="카페인 반영")
    ax1.legend(loc="lower center", frameon=False, fontsize=9, labelcolor=TEXT_PRIMARY,
               bbox_to_anchor=(0.36, 0.0), ncol=2)
    ax1.axhline(danger, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax1.text(start + (end - start) * 0.52, danger - 1.1, f"졸음 위험선 {danger}",
             color=TEXT_SECONDARY, fontsize=9)
    if highlight:
        ax1.hlines(focus_target, *highlight, color=TEXT_SECONDARY, linewidth=1,
                   linestyle=(0, (1, 2)), zorder=1)
        ax1.text(highlight[1] + 0.15, focus_target - 0.3, f"참고선 {focus_target}",
                 color=TEXT_SECONDARY, fontsize=9)
        ax1.text(sum(highlight) / 2, 15.6, highlight_label, ha="center", color=TEXT_SECONDARY, fontsize=9)
    ax1.text(bed - 0.1, 15.6, f"취침 {h_to_hhmm(bed)}", ha="right", color=TEXT_SECONDARY, fontsize=9)
    ax1.annotate("기상 직후 멍함", xy=(start, alert[0].score), xytext=(start + 0.6, 4.2),
                 color=TEXT_SECONDARY, fontsize=9,
                 arrowprops=dict(arrowstyle="-", color=TEXT_SECONDARY, linewidth=0.8))
    if crossing is not None:
        crossing_score = next(p.score for p in alert if p.t == crossing)
        ax1.plot(crossing, crossing_score, marker="o", markersize=8, color=TEXT_SECONDARY,
                 markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)
        ax1.annotate(f"{h_to_hhmm(crossing)} 위험선 아래로", xy=(crossing, crossing_score),
                     xytext=(crossing - 0.4, crossing_score - 2.6), ha="right",
                     color=TEXT_PRIMARY, fontsize=9)
    ax1.set_ylim(2, 16.5)
    ax1.set_title("각성 점수 — 수면 기록 + 카페인 효과", loc="left", color=TEXT_PRIMARY,
                  fontsize=11, pad=10)

    # ── 아래: 몸속 카페인 ──
    _style(ax2, "몸속 카페인 (mg)", highlight, bed)
    ax2.plot([t for t, _ in caffeine], [mg for _, mg in caffeine], color=SERIES_CAFFEINE,
             linewidth=2, zorder=3)
    ax2.axhline(residual_limit, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax2.text(start + (end - start) * 0.52, residual_limit - 11, f"취침 허용 잔량 {residual_limit}mg",
             color=TEXT_SECONDARY, fontsize=9)
    for d in doses:
        tag = " 추천" if d in planned else ""
        ax2.plot(d.time_h, 0, marker="v", markersize=8, color=SERIES_CAFFEINE, zorder=4, clip_on=False)
        ax2.text(d.time_h, -26, f"{h_to_hhmm(d.time_h)} {d.mg:.0f}mg{tag}", ha="center",
                 color=TEXT_PRIMARY, fontsize=9, fontweight="bold" if tag else "normal")
    if cutoff is not None:
        for ax in (ax1, ax2):
            ax.axvline(cutoff, color=TEXT_SECONDARY, linewidth=1, linestyle=(0, (1, 2)), zorder=1)
        ax2.text(cutoff - 0.12, 112, f"{h_to_hhmm(cutoff)}부터\n카페인 금지", ha="right",
                 color=TEXT_PRIMARY, fontsize=9)
    ax2.plot(bed, residual, marker="o", markersize=8, color=SERIES_CAFFEINE, markeredgecolor=SURFACE,
             markeredgewidth=2, zorder=5)
    ax2.annotate(f"취침 때 {residual:.1f}mg", xy=(bed, residual), xytext=(bed + 0.15, residual - 22),
                 ha="left", color=TEXT_PRIMARY, fontsize=9)
    ax2.set_ylim(-34, 135)
    ax2.set_yticks([0, 40, 80, 120])
    half_life = params.value("pk", "half_life_h")
    ax2.set_title(f"몸속 카페인 (반감기 {half_life:g}시간)", loc="left", color=TEXT_PRIMARY,
                  fontsize=11, pad=10)

    ticks = list(range(int(start) + int(start) % 2, int(end) + 1, 2))
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([h_to_hhmm(t) for t in ticks], color=TEXT_SECONDARY)
    ax2.set_xlim(start, end)

    out = ROOT / "figures" / out_name
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return {"out": out, "alert": alert, "alert_caf": alert_caf, "crossing": crossing, "residual": residual}
