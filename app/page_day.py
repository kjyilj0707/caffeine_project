"""하루 입력 — 날짜를 고르고 그날의 어젯밤 잠 · 이미 마신 것 · 일정 · 음료를 넣는다."""
import pandas as pd
import streamlit as st

import calendar_view
import dial
import state
import store
from forms import (LATENCY_COL, LATENCY_OPTIONS, WINDOW_HINT, amount_entry, amount_text, amount_units,
                   beverage_choices, beverage_spec, size_label, sleep_list_to_rows, sleep_rows_to_list)

from caffeine_engine import params
from caffeine_engine.convert import load_beverage_db
from caffeine_engine.notify import current_time_h
from caffeine_engine.timeutil import h_to_hhmm

DRINK_DB = load_beverage_db()
DRINKS = beverage_choices(DRINK_DB)                       # {브랜드: {메뉴: [사이즈별 음료]}}
DRINK_BY_LABEL = {d.label: d for d in DRINK_DB}
STEP = 300                                                # 시각은 5분 단위
QUALITY = {1: "아주 나쁨", 2: "나쁨", 3: "보통", 4: "좋음", 5: "아주 좋음"}

d = state.data()
k = state.wkey

st.markdown("<div style='text-align:center;font-size:17px;font-weight:600;margin:-4px 0 10px'>하루 입력</div>",
            unsafe_allow_html=True)

# ── 달력 보기 (일주일 / 한 달) — 버튼으로 들어가고, 날짜를 누르면 아래 하루 입력으로 돌아온다 ──
with st.container(horizontal=True):
    for view, label in [("week", "일주일 보기"), ("month", "한 달 보기")]:
        if st.button(label, width="stretch", type="primary" if st.session_state.get("cal_view") == view else "secondary"):
            st.session_state.cal_view = view
            st.session_state.cal_anchor = state.selected_day()
            st.rerun()
if st.session_state.get("cal_view"):
    calendar_view.render(st.session_state.cal_view)
    st.stop()

# ── 날짜 (휠) ──
day = dial.date_wheel("날짜", state.selected_day(), state.default_day(), key=k("day"))
if day != state.selected_day():
    state.load(day)          # 로그인했으면 그날 기록을 불러오고, 아니면 날짜만 바꾼다
    st.rerun()
days = state.recorded_days()
if days:
    st.caption("기록 있는 날: " + " · ".join(f"{x.month}/{x.day}" for x in days[-10:]))
elif state.session() is None:
    st.caption("로그인하면 날짜별로 저장하고, 기록 있는 날을 볼 수 있어요.")

# ── 어젯밤 잠: 잠든~깬 시각 휠 · 잠의 질 선 · 잠들기 휠 ──
st.subheader("어젯밤 잠")
night = d.get("last_night")
if night is None:
    st.info(f"{state.day_label(day)} 아침에 깬 잠 기록이 없어요. 아래 휠을 돌려 넣어 주세요.")
    night = {"time": "00:00-07:00"}
start_txt, wake_txt = night["time"].split("-")
slept, woke = dial.span_wheel("잠든 시각 ~ 깬 시각", start_txt, wake_txt, key=k("sleep_span"))
q0 = (night["quality"] - 1) / 4 if night.get("quality") in QUALITY else 0.5
q = dial.line("잠의 질", q0, list(QUALITY.values()), key=k("quality"), ends=("아주 나쁨", "아주 좋음"))
quality = 1 + min(4, int(q * 5 * 0.9999))           # 선 길이 0~1 → 1~5 (다섯 칸으로 나눔)
latency = dial.number_wheel("잠들기까지 걸린 시간", night.get("latency_min", "모름"), LATENCY_OPTIONS, "분",
                            key=k("latency"))
new_night = {"time": f"{slept}-{woke}", "quality": quality}
if latency != "모름":
    new_night["latency_min"] = int(latency)
d["last_night"] = new_night

prev = d.get("prev_nights", [])
with st.expander(f"그 전 밤들 ({len(prev)}밤) — 며칠 쌓인 피로를 계산하는 데 써요"):
    st.caption("오래된 밤부터 적어요. 처음이면 비워 둬도 돼요 (어젯밤만으로 계산). 로그인하면 저장된 기록이 자동으로 들어와요.")
    rows = pd.DataFrame(sleep_list_to_rows(prev), columns=["잠든 시각", "깬 시각", "수면 질", LATENCY_COL])
    rows[["수면 질", LATENCY_COL]] = rows[["수면 질", LATENCY_COL]].astype("float64")
    edited = st.data_editor(rows, num_rows="dynamic", key=k("prev"), width="stretch", column_config={
        "잠든 시각": st.column_config.TimeColumn(format="HH:mm", step=STEP, required=True),
        "깬 시각": st.column_config.TimeColumn(format="HH:mm", step=STEP, required=True),
        "수면 질": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
        LATENCY_COL: st.column_config.NumberColumn(min_value=0, max_value=180, step=5),
    })
    d["prev_nights"] = sleep_rows_to_list(edited.to_dict("records"))

# ── 이미 마신 것: 시각 휠 + 양 휠(잔 크기·모금·mg) ──
st.subheader("오늘 이미 마신 것")
already = d["today"].setdefault("already", [])
for i, a in enumerate(already):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{a['time']}** · {amount_text(a)}", width="stretch")
        if st.button("✕", key=k(f"del_already_{i}"), help="지우기", type="tertiary"):
            already.pop(i)
            state.refresh_widgets()
            st.rerun()
if not already:
    st.caption("아직 없으면 비워 두세요.")
