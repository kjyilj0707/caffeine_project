"""카페인 효과 테스트 — Ramakrishnan 2016 모델의 성질을 확인."""
import pytest

from caffeine_engine.effect import (caffeine_factor, curve_with_caffeine, score_with_caffeine,
                                    sleepiness_reduction)
from caffeine_engine.fatigue import AlertnessPoint, SleepEpisode, alertness_curve
from caffeine_engine.pk import Dose, amount_at


def reduction(mg, hours_after, metric=None):
    return sleepiness_reduction(hours_after, [Dose(0.0, mg)], metric)


def test_no_effect_before_drinking():
    assert caffeine_factor(-0.1, [Dose(0.0, 100)]) == 1.0
    assert caffeine_factor(5.0, []) == 1.0


def test_factor_stays_between_0_and_1():
    doses = [Dose(0.0, 200), Dose(2.0, 200), Dose(4.0, 200)]
    for t in [0.5, 1, 3, 5, 8]:
        assert 0 < caffeine_factor(t, doses) <= 1


def test_100mg_peak_effect_size():
    # 반응 속도 기준: 100mg → 약 1시간 뒤 졸림 약 19% 감소
    assert reduction(100, 1.0) == pytest.approx(0.19, abs=0.02)


def test_bigger_dose_bigger_effect():
    assert reduction(50, 1.0) < reduction(100, 1.0) < reduction(200, 1.0)


def test_lapse_metric_shows_larger_effect():
    assert reduction(100, 1.0, "lapse") > reduction(100, 1.0, "mean_rt")


def test_bigger_dose_lasts_longer():
    # kc = k0·e^(−z·c): 용량이 클수록 효과가 천천히 사라짐
    def remaining(mg):
        return reduction(mg, 4.0) / reduction(mg, 1.0)
    assert remaining(200) > remaining(50)


def test_effect_fades_faster_than_body_caffeine():
    # 4시간 뒤 몸속 카페인은 최고치의 절반 이상 남지만 효과는 그보다 더 많이 줄어듦
    dose = [Dose(0.0, 100)]
    body_left = amount_at(4.0, dose) / amount_at(1.0, dose)
    effect_left = reduction(100, 4.0) / reduction(100, 1.0)
    assert body_left > 0.6
    assert effect_left < body_left


def test_effect_nearly_gone_after_8h():
    assert reduction(100, 8.0) < 0.03


def test_score_goes_up_but_not_past_reference():
    point = AlertnessPoint(t=15.0, s=10.0, c=1.0, u=0.0, w=0.0, asleep=False)  # 점수 11
    lifted = score_with_caffeine(point, [Dose(14.0, 200)])
    assert 11 < lifted < 14


def test_no_change_while_asleep_or_already_alert():
    asleep = AlertnessPoint(t=3.0, s=10.0, c=0.0, u=0.0, w=0.0, asleep=True)
    alert = AlertnessPoint(t=15.0, s=13.0, c=2.0, u=0.0, w=0.0, asleep=False)
    doses = [Dose(2.0, 200), Dose(14.0, 200)]
    assert score_with_caffeine(asleep, doses) == asleep.score
    assert score_with_caffeine(alert, doses) == alert.score


def test_curve_without_doses_is_unchanged():
    sleeps = [SleepEpisode(-1.0, 7.0)]
    points = alertness_curve(sleeps, 8.0, 20.0)
    assert curve_with_caffeine(points, []) == [p.score for p in points]
