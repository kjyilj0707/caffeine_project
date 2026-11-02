"""기록 저장·불러오기 (Step 4-3) — 화면 형식 ↔ 서버 행 변환, 저장 순서, 화면 연결. 실제 서버는 쓰지 않는다."""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import account  # noqa: E402
import store  # noqa: E402
from account import Session  # noqa: E402
from store import (load_day, profile_to_row, row_to_profile, rows_to_intakes, rows_to_sleeps,  # noqa: E402
                   save_day, sleeps_to_rows)

from caffeine_engine.notify import local_tz  # noqa: E402
from caffeine_engine.pipeline import run_day  # noqa: E402
from caffeine_engine.scenario import from_dict  # noqa: E402

KST = local_tz()
SESSION = Session("https://x.supabase.co", "key", "u1", "a@b.c", "tok", 9_999_999_999)


def exam_day():
    d = yaml.safe_load((ROOT / "scenarios" / "exam_day.yaml").read_text(encoding="utf-8"))
    d["sip_ml"] = 17.5
    d["today"]["already"] = [{"time": "09:00", "sips": 8}, {"time": "10:30", "mg": 50}]
    return d


def test_profile_round_trip():
    prof = {"age": 24, "weight_kg": 60.5, "oral_contraceptive": True, "pregnancy_trimester": None,
            "sensitivity": "sensitive", "daily_cap_mg": 300.0}
    row = profile_to_row("u1", prof, "여성", 15.0, 2026)
    assert row["birth_year"] == 2002 and row["sex"] == "female" and row["smoker"] is False
    back, sex, sip = row_to_profile(row, 2026)
    assert sex == "여성" and sip == 15.0
    assert back["age"] == 24 and back["oral_contraceptive"] and back["daily_cap_mg"] == 300.0
    assert "pregnancy_trimester" not in back  # 비어 있는 값은 엔진 기본값에 맡김


def test_sleep_rows_have_real_dates_and_round_trip():
    start = datetime(2026, 11, 2, tzinfo=KST)
    rows = sleeps_to_rows(exam_day(), start)
    assert [r["woke_at"][:16] for r in rows] == ["2026-10-31T07:30", "2026-11-01T07:00", "2026-11-02T08:00"]
    assert rows[0]["slept_at"].startswith("2026-10-31T00:30")
    assert rows_to_sleeps(rows) == exam_day()["sleep"]


def test_loaded_sleeps_stop_at_a_missing_night():
    rows = [{"slept_at": "2026-10-29T00:00:00+09:00", "woke_at": "2026-10-29T07:00:00+09:00", "quality": None},
            # 10-30, 10-31 아침 기록 없음 → 그 앞(10-29)은 불러오지 않음
            {"slept_at": "2026-11-01T00:00:00+09:00", "woke_at": "2026-11-01T07:00:00+09:00", "quality": None},
            {"slept_at": "2026-11-01T23:30:00+09:00", "woke_at": "2026-11-02T06:30:00+09:00", "quality": 2}]
    assert rows_to_sleeps(rows) == ["00:00-07:00", {"time": "23:30-06:30", "quality": 2}]


def test_intakes_round_trip_keeps_sips():
    rows = [{"taken_at": "2026-11-02T01:30:00Z", "mg": 50, "sips": None},   # UTC로 와도 한국 시각으로
            {"taken_at": "2026-11-02T09:00:00+09:00", "mg": 60, "sips": 8}]
    assert rows_to_intakes(rows) == [{"time": "09:00", "sips": 8.0}, {"time": "10:30", "mg": 50.0}]


class FakeServer:
    """요청을 기록하고, 표마다 정해 둔 응답을 돌려준다."""
    def __init__(self, tables=None):
        self.calls, self.tables = [], tables or {}

    def __call__(self, method, url, headers, body):
        path = url.split("/rest/v1/")[1]
        self.calls.append((method, path, json.loads(body) if body else None, headers["Prefer"]))
        return 200, json.dumps(self.tables.get(path.split("?")[0], []) if method == "GET" else [])


