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


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60)


def test_plan_page_shows_doses_first_and_switches_preset():
    at = _app().run()
    assert not at.exception
    assert any("오늘 추천" in m.value for m in at.markdown)
    assert any("예시 값" in i.value for i in at.info)                    # 아직 내 정보가 아님을 알려줌
    labels = [e.label.split(" —")[0] for e in at.expander]
    assert {"그래프로 보기", "자세한 수치", "핸드폰 알림 받기 (ntfy 앱 · 로그인 없이)"} <= set(labels)   # 펼쳐 보기
    assert not at.metric or all(m.proto.label for m in at.metric)
    at.switch_page("page_profile.py").run()                               # 예시 채우기는 프로필 탭 아래로 옮김
    at.selectbox(key="example_preset").set_value("임신 후기 · 민감 (22시 30분 취침)")
    at.button(key="example_fill").click().run()
    assert not at.exception and at.session_state.data["profile"].get("pregnancy_trimester") == 3


def test_bottom_tab_bar_has_five_tabs_in_order():
    at = _app().run()
    labels = [t.proto.label for t in at.get("page_link")]
    assert labels[:5] == ["오늘 추천", "하루 입력", "리포트", "음료", "프로필"]   # 탭 바가 페이지보다 먼저 그려짐
    assert len(at.sidebar.children) == 0                                     # 왼쪽 메뉴 없음


def test_day_page_add_and_remove_intake_then_plan():
    # 다이얼(휠)은 테스트 도구에서 그려지지 않아 기본값(마신 양 = 기본 사이즈 1잔, 시간대 14:00~16:00)이 들어간다
    at = _app().run()
    at.switch_page("page_day.py").run()
    assert not at.exception
    assert any(m.value.endswith("하루 입력</div>") for m in at.markdown)
    next(b for b in at.button if b.key == "add_already_0").click().run()
    assert not at.exception
    assert any("기본 사이즈 1잔" in m.value for m in at.markdown)
    assert at.session_state.data["today"]["already"][-1]["cups"] == 1.0
    next(b for b in at.button if b.key == "add_win_1").click().run()         # 졸면 안 됨 14:00~16:00
    assert any("14:00 ~ 16:00" in m.value for m in at.markdown)
    next(b for b in at.button if b.label == "저장하고 추천 보기 →").click().run()
    assert not at.exception
    assert any("오늘 추천" in m.value for m in at.markdown)
    assert any("이미 마신 것" in c.value and "기본 사이즈 1잔" in c.value for c in at.caption)


def test_cup_amount_converts_to_mg():
    from forms import AMOUNT_UNITS, amount_entry
    from caffeine_engine.scenario import from_dict
    entry = amount_entry("09:00", 1, 1.0)                                   # 기본 잔 1
    assert entry == {"time": "09:00", "cups": 1.0, "size": "기본", "cup_ml": 520.0, "cup_name": "기본"}
    from forms import amount_text, amount_units
    sb = amount_units("스타벅스")
    assert [u["name"] for u in sb] == ["Short 잔", "Tall 잔", "Venti 잔", "모금", "mg"]
    tall = amount_entry("09:00", 1, 2.0, sb)
    assert tall["cup_ml"] == 355 and amount_text(tall) == "Tall 2잔"
    assert amount_entry("09:00", 3, 8) == {"time": "09:00", "sips": 8.0}   # 모금 8
    assert amount_entry("09:00", 4, 250) == {"time": "09:00", "mg": 250.0} # 직접 입력 250mg
    sc = from_dict({"profile": {"age": 30, "weight_kg": 60}, "sleep": ["00:00-07:00"], "today": {"now": "08:00", "bed": "23:00", "already": [entry]}})
    assert abs(sc.already[0].mg - 520 * 0.428) < 0.5                        # 브랜드 모를 때 기본 520ml
    from caffeine_engine.convert import cup_sizes
    assert [(c.key, c.name, c.ml) for c in cup_sizes("스타벅스")] == [("스몰", "Short", 237), ("기본", "Tall", 355),
                                                                     ("빅", "Venti", 591)]
    assert [c.key for c in cup_sizes("메가MGC커피")] == ["기본", "빅"]           # 스몰 없는 브랜드
    assert len(AMOUNT_UNITS) == 5


def test_profile_page_updates_shared_data():
    at = _app().run()
    at.switch_page("page_profile.py").run()
    assert not at.exception
    labels = [b.label for b in at.button if b.key and b.key.startswith("open_")]
    assert [x.split(" · ")[0] for x in labels] == ["**기본**", "**건강**", "**카페인**", "**화면**"]   # 첫 화면 = 항목 목록
    at.button(key="open_basic").click().run()
    at.radio(key="sex_0").set_value("여성").run()
    assert at.session_state.data["sex"] == "남성"                         # 반영 전에는 그대로
    at.button(key="settings_back").click().run()
    at.button(key="open_health").click().run()
    at.checkbox(key="oc_0").check().run()
    at.button(key="apply_settings").click().run()                          # [설정 반영하기]
    assert not at.exception
    assert at.session_state.data["profile"]["oral_contraceptive"] is True
    assert at.session_state.data["sex"] == "여성"
    assert at.button(key="apply_settings").disabled                       # 반영 후엔 바뀐 게 없음


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


