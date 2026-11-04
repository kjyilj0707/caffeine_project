"""아래 탭 바 — 인스타그램·네이버 웹툰·러닝 앱처럼 화면 맨 아래에 고정된 아이콘 메뉴.

왼쪽 사이드바 메뉴는 숨기고(st.navigation position="hidden"), 페이지 링크 5개를 가로로 놓은 뒤 CSS로
화면 아래에 고정한다. 아이콘 위 · 글자 아래, 지금 페이지만 진하게.
페이지가 st.stop()으로 일찍 끝나도 바는 보이도록 nav.run() 전에 그린다.
"""
import streamlit as st

import theme

# (파일, 탭 글자, 아이콘) — 왼쪽부터. 프로필은 다른 앱들처럼 맨 오른쪽
TABS = [
    ("page_plan.py", "오늘 추천", ":material/home:"),
    ("page_day.py", "하루 입력", ":material/edit_calendar:"),
    ("page_report.py", "리포트", ":material/bar_chart:"),
    ("page_drinks.py", "브랜드별", ":material/local_cafe:"),
    ("page_profile.py", "설정", ":material/person:"),
]
BAR_H = 64  # px, 본문 아래 여백도 이만큼 + α

_CSS = """
<style>
/* 위쪽 빈 머리 영역 없애고, 아래 탭 바에 본문이 가리지 않게 여백 */
header[data-testid="stHeader"] { display: none; }
[data-testid="stMainBlockContainer"] { padding-top: 1.5rem; padding-bottom: __PAD__px; }

.st-key-tabbar {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 999990;
  height: calc(__H__px + env(safe-area-inset-bottom)); padding: 0 4px env(safe-area-inset-bottom);
  background: __BG__; border-top: 1px solid __LINE__;
  display: flex; flex-direction: row; flex-wrap: nowrap; align-items: center; gap: 0 !important;
}
/* 탭 5칸을 똑같은 폭으로, 아이콘·글자는 칸 가운데 */
.st-key-tabbar [class*="st-key-tabon_"], .st-key-tabbar [class*="st-key-taboff_"] {
  flex: 1 1 0 !important; width: auto !important; min-width: 0 !important; height: 100%;
  display: flex; align-items: center; justify-content: center;
}
.st-key-tabbar [data-testid="stPageLink"] { width: 100%; height: 100%; }
.st-key-tabbar a {
  height: 100%; margin: 0 !important; padding: 6px 0 !important; border-radius: 0 !important;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  background: transparent !important; text-decoration: none;
}
.st-key-tabbar a [data-testid="stIconMaterial"] { font-size: 26px; margin: 0 !important; color: __OFF__; }
.st-key-tabbar a p { font-size: 11px; line-height: 1.2; white-space: nowrap; color: __OFF__; margin: 0; }
.st-key-tabbar a:hover p, .st-key-tabbar a:hover [data-testid="stIconMaterial"] { color: __ON__; }
.st-key-tabbar [class*="st-key-tabon_"] p { color: __ON__; font-weight: 700; }
.st-key-tabbar [class*="st-key-tabon_"] [data-testid="stIconMaterial"] { color: __ON__; font-variation-settings: "FILL" 1; }
</style>
"""


def _colors() -> dict:
    dark = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
    if dark:
        return {"__BG__": "#0e1117", "__LINE__": "rgba(250,250,250,.12)", "__ON__": "#fafafa", "__OFF__": "#8b8d94"}
    return {"__BG__": "#ffffff", "__LINE__": "rgba(49,51,63,.12)", "__ON__": "#111111", "__OFF__": "#9a9aa0"}


def pages():
    return [st.Page(file, title=label, icon=icon, default=(i == 0)) for i, (file, label, icon) in enumerate(TABS)]


def render(all_pages, current) -> None:
    css = _CSS.replace("__H__", str(BAR_H)).replace("__PAD__", str(BAR_H + 40))
    for k, v in _colors().items():
        css = css.replace(k, v)
    st.html(css)
    theme.accent()
    with st.container(key="tabbar", horizontal=True, gap=None):
        for i, page in enumerate(all_pages):
            on = page.url_path == current.url_path
            with st.container(key=f"{'tabon' if on else 'taboff'}_{i}"):
                st.page_link(page, label=page.title, icon=page.icon)
