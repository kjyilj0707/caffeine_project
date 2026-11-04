"""프로필 / 설정 — 첫 화면은 항목 목록(기본 · 건강 · 카페인 · 화면)만, 누르면 그 항목 화면으로 넘어간다.

고친 값은 바로 계산에 쓰지 않고 '임시본(draft)'에 모아 두었다가 [설정 반영하기]를 누르면 반영한다
(로그인했으면 서버에도 저장). 화면 모드는 고르는 즉시 바뀐다 (새로고침).
"""
import streamlit as st

import dial
import state
import store
import theme
from forms import CHRONOTYPE_LABEL, SENSITIVITY_LABEL, sensitivity_from_survey

from caffeine_engine import params

PREGNANCY = ["아니오", "임신 초기 (1~3개월)", "임신 중기 (4~6개월)", "임신 후기 (7개월~)"]
SECTIONS = {"basic": ("기본", ":material/person:"), "health": ("건강", ":material/favorite:"),
            "caffeine": ("카페인", ":material/local_cafe:"), "display": ("화면", ":material/contrast:")}
CAP_OPTIONS = ["권고량"] + list(range(50, 1001, 25))

d = state.data()
k = state.wkey
s = state.session()

# ── 임시본: 화면에서 고친 값은 여기에 모았다가 [설정 반영하기]로 d에 넣는다 ──
if st.session_state.get("draft_version") != st.session_state.version:
    st.session_state.profile_draft = {"profile": dict(d["profile"]), "sex": d.get("sex", "남성")}
    st.session_state.draft_version = st.session_state.version
draft = st.session_state.profile_draft
prof = draft["profile"]
dirty = draft["profile"] != d["profile"] or draft["sex"] != d.get("sex", "남성")

st.html("""<style>
.st-key-settings_list button { justify-content: flex-start; padding: 14px 16px; border-radius: 14px; min-height: 56px; }
.st-key-settings_list button p { font-size: 16px; }
.st-key-settings_list button::after { content: "›"; margin-left: auto; font-size: 22px; opacity: .45; }
</style>""")


def header(title: str, back: bool) -> None:
    with st.container(horizontal=True, vertical_alignment="center"):
        if back:
            if st.button("", icon=":material/chevron_left:", key="settings_back", type="tertiary"):
                st.session_state.profile_section = None
                st.rerun()
        st.markdown(f"<div style='text-align:center;font-size:17px;font-weight:600;margin:-4px 0 6px'>{title}</div>",
                    unsafe_allow_html=True, width="stretch")
        if back:
            st.markdown("<div style='width:32px'></div>", unsafe_allow_html=True, width="content")


def apply_button() -> None:
    """[설정 반영하기] — 하루 입력의 [저장하고 추천 보기]처럼 맨 아래 큰 버튼."""
    st.divider()
    if dirty:
        st.caption("아직 반영하지 않은 변경이 있어요.")
    if st.button("설정 반영하기", type="primary", width="stretch", key="apply_settings", disabled=not dirty):
        d.update(profile=dict(draft["profile"]), sex=draft["sex"])
        if s is not None:
            try:
                store.save_profile(s, d["profile"], d["sex"], float(d.get("sip_ml") or params.value("conversion", "sip_ml")),
                                   state.selected_day().year)
                d["example"] = False
            except Exception as e:
                st.error(f"저장하지 못했어요: {e}")
                st.stop()
        st.session_state.pop("report_cache", None)
        st.toast("반영했어요" + (" · 저장됨" if s is not None else ""))
        st.rerun()
    if s is None:
        st.caption("로그인하지 않으면 이 화면을 닫을 때 설정이 사라져요. 화면 맨 위에서 로그인하면 저장돼요.")


def summary(section: str) -> str:
    if section == "basic":
        return f"{prof.get('age', 24)}세 · {prof.get('weight_kg', 70):g}kg · {draft['sex']}"
    if section == "health":
        flags = [name for key, name in [("smoker", "흡연"), ("liver_disease", "간 질환"), ("cyp1a2_inhibitor", "약 복용"),
                                         ("heart_or_anxiety", "심장·불안"), ("oral_contraceptive", "피임약"),
                                         ("breastfeeding", "수유")] if prof.get(key)]
        if prof.get("pregnancy_trimester"):
            flags.append("임신")
        return " · ".join(flags) or "해당 없음"
    if section == "caffeine":
        cap = f"{prof['daily_cap_mg']:g}mg" if prof.get("daily_cap_mg") else "권고량"
        return f"민감도 {SENSITIVITY_LABEL[prof.get('sensitivity', 'normal')]} · 하루 최대 {cap}"
    return theme.saved_mode()


section = st.session_state.get("profile_section")

# ── 첫 화면: 항목 목록 ──
if section is None:
    header("프로필 / 설정", back=False)
    st.caption("카페인이 몸에서 얼마나 빨리 빠지는지, 하루 얼마까지 괜찮은지를 정하는 정보예요.")
    with st.container(key="settings_list"):
        for key, (title, icon) in SECTIONS.items():
            if st.button(f"**{title}** · {summary(key)}", icon=icon, width="stretch", key=f"open_{key}"):
                st.session_state.profile_section = key
                st.rerun()
    if dirty:
        apply_button()
    st.divider()
    if s is None:
        st.caption("로그인 안 됨 — 화면 맨 위에서 이메일로 로그인하면 입력이 저장돼요.")
    else:
        st.caption(f"{s.email} 로그인됨")
        if st.session_state.get("load_error"):
            st.error(st.session_state.load_error)
    if d["example"]:
        with st.expander("예시로 채워 보기"):
            preset = st.selectbox("예시", list(state.SCENARIOS), index=list(state.SCENARIOS).index(state.DEFAULT),
                                  label_visibility="collapsed", key="example_preset")
            if st.button("이 예시로 채우기", width="stretch", key="example_fill"):
                st.session_state.data = state.from_example(preset)
                state.refresh_widgets()
                st.rerun()
    st.caption("※ 의학적 조언이 아니에요. 평균적인 성인 기준 예측입니다.")
    st.stop()

