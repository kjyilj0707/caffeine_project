"""오늘의 추천 — 몇 시에 몇 모금, 언제부터 금지. 로그인하면 앱 알림 예약·졸림 기록.
그래프·자세한 수치는 아래에서 펼쳐 본다."""
import pandas as pd
import streamlit as st
import yaml

import state
import store
import timer_view
from charts import build_charts, build_frames
from forms import KSS_LABEL, amount_text
from ntfy import publish, valid_topic

from caffeine_engine.notify import (current_time_h, feedback_notifications, plan_notifications, schedule,
                                    schedule_test)
from caffeine_engine.pipeline import format_card
from caffeine_engine.timeutil import h_to_hhmm

d = state.data()
day = state.selected_day()
s = state.session()

# 큰 제목 대신 작은 날짜 줄 — 타이머 링이 화면 가운데를 채우게
st.markdown(f"<div style='text-align:center;font-size:15px;color:#8a8a8f;margin:-4px 0 4px'>"
            f"{state.day_label(day)} · 오늘 추천</div>", unsafe_allow_html=True)
if st.session_state.pop("just_saved", False):
    st.toast("저장했어요")
if d.get("last_night") is None:
    st.warning(f"{state.day_label(day)}의 어젯밤 잠 기록이 없어요. 잠든·깬 시각을 넣어야 계산할 수 있어요.")
    st.page_link("page_day.py", label="하루 입력으로 가기 →")
    st.stop()

try:
    sd, sc, result = state.compute()
except ValueError as e:
    st.error(f"입력을 확인해 주세요: {e}")
    st.page_link("page_day.py", label="하루 입력에서 고치기 →")
    st.stop()
plan = result.plan
if plan is None:
    for note in result.notes:
        st.error(note)
    st.stop()

# ── 메인: 타이머 (다음 일정까지 남은 시간, 가운데 큰 링) ──
bev_name = sc.beverage.name
dark = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
timer_view.render(day, sc.sleeps[-1].end_h, timer_view.events(day, plan, result.servings, bev_name, sc.bed_h),
                  live=state.is_today(), dark=dark)
if not result.servings:
    st.caption("오늘은 더 마시지 않는 게 좋아요 — 이미 마신 양이나 잘 시각을 보면 잠을 방해할 가능성이 커요.")
else:
    st.caption(f"{bev_name} 기준 · 한 번에 들이켜지 말고 정해진 시간 동안 나눠 마시기"
               + (f" · {h_to_hhmm(plan.last_dose_h)} 이후엔 추천 외 카페인 금지" if plan.last_dose_h is not None else ""))
if d["example"]:
    st.info("지금은 **예시 값**으로 보여주고 있어요. **프로필 → 하루 입력** 순서로 내 정보를 넣으면 "
            "나에게 맞는 추천이 나와요.")

already = sd["today"]["already"]
if already:
    st.caption("이미 마신 것: " + " · ".join(f"{a['time']} {amount_text(a)}" for a in already))
st.caption(f"오늘 총 {result.cap.total_mg:.0f}mg (하루 상한의 {result.cap.ratio * 100:.0f}%) · "
           f"졸면 안 되는 시간의 졸림 −{plan.sleepiness_reduction * 100:.0f}% · "
           f"예상 수면 감소 {max(plan.sleep_loss_min, 0):.0f}분")
if result.cap.level != "ok":
    st.warning(f"오늘 섭취가 하루 상한의 {result.cap.ratio * 100:.0f}%예요.")
for note in result.notes:
    st.warning(note)
st.page_link("page_day.py", label="입력 고치기 (잠 · 마신 것 · 일정 · 음료) →")

