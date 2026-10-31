"""④ 최적화 엔진 테스트 — 규칙을 지키는지, 상식적인 플랜을 내는지 확인."""
import pytest

from caffeine_engine import params
from caffeine_engine.fatigue import SleepEpisode
from caffeine_engine.optimizer import Window, gardiner_sleep_loss_min, optimize
from caffeine_engine.pk import Dose, amount_at
from caffeine_engine.timeutil import hhmm_to_h

RECENT = [  # 최근 3일 6~7시간 수면, 오늘 08:00 기상
    SleepEpisode(hhmm_to_h("00:30") - 48, hhmm_to_h("07:30") - 48),
    SleepEpisode(hhmm_to_h("01:00") - 24, hhmm_to_h("07:00") - 24),
    SleepEpisode(hhmm_to_h("01:30"), hhmm_to_h("08:00")),
]
EXAM = [Window(14.0, 17.0, "must_not_sleep"), Window(15.0, 16.0, "focus")]
BED = 23.0
DAY = [Window(8.0, BED, "stay_awake")] + EXAM


def plan_for(**kw):
    args = dict(sleeps=RECENT, windows=DAY, bed_h=BED, now_h=8.0)
    args.update(kw)
    return optimize(**args)


def test_exam_dose_lands_about_an_hour_before():
    # 카페인 효과는 마신 뒤 약 1시간에 최대 → 시험 직전에 마시라고 해야 함
    plan = plan_for()
    assert len(plan.new_doses) >= 1
    assert any(12.5 <= d.time_h <= 15.0 for d in plan.new_doses)
    assert plan.sleepiness_reduction > 0


def test_sleep_protection_rules_hold():
    plan = plan_for()
    limit = params.value("sleep_protection", "bedtime_residual_mg")
    window = params.value("optimizer", "residual_window_h")
    for t in [BED + i * 0.25 for i in range(int(window * 4) + 1)]:
        assert amount_at(t, plan.all_doses) <= limit + 1e-6
    assert gardiner_sleep_loss_min(plan.all_doses[-1], BED) < 20


def test_caps_and_spacing_hold_even_when_caffeine_is_cheap():
    # 반감기가 짧으면 수면 기준이 느슨해져 많이 마시려 함 → 그래도 규칙은 지켜야 함
    plan = plan_for(half_life_h=2.0)
    times = [d.time_h for d in plan.all_doses]
    assert plan.total_mg <= params.value("limits", "daily_mg_adult")
    assert all(d.mg <= params.value("limits", "single_dose_mg") for d in plan.new_doses)
    assert all(b - a >= 2.0 - 1e-9 for a, b in zip(times, times[1:]))


def test_faster_metabolism_allows_more_caffeine():
    assert plan_for(half_life_h=3.0).total_mg > plan_for(half_life_h=5.0).total_mg


def test_daily_cap_from_user_is_respected():
    assert plan_for(half_life_h=2.0, daily_cap_mg=150).total_mg <= 150


def test_doses_only_after_now():
    plan = plan_for(now_h=12.0)
    assert all(d.time_h >= 12.0 for d in plan.new_doses)


def test_already_over_limit_means_no_more_caffeine():
    plan = plan_for(now_h=21.0, already=[Dose(20.0, 200)])
    assert plan.new_doses == []
    assert plan.warnings and "더 마시지 않기" in plan.warnings[0]


def test_warns_when_caffeine_cannot_fix_late_night():
    # 01시까지 깨어 있어야 하는데 밤엔 위험선 아래 → 수면 기준 때문에 카페인으로 못 메움
    bed = hhmm_to_h("01:00", next_day=True)
    plan = plan_for(windows=[Window(8.0, bed, "stay_awake")] + EXAM, bed_h=bed)
    assert plan.danger_hours_without > 0
    assert plan.danger_hours <= plan.danger_hours_without
    assert any("수면·휴식" in w for w in plan.warnings)


def test_drinking_right_before_bed_is_never_planned():
    # 취침 직전에 마시면 취침 시각엔 흡수 전이라 잔량 0 → 잠든 뒤 2시간 최대 잔량으로 막아야 함
    plan = plan_for(windows=[Window(20.0, BED, "must_not_sleep")], now_h=20.0)
    assert all(BED - d.time_h > 1.5 for d in plan.new_doses)


def test_absolute_cutoff():
    plan = plan_for()
    assert plan.cutoff_h is not None and 18.0 <= plan.cutoff_h <= BED
    # 컷오프 시각에 25mg → 수면 기준 위반, 그 1시간 전엔 괜찮음
    late, early = Dose(plan.cutoff_h, 25), Dose(plan.cutoff_h - 1, 25)
    limit = params.value("sleep_protection", "bedtime_residual_mg")

    def breaks(d):
        worst = max(amount_at(BED + i * 0.25, [d]) for i in range(9))
        return worst > limit or gardiner_sleep_loss_min(d, BED) >= 20
    assert breaks(late)
    assert not breaks(early)


def test_more_room_for_focus_than_for_plain_waking():
    # 같은 조건에서 시험 구간이 있으면 졸림 감소가 그 구간에 집중됨
    with_exam = plan_for(windows=EXAM)
    assert with_exam.sleepiness_reduction > plan_for().sleepiness_reduction


def test_needs_a_window():
    with pytest.raises(ValueError):
        optimize(RECENT, [], BED, 8.0)
    with pytest.raises(ValueError):
        Window(1.0, 2.0, "nap")
