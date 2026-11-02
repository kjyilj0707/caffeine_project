"""📅 달력 보기 (일주일 / 한 달) — 날짜 계산, 칸 글자, 서버 요약, 화면 흐름."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import account  # noqa: E402
import store  # noqa: E402
from account import Session  # noqa: E402
from calendar_view import cell_text, month_weeks, week_days  # noqa: E402

SESSION = Session("https://x.supabase.co", "key", "u1", "a@b.c", "tok", 9_999_999_999)


def test_week_and_month_grids():
    week = week_days(date(2026, 11, 5))                       # 목요일
    assert week[0] == date(2026, 11, 2) and week[-1] == date(2026, 11, 8) and len(week) == 7
    weeks = month_weeks(date(2026, 11, 15))
    days = [d for w in weeks for d in w if d]
    assert days[0] == date(2026, 11, 1) and days[-1] == date(2026, 11, 30) and len(days) == 30
    assert weeks[0][:6] == [None] * 6                          # 11/1은 일요일 → 첫 주 월~토는 빈칸
    assert all(len(w) == 7 for w in weeks)


def test_cell_text():
    info = {"sleep": "01:30~08:00", "mg": 210.4, "plan": 2, "kss": 5.5}
    week = cell_text(date(2026, 11, 2), info, detailed=True, is_today=True)
    assert week.startswith("**11/2 오늘**") and "😴 01:30~08:00" in week and "☕ 210mg" in week
    assert "📋 추천 2잔" in week and "📝 졸림 5.5" in week
    assert cell_text(date(2026, 11, 3), {}, detailed=True).count("—") == 2
    assert cell_text(date(2026, 11, 2), info, detailed=False) == "2  \n😴☕📋"
    assert cell_text(date(2026, 11, 3), {}, detailed=False) == "3  \n·"


def test_range_summary_groups_by_day():
    tables = {
        "sleep_logs": [{"slept_at": "2026-11-01T16:30:00Z", "woke_at": "2026-11-01T23:00:00Z"}],   # 11/2 01:30~08:00
        "intakes": [{"taken_at": "2026-11-02T09:00:00+09:00", "mg": 100},
                    {"taken_at": "2026-11-02T16:30:00Z", "mg": 50}],                               # 11/3 01:30 → 11/2
        "plans": [{"plan_date": "2026-11-02", "result": {"doses": [{}]}},
                  {"plan_date": "2026-11-02", "result": {"doses": [{}, {}]}}],                    # 마지막 저장
        "feedback": [{"at": "2026-11-02T05:00:00Z", "kss": 4}, {"at": "2026-11-02T08:00:00Z", "kss": 7}],
    }

    def fake(method, url, headers, body):
        return 200, json.dumps(tables[url.split("/rest/v1/")[1].split("?")[0]])

    out = store.range_summary(SESSION, date(2026, 11, 2), date(2026, 11, 8), transport=fake)
    assert out["2026-11-02"] == {"sleep": "01:30~08:00", "mg": 150.0, "plan": 2, "kss": 5.5}


def test_calendar_buttons_open_and_pick_day(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(account, "current_session", lambda: SESSION)
    monkeypatch.setattr(store, "load_day", lambda s, day: ({}, []))
    monkeypatch.setattr(store, "recorded_days", lambda s: [])
    monkeypatch.setattr(store, "today_sleepiness", lambda s: [])
    monkeypatch.setattr(store, "range_summary", lambda s, a, b: {a.isoformat(): {"sleep": "00:00~07:00"}})
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    at.switch_page("page_day.py").run()
    next(b for b in at.button if b.label == "📆 일주일 보기").click().run()
    assert not at.exception
    cells = [b for b in at.button if (b.key or "").startswith("cal_")]
    assert len(cells) == 7 and any("😴 00:00~07:00" in b.label for b in cells)
    next(b for b in at.button if b.label == "🗓 한 달 보기").click().run()
    cells = [b for b in at.button if (b.key or "").startswith("cal_")]
    assert 28 <= len(cells) <= 31
    target = cells[0]
    target.click().run()                                       # 날짜를 누르면 그날 입력으로
    assert not at.exception
    assert at.session_state.data["day"] == target.key[4:]
    assert not any((b.key or "").startswith("cal_") for b in at.button)