header(SECTIONS[section][0], back=True)

# ── 기본: 나이 · 몸무게 휠, 성별 ──
if section == "basic":
    prof["age"] = int(dial.number_wheel("나이", int(prof.get("age", 24)), range(10, 101), "세", key=k("age")))
    prof["weight_kg"] = float(dial.number_wheel("몸무게", int(round(prof.get("weight_kg", 70))), range(30, 151), "kg",
                                                key=k("weight")))
    draft["sex"] = st.radio("성별", ["남성", "여성"], index=int(draft["sex"] == "여성"), horizontal=True, key=k("sex"))
    if draft["sex"] == "남성":   # 여성 전용 항목은 끈다
        prof.update(oral_contraceptive=False, pregnancy_trimester=None, breastfeeding=False)

# ── 건강 ──
elif section == "health":
    prof["smoker"] = st.checkbox("흡연", bool(prof.get("smoker")), key=k("smoker"), help="흡연하면 카페인이 더 빨리 분해돼요")
    prof["liver_disease"] = st.checkbox("간 질환", bool(prof.get("liver_disease")), key=k("liver"))
    prof["cyp1a2_inhibitor"] = st.checkbox("카페인 분해를 늦추는 약 복용", bool(prof.get("cyp1a2_inhibitor")), key=k("inhib"),
                                           help="예: 플루복사민(항우울제) 등 CYP1A2 억제제. 모르면 약사에게 확인")
    prof["heart_or_anxiety"] = st.checkbox("심장질환 · 고혈압 · 불안장애", bool(prof.get("heart_or_anxiety")), key=k("heart"))
    if draft["sex"] == "여성":
        prof["oral_contraceptive"] = st.checkbox("경구피임약 복용", bool(prof.get("oral_contraceptive")), key=k("oc"),
                                                 help="분해가 느려져요")
        preg = st.selectbox("임신", PREGNANCY, index=int(prof.get("pregnancy_trimester") or 0), key=k("preg"))
        prof["pregnancy_trimester"] = PREGNANCY.index(preg) or None
        prof["breastfeeding"] = st.checkbox("수유 중", bool(prof.get("breastfeeding")), key=k("bf"))
    else:
        st.caption("여성이면 피임약 · 임신 · 수유 항목이 더 나와요 (기본에서 성별을 바꿔 주세요).")

# ── 카페인: 민감도 · 생활 리듬 · 하루 최대량 휠 ──
elif section == "caffeine":
    how = st.radio("민감도 정하기", ["설문으로", "직접 고르기"], horizontal=True, key=k("sens_how"),
                   index=1 if "sensitivity" in prof else 0)
    if how == "설문으로":
        cups = st.select_slider("평소 하루 커피", [0, 1, 2, 3], value=1, key=k("cups"),
                                format_func=lambda x: "3잔 이상" if x == 3 else f"{x}잔")
        q2 = st.radio("오후 3시 이후 커피를 마시면 잠이 안 온다", ["예", "가끔", "아니오"], index=1, horizontal=True,
                      key=k("q2"))
        q3 = st.radio("커피를 마시면 두근거림·불안이 있다", ["예", "가끔", "아니오"], index=2, horizontal=True, key=k("q3"))
        prof["sensitivity"] = sensitivity_from_survey(cups, q2, q3)
        st.caption(f"설문 결과: **{SENSITIVITY_LABEL[prof['sensitivity']]}**")
    else:
        options = list(SENSITIVITY_LABEL)
        prof["sensitivity"] = st.radio("민감도", options, index=options.index(prof.get("sensitivity", "normal")),
                                       format_func=SENSITIVITY_LABEL.get, horizontal=True, key=k("sens"))
    chrono = list(CHRONOTYPE_LABEL)
    prof["chronotype"] = st.radio("생활 리듬", chrono, index=chrono.index(prof.get("chronotype", "neutral")),
                                  format_func=CHRONOTYPE_LABEL.get, horizontal=True, key=k("chrono"))
    cap0 = int(prof["daily_cap_mg"]) if prof.get("daily_cap_mg") else "권고량"
    cap = dial.number_wheel("하루 최대량 직접 정하기", cap0, CAP_OPTIONS, "mg", key=k("cap"))
    if cap == "권고량":
        prof.pop("daily_cap_mg", None)
    else:
        prof["daily_cap_mg"] = float(cap)
    st.caption("권고량 = 성인 400mg · 임신 300mg · 수유 200mg · 청소년 몸무게 1kg당 2.5mg (식약처·EFSA). "
               "직접 정하면 권고량보다 낮은 쪽을 써요.")

# ── 화면: 다크 / 라이트 (고르는 즉시 새로고침) ──
elif section == "display":
    def _pick_theme():
        st.session_state.apply_theme = st.session_state.theme_mode

    st.radio("화면 모드", list(theme.MODES), index=list(theme.MODES).index(theme.saved_mode()), key="theme_mode",
             on_change=_pick_theme, horizontal=True)
    st.caption("고르면 화면을 새로 불러와요. 시스템 설정 = 핸드폰·컴퓨터의 다크 모드 설정을 따라감")
    if st.session_state.get("apply_theme"):
        theme.apply(st.session_state.pop("apply_theme"))
    st.stop()

apply_button()
