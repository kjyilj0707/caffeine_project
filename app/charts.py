"""입력 화면용 인터랙티브 그래프 (Altair).

위: 각성 점수 (카페인 없을 때 / 반영)   아래: 몸속 카페인
두 그래프는 같은 시간 범위를 쓰고, 위 그래프에 마우스를 올리면 그 시각의 두 값을 함께 보여준다.
색: dataviz 기준 팔레트 — 계열 1 파랑(각성), 계열 2 주황(카페인), 기준선은 회색.
"""
from typing import Dict, Tuple

import altair as alt
import pandas as pd

from caffeine_engine import params
from caffeine_engine.effect import curve_with_caffeine
from caffeine_engine.fatigue import alertness_curve
from caffeine_engine.pk import amount_at
from caffeine_engine.timeutil import h_to_hhmm

BLUE, ORANGE, GRAY, FILL = "#2a78d6", "#eb6834", "#8a8984", "#e4e3df"
KIND_NAME = {"stay_awake": "깨어 있기", "must_not_sleep": "졸면 안 됨", "focus": "집중"}
# x축 숫자(그날 0시부터 시간) → 'HH:MM'
HHMM = "format(floor(datum.value) % 24, '02d') + ':' + format(round((datum.value % 1) * 60), '02d')"


def build_frames(sc, result) -> Dict[str, pd.DataFrame]:
    """그래프에 쓸 표들. 테스트에서 값 확인용으로도 쓴다."""
    personal = result.personal
    plan = result.plan
    doses = plan.all_doses if plan else list(sc.already)
    start, end = sc.sleeps[-1].end_h, sc.bed_h + 1

    points = alertness_curve(sc.sleeps, start, end, chronotype=personal.chronotype)
    lifted = curve_with_caffeine(points, doses)
    series = pd.DataFrame({
        "t": [round(p.t, 4) for p in points],
        "시각": [h_to_hhmm(p.t) for p in points],
        "카페인 없을 때": [round(p.score, 2) for p in points],
        "카페인 반영": [round(s, 2) for s in lifted],
        "몸속 카페인(mg)": [round(amount_at(p.t, doses, personal.half_life_h), 1) for p in points],
    })

    planned = set(plan.new_doses) if plan else set()
    servings = dict(zip(plan.new_doses, result.servings)) if plan else {}
    dose_rows = []
    for d in doses:
        s = servings.get(d)
        dose_rows.append({
            "t": d.time_h, "시각": h_to_hhmm(d.time_h), "mg": round(d.mg),
            "구분": "추천" if d in planned else "이미 마심",
            "설명": f"{s.beverage.name} {s.cup} · {s.minutes}분 동안 (약 {s.mg_actual:.0f}mg)" if s else f"{d.mg:.0f}mg",
        })
    windows = pd.DataFrame([{"start": w.start_h, "end": w.end_h, "구간": KIND_NAME[w.kind],
                             "시간": f"{h_to_hhmm(w.start_h)}–{h_to_hhmm(w.end_h)}"}
                            for w in sc.windows if w.kind != "stay_awake"])
    marks = [{"t": sc.bed_h, "표시": f"취침 {h_to_hhmm(sc.bed_h)}"}]
    if plan and plan.cutoff_h is not None:
        marks.append({"t": plan.cutoff_h, "표시": f"{h_to_hhmm(plan.cutoff_h)}부터 카페인 금지"})
    return {"series": series, "doses": pd.DataFrame(dose_rows), "windows": windows,
            "marks": pd.DataFrame(marks), "residual_limit": personal.residual_limit_mg}


