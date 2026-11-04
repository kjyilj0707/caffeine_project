"""Step 3 알림 테스트 — 알림 만들기 · 실제 시각 붙이기 · ntfy 보낼 내용 (실제 전송 없이)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from ntfy import payload, publish, valid_topic  # noqa: E402

from caffeine_engine.notify import (day_start, local_tz, plan_notifications, schedule,  # noqa: E402
                                    make_test_notification)
from caffeine_engine.pipeline import run_day  # noqa: E402
from caffeine_engine.scenario import load  # noqa: E402

KST = local_tz()
ROOT = Path(__file__).resolve().parent.parent


def kst(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=KST)


def exam_day():
    sc = load(ROOT / "scenarios" / "exam_day.yaml")  # 13:45 커피 스몰 2/3잔 30분 동안, 21:30부터 금지, 23:00 취침
    r = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h,
                already=sc.already, beverage=sc.beverage, sip_ml=sc.sip_ml)
    return sc, r


def test_plan_becomes_drink_and_stop_notifications():
    sc, r = exam_day()
    notes = plan_notifications(r.plan, r.servings, sc.bed_h)
    assert [n.kind for n in notes] == ["drink", "stop"]
    assert notes[0].title == "13:45 커피 스몰 사이즈 2/3잔 · 30분 동안"     # 몇 모금 대신 잔 크기 + 마시는 시간
    assert "마지막 잔" in notes[0].message
    assert notes[1].time_h == r.plan.cutoff_h and "금지" in notes[1].title


def test_day_start_is_that_mornings_midnight():
    assert day_start(8.0, kst(2026, 11, 1, 8, 3)) == kst(2026, 11, 1, 0)
    # 새벽 00:30에 앱을 열고 '24:30'(전날 기준)으로 입력 → 기준은 전날 0시
    assert day_start(24.5, kst(2026, 11, 2, 0, 30)) == kst(2026, 11, 1, 0)
    # 입력한 '지금'이 실제와 몇 시간 달라도 같은 날로 맞춤
    assert day_start(9.0, kst(2026, 11, 1, 12, 0)) == kst(2026, 11, 1, 0)


def test_schedule_uses_korean_time_and_handles_midnight():
    sc, r = exam_day()
    notes = plan_notifications(r.plan, r.servings, sc.bed_h)
    items = schedule(notes, now_h=8.0, real_now=kst(2026, 11, 1, 8, 0))
    assert [i.at for i in items] == [kst(2026, 11, 1, 13, 45), kst(2026, 11, 1, 21, 30)]
    assert all(i.send for i in items)
    late = schedule([make_test_notification(24.5, minutes=60)], now_h=24.5, real_now=kst(2026, 11, 2, 0, 30))
    assert late[0].at == kst(2026, 11, 2, 1, 30)


def test_past_and_too_far_are_skipped():
    sc, r = exam_day()
    notes = plan_notifications(r.plan, r.servings, sc.bed_h)
    items = schedule(notes, now_h=14.0, real_now=kst(2026, 11, 1, 14, 0))
    assert [(i.send, i.reason) for i in items] == [(False, "이미 지난 시각"), (True, "")]
    far = schedule([make_test_notification(8.0, minutes=60 * 80)], now_h=8.0, real_now=kst(2026, 11, 1, 8))
    assert not far[0].send


def test_test_notification_one_minute_ahead():
    item = schedule([make_test_notification(10.0)], now_h=10.0, real_now=kst(2026, 11, 1, 10, 0))[0]
    assert item.send and item.at == kst(2026, 11, 1, 10, 1)


def test_payload_and_publish_with_fake_transport():
    item = schedule([make_test_notification(10.0)], now_h=10.0, real_now=kst(2026, 11, 1, 10, 0))[0]
    p = payload("caffeine-abc123", item)
    assert p["topic"] == "caffeine-abc123"
    assert p["delay"] == str(int(kst(2026, 11, 1, 10, 1).timestamp()))
    assert p["tags"] == ["bell"]

    sent = {}

    def fake(url, body):
        sent["url"], sent["body"] = url, json.loads(body.decode())
        return {"id": "x1", "time": int(item.at.timestamp())}

    assert publish("caffeine-abc123", item, transport=fake)["id"] == "x1"
    assert sent["url"] == "https://ntfy.sh"
    assert sent["body"]["title"] == "카페인 측정기 테스트 알림"  # 한글이 깨지지 않음


@pytest.mark.parametrize("topic,ok", [("caffeine-5cpt0dzk", True), ("my_topic-1", True), ("", False),
                                      ("한글채널", False), ("has space", False), ("a" * 65, False)])
def test_topic_rules(topic, ok):
    assert valid_topic(topic) is ok


def test_kst_offset():
    assert local_tz().utcoffset(None) == timedelta(hours=9)


def test_schedule_test_uses_real_clock():
    from caffeine_engine.notify import current_time_h, schedule_test
    item = schedule_test(1, real_now=kst(2026, 11, 1, 14, 26, ))
    assert item.send and item.at == kst(2026, 11, 1, 14, 27)
    assert item.notification.kind == "test"
    assert current_time_h(kst(2026, 11, 1, 14, 29)) == 14.25