default_t = h_to_hhmm(current_time_h())[:4] + "0" if state.is_today() else "09:00"
add_t = dial.time_wheel("마신 시각", default_t, key=k("add_already_t"))
_bev = d.get("beverage")
_brand = DRINK_BY_LABEL[_bev["db"]].brand if isinstance(_bev, dict) and _bev.get("db") in DRINK_BY_LABEL else None
units = amount_units(_brand)            # 고른 음료가 브랜드 메뉴면 그 브랜드 컵 크기 (예: Tall 잔)
default_unit = next(i for i, u in enumerate(units) if u.get("cup", {}).get("size") == "기본")
unit_i, amount_v = dial.amount_wheel("마신 양", units, default_unit, 1, key=k(f"add_already_amount_{_brand}"))
if st.button("＋ 마신 것 추가", key=k("add_already"), width="stretch"):
    already.append(amount_entry(add_t, unit_i, amount_v, units))
    already.sort(key=lambda a: a["time"])
    state.refresh_widgets()
    st.rerun()

# ── 일정: 잘 시각 휠 · 시간대(시작~끝) 휠 ──
st.subheader("오늘 일정")
d["today"]["bed"] = dial.time_wheel("오늘 잘 시각", d["today"].get("bed", "23:00"), key=k("bed"))
st.caption("일어난 시각부터 잘 시각까지는 깨어 있는 시간으로 계산해요. 새벽 시각(예: 01:00)은 다음 날로 봐요")
windows = d["today"].setdefault("windows", [])
for i, w in enumerate(windows):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{w['kind']}** · {w['from']} ~ {w['to']}", width="stretch")
        if st.button("✕", key=k(f"del_win_{i}"), help="지우기", type="tertiary"):
            windows.pop(i)
            state.refresh_widgets()
            st.rerun()
kind = st.radio("시간대 종류", list(WINDOW_HINT), horizontal=True, key=k("add_win_kind"),
                format_func=lambda x: f"{x}", help=" · ".join(f"{a}: {b}" for a, b in WINDOW_HINT.items()))
w_from, w_to = dial.span_wheel("시작 ~ 끝", "14:00", "16:00", key=k("add_win_span"))
if st.button(f"＋ '{kind}' 시간 추가", key=k("add_win"), width="stretch"):
    windows.append({"kind": kind, "from": w_from, "to": w_to})
    windows.sort(key=lambda w: w["from"])
    state.refresh_widgets()
    st.rerun()

# ── 음료 ──
st.subheader("마실 음료")
bev_spec = d.get("beverage", "coffee")
picked = DRINK_BY_LABEL.get(bev_spec.get("db")) if isinstance(bev_spec, dict) else None
bev_options = ["메뉴에서 고르기", "커피 (보통)", "홍차", "직접 입력"]
bev_index = (0 if picked else 3) if isinstance(bev_spec, dict) else (2 if bev_spec == "black_tea" else 1)
bev_choice = st.radio("음료", bev_options, index=bev_index, horizontal=True, key=k("bev"),
                      label_visibility="collapsed")
if bev_choice == "메뉴에서 고르기":
    # 브랜드를 바꾸면 메뉴 목록도 바뀌므로 칸 이름(key)에 브랜드·메뉴를 넣어 따로 기억하게 한다
    b1, b2, b3 = st.columns(3)
    brands = list(DRINKS)
    brand = b1.selectbox("브랜드", brands, index=brands.index(picked.brand) if picked else 0, key=k("bev_brand"))
    menus = list(DRINKS[brand])
    menu = b2.selectbox("메뉴", menus, key=k(f"bev_menu_{brand}"),
                        index=menus.index(picked.menu) if picked and picked.brand == brand else 0)
    sizes = DRINKS[brand][menu]
    drink = b3.selectbox("온도 · 사이즈", sizes, format_func=size_label, key=k(f"bev_size_{brand}_{menu}"),
                         index=sizes.index(picked) if picked in sizes else 0)
    d["beverage"] = beverage_spec(drink)
    st.caption(f"출처: {drink.source_type} · [자료 보기]({drink.source_url})" + (f" · {drink.note}" if drink.note else ""))
    if drink.mg > params.value("limits", "daily_mg_adult"):
        st.warning(f"이 한 잔({drink.mg:g}mg)만으로 성인 하루 권고량을 넘어요. 나눠 마시는 플랜으로 계산해요.")
elif bev_choice == "직접 입력":
    spec = bev_spec if isinstance(bev_spec, dict) else {"name": "아메리카노 톨", "mg": 150, "ml": 355}
    b1, b2, b3 = st.columns([2, 1, 1])
    d["beverage"] = {"name": b1.text_input("메뉴", spec["name"], key=k("bev_name")),
                     "mg": b2.number_input("카페인 mg", 1.0, 1000.0, float(spec["mg"]), key=k("bev_mg")),
                     "ml": b3.number_input("용량 ml", 10.0, 2000.0, float(spec["ml"]), key=k("bev_ml"))}
else:
    d["beverage"] = "black_tea" if bev_choice == "홍차" else "coffee"

# ── 저장하고 추천 보기 ──
st.divider()
if st.button("저장하고 추천 보기 →", type="primary", width="stretch"):
    try:
        sd, sc, result = state.compute()
    except ValueError as e:
        st.error(f"입력을 확인해 주세요: {e}")
        st.stop()
    s = state.session()
    if s is not None:
        try:
            store.save_day(s, sd, d["sex"], result, state.selected_day())
            d["example"] = False
            st.session_state.pop("recorded_days", None)
            st.session_state.pop("cal_cache", None)      # 달력·리포트도 새 기록으로
            st.session_state.pop("report_cache", None)
            st.session_state.just_saved = True
        except Exception as e:
            st.error(f"저장하지 못했어요: {e}")
            st.stop()
    st.switch_page("page_plan.py")
if state.session() is None:
    st.caption("로그인하지 않으면 저장하지 않고 추천만 보여줘요.")
