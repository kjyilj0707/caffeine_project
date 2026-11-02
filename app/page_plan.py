"""☕ 오늘의 추천 — 몇 시에 몇 모금, 언제부터 금지. 그래프·자세한 수치·알림은 아래에서 펼쳐 본다."""
import pandas as pd
import streamlit as st
import yaml

import state
import store
from charts import build_charts, build_frames
from forms import KSS_LABEL
from ntfy import publish, valid_topic

from caffeine_engine.notify import current_time_h, plan_notifications, schedule, schedule_test
from caffeine_engine.pipeline import format_card
from caffeine_engine.timeutil import h_to_hhmm

d = state.data()
day = state.selected_day()
s = state.session()

st.title(f"☕ {state.day_label(day)} 추천")
if st.session_state.pop("just_saved", False):
    st.toast("저장했어요", icon="☁️")
if d["example"]:
    st.info("지금은 **예시 값**으로 보여주고 있어요. **👤 내 프로필 → 📅 하루 입력** 순서로 내 정보를 넣으면 "
            "나에게 맞는 추천이 나와요.")
if d.get("last_night") is None:
    st.warning(f"{state.day_label(day)}의 어젯밤 잠 기록이 없어요. 잠든·깬 시각을 넣어야 계산할 수 있어요.")
    st.page_link("page_day.py", label="📅 하루 입력으로 가기", icon="➡️")
    st.stop()

try:
    sd, sc, result = state.compute()
except ValueError as e:
    st.error(f"입력을 확인해 주세요: {e}")
    st.page_link("page_day.py", label="📅 하루 입력에서 고치기", icon="➡️")
    st.stop()
plan = result.plan
if plan is None:
    for note in result.notes:
        st.error(note)
    st.stop()

# ── 메인: 몇 시에 몇 모금 ──
next_i = 0 if state.is_today() else None    # 오늘이면 첫 잔이 '다음에 마실 잔' (추천은 지금 이후만 나옴)
bev_name = sc.beverage.name
if result.servings:
    st.caption(f"{bev_name} 기준 · 모금 = 한 모금 {sd['sip_ml']:g}ml")
    for i, (dose, serving) in enumerate(zip(plan.new_doses, result.servings)):
        with st.container(border=True):
            c1, c2 = st.columns([1, 1.25], vertical_alignment="center")
            badge = " :orange-badge[다음]" if i == next_i else ""
            c1.markdown(f"<div style='font-size:2.6rem;font-weight:700;line-height:1.1'>{h_to_hhmm(dose.time_h)}</div>",
                        unsafe_allow_html=True)
            c2.markdown(f"<div style='font-size:2rem;font-weight:700;line-height:1.1'>☕ {serving.sips}모금</div>",
                        unsafe_allow_html=True)
            c2.caption(f"약 {serving.ml:.0f}ml · {serving.mg_actual:.0f}mg{badge}")
else:
    with st.container(border=True):
        st.markdown("<div style='font-size:1.6rem;font-weight:700'>오늘은 더 마시지 않는 게 좋아요</div>",
                    unsafe_allow_html=True)
        st.caption("이미 마신 양이나 잘 시각을 보면, 더 마시면 잠을 방해할 가능성이 커요.")

stops = []
if plan.last_dose_h is not None and result.servings:
    stops.append(f"🔕 **{h_to_hhmm(plan.last_dose_h)}** 이후엔 추천 외 카페인 금지")
if plan.cutoff_h is not None:
    stops.append(f"⛔ **{h_to_hhmm(plan.cutoff_h)}부터는 한 모금도 금지** (잠 보호)")
if stops:
    st.markdown("  \n".join(stops))

already = sd["today"]["already"]
if already:
    st.caption("이미 마신 것: " + " · ".join(f"{a['time']} {a['sips']:g}모금" if "sips" in a else
                                          f"{a['time']} {a['mg']:g}mg" for a in already))
st.caption(f"오늘 총 {result.cap.total_mg:.0f}mg (하루 상한의 {result.cap.ratio * 100:.0f}%) · "
           f"졸면 안 되는 시간의 졸림 −{plan.sleepiness_reduction * 100:.0f}% · "
           f"예상 수면 감소 {max(plan.sleep_loss_min, 0):.0f}분")
if result.cap.level != "ok":
    st.warning(f"오늘 섭취가 하루 상한의 {result.cap.ratio * 100:.0f}%예요.")
for note in result.notes:
    st.warning(note)
st.page_link("page_day.py", label="입력 고치기 (잠 · 마신 것 · 일정 · 음료)", icon="📅")

# ── 지금 졸림 기록 (로그인했을 때) ──
if s is not None and state.is_today():
    st.divider()
    st.subheader("📝 지금 얼마나 졸려요?")
    st.caption("수업·시험처럼 중요한 시간에 남겨 주세요. 예측과 실제를 비교해 나중에 나에게 맞게 보정하는 데 써요.")
    kss = st.select_slider("졸림 (1~9)", options=list(range(1, 10)), value=5, key="kss",
                           format_func=lambda x: f"{x} · {KSS_LABEL[x]}" if x in KSS_LABEL else str(x))
    k1, k2 = st.columns([3, 1])
    kss_note = k1.text_input("메모 (선택)", key="kss_note", placeholder="예: 시험 직전, 커피 2잔째",
                             label_visibility="collapsed")
    if k2.button("기록", width="stretch"):
        try:
            store.add_sleepiness(s, kss, kss_note)
            st.session_state.pop("kss_today", None)   # 아래 '오늘 기록'을 다시 불러오게
            st.success(f"기록했어요: {h_to_hhmm(current_time_h())} 즈음 졸림 {kss}")
        except Exception as e:
            st.error(f"기록하지 못했어요: {e}")
    if "kss_today" not in st.session_state:
        try:
            st.session_state.kss_today = store.today_sleepiness(s)
        except Exception:
            st.session_state.kss_today = []
    if st.session_state.kss_today:
        st.caption("오늘 기록: " + " · ".join(f"{r['time']} → {r['kss']}" for r in st.session_state.kss_today))

