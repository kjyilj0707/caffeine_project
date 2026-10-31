"""③ 체내 카페인 엔진 테스트 — 논문 결과와 설계서 예시를 재현하는지 확인."""
import pytest

from caffeine_engine import params
from caffeine_engine.pk import Dose, amount_at, curve, time_to_peak_h
from caffeine_engine.timeutil import h_to_hhmm, hhmm_to_h

BED = hhmm_to_h("01:00", next_day=True)


def test_every_parameter_has_source_and_status():
    for section, entries in params.load().items():
        for name, entry in entries.items():
            assert "source" in entry, f"{section}.{name} 출처 없음"
            assert entry.get("status") in ("confirmed", "provisional"), f"{section}.{name} 상태 없음"


def test_nothing_in_body_before_drinking():
    assert amount_at(8.99, [Dose(9.0, 100)]) == 0.0


def test_peak_within_30_to_120_min():
    # Gardiner 2023: 혈중 최고치는 마신 뒤 30~120분
    assert 30 <= time_to_peak_h() * 60 <= 120


def test_halves_every_half_life_after_absorption():
    doses = [Dose(0.0, 100)]
    assert amount_at(15.0, doses) / amount_at(10.0, doses) == pytest.approx(0.5, abs=0.01)


def test_gardiner_coffee_cutoff_leaves_about_30mg():
    # 커피 107mg을 취침 8.8시간 전 → 설계서의 '취침 허용 잔량 30mg' 근거
    residual = amount_at(BED, [Dose(BED - 8.8, 107)])
    assert 30 <= residual <= 35


def test_gardiner_preworkout_cutoff_leaves_about_30mg():
    residual = amount_at(BED, [Dose(BED - 13.2, 217.5)])
    assert 30 <= residual <= 37


def test_design_doc_example_day():
    # 설계서 예시: 09:00 100mg 이미 마심, 13:15 추가분 비교, 01:00 취침
    already = Dose(hhmm_to_h("09:00"), 100)
    t = hhmm_to_h("13:15")
    assert amount_at(BED, [already, Dose(t, 100)]) == pytest.approx(32.1, abs=0.1)
    assert amount_at(BED, [already, Dose(t, 75)]) == pytest.approx(26.9, abs=0.1)


def test_curve_has_15min_steps():
    points = curve([Dose(9.0, 100)], 6.0, 26.0)
    assert len(points) == 81
    assert points[1][0] - points[0][0] == pytest.approx(0.25)


def test_time_helpers_round_trip():
    assert BED == 25.0
    assert h_to_hhmm(BED) == "01:00"
    assert h_to_hhmm(hhmm_to_h("13:15")) == "13:15"
