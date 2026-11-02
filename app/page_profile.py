"""👤 내 프로필 — 나이·몸무게·건강·카페인 민감도 (한 번 입력하면 저장)."""
import streamlit as st

import state
import store
from forms import CHRONOTYPE_LABEL, SENSITIVITY_LABEL, sensitivity_from_survey

from caffeine_engine import params

PREGNANCY = ["아니오", "임신 초기 (1~3개월)", "임신 중기 (4~6개월)", "임신 후기 (7개월~)"]

d = state.data()
prof = d["profile"]
k = state.wkey

st.title("👤 내 프로필")
st.caption("카페인이 몸에서 얼마나 빨리 빠지는지, 하루 얼마까지 괜찮은지를 정하는 정보예요. 한 번만 넣으면 돼요.")

st.subheader("기본")
c1, c2, c3 = st.columns(3)
age = c1.number_input("나이", 10, 100, int(prof.get("age", 24)), key=k("age"))
weight = c2.number_input("몸무게 (kg)", 30.0, 200.0, float(prof.get("weight_kg", 70)), 0.5, key=k("weight"))
sex = c3.radio("성별", ["남성", "여성"], index=int(d.get("sex") == "여성"), horizontal=True, key=k("sex"))

st.subheader("건강")
h1, h2 = st.columns(2)
smoker = h1.checkbox("흡연", bool(prof.get("smoker")), key=k("smoker"), help="흡연하면 카페인이 더 빨리 분해돼요")
liver = h1.checkbox("간 질환", bool(prof.get("liver_disease")), key=k("liver"))
inhibitor = h2.checkbox("카페인 분해를 늦추는 약 복용", bool(prof.get("cyp1a2_inhibitor")), key=k("inhib"),
                        help="예: 플루복사민(항우울제) 등 CYP1A2 억제제. 모르면 약사에게 확인")
heart = h2.checkbox("심장질환 · 고혈압 · 불안장애", bool(prof.get("heart_or_anxiety")), key=k("heart"))
oral_contraceptive, trimester, breastfeeding = False, None, False
if sex == "여성":
    f1, f2, f3 = st.columns([1, 1.4, 1])
    oral_contraceptive = f1.checkbox("경구피임약 복용", bool(prof.get("oral_contraceptive")), key=k("oc"),
                                     help="분해가 느려져요")
    trimester = f2.selectbox("임신", PREGNANCY, index=int(prof.get("pregnancy_trimester") or 0), key=k("preg"))
    trimester = PREGNANCY.index(trimester) or None
    breastfeeding = f3.checkbox("수유 중", bool(prof.get("breastfeeding")), key=k("bf"))

st.subheader("카페인")
how = st.radio("민감도 정하기", ["설문으로", "직접 고르기"], horizontal=True, key=k("sens_how"),
               index=1 if "sensitivity" in prof else 0)
if how == "설문으로":
    cups = st.select_slider("평소 하루 커피", [0, 1, 2, 3], value=1, key=k("cups"),
                            format_func=lambda x: "3잔 이상" if x == 3 else f"{x}잔")
    q2 = st.radio("오후 3시 이후 커피를 마시면 잠이 안 온다", ["예", "가끔", "아니오"], index=1, horizontal=True,
                  key=k("q2"))
    q3 = st.radio("커피를 마시면 두근거림·불안이 있다", ["예", "가끔", "아니오"], index=2, horizontal=True, key=k("q3"))
    sensitivity = sensitivity_from_survey(cups, q2, q3)
    st.caption(f"설문 결과: **{SENSITIVITY_LABEL[sensitivity]}**")
else:
    options = list(SENSITIVITY_LABEL)
    sensitivity = st.radio("민감도", options, index=options.index(prof.get("sensitivity", "normal")),
                           format_func=SENSITIVITY_LABEL.get, horizontal=True, key=k("sens"))
chrono_options = list(CHRONOTYPE_LABEL)
chronotype = st.radio("생활 리듬", chrono_options, index=chrono_options.index(prof.get("chronotype", "neutral")),
                      format_func=CHRONOTYPE_LABEL.get, horizontal=True, key=k("chrono"))
c1, c2 = st.columns(2)
cap = c1.number_input("하루 최대량 직접 정하기 (mg, 0 = 권고량 그대로)", 0, 1000, int(prof.get("daily_cap_mg") or 0), 25,
                      key=k("cap"))
sip_ml = c2.number_input("한 모금 (ml)", 5.0, 50.0, float(d.get("sip_ml") or params.value("conversion", "sip_ml")),
                         0.5, key=k("sip"), help="보통 15~20ml. 컵에 물을 담아 10모금 마신 양 ÷ 10으로 재 볼 수 있어요")

# 입력값을 공용 data에 반영 (다른 페이지가 이 값으로 계산)
new_profile = {"age": int(age), "weight_kg": float(weight), "smoker": smoker,
               "oral_contraceptive": oral_contraceptive, "pregnancy_trimester": trimester,
               "breastfeeding": breastfeeding, "liver_disease": liver, "cyp1a2_inhibitor": inhibitor,
               "heart_or_anxiety": heart, "sensitivity": sensitivity, "chronotype": chronotype}
if cap:
    new_profile["daily_cap_mg"] = float(cap)
d.update(profile=new_profile, sex=sex, sip_ml=float(sip_ml))

st.divider()
s = state.session()
if s is None:
    st.caption("로그인하지 않으면 이 화면을 닫을 때 입력이 사라져요. 화면 맨 위에서 로그인하면 저장할 수 있어요.")
    st.page_link("page_day.py", label="다음: 📅 하루 입력 →")
elif st.button("💾 프로필 저장", type="primary"):
    try:
        store.save_profile(s, new_profile, sex, float(sip_ml), state.selected_day().year)
        d["example"] = False
        st.success("저장했어요. 다음에 열면 자동으로 채워져요.")
        st.page_link("page_day.py", label="다음: 📅 하루 입력 →")
    except Exception as e:
        st.error(f"저장하지 못했어요: {e}")