def test_menu_choices_skip_unknown_volume():
    from forms import beverage_choices, beverage_spec, sleep_list_to_rows, sleep_rows_to_list
    from caffeine_engine.convert import load_beverage_db
    db = load_beverage_db()
    choices = beverage_choices(db)
    assert all(d.ml for menus in choices.values() for sizes in menus.values() for d in sizes)
    tall = next(d for d in choices["스타벅스"]["카페 아메리카노"] if d.size == "Tall")
    assert beverage_spec(tall) == {"name": tall.label, "mg": 150.0, "ml": 355.0, "db": tall.label}
    assert '"beverages.yaml"' in (ROOT / "index.html").read_text(encoding="utf-8")  # 웹에서도 DB를 읽게
    nights = ["00:30-07:30", {"time": "01:30-08:00", "quality": 3, "latency_min": 20}]
    assert sleep_rows_to_list(sleep_list_to_rows(nights)) == nights


def test_drink_groups():
    from forms import drink_group
    assert drink_group("스타벅스") == "카페" and drink_group("핫식스") == "에너지음료"
    assert drink_group("스타벅스 RTD") == "편의점 커피" and drink_group("일반") == "차·탄산·믹스"


def test_drinks_page_search_and_sort():
    at = _app().run()
    at.switch_page("page_drinks.py").run()
    assert not at.exception
    table = at.dataframe[0].value
    assert len(table) > 100 and table["카페인(mg)"].is_monotonic_decreasing
    at.text_input[0].set_value("콜드브루").run()
    table = at.dataframe[0].value
    assert not at.exception and len(table) > 0 and table["메뉴"].str.replace(" ", "").str.contains("콜드브루").all()
    assert "콜드 브루" in set(table["메뉴"])                    # 띄어쓰기 달라도 찾음


def test_timer_events_order_and_times():
    from datetime import date, datetime
    from types import SimpleNamespace
    import timer_view
    from caffeine_engine.pk import Dose
    plan = SimpleNamespace(new_doses=[Dose(13.75, 100, 0.5)], cutoff_h=21.5)
    serving = SimpleNamespace(sips=13, mg_actual=97, ml=228, cup="스몰 사이즈 1잔", minutes=30, pace="2~3분에 한 모금")
    ev = timer_view.events(date(2026, 11, 4), plan, [serving], "커피", bed_h=23.0)
    assert [e["kind"] for e in ev] == ["drink", "stop", "bed"]
    assert ev[0]["title"] == "커피 스몰 사이즈 1잔" and ev[0]["sub"] == "약 228ml · 97mg"
    assert ev[0]["pace"] == "30분 동안 나눠서 · 2~3분에 한 모금" and ev[0]["until"] - ev[0]["at"] == 30 * 60000
    kst = datetime.fromtimestamp(ev[0]["at"] / 1000, tz=timer_view.local_tz())
    assert (kst.hour, kst.minute) == (13, 45)


def test_theme_mode_picker_writes_all_pages():
    import theme
    at = _app().run()
    at.switch_page("page_profile.py").run()
    at.button(key="open_display").click().run()
    assert not at.exception and at.radio(key="theme_mode").value == "시스템 설정"
    at.radio(key="theme_mode").set_value("다크").run()
    assert not at.exception
    assert len(theme.PAGES) == 6 and theme.MODES["다크"] == "Dark"


def test_day_boundary_follows_bedtime():
    from datetime import date, datetime
    import state
    from caffeine_engine.notify import local_tz
    at = lambda h, m: datetime(2026, 11, 4, h, m, tzinfo=local_tz())
    assert state.day_for(at(22, 59), "23:00") == date(2026, 11, 4)
    assert state.day_for(at(23, 30), "23:00") == date(2026, 11, 5)   # 잘 시각이 지나면 다음 날 아침
    assert state.day_for(at(0, 30), "01:00") == date(2026, 11, 3)    # 자정 넘어 자는 사람: 아직 어제
    assert state.day_for(at(1, 30), "01:00") == date(2026, 11, 4)
    assert state.day_for(at(8, 0), "01:00") == date(2026, 11, 4)


def test_dial_typed_input_parsing():
    from datetime import date
    import dial
    assert dial.parse_time("1:37") == "01:37" and dial.parse_time("0137") == "01:37"
    assert dial.parse_time("7시 30분") == "07:30" and dial.parse_time("7시") == "07:00"
    assert dial.parse_time("25:00") is None and dial.parse_time("abc") is None
    assert dial.parse_span("01:30-08:00") == ("01:30", "08:00") and dial.parse_span("1400 ~ 1630") == ("14:00", "16:30")
    today = date(2026, 11, 4)
    assert dial.parse_date("11/3", today) == date(2026, 11, 3) and dial.parse_date("어제", today) == date(2026, 11, 3)
    assert dial.parse_date("2026-10-30", today) == date(2026, 10, 30) and dial.parse_date("13/40", today) is None
    assert dial.parse_number("250") == 250 and dial.parse_number("7분") == 7 and dial.parse_number("x") is None
