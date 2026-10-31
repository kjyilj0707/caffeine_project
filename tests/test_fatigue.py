"""② 피로도 엔진 테스트 — Åkerstedt 2004, Van Dongen 2003 결과를 재현하는지 확인."""
import pytest

from caffeine_engine.fatigue import SleepEpisode, alertness_curve, first_time_below


def nights(hours: float, days: int, wake_h: float = 7.0, quality=None):
    """오늘 아침까지 days일 동안 매일 wake_h에 일어나고 hours시간 잔 기록."""
    return [SleepEpisode(-24 * k + wake_h - hours, -24 * k + wake_h, quality)
            for k in range(days - 1, -1, -1)]


def score_at(sleeps, t, **kw):
    return alertness_curve(sleeps, t, t, **kw)[0].score


NORMAL = nights(8, 7)  # 23:00~07:00을 7일


def test_normal_sleeper_wakes_near_full_recovery():
    # Åkerstedt: 기상 시 S 기본값 14, 8시간이면 회복 완료
    s_wake = alertness_curve(NORMAL, 7.0, 7.0)[0].s
    assert 13.3 <= s_wake <= 14.3


def test_afternoon_is_most_alert():
    points = alertness_curve(NORMAL, 9.0, 22.0)
    peak = max(points, key=lambda p: p.score)
    assert 13.0 <= peak.t <= 18.0
    assert peak.score >= 12.5


def test_staying_up_crosses_danger_line_after_midnight():
    # Åkerstedt: 07시 기상 후 계속 깨어 있으면 첫날 밤에 위험선(7) 아래로
    points = alertness_curve(NORMAL, 7.0, 31.0)
    crossing = first_time_below(points)
    assert 24.0 <= crossing <= 27.0


def test_inertia_right_after_waking():
    just_woke = alertness_curve(NORMAL, 7.0, 7.0)[0]
    hour_later = alertness_curve(NORMAL, 8.0, 8.0)[0]
    assert just_woke.w > 5
    assert hour_later.score > just_woke.score + 2


def test_inertia_does_not_count_as_danger():
    points = alertness_curve(NORMAL, 7.0, 20.0)
    assert first_time_below(points) is None
    assert first_time_below(points, include_inertia=True) == pytest.approx(7.0)


def test_eight_hours_is_stable_across_two_weeks():
    sleeps = nights(8, 14)
    day1, day14 = score_at(sleeps, -24 * 12 + 16), score_at(sleeps, 16)
    assert abs(day14 - day1) < 0.5


def test_short_sleep_accumulates_like_van_dongen():
    # Van Dongen 2003: 하루 6·4시간 수면이 이어지면 날마다 나빠지고, 적게 잘수록 더 나쁨
    six, four, eight = nights(6, 14), nights(4, 14), nights(8, 14)
    six_day1, six_day7 = score_at(six, -24 * 12 + 16), score_at(six, -24 * 6 + 16)
    assert six_day7 < six_day1
    assert score_at(four, 16) < score_at(six, 16) < score_at(eight, 16)


def test_model_plateaus_unlike_van_dongen():
    # 알려진 한계: 실제(Van Dongen)는 14일 내내 나빠지지만 이 모델은 약 1주 뒤 멈춘다.
    # 이 테스트가 실패하면 모델이 바뀐 것이니 노션 설계서의 한계 설명도 고칠 것.
    four = nights(4, 14)
    week2_change = score_at(four, 16) - score_at(four, -24 * 6 + 16)
    assert abs(week2_change) < 0.2


def test_poor_sleep_quality_recovers_less():
    good = alertness_curve(nights(7, 3, quality=5), 7.0, 7.0)[0].s
    poor = alertness_curve(nights(7, 3, quality=1), 7.0, 7.0)[0].s
    assert poor < good


def test_chronotype_shifts_the_peak():
    def peak(chronotype):
        pts = alertness_curve(NORMAL, 9.0, 22.0, chronotype=chronotype)
        return max(pts, key=lambda p: p.c).t
    assert peak("morning") < peak("neutral") < peak("evening")


def test_needs_sleep_history():
    with pytest.raises(ValueError):
        alertness_curve([], 7.0, 8.0)
