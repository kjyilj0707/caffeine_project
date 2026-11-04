"""리포트 카드 그리기 — Apple 피트니스 '요약'처럼 둥근 카드 + 큰 색 숫자 + 작은 막대그래프 (HTML 문자열).

화면(page_report.py)은 숫자만 계산해 넘기고, 모양은 여기서 정한다. 그래프는 SVG라 브라우저 속 Python(stlite)에서도 그대로 나온다.
"""
from html import escape
from typing import List, Optional, Sequence

# 지표별 색 (카페인은 타이머와 같은 초록)
CAFFEINE, SLEEP, KSS, PLAN, CUTOFF, LATENCY, OVER = (
    "#34C759", "#7D7AFF", "#FF9F0A", "#0A84FF", "#30B0C7", "#64D2FF", "#FF3B30")


def css(dark: bool) -> str:
    card, fg, muted, grid = (("#1c1c1e", "#fafafa", "#8e8e93", "rgba(255,255,255,.08)") if dark else
                             ("#f2f2f7", "#111111", "#8a8a8f", "rgba(0,0,0,.07)"))
    return f"""<style>
.rc-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 4px 0 8px; }}
.rc-card {{ background: {card}; border-radius: 22px; padding: 16px 16px 14px; color: {fg}; min-width: 0;
           display: flex; flex-direction: column; }}
.rc-wide {{ grid-column: 1 / -1; }}
.rc-h {{ font-size: 19px; font-weight: 700; line-height: 1.2; }}
.rc-sub {{ font-size: 14px; color: {fg}; margin-top: 10px; }}
.rc-big {{ font-size: 34px; font-weight: 700; line-height: 1.1; letter-spacing: -.5px; white-space: nowrap;
          font-variant-numeric: tabular-nums; }}
.rc-unit {{ font-size: 18px; font-weight: 700; margin-left: 2px; }}
.rc-foot {{ font-size: 13px; color: {muted}; margin-top: 6px; line-height: 1.35; }}
.rc-empty {{ flex: 1; display: flex; align-items: center; justify-content: center; text-align: center;
            color: {muted}; font-size: 15px; min-height: 90px; }}
.rc-chart {{ margin-top: 10px; }}
.rc-plot {{ position: relative; height: 64px; display: flex; align-items: flex-end; gap: 2px;
           border-bottom: 1px solid {grid}; }}
.rc-col {{ flex: 1 1 0; height: 100%; display: flex; align-items: flex-end; justify-content: center; }}
.rc-bar {{ width: min(60%, 8px); border-radius: 3px; }}
.rc-none {{ height: 3px; opacity: .25; }}
.rc-cap {{ position: absolute; left: 0; right: 0; border-top: 1.5px dashed {OVER}; opacity: .7; }}
.rc-axis {{ display: flex; justify-content: space-between; font-size: 11px; color: {muted}; margin-top: 4px; }}
.rc-ring {{ display: flex; align-items: center; gap: 18px; }}
.rc-donut {{ width: 128px; height: 128px; border-radius: 50%; flex: none; display: flex; align-items: center;
            justify-content: center; }}
.rc-hole {{ width: 84px; height: 84px; border-radius: 50%; background: {card}; }}
.rc-ring .rc-big {{ font-size: 30px; }}
.rc-row {{ display: flex; justify-content: space-between; gap: 8px; font-size: 15px; padding: 9px 0;
          border-top: 1px solid {grid}; }}
.rc-row:first-of-type {{ border-top: 0; }}
.rc-row .m {{ color: {muted}; }}
.rc-msg {{ font-size: 15px; line-height: 1.45; margin-top: 8px; }}
.rc-gauge {{ position: relative; height: 18px; margin-top: 12px; }}
.rc-gauge-bar {{ position: absolute; left: 0; right: 0; top: 6px; height: 6px; border-radius: 3px;
                background: linear-gradient(90deg, #34C759, #FFCC00 50%, #FF3B30); }}
.rc-gauge-mark {{ position: absolute; top: 0; width: 18px; height: 18px; margin-left: -9px; border-radius: 50%;
                 background: {card}; border: 4px solid; box-sizing: border-box; }}
</style>"""


def _big(value: str, unit: str, color: str) -> str:
    unit_html = f"<span class='rc-unit'>{escape(unit)}</span>" if unit else ""
    return f"<div class='rc-big' style='color:{color}'>{escape(value)}{unit_html}</div>"


def bars(values: Sequence[Optional[float]], color: str, axis: Sequence[str] = (), cap: Optional[float] = None,
         color_of=None, top: Optional[float] = None) -> str:
    """작은 막대그래프 (div). None·0 = 기록 없음(바닥에 옅은 점). cap이 있으면 점선 + 넘은 막대는 빨강.
    st.html이 SVG를 지우므로 일반 상자로 그린다."""
    top = top or max([v for v in values if v] + [cap or 0, 1e-9])
    cols = []
    for v in values:
        if v:
            fill = OVER if cap and v > cap else (color_of(v) if color_of else color)
            cols.append(f"<div class='rc-col'><div class='rc-bar' style='height:{max(4, v / top * 100):.0f}%;background:{fill}'></div></div>")
        else:
            cols.append(f"<div class='rc-col'><div class='rc-bar rc-none' style='background:{color}'></div></div>")
    line = f"<div class='rc-cap' style='bottom:{cap / top * 100:.0f}%'></div>" if cap else ""
    labels = "".join(f"<span>{escape(a)}</span>" for a in axis)
    return f"<div class='rc-chart'><div class='rc-plot'>{''.join(cols)}{line}</div><div class='rc-axis'>{labels}</div></div>"