def build_charts(frames: Dict[str, pd.DataFrame], width="container") -> Tuple[alt.LayerChart, alt.LayerChart]:
    """(위 각성 점수, 아래 몸속 카페인) 두 그래프.

    width="container"는 칸 너비에 맞춤. 위아래를 하나로 붙이면(vconcat) Vega-Lite에서 container 너비가
    적용되지 않아 그래프가 찌그러지므로 따로 그린다. 같은 시간 범위(x_scale)를 써서 줄이 맞는다.
    """
    s = frames["series"]
    # 모든 층이 같은 시간 범위를 쓰게 한다 (안 그러면 0시부터 그려짐)
    x_scale = alt.Scale(domain=[float(s["t"].min()), float(s["t"].max())], nice=False, zero=False)
    x = alt.X("t:Q", scale=x_scale, title=None, axis=alt.Axis(labelExpr=HHMM, tickMinStep=1, grid=False))
    xt = alt.X("t:Q", scale=x_scale)
    hover = alt.selection_point(fields=["t"], nearest=True, on="pointerover", clear="pointerout",
                                empty=False)

    def backdrop():
        layers = []
        if not frames["windows"].empty:
            layers.append(alt.Chart(frames["windows"]).mark_rect(color=FILL, opacity=0.6).encode(
                x=alt.X("start:Q", scale=x_scale), x2="end:Q",
                tooltip=[alt.Tooltip("구간:N"), alt.Tooltip("시간:N")]))
        layers.append(alt.Chart(frames["marks"]).mark_rule(color=GRAY, strokeDash=[2, 3]).encode(
            x=xt, tooltip=[alt.Tooltip("표시:N", title="")]))
        return layers

    # 위: 각성 점수
    long = s.melt(id_vars=["t", "시각"], value_vars=["카페인 없을 때", "카페인 반영"],
                  var_name="선", value_name="점수")
    lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=x, y=alt.Y("점수:Q", title="각성 점수", scale=alt.Scale(domain=[2, 16])),
        color=alt.Color("선:N", scale=alt.Scale(domain=["카페인 없을 때", "카페인 반영"], range=[GRAY, BLUE]),
                        legend=alt.Legend(title=None, orient="top", direction="horizontal")),
        strokeDash=alt.StrokeDash("선:N", scale=alt.Scale(domain=["카페인 없을 때", "카페인 반영"],
                                                          range=[[4, 3], [1, 0]]), legend=None))
    danger = params.value("fatigue", "danger_threshold")
    danger_rule = alt.Chart(pd.DataFrame({"y": [danger]})).mark_rule(color=GRAY, strokeDash=[6, 4]).encode(
        y="y:Q", tooltip=[alt.Tooltip("y:Q", title="졸음 위험선")])
    selectors = alt.Chart(s).mark_rule(opacity=0).encode(x=xt).add_params(hover)
    cross = alt.Chart(s).mark_rule(color=GRAY).encode(
        x=xt,
        opacity=alt.condition(hover, alt.value(0.7), alt.value(0)),
        tooltip=[alt.Tooltip("시각:N"), alt.Tooltip("카페인 반영:Q", title="각성 점수(카페인 반영)"),
                 alt.Tooltip("카페인 없을 때:Q"), alt.Tooltip("몸속 카페인(mg):Q")])
    top = alt.layer(*backdrop(), danger_rule, lines, selectors, cross).properties(
        width=width, height=220, title="각성 점수 — 14 또렷 · 7 졸음 위험선")

    # 아래: 몸속 카페인
    area = alt.Chart(s).mark_line(color=ORANGE, strokeWidth=2).encode(
        x=x, y=alt.Y("몸속 카페인(mg):Q", title="몸속 카페인 (mg)"))
    limit = alt.Chart(pd.DataFrame({"y": [frames["residual_limit"]]})).mark_rule(
        color=GRAY, strokeDash=[6, 4]).encode(y="y:Q", tooltip=[alt.Tooltip("y:Q", title="취침 허용 잔량(mg)")])
    layers = [*backdrop(), limit, area]
    if not frames["doses"].empty:
        layers.append(alt.Chart(frames["doses"]).mark_point(
            shape="triangle-down", size=140, filled=True, color=ORANGE).encode(
            x=xt, y=alt.datum(0),
            opacity=alt.condition(alt.datum["구분"] == "추천", alt.value(1), alt.value(0.5)),
            tooltip=[alt.Tooltip("시각:N"), alt.Tooltip("구분:N"), alt.Tooltip("설명:N"), alt.Tooltip("mg:Q")]))
    hover2 = alt.selection_point(fields=["t"], nearest=True, on="pointerover", clear="pointerout",
                                 empty=False)
    layers.append(alt.Chart(s).mark_rule(opacity=0).encode(x=xt).add_params(hover2))
    layers.append(alt.Chart(s).mark_rule(color=GRAY).encode(
        x=xt, opacity=alt.condition(hover2, alt.value(0.7), alt.value(0)),
        tooltip=[alt.Tooltip("시각:N"), alt.Tooltip("몸속 카페인(mg):Q")]))
    bottom = alt.layer(*layers).properties(width=width, height=180, title="몸속 카페인 — ▼ 마시는 시각")

    # 너비만 칸에 맞추고 높이는 그대로 (기본 'fit'은 높이까지 줄여 납작해짐)
    fit_x = alt.AutoSizeParams(type="fit-x", contains="padding")
    return (top.configure_view(stroke=None).properties(autosize=fit_x),
            bottom.configure_view(stroke=None).properties(autosize=fit_x))