# ── 더 보기 (펼쳐서) ──
st.divider()
with st.expander("📈 그래프로 보기 — 몸속 카페인 · 졸림 정도"):
    top_chart, bottom_chart = build_charts(build_frames(sc, result))
    st.altair_chart(top_chart)
    st.altair_chart(bottom_chart)
    st.caption("그래프에 마우스를 올리면 그 시각의 값을 볼 수 있어요. "
               "회색 띠 = 졸면 안 됨·집중 시간대, 점선 = 취침·금지 시각")

with st.expander("📊 자세한 수치"):
    m1, m2 = st.columns(2)
    m3, m4 = st.columns(2)
    m1.metric(f"오늘 총 섭취 (상한 {result.cap.cap_mg:.0f}mg)",
              f"{result.cap.total_mg:.0f}mg · {result.cap.ratio * 100:.0f}%")
    m2.metric(f"잠든 뒤 최대 잔량 (기준 {result.personal.residual_limit_mg:.0f}mg 이하)",
              f"{plan.max_residual_mg:.1f}mg")
    m3.metric("예상 수면 감소 (기준 20분 미만)", f"{max(plan.sleep_loss_min, 0):.1f}분")
    m4.metric(f"목표 구간 졸림 (수면 부채 {result.sleep_debt_h:.1f}시간)", f"−{plan.sleepiness_reduction * 100:.0f}%")
    p = result.personal
    st.caption(f"내 반감기 {p.half_life_h:.1f}시간 · 하루 상한 {p.daily_cap_mg:.0f}mg · 1회 상한 {p.single_cap_mg:.0f}mg · "
               f"잠들 때 허용 잔량 {p.residual_limit_mg:.0f}mg")
    st.code(format_card(result), language=None)
    st.download_button("입력 내려받기 (.yaml)", yaml.safe_dump(sd, allow_unicode=True, sort_keys=False),
                       file_name="my_day.yaml", help="scenarios 폴더에 넣으면 데모·예시로 쓸 수 있어요")

with st.expander("🔔 핸드폰 알림 받기 (ntfy · 임시)", expanded=bool(st.query_params.get("ntfy"))):
    st.caption("곧 앱 자체 알림으로 바뀔 예정이에요. 지금은 ntfy 앱으로 받아요.")
    topic = st.text_input(
        "ntfy 알림 채널 이름", value=st.query_params.get("ntfy", ""), type="password", key="ntfy_topic",
        help="핸드폰 ntfy 앱에서 구독한 채널 이름. 입력하면 주소창 링크에 들어가니, 그 주소를 즐겨찾기하면 다음부터 자동 입력돼요")
    st.markdown(
        "1. 앱스토어·플레이스토어에서 **ntfy** 설치 → 알림 **허용**\n"
        "2. 앱의 **＋** → Subscribe to topic → 채널 이름 입력 (영문·숫자·-·_, 남이 못 맞힐 만큼 길게)\n"
        "3. 같은 이름을 위 칸에 넣고 **「1분 뒤 테스트 알림」**으로 확인")
    if topic and not valid_topic(topic):
        st.error("채널 이름은 영문·숫자·-·_ 로 64자 이하여야 해요.")
    elif topic and not state.is_today():
        st.caption("알림은 오늘 추천에만 예약할 수 있어요.")
    elif topic:
        if st.query_params.get("ntfy") != topic:
            st.query_params["ntfy"] = topic
        # 링크 복사 중 이름이 잘리는 실수가 실제로 있었음 → 끝자리를 보여줘 ntfy 앱과 비교하게
        st.caption(f"채널 끝 4자리: **…{topic[-4:]}** ({len(topic)}자) — 핸드폰 ntfy 앱의 채널 이름과 같은지 확인하세요")
        items = schedule(plan_notifications(plan, result.servings, sc.bed_h), now_h=sc.now_h)
        if items:
            st.dataframe(pd.DataFrame([{
                "시각": i.at.strftime("%H:%M"),
                "상태": "✅ 보낼 예정" if i.send else f"⏭️ {i.reason}",
                "알림": f"{i.notification.title} — {i.notification.message}",
            } for i in items]), hide_index=True, width="stretch")
        to_send = [i for i in items if i.send]
        b1, b2 = st.columns(2)
        sent = st.session_state.setdefault("ntfy_sent", set())
        if b1.button(f"오늘 알림 예약 ({len(to_send)}개)", type="primary", disabled=not to_send, width="stretch"):
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
        st.caption("※ 플랜을 바꿔 다시 예약해도 이전 예약은 취소되지 않아 알림이 중복될 수 있어요.")