def ring_card(title: str, label: str, value: float, cap: float, unit: str, color: str, foot: str = "") -> str:
    """맨 위 큰 카드: 두꺼운 링(상한 대비) + 오른쪽 '라벨 / 값/상한'."""
    ratio = value / cap if cap else 0
    c = OVER if ratio > 1 else color
    deg = min(ratio, 1) * 360
    ring = (f"<div class='rc-donut' style='background:conic-gradient({c} {deg:.0f}deg, {c}2e {deg:.0f}deg)'>"
            f"<div class='rc-hole'></div></div>")
    text = (f"<div><div style='font-size:15px'>{escape(label)}</div>"
            f"<div class='rc-big' style='color:{c}'>{value:.0f}/{cap:.0f}<span class='rc-unit'>{escape(unit)}</span></div>"
            + (f"<div class='rc-foot'>{escape(foot)}</div>" if foot else "") + "</div>")
    return f"<div class='rc-card rc-wide'><div class='rc-h'>{escape(title)}</div><div class='rc-ring'>{ring}{text}</div></div>"


def stat_card(title: str, sub: str, value: Optional[str], unit: str, color: str, chart: str = "",
              foot: str = "", empty: str = "기록이 없어요", wide: bool = False) -> str:
    cls = "rc-card rc-wide" if wide else "rc-card"
    if value is None:
        return f"<div class='{cls}'><div class='rc-h'>{escape(title)}</div><div class='rc-empty'>{escape(empty)}</div></div>"
    return (f"<div class='{cls}'><div class='rc-h'>{escape(title)}</div><div class='rc-sub'>{escape(sub)}</div>"
            + _big(value, unit, color) + chart + (f"<div class='rc-foot'>{escape(foot)}</div>" if foot else "") + "</div>")


def list_card(title: str, rows: List[tuple], empty: str = "기록이 없어요", msg: str = "") -> str:
    """넓은 카드: [(왼쪽, 오른쪽), ...] 줄 목록 + 아래 설명."""
    body = ("".join(f"<div class='rc-row'><span>{escape(a)}</span><span class='m'>{escape(b)}</span></div>"
                    for a, b in rows) if rows else f"<div class='rc-empty'>{escape(empty)}</div>" if empty else "")
    extra = f"<div class='rc-msg'>{msg}</div>" if msg else ""
    return f"<div class='rc-card rc-wide'><div class='rc-h'>{escape(title)}</div>{body}{extra}</div>"


def grid(cards: List[str]) -> str:
    return "<div class='rc-grid'>" + "".join(cards) + "</div>"


def hm(hours: Optional[float]) -> Optional[str]:
    """6.5 → '6시간 30분'"""
    if hours is None:
        return None
    m = round(hours * 60)
    return f"{m // 60}시간 {m % 60}분" if m % 60 else f"{m // 60}시간"


# ── 졸림 (KSS 1~9): 초록(또렷) → 노랑(보통) → 빨강(졸림) ──
_KSS_STOPS = [(1, (52, 199, 89)), (5, (255, 204, 0)), (9, (255, 59, 48))]
KSS_WORDS = [(2.5, "매우 또렷"), (4.5, "또렷"), (6.0, "보통"), (7.5, "졸림"), (9.1, "매우 졸림")]


def kss_color(v: float) -> str:
    v = max(1.0, min(9.0, v))
    (a, ca), (b, cb) = (_KSS_STOPS[0], _KSS_STOPS[1]) if v <= 5 else (_KSS_STOPS[1], _KSS_STOPS[2])
    t = (v - a) / (b - a)
    r, g, bl = (round(x + (y - x) * t) for x, y in zip(ca, cb))
    return f"#{r:02x}{g:02x}{bl:02x}"


def kss_word(v: float) -> str:
    return next(w for limit, w in KSS_WORDS if v < limit)


def kss_card(title: str, sub: str, mean: Optional[float], per_day: Sequence[Optional[float]] = (),
             axis: Sequence[str] = (), foot: str = "") -> str:
    """졸림 카드: 큰 숫자(색 = 졸림 정도) + 말 + 1~9 색 막대 위 평균 표시 + (기간이면) 날짜별 색 막대."""
    if mean is None:
        return stat_card(title, sub, None, "", KSS)
    c = kss_color(mean)
    pos = (mean - 1) / 8 * 100
    gauge = (f"<div class='rc-gauge'><div class='rc-gauge-bar'></div>"
             f"<div class='rc-gauge-mark' style='left:{pos:.0f}%;border-color:{c}'></div></div>"
             f"<div class='rc-axis'><span>1 또렷</span><span>5</span><span>9 졸림</span></div>")
    chart = bars(per_day, KSS, axis, color_of=kss_color, top=9) if per_day else ""
    return (f"<div class='rc-card'><div class='rc-h'>{escape(title)}</div><div class='rc-sub'>{escape(sub)}</div>"
            f"<div class='rc-big' style='color:{c}'>{mean:.1f}<span class='rc-unit'>{escape(kss_word(mean))}</span></div>"
            + gauge + chart + (f"<div class='rc-foot'>{escape(foot)}</div>" if foot else "") + "</div>")
