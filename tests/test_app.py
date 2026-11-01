"""입력 화면(Step 2) 테스트 — 화면 변환 함수, 그래프 데이터, 화면 전체 실행, GitHub Pages 파일 목록."""
import re
import sys
from datetime import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from charts import build_charts, build_frames  # noqa: E402
from forms import (intake_rows_to_list, sensitivity_from_survey, sleep_list_to_rows,  # noqa: E402
                   sleep_rows_to_list, window_rows_to_list)

from caffeine_engine.pipeline import run_day  # noqa: E402
from caffeine_engine.scenario import load  # noqa: E402


def test_survey_to_sensitivity():
    assert sensitivity_from_survey(1, "예", "아니오") == "sensitive"
    assert sensitivity_from_survey(0, "아니오", "예") == "sensitive"
    assert sensitivity_from_survey(3, "아니오", "아니오") == "tolerant"
    assert sensitivity_from_survey(1, "가끔", "아니오") == "normal"


def test_table_rows_to_scenario_lists():
    sleep = sleep_rows_to_list([
        {"잠든 시각": time(0, 30), "깬 시각": time(7, 30), "수면 질": None},
        {"잠든 시각": time(1, 30), "깬 시각": time(8, 0), "수면 질": 3.0},
        {"잠든 시각": None, "깬 시각": None, "수면 질": None},  # 빈 행은 건너뜀
    ])
    assert sleep == ["00:30-07:30", {"time": "01:30-08:00", "quality": 3}]
    assert sleep_rows_to_list(sleep_list_to_rows(sleep)) == sleep
    assert intake_rows_to_list([{"시각": time(9, 0), "양": 8, "단위": "모금"},
                                {"시각": time(10, 0), "양": 100, "단위": "mg"},
                                {"시각": time(11, 0), "양": 0, "단위": "mg"}]) == [
        {"time": "09:00", "sips": 8.0}, {"time": "10:00", "mg": 100.0}]
    assert window_rows_to_list([{"종류": "졸면 안 됨", "시작": time(14), "끝": time(17)},
                                {"종류": None, "시작": time(1), "끝": time(2)}]) == [
        {"kind": "졸면 안 됨", "from": "14:00", "to": "17:00"}]


def test_chart_frames_cover_wake_to_after_bed():
    sc = load(ROOT / "scenarios" / "late_night.yaml")
    result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h,
                     already=sc.already, beverage=sc.beverage, sip_ml=sc.sip_ml)
    frames = build_frames(sc, result)
    s = frames["series"]
    assert s["t"].min() == pytest.approx(sc.sleeps[-1].end_h)
    assert s["t"].max() == pytest.approx(sc.bed_h + 1)
    assert set(frames["doses"]["구분"]) == {"추천", "이미 마심"}
    assert (s["카페인 반영"] >= s["카페인 없을 때"] - 1e-9).all()
    top, bottom = (c.to_dict() for c in build_charts(frames))
    assert top["layer"] and bottom["layer"]


def test_app_runs_and_switches_preset():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60).run()
    assert not at.exception
    assert [m.label.split(" (")[0] for m in at.metric] == ["오늘 총 섭취", "잠든 뒤 최대 잔량", "예상 수면 감소",
                                                        "목표 구간 졸림"]
    at.sidebar.selectbox[0].set_value("임신 후기 · 민감 (22시 30분 취침)")
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any("마실 수 있는 시각이 없어요" in w.value for w in at.warning)


def test_pages_index_lists_every_runtime_file():
    # GitHub Pages(stlite)는 index.html에 적힌 파일만 브라우저로 가져온다
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    listed = set(re.findall(r'"((?:app|caffeine_engine|scenarios)/[^"]+|parameters\.yaml)"', html))
    needed = {str(p.relative_to(ROOT)) for p in (ROOT / "caffeine_engine").glob("*.py")}
    needed |= {str(p.relative_to(ROOT)) for p in (ROOT / "app").glob("*.py")} | {"parameters.yaml"}
    needed |= {str(p.relative_to(ROOT)) for p in (ROOT / "scenarios").glob("*.yaml")}
    assert needed <= listed, f"index.html에 빠진 파일: {needed - listed}"
    assert (ROOT / ".nojekyll").exists()  # 없으면 __init__.py 같은 _로 시작하는 파일이 배포에서 빠짐


def _app_with_fake_ntfy(monkeypatch, topic="caffeine-test-topic123"):
    """실제 전송 대신 보낸 내용을 기록하는 가짜 publish로 화면을 띄운다."""
    import ntfy
    from streamlit.testing.v1 import AppTest
    sent = []
    monkeypatch.setattr(ntfy, "publish", lambda t, item, **kw: sent.append((t, item)) or {"id": "fake"})
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60)
    at.query_params["ntfy"] = topic
    return at.run(), sent


def test_notification_section_schedules_with_fake_transport(monkeypatch):
    at, sent = _app_with_fake_ntfy(monkeypatch)
    assert not at.exception
    assert at.text_input(key="ntfy_topic").value == "caffeine-test-topic123"
    assert any("…c123" in c.value and "22자" in c.value for c in at.caption)  # 끝자리로 잘림 확인
    # 예시의 '지금 시각'(08:00)이 실제와 다르면 일부는 '지난 시각'으로 건너뛸 수 있으니 버튼 상태만 맞는지 본다
    reserve = next(b for b in at.button if b.label.startswith("오늘 알림 예약"))
    if not reserve.disabled:
        reserve.click().run()
        assert not at.exception
        assert sent and all(t == "caffeine-test-topic123" for t, _ in sent)
        n = len(sent)
        next(b for b in at.button if b.label.startswith("오늘 알림 예약")).click().run()
        assert len(sent) == n  # 같은 알림은 다시 보내지 않음 (중복 방지)
        assert any("이미 예약" in i.value for i in at.info)


def test_test_notification_button_and_bad_topic(monkeypatch):
    at, sent = _app_with_fake_ntfy(monkeypatch)
    next(b for b in at.button if b.label == "1분 뒤 테스트 알림").click().run()
    assert not at.exception
    assert len(sent) == 1 and sent[0][1].notification.kind == "test"
    at.text_input(key="ntfy_topic").set_value("한글 채널").run()
    assert any("영문" in e.value for e in at.error)


def test_real_now_button_sets_current_time(monkeypatch):
    from caffeine_engine.notify import current_time_h
    from caffeine_engine.timeutil import h_to_hhmm
    at, _ = _app_with_fake_ntfy(monkeypatch)
    next(b for b in at.button if b.label == "🕒 실제 현재 시각으로").click().run()
    assert not at.exception
    assert at.time_input[0].value.strftime("%H:%M") == h_to_hhmm(current_time_h())
