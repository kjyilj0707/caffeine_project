"""카페인 측정기 — 시작 파일: 페이지 5개를 묶고 화면 아래 탭 바(tabbar.py)를 그린다.

실행: .venv/bin/streamlit run app/streamlit_app.py

  오늘 추천 (page_plan.py)    몇 시에 몇 모금 · 금지 시각 (그래프·수치·알림은 펼쳐 보기)
  하루 입력 (page_day.py)     날짜 고르기 → 어젯밤 잠 · 마신 것 · 일정 · 음료
  리포트    (page_report.py)  하루·일주일·한 달: 마신 양, 추천대로 마셨나, 금지 시각, 잠, 졸림
  음료      (page_drinks.py)  시중 메뉴별 카페인 찾아보기 (분류·브랜드·검색·정렬)
  프로필    (page_profile.py) 나이·몸무게·건강·민감도 + 로그인 상태 · 예시 채우기

입력값은 state.py의 data 한 곳에 모인다. 로그인은 화면 맨 위 바(index.html)에서.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import streamlit as st  # noqa: E402

import state  # noqa: E402
import tabbar  # noqa: E402

st.set_page_config(page_title="카페인 측정기", page_icon=":material/local_cafe:", layout="centered", initial_sidebar_state="collapsed")
state.init()
state.ensure_loaded()

pages = tabbar.pages()
extra = [st.Page("page_feedback.py", title="피드백")]     # 탭에는 없고 리포트 카드에서 들어가는 화면
nav = st.navigation(pages + extra, position="hidden")
if state.needs_morning_input():      # 아침에 처음 열면 (오늘 잠 기록이 없을 때) 하루 입력부터
    st.switch_page("page_day.py")
tabbar.render(pages, nav)
nav.run()
