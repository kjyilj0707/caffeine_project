"""📊 리포트 — 하루 / 일주일 / 한 달: 마신 양, 추천대로 마셨나, 금지 시각, 잠, 졸림 기록."""
from datetime import timedelta

import altair as alt
import pandas as pd
import streamlit as st

import report
import state
import store
from calendar_view import month_weeks, week_days

from caffeine_engine.timeutil import h_to_hhmm

PERIODS = {"하루": "day", "일주일": "week", "한 달": "month"}

st.title("📊 리포트")
s = state.session()
if s is None:
    st.info("로그인하면 저장한 기록으로 하루·일주일·한 달 리포트를 볼 수 있어요. 화면 맨 위에서 로그인해 주세요.")
    st.stop()

# ── 기간 고르기 ──
period = PERIODS[st.radio("기간", list(PERIODS), index=1, horizontal=True, key="report_period",
                          label_visibility="collapsed")]
anchor = st.session_state.setdefault("report_anchor", state.selected_day())
if period == "day":
    first = last = anchor
    title = state.day_label(anchor)
elif period == "week":
    days = week_days(anchor)
    first, last = days[0], days[-1]
    title = f"{first.month}/{first.day} ~ {last.month}/{last.day}"
else:
    days = [d for w in month_weeks(anchor) for d in w if d]
    first, last = days[0], days[-1]
    title = f"{anchor.year}년 {anchor.month}월"
c1, c2, c3 = st.columns([1, 2.4, 1], vertical_alignment="center")
step = {"day": timedelta(days=1), "week": timedelta(days=7)}.get(period)
if c1.button("◀ 이전", width="stretch"):
    st.session_state.report_anchor = anchor - step if step else first - timedelta(days=1)
    st.rerun()
c2.markdown(f"<div style='text-align:center;font-weight:600;font-size:1.1rem'>{title}</div>", unsafe_allow_html=True)
if c3.button("다음 ▶", width="stretch"):
    st.session_state.report_anchor = anchor + step if step else last + timedelta(days=1)
    st.rerun()

# ── 자료 불러오기 (같은 기간은 한 번만) ──
cache = st.session_state.setdefault("report_cache", {})
key = (first.isoformat(), last.isoformat())
if key not in cache:
    try:
        cache[key] = store.report_rows(s, first, last)
    except Exception as e:
        st.error(f"기록을 불러오지 못했어요: {e}")
        st.stop()
stats = report.day_stats(cache[key], first, last)
cap = state.data()["profile"].get("daily_cap_mg")
sm = report.summarize(stats, cap)

if not any(x.intakes or x.planned or x.sleep_h or x.kss for x in stats):
    st.info("이 기간에는 저장한 기록이 없어요. 📅 하루 입력에서 잠·마신 것을 넣고 저장하면 여기에 쌓여요.")
    st.stop()

# ── 요약 ──
m1, m2 = st.columns(2)
m3, m4 = st.columns(2)
if period == "day":
    m1.metric(f"마신 양 (상한 {sm.cap_mg:.0f}mg)", f"{sm.total_mg:.0f}mg")
else:
    m1.metric("하루 평균 마신 양", f"{sm.daily_average_mg:.0f}mg",
              help=f"기간 전체 {sm.total_mg:.0f}mg · 마신 날 {sm.days_with_caffeine}일 · 하루 상한 {sm.cap_mg:.0f}mg")
m2.metric("추천대로 마신 잔", f"{sm.matched_cups} / {sm.planned_cups}" if sm.planned_cups else "—",
          help=f"추천 시각 ±{report.MATCH_MIN}분 안에 마신 기록이 있는 잔")
m3.metric("금지 시각 지킨 날", f"{sm.cutoff_kept_days} / {sm.cutoff_days}" if sm.cutoff_days else "—",
          help="금지 시각 뒤에 마신 기록이 없으면 지킨 것. 추천을 저장하고 마신 것을 기록한 날만 셉니다")
