"""기록 저장·불러오기 (Step 4-3) — 화면 형식 ↔ 서버 행 변환, 저장 순서, 화면 연결. 실제 서버는 쓰지 않는다."""
import json
import sys
from datetime import datetime
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
    n = save_day(SESSION, d, "남성", result, transport=fake, real_now=datetime(2026, 11, 2, 11, 5, tzinfo=KST))
    assert n == {"nights": 3, "intakes": 2}
    order = [(m, p.split("?")[0]) for m, p, _, _ in fake.calls]
    assert order == [("POST", "profiles"), ("DELETE", "sleep_logs"), ("POST", "sleep_logs"),
                     ("DELETE", "intakes"), ("POST", "intakes"), ("POST", "plans")]
    assert "merge-duplicates" in fake.calls[0][3]
    assert "%2B09%3A00" in fake.calls[1][1]          # 시각의 +가 주소에서 공백으로 바뀌지 않게
    intakes = fake.calls[4][2]
    assert intakes[0]["sips"] == 8 and intakes[0]["mg"] > 0 and intakes[1]["mg"] == 50
    plan = fake.calls[5][2]
    assert plan["plan_date"] == "2026-11-02" and plan["inputs"]["sex"] == "남성"
    assert "doses" in plan["result"] and len(plan["params_hash"]) == 12


def test_load_with_nothing_saved():
    base, notes = load_day(SESSION, transport=FakeServer(), real_now=datetime(2026, 11, 2, 12, tzinfo=KST))
    assert base == {} and notes == []


def test_app_loads_saved_records_and_saves(monkeypatch):
    from streamlit.testing.v1 import AppTest
    saved = {"profile": {"age": 30, "weight_kg": 55.0, "sensitivity": "normal", "chronotype": "neutral"},
             "sex": "여성", "sleep": ["00:00-07:00"],
             "today": {"already": [], "bed": "23:30",
                       "windows": [{"kind": "깨어 있기", "from": "07:00", "to": "23:30"}]}}
    calls = []
    monkeypatch.setattr(account, "current_session", lambda: SESSION)
    monkeypatch.setattr(store, "load_day", lambda s: (saved, ["기본 정보", "수면 1밤", "최근 목표"]))
    monkeypatch.setattr(store, "save_day", lambda *a: calls.append(a) or {"nights": 1, "intakes": 0})
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    assert not at.exception
    assert at.number_input[0].value == 30                       # 나이가 저장값으로
    assert any("불러온 기록" in c.value for c in at.sidebar.caption)
    save = next(b for b in at.button if "저장" in b.label and "☁️" in b.label)
    save.click().run()
    assert not at.exception and calls and calls[0][2] == "여성"
    assert any("저장했어요" in m.value for m in at.success)


def test_sleep_latency_is_saved_and_loaded():
    d = exam_day()
    d["sleep"][-1] = {"time": "01:30-08:00", "quality": 3, "latency_min": 25}
    rows = sleeps_to_rows(d, datetime(2026, 11, 2, tzinfo=KST))
    assert [r["sleep_latency_min"] for r in rows] == [None, None, 25]
    assert rows_to_sleeps(rows)[-1] == {"time": "01:30-08:00", "quality": 3, "latency_min": 25}


def test_sleepiness_feedback():
    from store import add_sleepiness, today_sleepiness
    fake = FakeServer({"feedback": [{"at": "2026-11-02T05:30:00+00:00", "kss": 7, "note": None}]})
    now = datetime(2026, 11, 2, 14, 30, tzinfo=KST)
    fake_post = lambda m, u, h, b: (fake(m, u, h, b), (201, json.dumps([json.loads(b)])))[1]  # noqa: E731
    row = add_sleepiness(SESSION, 7, " 시험 직전 ", transport=fake_post, real_now=now)
    assert row == {"at": "2026-11-02T14:30:00+09:00", "kind": "sleepiness", "kss": 7, "note": "시험 직전"}
    today = today_sleepiness(SESSION, transport=fake, real_now=now)
    assert today[0]["time"] == "14:30"                         # 서버의 UTC 시각 → 한국 시각
    assert "at=gte.2026-11-02T00%3A00%3A00%2B09%3A00" in fake.calls[-1][1]


def test_app_menu_beverage_and_feedback(monkeypatch):
    from streamlit.testing.v1 import AppTest
    saved = {"beverage": {"name": "스타벅스 카페 아메리카노 (Grande 473ml)", "mg": 225.0, "ml": 473.0,
                          "db": "스타벅스 카페 아메리카노 (Grande 473ml)"}}
    posted = []
    monkeypatch.setattr(account, "current_session", lambda: SESSION)
    monkeypatch.setattr(store, "load_day", lambda s: (saved, ["최근 목표"]))
    monkeypatch.setattr(store, "today_sleepiness", lambda s: [])
    monkeypatch.setattr(store, "add_sleepiness", lambda s, k, n: posted.append((k, n)))
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    assert not at.exception
    assert at.radio(key="bev_1").value == "메뉴에서 고르기"           # 저장된 메뉴 음료가 다시 선택됨
    assert at.selectbox(key="bev_brand_1").value == "스타벅스"
    assert any("Grande" in m.value for m in at.markdown if "☕" in m.value)
    at.select_slider(key="kss").set_value(7)
    next(b for b in at.button if b.label == "기록").click().run()
    assert not at.exception and posted == [(7, "")]
