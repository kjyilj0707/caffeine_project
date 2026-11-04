"""피드백 — 리포트의 '피드백' 카드에서 들어오는 입력 화면 (아래 탭에는 없음).

지금 졸림(KSS 1~9)을 끌어서 남기면, 엔진 예측과 비교해 나중에 나에게 맞게 보정하는 데 쓴다.
아래에는 지금까지 쌓인 '모델 예측 vs 내 기록' 비교를 보여준다.
"""
import pandas as pd
import streamlit as st

import dial
import report
import state
import store
from forms import KSS_LABEL

from caffeine_engine.calibration import kss_bias, latency_compare
from caffeine_engine.notify import current_time_h
from caffeine_engine.profile import Profile, personal_params
from caffeine_engine.timeutil import h_to_hhmm

KSS_TEXT = [f"{k} · {KSS_LABEL[k]}" if k in KSS_LABEL else f"{k}" for k in range(1, 10)]

with st.container(horizontal=True, vertical_alignment="center"):
    if st.button("", icon=":material/chevron_left:", key="fb_back", type="tertiary", help="리포트로"):
        st.switch_page("page_report.py")
    st.markdown("<div style='text-align:center;font-size:17px;font-weight:600'>피드백</div>",
                unsafe_allow_html=True, width="stretch")
    st.markdown("<div style='width:32px'></div>", unsafe_allow_html=True, width="content")

s = state.session()

# ── 지금 졸림 남기기 ──
st.subheader("지금 얼마나 졸려요?")
st.caption("선을 끌어서 지금 상태에 맞춰 주세요. 수업·시험처럼 중요한 시간에 남기면 예측과 비교하기 좋아요.")
v = dial.line("졸림", st.session_state.get("fb_kss_v", 0.5), KSS_TEXT, key="fb_kss", ends=("또렷함", "매우 졸림"))
kss = 1 + min(8, int(v * 9 * 0.9999))           # 선 길이 0~1 → 1~9
note = st.text_input("메모 (선택)", key="fb_note", placeholder="예: 시험 직전, 커피 2잔째")
if s is None:
    st.info("로그인하면 기록을 저장해 예측과 비교할 수 있어요. 화면 맨 위에서 로그인해 주세요.")
elif st.button(f"졸림 {kss} 기록하기", type="primary", width="stretch", key="fb_save"):
    try:
        store.add_sleepiness(s, kss, note)
        st.session_state.pop("kss_today", None)
        st.session_state.pop("report_cache", None)
        st.success(f"기록했어요: {h_to_hhmm(current_time_h())} 즈음 졸림 {kss}")
    except Exception as e:
        st.error(f"기록하지 못했어요: {e}")

# ── 지금까지 비교 (모델 예측 vs 내 기록) ──
st.divider()
st.subheader("모델 예측 vs 내 기록")
first, last = state.selected_day().replace(day=1), state.selected_day()
try:
    rows = store.report_rows(s, first, last) if s else report.demo_rows(first, last, state.default_day())
    prof = state.data()["profile"]
    personal = personal_params(Profile(**prof))
    pairs = report.kss_pairs(rows, prof.get("chronotype", "neutral"))
    bias = kss_bias([p for _, p in pairs])
    latency = latency_compare(report.night_checks(rows, personal.half_life_h), personal.residual_limit_mg)
except Exception as e:
    st.caption(f"비교를 계산하지 못했어요: {e}")
else:
    st.markdown(f"**졸림** — {bias.message}  \n**잠들기** — {latency.message} "
                f"(기준: 잠들 때 몸속 {personal.residual_limit_mg:.0f}mg)")
    if pairs:
        st.dataframe(pd.DataFrame([{"날짜": f"{d.month}/{d.day}", "시각": h_to_hhmm(p.t), "내 졸림": p.observed,
                                    "모델 예측": round(p.predicted, 1), "차이": round(p.diff, 1)} for d, p in pairs]),
                     hide_index=True, width="stretch")
    st.caption("이번 달 기록 기준 · 예측 졸림 = 10.6 − 0.6 × 각성 점수 (Ingre 2014)"
               + (" · 지금은 예시 기록이에요" if s is None else ""))