m4.metric("졸림 기록", f"평균 {sm.kss_mean:.1f}" if sm.kss_mean else "—",
          help=f"{sm.kss_count}번 기록 · 1 매우 또렷함 ~ 9 매우 졸림")
if sm.days_over_cap:
    st.warning(f"하루 상한({sm.cap_mg:.0f}mg)을 넘은 날이 {sm.days_over_cap}일 있어요"
               + (f" · 가장 많이 마신 날 {sm.max_day.month}/{sm.max_day.day} {sm.max_day_mg:.0f}mg" if sm.max_day else ""))
sleep_bits = []
if sm.sleep_h:
    sleep_bits.append(f"평균 잠 {int(sm.sleep_h)}시간 {round(sm.sleep_h % 1 * 60)}분")
if sm.latency_min is not None:
    sleep_bits.append(f"잠들기까지 평균 {sm.latency_min:.0f}분")
if sleep_bits:
    st.caption("😴 " + " · ".join(sleep_bits))

# ── 하루: 추천 vs 실제 ──
if period == "day":
    d = stats[0]
    st.subheader("추천 vs 실제")
    rows = [{"구분": "추천", "시각": h_to_hhmm(p.time_h), "양": f"{p.mg:.0f}mg"} for p in d.planned]
    rows += [{"구분": "마심", "시각": h_to_hhmm(x.time_h), "양": f"{x.mg:.0f}mg"} for x in d.intakes]
    if rows:
        st.dataframe(pd.DataFrame(sorted(rows, key=lambda r: (r["시각"] < "04:00", r["시각"]))),
                     hide_index=True, width="stretch")
    if d.cutoff_h is not None:
        kept = {True: "✅ 지킴", False: "❌ 금지 시각 뒤에 마신 기록이 있어요", None: "마신 기록이 없어 판단 못 함"}
        st.caption(f"⛔ 금지 시각 {h_to_hhmm(d.cutoff_h)} — {kept[d.cutoff_kept]}")
    if d.kss:
        st.caption("📝 졸림 기록: " + " · ".join(str(k) for k in d.kss))
    st.stop()

# ── 일주일·한 달: 날짜별 마신 양 ──
st.subheader("날짜별 마신 양")
df = pd.DataFrame([{"날짜": x.day.isoformat(), "마신 양 (mg)": round(x.mg), "표시": f"{x.day.month}/{x.day.day}"}
                   for x in stats])
bars = alt.Chart(df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color="#6f4e37").encode(
    x=alt.X("표시:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
    y=alt.Y("마신 양 (mg):Q", title="mg"),
    tooltip=["날짜", "마신 양 (mg)"])
cap_line = alt.Chart(pd.DataFrame({"상한": [sm.cap_mg]})).mark_rule(strokeDash=[4, 4], color="#9a9a96").encode(
    y="상한:Q", tooltip=[alt.Tooltip("상한:Q", title="하루 상한 (mg)")])
st.altair_chart((bars + cap_line).properties(height=220, width="container"))
st.caption(f"점선 = 하루 상한 {sm.cap_mg:.0f}mg · 막대에 마우스를 올리면 그날 양이 보여요")

with st.expander("날짜별 자세히"):
    kept = {True: "✅", False: "❌", None: "—"}
    st.dataframe(pd.DataFrame([{
        "날짜": f"{x.day.month}/{x.day.day} ({state.WEEKDAY[x.day.weekday()]})",
        "마신 양": f"{x.mg:.0f}mg" if x.intakes else "—",
        "추천대로": f"{x.matched}/{len(x.planned)}" if x.planned else "—",
        "금지 시각": kept[x.cutoff_kept],
        "잠": f"{x.sleep_h:.1f}시간" if x.sleep_h else "—",
        "잠들기": f"{x.latency_min}분" if x.latency_min is not None else "—",
        "졸림": " · ".join(map(str, x.kss)) or "—",
    } for x in stats]), hide_index=True, width="stretch")
