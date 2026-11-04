"""화면 모드 (시스템 설정 / 라이트 / 다크) + 앱 강조색(초록).

테마 전환은 Streamlit 기본 테마를 그대로 쓴다 (입력칸·표까지 한꺼번에 바뀜). Streamlit은 고른 테마를
브라우저 저장소 'stActiveTheme-{주소}-v1'에 페이지 주소마다 따로 기억하므로, 고르면 모든 페이지 주소에 같은 값을
써 넣고 새로고침한다. 서버 설정에 사용자 테마(primaryColor)를 두면 저장한 테마가 무시되므로,
강조색은 설정 대신 아래 CSS로 덮어쓴다 (Streamlit 1.50 기준 선택자).
"""
import json

import streamlit as st
import streamlit.components.v1 as components

ACCENT = "#34C759"
MODES = {"시스템 설정": "Use system setting", "라이트": "Light", "다크": "Dark"}
COOKIE = "caffeine_theme"
PAGES = ["", "page_plan", "page_day", "page_report", "page_drinks", "page_profile"]

ACCENT_CSS = f"""
<style>
[data-testid="stBaseButton-segmented_controlActive"], [data-testid="stBaseButton-pillsActive"] {{
  color: {ACCENT} !important; border-color: {ACCENT} !important; outline-color: {ACCENT} !important;
  background-color: rgba(52, 199, 89, .12) !important; }}
[data-testid="stBaseButton-segmented_controlActive"] *, [data-testid="stBaseButton-pillsActive"] * {{ color: {ACCENT} !important; }}
[data-testid="stBaseButton-primary"] {{ background-color: {ACCENT} !important; border-color: {ACCENT} !important; color: #fff !important; }}
[data-testid="stBaseButton-primary"] * {{ color: #fff !important; }}
[data-testid="stBaseButton-primary"]:hover {{ filter: brightness(.94); }}
[data-testid="stBaseButton-primary"]:disabled {{ opacity: .35; cursor: not-allowed; filter: none; }}
label[data-baseweb="radio"]:has(input:checked) > div:first-child {{ background-color: {ACCENT} !important; }}
label[data-baseweb="checkbox"]:has(input:checked) > span {{ background-color: {ACCENT} !important; border-color: {ACCENT} !important; }}
[data-testid="stSlider"] [role="slider"] {{ background-color: {ACCENT} !important; }}
[data-testid="stSliderThumbValue"] {{ color: {ACCENT} !important; }}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, [data-baseweb="textarea"]:focus-within {{
  border-color: {ACCENT} !important; }}
a[data-testid="stPageLink-NavLink"]:focus-visible {{ outline-color: {ACCENT} !important; }}
</style>
"""


def accent() -> None:
    st.html(ACCENT_CSS)


def saved_mode() -> str:
    """지난번에 고른 모드 (쿠키). 없으면 '시스템 설정'."""
    try:
        value = st.context.cookies.get(COOKIE)
    except Exception:
        value = None
    return next((k for k, v in MODES.items() if v == value), "시스템 설정")


def apply(mode: str) -> None:
    """모든 페이지 주소에 테마를 저장하고 새로고침 (부모 창 = 앱 화면)."""
    name = json.dumps(json.dumps({"name": MODES[mode]}))
    pages = json.dumps(PAGES)
    components.html(f"""<script>
    const w = window.parent, base = w.location.pathname.replace(/[^/]*$/, "");
    for (const p of {pages}) {{
      for (const path of [base + p, (base + p).replace(/\\/$/, "") || "/"]) {{
        try {{ w.localStorage.setItem(`stActiveTheme-${{path}}-v1`, {name}); }} catch (e) {{}}
      }}
    }}
    w.document.cookie = "{COOKIE}={MODES[mode]}; path=/; max-age=31536000; SameSite=Lax";
    w.location.reload();
    </script>""", height=0)
