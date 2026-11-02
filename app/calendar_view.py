"""📅 하루 입력의 달력 보기 (일주일 / 한 달). 날짜를 누르면 그날 입력으로 돌아간다."""
import calendar
from datetime import date, timedelta
from typing import Dict, List, Optional

import streamlit as st

import state
import store

WEEK_HEAD = ["월", "화", "수", "목", "금", "토", "일"]


def week_days(anchor: date) -> List[date]:
    """anchor가 있는 주의 월~일."""
    monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def month_weeks(anchor: date) -> List[List[Optional[date]]]:
    """anchor가 있는 달을 주(월~일) 단위로. 그 달이 아닌 칸은 None."""
    return [[d if d.month == anchor.month else None for d in week]
            for week in calendar.Calendar(firstweekday=0).monthdatescalendar(anchor.year, anchor.month)]


def cell_text(day: date, info: Dict, detailed: bool, is_today: bool = False) -> str:
    """달력 칸 글자. 한 달 보기는 짧게(표시만), 일주일 보기는 자세히."""
    head = f"{day.month}/{day.day}" if detailed else str(day.day)
    lines = [f"**{head} 오늘**" if is_today else head]
    if detailed:
        lines.append(f"😴 {info['sleep']}" if "sleep" in info else "😴 —")
        lines.append(f"☕ {info['mg']:.0f}mg" if "mg" in info else "☕ —")
        if "plan" in info:
            lines.append(f"📋 추천 {info['plan']}잔")
        if "kss" in info:
            lines.append(f"📝 졸림 {info['kss']:g}")
    else:
        marks = ("😴" if "sleep" in info else "") + ("☕" if "mg" in info else "") + ("📋" if "plan" in info else "")
        lines.append(marks or "·")
    return "  \n".join(lines)


def _summary(first: date, last: date) -> Dict[str, Dict]:
    s = state.session()
    if s is None:
        return {}
    cache = st.session_state.setdefault("cal_cache", {})
    key = (first.isoformat(), last.isoformat())
    if key not in cache:
        try:
            cache[key] = store.range_summary(s, first, last)
        except Exception as e:
            st.error(f"기록을 불러오지 못했어요: {e}")
            return {}
    return cache[key]


def _pick(day: date) -> None:
    st.session_state.cal_view = None
    state.load(day)


def render(view: str) -> None:
    anchor: date = st.session_state.setdefault("cal_anchor", state.selected_day())
    step = timedelta(days=7) if view == "week" else None
    c1, c2, c3, c4 = st.columns([1, 2.2, 1, 1.4], vertical_alignment="center")
    if c1.button("◀ 이전", width="stretch"):
        st.session_state.cal_anchor = anchor - step if step else (anchor.replace(day=1) - timedelta(days=1))
        st.rerun()
    if view == "week":
        days = week_days(anchor)
        c2.markdown(f"**{days[0].month}/{days[0].day} ~ {days[-1].month}/{days[-1].day}**")
    else:
        c2.markdown(f"**{anchor.year}년 {anchor.month}월**")
    if c3.button("다음 ▶", width="stretch"):
        st.session_state.cal_anchor = anchor + step if step else (anchor.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.rerun()
    if c4.button("✕ 달력 닫기", width="stretch"):
        st.session_state.cal_view = None
        st.rerun()

    weeks = [week_days(anchor)] if view == "week" else month_weeks(anchor)
    real = [d for w in weeks for d in w if d]
    info = _summary(min(real), max(real))
    if state.session() is None:
        st.info("로그인하면 날짜마다 저장한 기록이 달력에 표시돼요. 지금은 날짜를 골라 입력하는 것만 돼요.")
    else:
        st.caption("😴 잠 기록 · ☕ 마신 양 · 📋 저장한 추천 · 📝 졸림 평균 — 날짜를 누르면 그날 입력으로 가요.")

    head = st.columns(7)
    for col, name in zip(head, WEEK_HEAD):
        col.markdown(f"<div style='text-align:center;font-weight:600'>{name}</div>", unsafe_allow_html=True)
    selected, today = state.selected_day(), state.default_day()
    for week in weeks:
        cols = st.columns(7)
        for col, day in zip(cols, week):
            if day is None:
                continue
            label = cell_text(day, info.get(day.isoformat(), {}), detailed=view == "week", is_today=day == today)
            col.button(label, key=f"cal_{day.isoformat()}", width="stretch",
                       type="primary" if day == selected else "secondary", on_click=_pick, args=(day,))
