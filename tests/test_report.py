"""📊 리포트 (Step 4-6) — 날짜별 묶기, 추천대로 마셨나, 금지 시각, 기간 요약, 화면."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import account  # noqa: E402
import store  # noqa: E402
from account import Session  # noqa: E402
from report import day_stats, summarize  # noqa: E402

SESSION = Session("https://x.supabase.co", "key", "u1", "a@b.c", "tok", 9_999_999_999)
ROWS = {
    "intakes": [{"taken_at": "2026-11-02T09:10:00+09:00", "mg": 100},       # 추천 09:00과 10분 차이 → 추천대로
                {"taken_at": "2026-11-02T14:00:00+09:00", "mg": 60},
                {"taken_at": "2026-11-02T16:30:00Z", "mg": 50},             # 11/3 01:30 → 새벽이라 11/2, 금지 뒤
                {"taken_at": "2026-11-03T10:00:00+09:00", "mg": 400}],
    "plans": [{"plan_date": "2026-11-02", "result": {"doses": [{"time_h": 13.0, "mg": 50}], "cutoff": "15:00"}},
              {"plan_date": "2026-11-02",                                    # 같은 날 마지막 저장이 기준
               "result": {"doses": [{"time_h": 9.0, "mg": 100}, {"time_h": 13.0, "mg": 50}], "cutoff": "16:00"}},
              {"plan_date": "2026-11-03", "result": {"doses": [], "cutoff": "01:00"}}],
    "sleeps": [{"slept_at": "2026-11-01T16:30:00Z", "woke_at": "2026-11-01T23:00:00Z", "quality": 3,
                "sleep_latency_min": 20}],                                  # 11/2 01:30~08:00
    "kss": [{"at": "2026-11-02T05:00:00Z", "kss": 4}, {"at": "2026-11-02T08:00:00Z", "kss": 7}],
}


def test_day_stats():
    d2, d3 = day_stats(ROWS, date(2026, 11, 2), date(2026, 11, 3))
    assert d2.mg == 210 and [round(x.time_h, 2) for x in d2.intakes] == [9.17, 14.0, 25.5]
    assert d2.matched == 1 and len(d2.planned) == 2                    # 13:00 추천은 기록 없음
    assert d2.cutoff_h == 16.0 and d2.cutoff_kept is False             # 새벽 1:30에 마신 기록
    assert d2.sleep_h == 6.5 and d2.latency_min == 20 and d2.kss == [4, 7]
    assert d3.cutoff_h == 25.0 and d3.cutoff_kept is True               # 금지 01:00 = 다음 날 새벽


def test_summary():
    sm = summarize(day_stats(ROWS, date(2026, 11, 2), date(2026, 11, 8)), cap_mg=300)
    assert sm.total_mg == 610 and sm.days_with_caffeine == 2 and sm.days_over_cap == 1
    assert round(sm.daily_average_mg) == 87 and sm.max_day == date(2026, 11, 3)
    assert (sm.matched_cups, sm.planned_cups) == (1, 2)
    assert (sm.cutoff_kept_days, sm.cutoff_days) == (1, 2)
    assert sm.kss_count == 2 and sm.kss_mean == 5.5 and sm.sleep_h == 6.5


def test_report_page(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import state
    monkeypatch.setattr(account, "current_session", lambda: SESSION)
    monkeypatch.setattr(store, "load_day", lambda s, day: ({}, []))
    monkeypatch.setattr(store, "push_devices", lambda s: [])
    monkeypatch.setattr(store, "scheduled_notifications", lambda s, d: [])
    monkeypatch.setattr(store, "today_sleepiness", lambda s: [])
    monkeypatch.setattr(store, "report_rows", lambda s, a, b: ROWS)
    monkeypatch.setattr(state, "default_day", lambda: date(2026, 11, 2))
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    at.switch_page("page_report.py").run()
    assert not at.exception
    html = " ".join(h.proto.body for h in at.get("html"))
    assert "카페인" in html and "하루 평균" in html and "1/2" in html                # 링 카드 · 추천대로 1/2잔
    assert "피드백" in html and "졸림 기록 2/10개" in html                         # Step 5 개인화 ①
    assert "rc-gauge" in html                                                     # 졸림 색 막대
    assert not any("모델 비교를 계산하지 못했어요" in c.value for c in at.caption)
    at.button_group(key="report_period").set_value(["하루"]).run()
    html = " ".join(h.proto.body for h in at.get("html"))
    assert not at.exception and "시간대별 마신 양" in html and "16:00" in html and "못 지킴" in html
    at.button_group(key="report_period").set_value(["한 달"]).run()
    assert not at.exception and any("2026년 11월" in m.value for m in at.markdown)
    assert any(b.key == "go_feedback" for b in at.button)                       # 피드백 입력 화면으로 가는 버튼


def test_report_page_shows_demo_when_logged_out():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    at.switch_page("page_report.py").run()
    assert not at.exception and any("예시 기록" in i.value for i in at.info)
    assert "하루 평균" in " ".join(h.proto.body for h in at.get("html"))


def test_feedback_page_saves_sleepiness(monkeypatch):
    # 리포트의 기간 버튼(세그먼트)이 있는 화면에서 이동하면 테스트 도구가 멈추는 버그가 있어 피드백 화면만 따로 연다
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(account, "current_session", lambda: SESSION)
    monkeypatch.setattr(store, "load_day", lambda s, day: ({}, []))
    monkeypatch.setattr(store, "report_rows", lambda s, a, b: ROWS)
    saved_kss = []
    monkeypatch.setattr(store, "add_sleepiness", lambda s, k, n: saved_kss.append((k, n)))
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    at.switch_page("page_feedback.py").run()
    assert not at.exception and any("지금 얼마나 졸려요" in h.value for h in at.subheader)
    next(b for b in at.button if b.key == "fb_save").click().run()
    assert not at.exception and saved_kss == [(5, "")]                           # 선 기본값 = 가운데 = 5