def test_save_replaces_period_then_inserts():
    d = exam_day()
    d["today"]["now"] = "11:00"
    sc = from_dict(d)
    result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h, already=sc.already,
                     beverage=sc.beverage, sip_ml=sc.sip_ml)
    fake = FakeServer()
    n = save_day(SESSION, d, "남성", result, date(2026, 11, 2), transport=fake)
    assert n == {"nights": 3, "intakes": 2}
    order = [(m, p.split("?")[0]) for m, p, _, _ in fake.calls]
    assert order == [("POST", "profiles"), ("DELETE", "sleep_logs"), ("POST", "sleep_logs"),
                     ("DELETE", "intakes"), ("POST", "intakes"), ("POST", "plans")]
    assert "merge-duplicates" in fake.calls[0][3]
    assert "%2B09%3A00" in fake.calls[1][1]          # 시각의 +가 주소에서 공백으로 바뀌지 않게
    intakes = fake.calls[4][2]
    assert intakes[0]["sips"] == 8 and intakes[0]["mg"] > 0 and intakes[1]["mg"] == 50
    assert intakes[0]["taken_at"] == "2026-11-02T09:00:00+09:00"
    plan = fake.calls[5][2]
    assert plan["plan_date"] == "2026-11-02" and plan["inputs"]["sex"] == "남성"
    assert "doses" in plan["result"] and len(plan["params_hash"]) == 12


def test_load_with_nothing_saved():
    base, notes = load_day(SESSION, date(2026, 11, 2), transport=FakeServer())
    assert base == {} and notes == []


def _night(slept, woke, **kw):
    return {"slept_at": slept, "woke_at": woke, "quality": None, **kw}


def test_load_day_splits_last_night_and_previous():
    nights = [_night("2026-10-31T00:30:00+09:00", "2026-10-31T07:30:00+09:00"),
              _night("2026-10-31T16:00:00Z", "2026-10-31T22:00:00Z", sleep_latency_min=10),  # 11/1 01:00~07:00
              _night("2026-11-01T16:30:00Z", "2026-11-01T23:00:00Z", quality=3)]             # 11/2 01:30~08:00
    fake = FakeServer({"sleep_logs": nights, "plans": [{"plan_date": "2026-11-02", "inputs": exam_day()}]})
    base, notes = load_day(SESSION, date(2026, 11, 2), transport=fake)
    assert base["last_night"] == {"time": "01:30-08:00", "quality": 3}
    assert base["prev_nights"] == ["00:30-07:30", {"time": "01:00-07:00", "latency_min": 10}]
    assert base["today"]["bed"] == "23:00" and "그날 일정" in notes
    # 다음 날(11/3)을 고르면: 그날 아침 잠은 아직 없고, 11/2까지가 '그 전 밤들'
    base, notes = load_day(SESSION, date(2026, 11, 3), transport=FakeServer({"sleep_logs": nights}))
    assert "last_night" not in base and len(base["prev_nights"]) == 3


def _app(monkeypatch, saved, notes=("프로필",)):
    from streamlit.testing.v1 import AppTest
    calls = {"save": [], "kss": []}
    monkeypatch.setattr(account, "current_session", lambda: SESSION)
    monkeypatch.setattr(store, "load_day", lambda s, day: (saved, list(notes)))
    monkeypatch.setattr(store, "recorded_days", lambda s: [date(2026, 11, 1)])
    monkeypatch.setattr(store, "today_sleepiness", lambda s: [])
    monkeypatch.setattr(store, "save_day", lambda *a: calls["save"].append(a) or {"nights": 1, "intakes": 0})
    monkeypatch.setattr(store, "save_profile", lambda *a: calls["save"].append(a))
    monkeypatch.setattr(store, "add_sleepiness", lambda s, k, n: calls["kss"].append((k, n)))
    monkeypatch.setattr(store, "push_devices", lambda s: [])              # 실제 서버에 묻지 않게
    monkeypatch.setattr(store, "scheduled_notifications", lambda s, d: [])
    return AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run(), calls


SAVED = {"profile": {"age": 30, "weight_kg": 55.0, "sensitivity": "normal", "chronotype": "neutral"},
         "sex": "여성", "last_night": {"time": "00:00-07:00", "latency_min": 20}, "prev_nights": [],
         "today": {"already": [], "bed": "23:30", "windows": [{"kind": "졸면 안 됨", "from": "13:00", "to": "15:00"}]},
         "beverage": {"name": "스타벅스 카페 아메리카노 (Grande 473ml)", "mg": 225.0, "ml": 473.0,
                      "db": "스타벅스 카페 아메리카노 (Grande 473ml)"}}


