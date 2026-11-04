"""브랜드별 카페인 — 시중 메뉴별 카페인 (beverages.yaml) 찾아보기: 분류·브랜드·검색·정렬, 하루 상한 대비."""
import pandas as pd
import streamlit as st
import yaml

import state
from forms import DRINK_GROUPS, drink_group

from caffeine_engine.convert import BEVERAGES_PATH, load_beverage_db
from caffeine_engine.profile import Profile, personal_params


@st.cache_data
def _table() -> pd.DataFrame:
    return pd.DataFrame([{
        "분류": drink_group(d.brand), "브랜드": d.brand, "메뉴": d.menu, "온도": d.temp or "", "사이즈": d.size,
        "용량(ml)": d.ml, "카페인(mg)": d.mg, "100ml당(mg)": round(d.mg / d.ml * 100, 1) if d.ml else None,
        "출처": d.source_type, "링크": d.source_url, "메모": d.note,
    } for d in load_beverage_db()])


st.markdown("<div style='text-align:center;font-size:17px;font-weight:600;margin:-4px 0 10px'>브랜드별 카페인</div>",
            unsafe_allow_html=True)
st.caption("카페·편의점·에너지음료 메뉴별 카페인. 매장·원두·추출에 따라 실제 값은 달라질 수 있어요.")

df = _table()
try:
    cap = personal_params(Profile(**state.data()["profile"])).daily_cap_mg
except Exception:
    cap = 400.0

groups = ["카페", *DRINK_GROUPS]
picked = st.pills("분류", groups, selection_mode="multi", default=groups, label_visibility="collapsed")
c1, c2 = st.columns([2, 1])
query = c1.text_input("검색", placeholder="메뉴·브랜드 검색 (예: 콜드브루, 메가)", label_visibility="collapsed")
order = c2.selectbox("정렬", ["카페인 많은 순", "카페인 적은 순", "브랜드순"], label_visibility="collapsed")

view = df[df["분류"].isin(picked or groups)]
brands = list(dict.fromkeys(view["브랜드"]))
chosen = st.multiselect("브랜드", brands, placeholder="브랜드 전체", label_visibility="collapsed")
if chosen:
    view = view[view["브랜드"].isin(chosen)]
if query.strip():
    q = query.replace(" ", "").lower()      # '콜드브루'로 '콜드 브루'도 찾게 띄어쓰기 무시
    view = view[(view["메뉴"] + view["브랜드"]).str.replace(" ", "").str.lower().str.contains(q, regex=False)]
if order != "브랜드순":
    view = view.sort_values("카페인(mg)", ascending=order == "카페인 적은 순", kind="stable")

view = view.assign(**{"하루 상한 대비": view["카페인(mg)"] / cap})
st.caption(f"{len(view)}개 · 하루 상한 {cap:.0f}mg 기준 (내 프로필에서 바뀜)")
st.dataframe(
    view[["브랜드", "메뉴", "온도", "사이즈", "용량(ml)", "카페인(mg)", "하루 상한 대비", "100ml당(mg)", "출처", "메모", "링크"]],
    hide_index=True, width="stretch", height=560,
    column_config={
        "카페인(mg)": st.column_config.NumberColumn(format="%g mg"),
        "용량(ml)": st.column_config.NumberColumn(format="%g ml"),
        "하루 상한 대비": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "링크": st.column_config.LinkColumn(display_text="출처 보기"),
    },
)
st.caption("출처: 공식 = 브랜드 공식 사이트 · 2차 = 제품 스펙·블로그 등 · 공공 = 식약처·소비자원 · 학술 = 논문 "
           "(조사일 2026-11-01)")

with st.expander("브랜드별 컵 크기 (스몰 · 기본 · 빅)"):
    raw = yaml.safe_load(BEVERAGES_PATH.read_text(encoding="utf-8"))["cup_sizes"]
    st.dataframe(pd.DataFrame([{
        "브랜드": brand,
        **{k: (f"{row[k][0]} {row[k][1]}ml" if str(row[k][0]) != k else f"{row[k][1]}ml") if k in row else "—"
           for k in ("스몰", "기본", "빅")},
        "HOT": " · ".join(f"{k} {v}ml" for k, v in (row.get("hot") or {}).items()) or "같음",
        "확인": row.get("확인", ""), "메모": row.get("note", ""),
    } for brand, row in raw.items()]), hide_index=True, width="stretch")
    st.caption("아이스 기준 · 기본 = 따로 말하지 않으면 받는 크기. 하루 입력의 '마신 양'과 추천의 '몇 잔'이 이 크기를 써요 "
               "(조사일 2026-11-04 · 확인: 공식 = 브랜드 메뉴·공지, 2차 = 블로그·영양 DB)")
