"""리포트 — Apple 피트니스 '요약'처럼 카드로: 맨 위 카페인 링, 2열 지표 카드(큰 숫자 + 작은 막대), 넓은 추세 카드.

하루 / 일주일 / 한 달: 마신 양, 추천대로 마셨나, 금지 시각, 잠, 졸림, 모델 예측 vs 내 기록.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

import report
import report_cards as rc
import state
import store
from calendar_view import month_weeks, week_days

from caffeine_engine.calibration import kss_bias
from caffeine_engine.profile import Profile, personal_params
from caffeine_engine.timeutil import h_to_hhmm

PERIODS = {"하루": "day", "일주일": "week", "한 달": "month"}
WEEKDAY = state.WEEKDAY

st.markdown("<div style='text-align:center;font-size:17px;font-weight:600;margin:-4px 0 10px'>리포트</div>",
            unsafe_allow_html=True)
s = state.session()
demo = s is None    # 로그인 전에는 예시 기록으로 모양만 보여줌

# ── 기간 고르기: [하루 | 일주일 | 한 달] + ‹ 기간 › ──
choice = st.segmented_control("기간", list(PERIODS), default="일주일", key="report_period",
                              label_visibility="collapsed", width="stretch")
period = PERIODS[choice or "일주일"]
anchor = st.session_state.setdefault("report_anchor", state.selected_day())
if period == "day":
    first = last = anchor
    title = state.day_label(anchor)
elif period == "week":
    days = week_days(anchor)
    first, last = days[0], days[-1]
    title = f"{first.month}월 {first.day}일 ~ {last.month}월 {last.day}일"
else:
    days = [d for w in month_weeks(anchor) for d in w if d]
    first, last = days[0], days[-1]
    title = f"{anchor.year}년 {anchor.month}월"
step = {"day": timedelta(days=1), "week": timedelta(days=7)}.get(period)
with st.container(horizontal=True, vertical_alignment="center", key="report_nav"):
    if st.button("", icon=":material/chevron_left:", key="report_prev", type="tertiary"):
        st.session_state.report_anchor = anchor - step if step else first - timedelta(days=1)
        st.rerun()
    st.markdown(f"<div style='text-align:center;font-weight:600;font-size:16px'>{title}</div>",
                unsafe_allow_html=True, width="stretch")
    if st.button("", icon=":material/chevron_right:", key="report_next", type="tertiary"):
        st.session_state.report_anchor = anchor + step if step else last + timedelta(days=1)
        st.rerun()

# ── 자료 불러오기 (같은 기간은 한 번만) ──
cache = st.session_state.setdefault("report_cache", {})
key = (first.isoformat(), last.isoformat())
if demo:
    cache[key] = report.demo_rows(first, last, state.default_day())
elif key not in cache:
    try:
        cache[key] = store.report_rows(s, first, last)
    except Exception as e:
        st.error(f"기록을 불러오지 못했어요: {e}")
        st.stop()
stats = report.day_stats(cache[key], first, last)
prof = state.data()["profile"]
try:
    personal = personal_params(Profile(**prof))
except Exception:
    personal = None
cap = personal.daily_cap_mg if personal else None
sm = report.summarize(stats, cap)
dark = getattr(getattr(st.context, "theme", None), "type", None) == "dark"

if not any(x.intakes or x.planned or x.sleep_h or x.kss for x in stats):
    st.html(rc.css(dark) + rc.grid([rc.stat_card("이 기간 기록", "", None, "", rc.CAFFEINE,
                                                  empty="저장한 기록이 없어요. 하루 입력에서 잠·마신 것을 저장하면 여기에 쌓여요.",
                                                  wide=True)]))
    st.stop()

# ── 막대그래프 자료 ──
if period == "day":
    d0 = stats[0]
    by_hour = [0.0] * 24
    for x in d0.intakes:
        by_hour[int(x.time_h) % 24] += x.mg
    axis_day = ["오전 12시", "오전 6시", "오후 12시", "오후 6시"]
else:
    axis = ([f"{x.day.month}/{x.day.day}" for x in (stats[0], stats[-1])] if period == "month"
            else [WEEKDAY[x.day.weekday()] for x in stats])
    mg_days = [x.mg or None for x in stats]
    sleep_days = [x.sleep_h for x in stats]
    kss_days = [sum(x.kss) / len(x.kss) if x.kss else None for x in stats]

# ── 맨 위: 카페인 링 (상한 대비) ──
if period == "day":
    ring = rc.ring_card("카페인", "마신 양", sm.total_mg, sm.cap_mg, "mg", rc.CAFFEINE,
                        foot=f"하루 상한의 {sm.total_mg / sm.cap_mg * 100:.0f}%")
else:
    ring = rc.ring_card("카페인", "하루 평균", sm.daily_average_mg, sm.cap_mg, "mg", rc.CAFFEINE,
                        foot=f"기간 전체 {sm.total_mg:.0f}mg · 마신 날 {sm.days_with_caffeine}일"
                             + (f" · 상한 넘은 날 {sm.days_over_cap}일" if sm.days_over_cap else ""))

# ── 2열 카드 ──
sub = "오늘" if period == "day" and state.is_today() and anchor == state.default_day() else (
    "이날" if period == "day" else "평균")
cards = [ring]
if period == "day":
    cards.append(rc.stat_card("잠", "어젯밤", rc.hm(d0.sleep_h), "", rc.SLEEP,
                              foot=(f"잠들기 {d0.latency_min}분" if d0.latency_min is not None else "")))
    cards.append(rc.kss_card("졸림", "기록 평균", sum(d0.kss) / len(d0.kss) if d0.kss else None,
                             foot=f"{len(d0.kss)}번 기록: " + " · ".join(map(str, d0.kss)) if d0.kss else ""))
else:
    cards.append(rc.stat_card("잠", sub, rc.hm(sm.sleep_h), "", rc.SLEEP, rc.bars(sleep_days, rc.SLEEP, axis)))
    cards.append(rc.kss_card("졸림", sub, sm.kss_mean, kss_days, axis, foot=f"{sm.kss_count}번 기록"))
cards.append(rc.stat_card("추천대로", "마신 잔", f"{sm.matched_cups}/{sm.planned_cups}" if sm.planned_cups else None,
                          "잔", rc.PLAN, foot=f"추천 시각 ±{report.MATCH_MIN}분 안에 마심", empty="저장한 추천이 없어요"))
if period == "day":
    kept = {True: "지킴", False: "못 지킴", None: None}[d0.cutoff_kept]
    cards.append(rc.stat_card("금지 시각", h_to_hhmm(d0.cutoff_h) if d0.cutoff_h is not None else "", kept, "",
                              rc.CAFFEINE if d0.cutoff_kept else rc.CUTOFF, empty="판단할 기록이 없어요"))
else:
    cards.append(rc.stat_card("금지 시각", "지킨 날", f"{sm.cutoff_kept_days}/{sm.cutoff_days}" if sm.cutoff_days else None,
                              "일", rc.CUTOFF, foot="금지 시각 뒤에 마신 기록이 없으면 지킴", empty="판단할 기록이 없어요"))

# ── 넓은 카드: 마신 양 추세 ──
if period == "day":
    cards.append(rc.stat_card("시간대별 마신 양", "합계", f"{sm.total_mg:.0f}", "mg", rc.CAFFEINE,
                              rc.bars(by_hour, rc.CAFFEINE, axis_day), wide=True))
    rows = sorted([(h_to_hhmm(p.time_h), f"추천 {p.mg:.0f}mg") for p in d0.planned]
                  + [(h_to_hhmm(x.time_h), f"마심 {x.mg:.0f}mg") for x in d0.intakes],
                  key=lambda r: (r[0] < "04:00", r[0]))
    cards.append(rc.list_card("추천 vs 실제", rows, empty="추천·마신 기록이 없어요"))
else:
    cards.append(rc.stat_card("날짜별 마신 양", "하루 최대",
                              f"{sm.max_day_mg:.0f}" if sm.max_day_mg else None, "mg", rc.CAFFEINE,
                              rc.bars(mg_days, rc.CAFFEINE, axis, cap=sm.cap_mg),
                              foot=f"점선 = 하루 상한 {sm.cap_mg:.0f}mg", wide=True))

# ── 넓은 카드: 피드백 (요약만, 입력은 '피드백 남기기'로 넘어가서) ──
pairs = []
try:
    pairs = report.kss_pairs(cache[key], prof.get("chronotype", "neutral"))
    bias = kss_bias([p for _, p in pairs])
    cards.append(rc.list_card("피드백", [], empty="",
                              msg=f"지금 졸림을 남기면 모델 예측과 비교해 나에게 맞게 보정해요.<br>{bias.message}"))
except Exception as e:  # 비교가 실패해도 리포트 나머지는 보이게
    st.caption(f"모델 비교를 계산하지 못했어요: {e}")

st.html(rc.css(dark) + rc.grid(cards))
if st.button("피드백 남기기 →", type="primary", width="stretch", key="go_feedback"):
    st.switch_page("page_feedback.py")
if demo:
    st.info("지금은 **예시 기록**이에요. 화면 맨 위에서 로그인하고 하루 입력을 저장하면 내 기록으로 바뀌어요.")

# ── 자세히 (펼쳐 보기) ──
if period != "day":
    with st.expander("날짜별 자세히"):
        kept = {True: "지킴", False: "못 지킴", None: "—"}
        st.dataframe(pd.DataFrame([{
            "날짜": f"{x.day.month}/{x.day.day} ({WEEKDAY[x.day.weekday()]})",
            "마신 양": f"{x.mg:.0f}mg" if x.intakes else "—",
            "추천대로": f"{x.matched}/{len(x.planned)}" if x.planned else "—",
            "금지 시각": kept[x.cutoff_kept],
            "잠": f"{x.sleep_h:.1f}시간" if x.sleep_h else "—",
            "잠들기": f"{x.latency_min}분" if x.latency_min is not None else "—",
            "졸림": " · ".join(map(str, x.kss)) or "—",
        } for x in stats]), hide_index=True, width="stretch")