def test_app_loads_saved_records_into_pages(monkeypatch):
    at, calls = _app(monkeypatch, SAVED)
    assert not at.exception
    assert not any("예시 값" in i.value for i in at.info)            # 내 정보로 계산 중
    assert any("Grande" in c.value for c in at.caption)               # 저장된 메뉴 음료 기준
    at.switch_page("page_day.py").run()
    assert not at.exception
    assert at.number_input(key="latency_1").value == 20
    assert at.radio(key="bev_1").value == "메뉴에서 고르기"
    assert any(m.value == "13:00 ~ 15:00" for m in at.markdown)
    assert any("11/1" in c.value for c in at.caption)                 # 기록 있는 날
    at.switch_page("page_profile.py").run()
    assert at.number_input(key="age_1").value == 30
    next(b for b in at.button if "프로필 저장" in b.label).click().run()
    assert not at.exception and calls["save"]


def test_app_save_and_feedback(monkeypatch):
    at, calls = _app(monkeypatch, SAVED)
    at.switch_page("page_day.py").run()
    next(b for b in at.button if b.label == "저장하고 추천 보기 →").click().run()
    assert not at.exception and calls["save"][0][2] == "여성"
    assert "추천" in at.title[0].value


def test_app_sleepiness_feedback(monkeypatch):
    # (저장 후 바로 이어서 누르면 테스트 도구가 이전 페이지 칸을 찾다 멈춰서, 새 화면에서 따로 확인)
    at, calls = _app(monkeypatch, SAVED)
    at.select_slider(key="kss").set_value(7)
    next(b for b in at.button if b.label == "기록").click().run()
    assert not at.exception and calls["kss"] == [(7, "")]


def test_app_day_without_sleep_asks_for_it(monkeypatch):
    saved = {**SAVED, "last_night": None}
    saved.pop("last_night")
    at, _ = _app(monkeypatch, saved)
    assert not at.exception
    assert any("잠 기록이 없어요" in w.value for w in at.warning)


def test_feedback_notification_in_middle_of_must_not_sleep():
    from caffeine_engine.notify import feedback_notifications
    sc = from_dict(exam_day())                                  # 졸면 안 됨 14:00~17:00
    notes = feedback_notifications(sc.windows)
    assert [(n.kind, n.time_h) for n in notes] == [("feedback", 15.5)]


def test_schedule_push_cancels_then_inserts():
    from caffeine_engine.notify import Notification, Scheduled
    fake = FakeServer()
    at = datetime(2026, 11, 2, 13, 45, tzinfo=KST)
    items = [Scheduled(Notification(13.75, "drink", "☕ 13:45 커피 8모금", "약 60mg"), at, True)]
    assert store.schedule_push(SESSION, items, date(2026, 11, 2), transport=fake) == 1
    (m1, p1, b1, _), (m2, p2, b2, _) = fake.calls
    assert m1 == "PATCH" and b1 == {"status": "cancelled"} and "status=eq.pending" in p1
    assert "send_at=gte.2026-11-02T04%3A00%3A00%2B09%3A00" in p1      # 그날 새벽 4시 ~ 다음 날 새벽 4시
    assert m2 == "POST" and b2 == [{"send_at": "2026-11-02T13:45:00+09:00", "kind": "drink",
                                    "title": "☕ 13:45 커피 8모금", "body": "약 60mg"}]


def test_app_push_section(monkeypatch):
    at, calls = _app(monkeypatch, SAVED)
    monkeypatch.setattr(store, "push_devices", lambda s: [])
    monkeypatch.setattr(store, "scheduled_notifications", lambda s, d: [])
    at.run()
    assert any("알림 켜기" in i.value for i in at.info)                  # 기기 없으면 켜는 법 안내
    pushed = []
    monkeypatch.setattr(store, "push_devices", lambda s: [{"id": 1}])
    monkeypatch.setattr(store, "push_test", lambda s, item: pushed.append(item))
    next(b for b in at.button if b.label == "알림 켰어요 — 다시 확인").click().run()
    assert not at.exception
    assert any("기기 1대" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "1분 뒤 테스트 알림").click().run()
    assert not at.exception and pushed and pushed[0].notification.kind == "test"
    assert not any("ntfy" in e.label for e in at.expander)             # 로그인하면 ntfy 대신 앱 알림
