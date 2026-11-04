"""⑤ 변환 · ① 개인 파라미터 · 지표 · 전체 실행기 테스트."""
from datetime import date, timedelta

import pytest

from caffeine_engine import params
from caffeine_engine.convert import Beverage, default_beverages, from_sips, to_serving
from caffeine_engine.fatigue import SleepEpisode
from caffeine_engine.metrics import (cap_status, monthly_report, period_report, sleep_debt_h,
                                     weekly_report, window_coverage)
from caffeine_engine.optimizer import Window
from caffeine_engine.pipeline import format_card, run_day
from caffeine_engine.pk import Dose
from caffeine_engine.profile import Profile, personal_params

COFFEE = default_beverages()["coffee"]


def nights(hours, days, wake_h=7.0):
    return [SleepEpisode(-24 * k + wake_h - hours, -24 * k + wake_h) for k in range(days - 1, -1, -1)]


# ── ⑤ 변환 ─────────────────────────────────
def test_coffee_concentration_matches_gardiner():
    assert COFFEE.mg_per_ml * 250 == pytest.approx(107, abs=0.5)


def test_100mg_coffee_is_about_13_sips():
    s = to_serving(100, COFFEE)
    assert s.sips == 13
    sip_mg = params.value("conversion", "sip_ml") * COFFEE.mg_per_ml
    assert abs(s.mg_actual - 100) <= sip_mg / 2


def test_at_least_one_sip():
    assert to_serving(1, COFFEE).sips == 1


def test_sips_round_trip():
    s = to_serving(150, COFFEE)
    assert from_sips(s.sips, COFFEE) == pytest.approx(s.mg_actual)


def test_menu_beverage():
    tall = Beverage.from_serving("아메리카노 톨", 150, 355)
    assert to_serving(150, tall).ml == pytest.approx(355, abs=params.value("conversion", "sip_ml"))


# ── ① 개인 파라미터 ─────────────────────────
def test_adult_defaults():
    p = personal_params(Profile(age=24, weight_kg=70))
    assert (p.half_life_h, p.daily_cap_mg, p.single_cap_mg, p.residual_limit_mg) == (5.0, 400, 200, 30)
    assert not p.blocked


def test_half_life_adjustments():
    base = personal_params(Profile(age=24, weight_kg=70)).half_life_h
    assert personal_params(Profile(age=24, weight_kg=70, smoker=True)).half_life_h < base
    assert personal_params(Profile(age=24, weight_kg=70, oral_contraceptive=True)).half_life_h > base
    t1 = personal_params(Profile(age=30, weight_kg=60, pregnancy_trimester=1)).half_life_h
    t3 = personal_params(Profile(age=30, weight_kg=60, pregnancy_trimester=3)).half_life_h
    assert base < t1 < t3


def test_caps_by_group():
    assert personal_params(Profile(age=16, weight_kg=50)).daily_cap_mg == pytest.approx(125)  # 식약처 예시
    assert personal_params(Profile(age=30, weight_kg=60, pregnancy_trimester=2)).daily_cap_mg == 300
    assert personal_params(Profile(age=30, weight_kg=60, breastfeeding=True)).daily_cap_mg == 200
    assert personal_params(Profile(age=24, weight_kg=70, daily_cap_mg=150)).daily_cap_mg == 150
    assert personal_params(Profile(age=24, weight_kg=70, daily_cap_mg=900)).daily_cap_mg == 400


def test_light_person_single_cap_by_weight():
    assert personal_params(Profile(age=24, weight_kg=50)).single_cap_mg == pytest.approx(150)  # 3mg/kg


def test_sensitivity_changes_bedtime_limit():
    assert personal_params(Profile(age=24, weight_kg=70, sensitivity="sensitive")).residual_limit_mg == 20
    assert personal_params(Profile(age=24, weight_kg=70, sensitivity="tolerant")).residual_limit_mg == 40


def test_liver_disease_or_inhibitor_blocks_planning():
    assert personal_params(Profile(age=24, weight_kg=70, liver_disease=True)).blocked
    assert personal_params(Profile(age=24, weight_kg=70, cyp1a2_inhibitor=True)).blocked


# ── 지표 ───────────────────────────────────
def test_cap_levels():
    assert cap_status([Dose(9, 100)], 400).level == "ok"
    assert cap_status([Dose(9, 200), Dose(13, 125)], 400).level == "warning"
    assert cap_status([Dose(9, 200), Dose(13, 200)], 400).level == "over"


