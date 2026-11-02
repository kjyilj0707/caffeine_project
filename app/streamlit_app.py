"""☕ 카페인 측정기 — 시작 파일: 페이지 3개를 묶고 왼쪽 메뉴를 그린다.

실행: .venv/bin/streamlit run app/streamlit_app.py

  ☕ 오늘의 추천 (page_plan.py)    몇 시에 몇 모금 · 금지 시각 (그래프·수치·알림은 펼쳐 보기)
  📅 하루 입력  (page_day.py)     날짜 고르기 → 어젯밤 잠 · 마신 것 · 일정 · 음료
  👤 내 프로필  (page_profile.py) 나이·몸무게·건강·민감도 (한 번만)

입력값은 state.py의 data 한 곳에 모인다. 로그인은 화면 맨 위 바(index.html)에서.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import streamlit as st  # noqa: E402

import state  # noqa: E402

st.set_page_config(page_title="카페인 측정기", page_icon="☕", layout="centered")
state.init()
state.ensure_loaded()

nav = st.navigation([
    st.Page("page_plan.py", title="오늘의 추천", icon="☕", default=True),
    st.Page("page_day.py", title="하루 입력", icon="📅"),
    st.Page("page_profile.py", title="내 프로필", icon="👤"),
])

with st.sidebar:
    s = state.session()
    if s is None:
        st.caption("☁️ 로그인 안 됨 — 화면 맨 위에서 이메일로 로그인하면 입력이 저장돼요.")
    else:
        st.caption(f"☁️ {s.email} 로그인됨")
        if st.session_state.get("load_error"):
            st.error(st.session_state.load_error)
    if state.data()["example"]:
        with st.expander("예시로 채워 보기"):
            preset = st.selectbox("예시", list(state.SCENARIOS), index=list(state.SCENARIOS).index(state.DEFAULT),
                                  label_visibility="collapsed")
            if st.button("이 예시로 채우기", width="stretch"):
                st.session_state.data = state.from_example(preset)
                state.refresh_widgets()
                st.rerun()
    st.caption("※ 의학적 조언이 아니에요. 평균적인 성인 기준 예측입니다.")

nav.run()
