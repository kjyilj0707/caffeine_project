"""Step 5 개인화 ① — 예측 KSS 변환, 예측 vs 실제 졸림, 잠들기 비교, 리포트 연결."""
import sys
from datetime import date
from pathlib import Path

import pytest

from caffeine_engine.calibration import (KssPair, NightCheck, kss_bias, kss_from_score, kss_pairs,
                                         latency_compare)
from caffeine_engine.fatigue import SleepEpisode
from caffeine_engine.pk import Dose

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import report  # noqa: E402
from test_report import ROWS  # noqa: E402


def test_kss_from_score_uses_ingre_2014():
    assert kss_from_score(14) == pytest.approx(2.2)      # 매우 또렷 → KSS 2.2
    assert kss_from_score(7) == pytest.approx(6.4)       # 위험선 7 → KSS 6.4
    assert kss_from_score(0) == 9.0 and kss_from_score(20) == 1.0   # 1~9로 자름


def test_kss_pairs_skips_asleep_and_before_first_wake():
    sleeps = [SleepEpisode(-1.0, 7.0)]
    pairs = kss_pairs(sleeps, [], [(-0.5, 5), (3.0, 5), (12.0, 5)])
    assert [p.t for p in pairs] == [12.0]


def test_caffeine_lowers_predicted_kss():
    sleeps = [SleepEpisode(1.0, 6.0)]                     # 5시간만 잠
    without = kss_pairs(sleeps, [], [(16.0, 6)])[0]
    with_cup = kss_pairs(sleeps, [Dose(15.0, 100)], [(16.0, 6)])[0]
    assert with_cup.predicted < without.predicted
    assert with_cup.diff == pytest.approx(6 - with_cup.predicted)


def test_kss_bias_levels():
    few = kss_bias([KssPair(10, 7, 5.0)] * 3)
    assert not few.enough and few.level == "unknown" and "3/10" in few.message
    assert kss_bias([KssPair(10, 7, 5.0)] * 10).level == "sleepier"
    assert kss_bias([KssPair(10, 3, 5.0)] * 10).level == "more_alert"
    assert kss_bias([KssPair(10, 5, 4.6)] * 10).level == "matches"
    assert kss_bias([]).n == 0


def test_latency_compare():
    nights = [NightCheck(23, 50, 40)] * 3 + [NightCheck(23, 10, 15)] * 3
    c = latency_compare(nights, limit_mg=30)
    assert c.enough and c.high_mean == 40 and c.low_mean == 15 and "+25분" in c.message
    assert not latency_compare(nights[:4], 30).enough


def test_report_kss_pairs_and_night_checks():
    pairs = report.kss_pairs(ROWS)                        # 11/2 14:00 KSS 4, 17:00 KSS 7 (그날 01:30~08:00 잠)
    assert [(d, round(p.t, 2), p.observed) for d, p in pairs] == [(date(2026, 11, 2), 14.0, 4),
                                                                   (date(2026, 11, 2), 17.0, 7)]
    assert all(1 <= p.predicted <= 9 for _, p in pairs)
    nights = report.night_checks(ROWS, half_life_h=5.0)
    assert len(nights) == 1 and nights[0].latency_min == 20
    assert nights[0].onset_h == pytest.approx(1.5) and nights[0].residual_mg == 0   # 잠들기 전 마신 기록 없음


def test_report_kss_skipped_without_that_mornings_sleep():
    rows = {**ROWS, "kss": [{"at": "2026-11-03T05:00:00Z", "kss": 5}]}   # 11/3 아침 잠 기록 없음
    assert report.kss_pairs(rows) == []
