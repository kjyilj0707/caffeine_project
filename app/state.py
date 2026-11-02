"""여러 페이지가 함께 쓰는 입력 상태 · 계산 · 서버 불러오기 (Step 4 화면 개편).

페이지(👤 프로필 · 📅 하루 입력 · ☕ 추천)를 옮겨 다니면 Streamlit은 안 보이는 페이지의 입력칸을 지운다.
그래서 입력값은 모두 st.session_state["data"] 한 곳에 두고, 각 페이지는 칸을 그릴 때 여기서 읽고
바뀌면 여기에 다시 쓴다. 서버에서 불러오거나 예시를 고르면 version을 올려 모든 칸을 새 값으로 다시 만든다.

data 구조 (시나리오 형식과 거의 같음)
  profile, sex("남성"/"여성"), sip_ml, beverage
  day: 고른 날짜 "YYYY-MM-DD"
  last_night: 그날 아침에 깬 밤 {"time": "01:30-08:00", "quality": 3, "latency_min": 15} 또는 None
  prev_nights: 그 전 밤들 (오래된 밤부터, 시나리오 sleep 형식)
  today: {"bed": "23:00", "already": [...], "windows": [졸면 안 됨·집중만 — 깨어 있기는 자동]}
  example: 예시 값인지 (내 정보를 아직 안 넣었으면 True → 화면에 안내)
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import streamlit as st
import yaml

import account
import store
from caffeine_engine.notify import current_time_h, local_tz
from caffeine_engine.pipeline import run_day
from caffeine_engine.scenario import KIND_NAMES, from_dict
from caffeine_engine.timeutil import h_to_hhmm, hhmm_to_h

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = {yaml.safe_load(p.read_text(encoding="utf-8"))["name"]: p
             for p in sorted((ROOT / "scenarios").glob("*.yaml"))}
DEFAULT = "시험 날 (23시 취침)"
DAY_ROLLOVER_H = 4   # 새벽 4시 전에는 아직 '어제 하루'로 본다 (밤늦게 쓰는 경우)
WEEKDAY = "월화수목금토일"


def kst_now() -> datetime:
    return datetime.now(local_tz())


def default_day() -> date:
    now = kst_now()
    return (now - timedelta(hours=DAY_ROLLOVER_H)).date()


def day_label(d: date) -> str:
    return f"{d.month}월 {d.day}일 ({WEEKDAY[d.weekday()]})"


def from_example(name: str) -> Dict:
    """예시 시나리오 → data. 마지막 밤 = 어젯밤, 나머지 = 그 전 밤들. 깨어 있기는 자동이라 뺀다."""
    sc = yaml.safe_load(SCENARIOS[name].read_text(encoding="utf-8"))
    nights = [n if isinstance(n, dict) else {"time": n} for n in sc["sleep"]]
    today = sc.get("today", {})
    return {
        "profile": dict(sc.get("profile", {})),
        "sex": "여성" if any(sc.get("profile", {}).get(k) for k in
                            ("pregnancy_trimester", "oral_contraceptive", "breastfeeding")) else "남성",
        "sip_ml": sc.get("sip_ml"),
        "beverage": sc.get("beverage", "coffee"),
        "day": default_day().isoformat(),
        "last_night": nights[-1],
        "prev_nights": [n if len(n) > 1 else n["time"] for n in nights[:-1]],
        "today": {"bed": today.get("bed", "23:00"), "already": list(today.get("already", [])),
                  "windows": [w for w in today.get("windows", []) if KIND_NAMES[w["kind"]] != "stay_awake"]},
        "example": True,
    }


def init() -> None:
    if "data" not in st.session_state:
        st.session_state.data = from_example(DEFAULT)
        st.session_state.version = 0


def data() -> Dict:
    return st.session_state.data


def wkey(name: str) -> str:
    """입력칸 이름. version이 바뀌면 이름이 바뀌어 칸이 data의 새 값으로 다시 만들어진다."""
    return f"{name}_{st.session_state.version}"


def refresh_widgets() -> None:
    st.session_state.version += 1


def session():
    return account.current_session()


def selected_day() -> date:
    return date.fromisoformat(data()["day"])


# ── 서버 ──
def load(day: date) -> None:
    """로그인했으면 그날 기록을 서버에서 불러와 data를 채운다. 없는 항목: 프로필은 그대로, 그날 기록은 비움."""
    s = session()
    st.session_state.loaded = (s.user_id if s else None, day.isoformat())
    d = data()
    d["day"] = day.isoformat()
    if s is None:
        return
    try:
        saved, st.session_state.load_notes = store.load_day(s, day)
    except Exception as e:  # 원인을 화면에 그대로 보여줘 바로 알 수 있게
        st.session_state.load_error = f"저장된 기록을 불러오지 못했어요: {e}"
        return
    st.session_state.pop("load_error", None)
    st.session_state.pop("recorded_days", None)
    if "profile" in saved:
        d.update(profile=saved["profile"], sex=saved["sex"], example=False)
        if saved.get("sip_ml"):
            d["sip_ml"] = saved["sip_ml"]
    if not d["example"]:  # 내 정보가 있으면 그날 기록은 서버 것만 (예시 값과 섞지 않음)
        d["last_night"] = saved.get("last_night")
        d["prev_nights"] = saved.get("prev_nights", [])
        today = saved.get("today", {})
        d["today"] = {"bed": today.get("bed", d["today"].get("bed", "23:00")),
                      "already": today.get("already", []),
                      "windows": [w for w in today.get("windows", d["today"].get("windows", []))
                                  if KIND_NAMES[w["kind"]] != "stay_awake"]}
        if "beverage" in saved:
            d["beverage"] = saved["beverage"]
    refresh_widgets()


def ensure_loaded() -> None:
    """페이지를 열 때마다 부르고, 로그인한 사람·날짜가 바뀌었을 때만 실제로 불러온다."""
    s = session()
    if st.session_state.get("loaded") != (s.user_id if s else None, data()["day"]):
        load(selected_day())


def recorded_days():
    s = session()
    if s is None:
        return []
    if "recorded_days" not in st.session_state:
        try:
            st.session_state.recorded_days = store.recorded_days(s)
        except Exception:
            st.session_state.recorded_days = []
    return st.session_state.recorded_days


# ── 계산 ──
def is_today() -> bool:
    return selected_day() == default_day()


def scenario_dict(d: Optional[Dict] = None) -> Dict:
    """data → 엔진이 읽는 시나리오 형식. 깨어 있기 = 일어난 시각 ~ 잘 시각.
    지금 시각: 오늘이면 실제 현재 시각, 다른 날이면 일어난 시각(하루 전체를 계획)."""
    d = d or data()
    night = d["last_night"]
    wake = night["time"].split("-")[1]
    now = wake
    if is_today():
        real = current_time_h() + (24 if kst_now().hour < DAY_ROLLOVER_H else 0)
        now = h_to_hhmm(max(real, hhmm_to_h(wake)))
    sleep = list(d.get("prev_nights", [])) + [night if len(night) > 1 else night["time"]]
    return {
        "name": day_label(selected_day()),
        "profile": d["profile"],
        "sleep": sleep,
        "today": {"now": now, "bed": d["today"]["bed"], "already": d["today"].get("already", []),
                  "windows": [{"kind": "깨어 있기", "from": wake, "to": d["today"]["bed"]}]
                  + d["today"].get("windows", [])},
        "beverage": d["beverage"],
        "sip_ml": float(d.get("sip_ml") or 17.5),
    }


def compute(d: Optional[Dict] = None) -> Tuple[Dict, object, object]:
    """→ (시나리오, 엔진 입력, 엔진 결과). 입력이 이상하면 ValueError."""
    sd = scenario_dict(d)
    sc = from_dict(sd)
    result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h, already=sc.already,
                     beverage=sc.beverage, sip_ml=sc.sip_ml)
    return sd, sc, result
