"""☕ 카페인 측정기 — 입력 화면 (Step 2) + 알림 예약 (Step 3)

실행: .venv/bin/streamlit run app/streamlit_app.py
왼쪽에서 ① 기본 정보 ② 오늘 입력 ③ 목표를 넣으면 오른쪽에 플랜·지표·그래프가 바로 나오고,
아래 「🔔 알림 예약」에서 ntfy 채널로 ☕ 마셔 / ⛔ 금지 알림을 핸드폰에 예약한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd
import streamlit as st
import yaml

from charts import build_charts, build_frames
from ntfy import publish, valid_topic
from forms import (CHRONOTYPE_LABEL, KIND_LABELS, SENSITIVITY_LABEL, intake_list_to_rows, intake_rows_to_list,
                   sensitivity_from_survey, sleep_list_to_rows, sleep_rows_to_list, to_time, window_list_to_rows,
                   window_rows_to_list)

from caffeine_engine import params
from caffeine_engine.notify import current_time_h, plan_notifications, schedule, schedule_test
from caffeine_engine.pipeline import format_card, run_day
from caffeine_engine.scenario import from_dict
from caffeine_engine.timeutil import h_to_hhmm

st.set_page_config(page_title="카페인 측정기", page_icon="☕", layout="wide")

SCENARIOS = {yaml.safe_load(p.read_text(encoding="utf-8"))["name"]: p
             for p in sorted((ROOT / "scenarios").glob("*.yaml"))}
DEFAULT = "시험 날 (23시 취침)"
PREGNANCY = ["아니오", "임신 초기 (1~3개월)", "임신 중기 (4~6개월)", "임신 후기 (7개월~)"]

# ── 예시 불러오기: 바꾸면 모든 입력칸을 그 시나리오로 다시 채운다 ──
if "base" not in st.session_state:
    st.session_state.base = yaml.safe_load(SCENARIOS[DEFAULT].read_text(encoding="utf-8"))
    st.session_state.version = 0
with st.sidebar:
    st.header("☕ 카페인 측정기")
    preset = st.selectbox("예시 불러오기", list(SCENARIOS), index=list(SCENARIOS).index(DEFAULT))
    if st.button("이 예시로 입력칸 채우기", width="stretch"):
        st.session_state.base = yaml.safe_load(SCENARIOS[preset].read_text(encoding="utf-8"))
        st.session_state.version += 1
    st.caption("입력을 바꾸면 오른쪽 결과가 바로 다시 계산돼요.")
    st.caption("※ 의학적 조언이 아니에요. 평균적인 성인 기준 예측입니다.")

base, v = st.session_state.base, st.session_state.version
prof, today = base.get("profile", {}), base.get("today", {})


def key(name):
    return f"{name}_{v}"


left, right = st.columns([1, 1.35], gap="large")

with left:
    tab_profile, tab_today, tab_goal = st.tabs(["① 기본 정보", "② 오늘 입력", "③ 목표"])

    with tab_profile:
        c1, c2 = st.columns(2)
        age = c1.number_input("나이", 10, 100, int(prof.get("age", 24)), key=key("age"))
        weight = c2.number_input("몸무게 (kg)", 30.0, 200.0, float(prof.get("weight_kg", 70)), 0.5,
                                 key=key("weight"))
        female_default = bool(prof.get("pregnancy_trimester") or prof.get("oral_contraceptive")
                              or prof.get("breastfeeding"))
        sex = st.radio("성별", ["남성", "여성"], index=int(female_default), horizontal=True, key=key("sex"))
        smoker = st.checkbox("흡연", bool(prof.get("smoker")), key=key("smoker"),
                             help="흡연하면 카페인이 더 빨리 분해돼요")
        oral_contraceptive, trimester, breastfeeding = False, None, False
        if sex == "여성":
            oral_contraceptive = st.checkbox("경구피임약 복용", bool(prof.get("oral_contraceptive")),
                                             key=key("oc"), help="분해가 느려져요")
            trimester = st.selectbox("임신", PREGNANCY, index=int(prof.get("pregnancy_trimester") or 0),
                                     key=key("preg"))
            trimester = PREGNANCY.index(trimester) or None
            breastfeeding = st.checkbox("수유 중", bool(prof.get("breastfeeding")), key=key("bf"))

        st.markdown("**건강 상태**")
        liver = st.checkbox("간 질환", bool(prof.get("liver_disease")), key=key("liver"))
        inhibitor = st.checkbox("카페인 분해를 늦추는 약 복용", bool(prof.get("cyp1a2_inhibitor")),
                                key=key("inhib"), help="예: 플루복사민(항우울제) 등 CYP1A2 억제제. 모르면 약사에게 확인")
        heart = st.checkbox("심장질환 · 고혈압 · 불안장애", bool(prof.get("heart_or_anxiety")), key=key("heart"))

        st.markdown("**카페인 민감도**")
        how = st.radio("정하는 방법", ["설문으로", "직접 선택"], horizontal=True, key=key("sens_how"),
                       index=1 if "sensitivity" in prof else 0, label_visibility="collapsed")
        if how == "설문으로":
            cups = st.select_slider("평소 하루 커피", [0, 1, 2, 3], value=1, key=key("cups"),
                                    format_func=lambda x: "3잔 이상" if x == 3 else f"{x}잔")
            q2 = st.radio("오후 3시 이후 커피를 마시면 잠이 안 온다", ["예", "가끔", "아니오"], index=1,
                          horizontal=True, key=key("q2"))
            q3 = st.radio("커피를 마시면 두근거림·불안이 있다", ["예", "가끔", "아니오"], index=2,
                          horizontal=True, key=key("q3"))
            sensitivity = sensitivity_from_survey(cups, q2, q3)
            st.caption(f"설문 결과: **{SENSITIVITY_LABEL[sensitivity]}**")
        else:
            options = list(SENSITIVITY_LABEL)
            sensitivity = st.radio("민감도", options, index=options.index(prof.get("sensitivity", "normal")),
                                   format_func=SENSITIVITY_LABEL.get, horizontal=True, key=key("sens"))
        chrono_options = list(CHRONOTYPE_LABEL)
        chronotype = st.radio("생활 리듬", chrono_options,
                              index=chrono_options.index(prof.get("chronotype", "neutral")),
                              format_func=CHRONOTYPE_LABEL.get, horizontal=True, key=key("chrono"))
        cap = st.number_input("하루 최대량 직접 정하기 (mg, 0 = 권고량 그대로)", 0, 1000,
                              int(prof.get("daily_cap_mg") or 0), 25, key=key("cap"))

    with tab_today:
        st.markdown("**최근 수면** — 오래된 밤부터, 마지막 줄 = 어젯밤")
        sleep_df = st.data_editor(
            pd.DataFrame(sleep_list_to_rows(base.get("sleep", []))), num_rows="dynamic", key=key("sleep"),
            width="stretch",
            column_config={
                "잠든 시각": st.column_config.TimeColumn(format="HH:mm", step=900, required=True),
                "깬 시각": st.column_config.TimeColumn(format="HH:mm", step=900, required=True),
                "수면 질": st.column_config.NumberColumn(min_value=1, max_value=5, step=1, help="1~5, 비워도 됨"),
            })
        st.markdown("**이미 마신 카페인**")
        intake_df = st.data_editor(
            pd.DataFrame(intake_list_to_rows(today.get("already", [])), columns=["시각", "양", "단위"]),
            num_rows="dynamic", key=key("intake"), width="stretch",
            column_config={
                "시각": st.column_config.TimeColumn(format="HH:mm", step=900),
                "양": st.column_config.NumberColumn(min_value=0, step=1),
                "단위": st.column_config.SelectboxColumn(options=["mg", "모금"], default="모금"),
            })
        st.markdown("**마시는 음료**")
        bev_spec = base.get("beverage", "coffee")
        bev_options = ["커피", "홍차", "직접 입력"]
        bev_index = 2 if isinstance(bev_spec, dict) else (1 if bev_spec == "black_tea" else 0)
        bev_choice = st.radio("음료", bev_options, index=bev_index, horizontal=True, key=key("bev"),
                              label_visibility="collapsed")
        if bev_choice == "직접 입력":
            spec = bev_spec if isinstance(bev_spec, dict) else {"name": "아메리카노 톨", "mg": 150, "ml": 355}
            b1, b2, b3 = st.columns([2, 1, 1])
            beverage = {"name": b1.text_input("메뉴", spec["name"], key=key("bev_name")),
                        "mg": b2.number_input("카페인 mg", 1.0, 1000.0, float(spec["mg"]), key=key("bev_mg")),
                        "ml": b3.number_input("용량 ml", 10.0, 2000.0, float(spec["ml"]), key=key("bev_ml"))}
        else:
            beverage = "black_tea" if bev_choice == "홍차" else "coffee"
        sip_ml = st.number_input("한 모금 (ml)", 5.0, 50.0, float(base.get("sip_ml") or
                                 params.value("conversion", "sip_ml")), 0.5, key=key("sip"))

    with tab_goal:
        g1, g2 = st.columns(2)
        now_key = key("now")
        if now_key not in st.session_state:  # 기본값은 세션 상태로 (아래 버튼이 바꿀 수 있게)
            st.session_state[now_key] = to_time(today.get("now") or h_to_hhmm(current_time_h()))

        def use_real_now():
            st.session_state[now_key] = to_time(h_to_hhmm(current_time_h()))

        now = g1.time_input("지금 시각", step=900, key=now_key)
        g1.button("🕒 실제 현재 시각으로", on_click=use_real_now, key=key("now_btn"),
                  help="예시의 '지금 시각'이 실제와 다르면, 이미 지난 시각의 알림은 예약되지 않아요")
        bed = g2.time_input("오늘 잘 시각", to_time(today.get("bed", "23:00")), step=900, key=key("bed"))
        st.markdown("**시간대** — 깨어 있기 / 졸면 안 됨 / 집중")
        windows_df = st.data_editor(
            pd.DataFrame(window_list_to_rows(today.get("windows", [])), columns=["종류", "시작", "끝"]),
            num_rows="dynamic", key=key("windows"), width="stretch",
            column_config={
                "종류": st.column_config.SelectboxColumn(options=KIND_LABELS, required=True),
                "시작": st.column_config.TimeColumn(format="HH:mm", step=900, required=True),
                "끝": st.column_config.TimeColumn(format="HH:mm", step=900, required=True),
            })
        st.caption("일어난 시각보다 이른 시각(예: 01:00)은 다음 날 새벽으로 계산해요.")

profile = {"age": int(age), "weight_kg": float(weight), "smoker": smoker,
           "oral_contraceptive": oral_contraceptive, "pregnancy_trimester": trimester,
           "breastfeeding": breastfeeding, "liver_disease": liver, "cyp1a2_inhibitor": inhibitor,
           "heart_or_anxiety": heart, "sensitivity": sensitivity, "chronotype": chronotype}
if cap:
    profile["daily_cap_mg"] = float(cap)
scenario_dict = {
    "name": "내 하루",
    "profile": profile,
    "sleep": sleep_rows_to_list(sleep_df.to_dict("records")),
    "today": {"now": now.strftime("%H:%M"), "bed": bed.strftime("%H:%M"),
              "already": intake_rows_to_list(intake_df.to_dict("records")),
              "windows": window_rows_to_list(windows_df.to_dict("records"))},
    "beverage": beverage,
    "sip_ml": float(sip_ml),
}

with right:
    st.subheader("오늘의 카페인 플랜")
    if not scenario_dict["sleep"]:
        st.info("② 오늘 입력에 최근 수면을 한 줄 이상 넣어 주세요.")
        st.stop()
    if not scenario_dict["today"]["windows"]:
        st.info("③ 목표에 시간대를 한 줄 이상 넣어 주세요. (예: 깨어 있기 08:00–23:00)")
        st.stop()
    try:
        sc = from_dict(scenario_dict)
        result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h,
                         already=sc.already, beverage=sc.beverage, sip_ml=sc.sip_ml)
    except ValueError as e:
        st.error(f"입력을 확인해 주세요: {e}")
        st.stop()

    plan = result.plan
    if plan is None:
        st.error("이 경우엔 계산하지 않아요.")
    else:
        if result.servings:
            for d, s in zip(plan.new_doses, result.servings):
                st.markdown(f"#### ☕ {h_to_hhmm(d.time_h)} — {s.beverage.name} **{s.sips}모금**")
                st.caption(f"{s.ml:.0f}ml · 약 {s.mg_actual:.0f}mg")
        else:
            st.markdown("#### 오늘은 더 마시지 않는 게 좋아요")
        if plan.last_dose_h is not None:
            st.write(f"🔕 {h_to_hhmm(plan.last_dose_h)} 이후엔 플랜 외 카페인 금지")
        if plan.cutoff_h is not None:
            st.write(f"⛔ **{h_to_hhmm(plan.cutoff_h)}부터는 한 모금도 금지** (수면 보호)")

        # 2×2로 배치: 한 줄에 4개면 숫자가 잘림. 기준은 이름에 넣는다
        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
        m1.metric(f"오늘 총 섭취 (상한 {result.cap.cap_mg:.0f}mg)",
                  f"{result.cap.total_mg:.0f}mg · {result.cap.ratio * 100:.0f}%")
        m2.metric(f"잠든 뒤 최대 잔량 (기준 {result.personal.residual_limit_mg:.0f}mg 이하)",
                  f"{plan.max_residual_mg:.1f}mg")
        m3.metric("예상 수면 감소 (기준 20분 미만)", f"{max(plan.sleep_loss_min, 0):.1f}분")
        m4.metric(f"목표 구간 졸림 (수면 부채 {result.sleep_debt_h:.1f}시간)",
                  f"−{plan.sleepiness_reduction * 100:.0f}%")
        if result.cap.level != "ok":
            st.warning(f"오늘 섭취가 상한의 {result.cap.ratio * 100:.0f}%예요.")

    for note in result.notes:
        st.warning(note)

    top_chart, bottom_chart = build_charts(build_frames(sc, result))
    st.altair_chart(top_chart)
    st.altair_chart(bottom_chart)
    st.caption("그래프에 마우스를 올리면 그 시각의 값을 볼 수 있어요. "
               "회색 띠 = 졸면 안 됨·집중 시간대, 점선 = 취침·금지 시각")

    st.divider()
    st.subheader("🔔 알림 예약")
    topic = st.text_input(
        "ntfy 알림 채널 이름", value=st.query_params.get("ntfy", ""), type="password", key="ntfy_topic",
        help="핸드폰 ntfy 앱에서 구독한 채널 이름. 입력하면 주소창 링크에 들어가니, 그 주소를 즐겨찾기하면 다음부터 자동 입력돼요")
    with st.expander("처음이라면: 핸드폰 알림 설정 방법"):
        st.markdown(
            "1. 앱스토어·플레이스토어에서 **ntfy** 설치 → 알림 **허용**\n"
            "2. 앱의 **＋** → Subscribe to topic → 채널 이름 입력 (영문·숫자·-·_, 남이 못 맞힐 만큼 길게)\n"
            "3. 같은 이름을 위 칸에 넣고 **「1분 뒤 테스트 알림」**으로 확인")
    if topic and not valid_topic(topic):
        st.error("채널 이름은 영문·숫자·-·_ 로 64자 이하여야 해요.")
    elif topic:
        if st.query_params.get("ntfy") != topic:
            st.query_params["ntfy"] = topic
        notes = plan_notifications(plan, result.servings, sc.bed_h) if plan else []
        items = schedule(notes, now_h=sc.now_h)
        if items:
            # 칸이 좁으면 마지막 열이 잘리므로 '상태'를 앞쪽에 두고 상세 내용은 알림 칸 아래 줄로
            st.dataframe(pd.DataFrame([{
                "시각": i.at.strftime("%H:%M"),
                "상태": "✅ 보낼 예정" if i.send else f"⏭️ {i.reason}",
                "알림": f"{i.notification.title} — {i.notification.message}",
            } for i in items]), hide_index=True, width="stretch")
        else:
            st.caption("예약할 알림이 없어요.")
        to_send = [i for i in items if i.send]
        b1, b2 = st.columns(2)
        sent = st.session_state.setdefault("ntfy_sent", set())
        if b1.button(f"오늘 알림 예약 ({len(to_send)}개)", type="primary", disabled=not to_send,
                     width="stretch"):
            batch_key = (topic, tuple((i.notification.title, i.at.isoformat()) for i in to_send))
            if batch_key in sent:
                st.info("같은 알림을 이미 예약했어요. (중복 방지)")
            else:
                errors = []
                for i in to_send:
                    try:
                        publish(topic, i)
                    except Exception as e:  # 인터넷·서버 오류를 화면에 보여준다
                        errors.append(f"{i.notification.title}: {e}")
                if errors:
                    st.error("일부 알림을 예약하지 못했어요.\n\n" + "\n\n".join(errors))
                else:
                    sent.add(batch_key)
                    st.success(f"{len(to_send)}개 예약했어요. 그 시각에 핸드폰으로 알림이 와요 (브라우저를 닫아도 돼요).")
        if b2.button("1분 뒤 테스트 알림", width="stretch"):
            test = schedule_test(1)
            try:
                publish(topic, test)
                st.success(f"{test.at.strftime('%H:%M')}에 테스트 알림이 와요.")
            except Exception as e:
                st.error(f"테스트 알림을 보내지 못했어요: {e}")
        st.caption("※ 플랜을 바꿔 다시 예약해도 이전 예약은 취소되지 않아 알림이 중복될 수 있어요. "
                   "채널 이름은 어디에도 저장되지 않지만, 이름을 아는 사람은 알림 내용을 볼 수 있어요.")
    else:
        st.caption("채널 이름을 넣으면 ☕ 마실 시각과 ⛔ 금지 시각에 핸드폰 알림을 예약할 수 있어요.")

    with st.expander("텍스트 카드 · 개인 설정값"):
        st.code(format_card(result), language=None)
        p = result.personal
        st.write(f"반감기 {p.half_life_h:.1f}시간 · 하루 상한 {p.daily_cap_mg:.0f}mg · "
                 f"1회 상한 {p.single_cap_mg:.0f}mg · 취침 허용 잔량 {p.residual_limit_mg:.0f}mg")
    st.download_button("입력 저장 (.yaml)", yaml.safe_dump(scenario_dict, allow_unicode=True, sort_keys=False),
                       file_name="my_day.yaml", help="scenarios 폴더에 넣으면 데모·예시로 쓸 수 있어요")