def test_sleep_debt():
    assert sleep_debt_h(nights(8, 7)) == 0
    assert sleep_debt_h(nights(6, 3)) == pytest.approx(6.0)
    assert sleep_debt_h(nights(6, 10)) == pytest.approx(14.0)  # 최근 7일만


def test_coverage_improves_with_caffeine():
    sleeps = nights(6, 3, wake_h=8.0)
    late = [Window(20.0, 25.0, "stay_awake")]
    cov = window_coverage(sleeps, late, [Dose(20.0, 200)])[0]
    assert cov.without_caffeine < 1.0
    assert cov.with_caffeine >= cov.without_caffeine


def test_period_reports():
    d0 = date(2026, 10, 1)
    intake = {d0: [Dose(9, 100)], d0 + timedelta(1): [Dose(9, 200), Dose(14, 250)]}
    week = weekly_report(intake, d0 + timedelta(6))
    assert week.total_mg == 550
    assert week.days_with_caffeine == 2
    assert week.daily_average_mg == pytest.approx(550 / 7)
    assert week.max_day == d0 + timedelta(1)
    assert week.days_over_cap == 1
    month = monthly_report(intake, 2026, 10)
    assert (month.start, month.end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert monthly_report(intake, 2026, 12).end == date(2026, 12, 31)
    assert period_report({}, d0, d0).max_day is None


# ── 전체 실행기 ─────────────────────────────
SLEEPS = nights(6.5, 3, wake_h=8.0)
WINDOWS = [Window(8.0, 23.0, "stay_awake"), Window(14.0, 17.0, "must_not_sleep"),
           Window(15.0, 16.0, "focus")]


def test_run_day_end_to_end():
    r = run_day(Profile(age=24, weight_kg=70), SLEEPS, WINDOWS, bed_h=23.0, now_h=8.0)
    assert r.plan is not None and r.plan.new_doses
    assert len(r.servings) == len(r.plan.new_doses)
    assert all(s.sips >= 1 for s in r.servings)
    assert r.cap.total_mg == r.plan.total_mg
    card = format_card(r)
    assert "모금" in card and "금지" in card and "의학적 조언" in card


def test_run_day_blocked_profile_makes_no_plan():
    r = run_day(Profile(age=24, weight_kg=70, liver_disease=True), SLEEPS, WINDOWS, bed_h=23.0, now_h=8.0)
    assert r.plan is None
    assert "상담" in format_card(r)


def test_card_shows_already_consumed():
    r = run_day(Profile(age=24, weight_kg=70), SLEEPS, WINDOWS, bed_h=23.0, now_h=9.0,
                already=[Dose(9.0, 100)])
    assert "이미 마심: 09:00 100mg" in format_card(r)


def test_paced_dose_and_cup_text():
    from caffeine_engine.convert import cup_text, pace_text
    from caffeine_engine.pk import Dose, amount_at, pieces
    paced = Dose(10.0, 120, 0.5)                                   # 30분 동안 나눠 마시기
    parts = pieces(paced)
    assert len(parts) == 3 and sum(p.mg for p in parts) == pytest.approx(120) and parts[-1].time_h < paced.end_h
    assert amount_at(10.25, [paced]) < amount_at(10.25, [Dose(10.0, 120)])   # 천천히 마시면 초반 최고치가 낮음
    assert amount_at(20.0, [paced]) == pytest.approx(amount_at(20.0, [Dose(10.0, 120)]), rel=0.05)
    # 브랜드를 모를 때 컵 = 스몰 355 · 기본 520 · 빅 670 (beverages.yaml cup_sizes '그 외')
    assert cup_text(355, COFFEE) == "스몰 사이즈 1잔" and cup_text(520, COFFEE) == "기본 사이즈 1잔"
    assert cup_text(228, COFFEE) == "스몰 사이즈 2/3잔" and cup_text(175, Beverage("홍차", 0.1, 355)) == "반 잔"
    assert cup_text(1300, COFFEE) == "빅 사이즈 2잔"
    assert cup_text(240, Beverage.from_serving("톨", 150, 355)) == "2/3잔"   # 메뉴 용량을 알면 그 메뉴 기준
    assert pace_text(13, 0.5) == "2~3분에 한 모금" and pace_text(30, 0.25) == "1분에 2모금"