# ── 앱 알림 (로그인 + 오늘) — 서버가 그 시각에 핸드폰으로 보낸다 (브라우저를 닫아도 됨) ──
KIND_SHORT = {"drink": "마시기", "stop": "금지 시작", "feedback": "졸림 묻기", "test": "테스트"}
STATUS = {"pending": "대기", "sending": "보내는 중", "sent": "보냄 ✓", "failed": "실패"}
if s is not None and state.is_today():
    st.divider()
    st.subheader("알림")
    if "push_devices" not in st.session_state:
        try:
            st.session_state.push_devices = store.push_devices(s)
        except Exception as e:
            st.session_state.push_devices = []
            st.error(f"알림 기기를 확인하지 못했어요: {e}")
    plan_items = sorted([i for i in schedule(plan_notifications(plan, result.servings, sc.bed_h)
                                             + feedback_notifications(sc.windows), now_h=sc.now_h) if i.send],
                        key=lambda i: i.at)
    if not st.session_state.push_devices:
        st.info("먼저 화면 맨 위 **알림 켜기**를 눌러 이 기기에서 알림을 허용해 주세요.  \n"
                "아이폰은 사파리 아래 **[공유] → [홈 화면에 추가]** 한 뒤, 홈 화면의 '카페인' 앱을 열어 켜야 해요.")
        if st.button("알림 켰어요 — 다시 확인"):
            st.session_state.pop("push_devices", None)
            st.rerun()
    else:
        st.caption(f"알림 받을 기기 {len(st.session_state.push_devices)}대 · 브라우저를 닫아도 그 시각에 와요")
        if plan_items:
            st.markdown(" · ".join(f"**{i.at:%H:%M}** {KIND_SHORT[i.notification.kind]}" for i in plan_items))
        b1, b2 = st.columns(2)
        if b1.button(f"이 추천으로 알림 받기 ({len(plan_items)}개)", type="primary", disabled=not plan_items,
                     width="stretch", help="다시 누르면 아직 안 보낸 예전 알림은 취소되고 새 추천으로 바뀌어요"):
            try:
                n = store.schedule_push(s, plan_items, day)
                st.session_state.pop("push_scheduled", None)
                st.success(f"{n}개 예약했어요.")
            except Exception as e:
                st.error(f"예약하지 못했어요: {e}")
        if b2.button("1분 뒤 테스트 알림", width="stretch"):
            try:
                test = schedule_test(1)
                store.push_test(s, test)
                st.session_state.pop("push_scheduled", None)
                st.success(f"{test.at:%H:%M}쯤 테스트 알림이 와요 (최대 1분 늦을 수 있어요).")
            except Exception as e:
                st.error(f"테스트 알림을 예약하지 못했어요: {e}")
        if "push_scheduled" not in st.session_state:
            try:
                st.session_state.push_scheduled = store.scheduled_notifications(s, day)
            except Exception:
                st.session_state.push_scheduled = []
        if st.session_state.push_scheduled:
            st.caption("예약된 알림: " + " · ".join(
                f"{r['time']} {KIND_SHORT.get(r['kind'], r['kind'])} ({STATUS.get(r['status'], r['status'])})"
                for r in st.session_state.push_scheduled))

# ── 지금 졸림 기록 (로그인했을 때) ──
if s is not None and state.is_today():
    st.divider()
    st.subheader("지금 얼마나 졸려요?")
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
            st.session_state.pop("report_cache", None)
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
with st.expander("그래프로 보기 — 몸속 카페인 · 졸림 정도"):
    top_chart, bottom_chart = build_charts(build_frames(sc, result))
    st.altair_chart(top_chart)
    st.altair_chart(bottom_chart)
    st.caption("그래프에 마우스를 올리면 그 시각의 값을 볼 수 있어요. "
               "회색 띠 = 졸면 안 됨·집중 시간대, 점선 = 취침·금지 시각")

with st.expander("자세한 수치"):
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

# 로그인 안 한 사람용: ntfy 앱으로 받기 (로그인하면 위의 앱 알림을 쓴다)
if s is None:
    with st.expander("핸드폰 알림 받기 (ntfy 앱 · 로그인 없이)", expanded=bool(st.query_params.get("ntfy"))):
        st.caption("로그인하면 앱 설치 없이 바로 알림을 받을 수 있어요. 로그인 없이 쓰려면 ntfy 앱으로 받아요.")
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
                    "상태": "보낼 예정" if i.send else f"건너뜀 · {i.reason}",
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
