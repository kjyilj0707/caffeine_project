"""시나리오 파일 읽기 + 예시 시나리오가 끝까지 돌아가는지 테스트."""
from pathlib import Path

import pytest

from caffeine_engine.pipeline import format_card, run_day
from caffeine_engine.scenario import from_dict, load

SCENARIOS = sorted((Path(__file__).resolve().parent.parent / "scenarios").glob("*.yaml"))


def write(tmp_path, text):
    p = tmp_path / "s.yaml"
    p.write_text(text, encoding="utf-8")
    return load(p)


BASE = """
profile: {age: 24, weight_kg: 70}
sleep:
  - "23:30-07:00"
  - "01:30-08:00"
today:
  now: "09:00"
  bed: "01:00"
  windows:
    - {kind: 깨어 있기, from: "08:00", to: "01:00"}
    - {kind: 졸면 안 됨, from: "23:00", to: "00:30"}
"""


def test_sleep_times_before_and_after_midnight(tmp_path):
    sc = write(tmp_path, BASE)
    first, last = sc.sleeps
    assert (last.start_h, last.end_h) == (1.5, 8.0)            # 어젯밤: 오늘 01:30 → 08:00
    assert (first.start_h, first.end_h) == (-24.5, -17.0)      # 그 전날 23:30 → 07:00


def test_times_earlier_than_wake_are_next_day(tmp_path):
    sc = write(tmp_path, BASE)
    assert sc.now_h == 9.0
    assert sc.bed_h == 25.0
    awake, late = sc.windows
    assert (awake.kind, awake.start_h, awake.end_h) == ("stay_awake", 8.0, 25.0)
    assert (late.kind, late.start_h, late.end_h) == ("must_not_sleep", 23.0, 24.5)


def test_already_in_sips_uses_beverage(tmp_path):
    sc = write(tmp_path, BASE.replace('  now: "09:00"', '  now: "09:00"\n  already:\n    - {time: "08:30", sips: 10}')
               + 'beverage: {name: "톨", mg: 150, ml: 355}\nsip_ml: 20\n')
    assert sc.already[0].mg == pytest.approx(10 * 20 * 150 / 355)


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_example_scenarios_run(path):
    sc = load(path)
    result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h,
                     already=sc.already, beverage=sc.beverage, sip_ml=sc.sip_ml)
    assert "오늘의 카페인 플랜" in format_card(result)


def test_pregnant_late_term_explains_why_no_caffeine():
    sc = load(next(p for p in SCENARIOS if p.stem == "pregnant_sensitive"))
    result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h)
    assert result.plan.new_doses == []
    assert any("마실 수 있는 시각이 없어요" in n for n in result.notes)


def test_window_starting_before_wake_is_clipped_to_wake():
    # 실제 사례(4-3 시험): 08:30에 일어났는데 '깨어 있기 08:00-23:00' → 예전엔 다음 날 08시로 보고 계산이 멈춤
    from caffeine_engine.pipeline import run_day
    sc = from_dict({"profile": {"age": 24, "weight_kg": 70}, "sleep": ["01:30-08:30"],
                    "today": {"now": "09:00", "bed": "23:00",
                              "windows": [{"kind": "깨어 있기", "from": "08:00", "to": "23:00"},
                                          {"kind": "집중", "from": "06:00", "to": "07:00"}]}})
    assert (sc.windows[0].start_h, sc.windows[0].end_h) == (8.5, 23.0)
    assert (sc.windows[1].start_h, sc.windows[1].end_h) == (30.0, 31.0)  # 기상 전 시간대 → 다음 날 새벽 (기존 규칙)
    run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h)
