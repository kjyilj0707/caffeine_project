"""기록 저장·불러오기 (Step 4-3) — 입력 화면의 내용 ↔ 서버 표(profiles, sleep_logs, intakes, plans).

화면은 '시각만'(예: "01:30-08:00") 다루고 서버는 '날짜+시각'(timestamptz)을 저장한다.
그날의 기준(D)은 화면에서 고른 날짜(그날 아침에 깬 날)이고, 엔진 시각 h는 D 0시(한국 시간) + h시간이다.

  저장: 화면 내용을 엔진 형식으로 바꾼 뒤(scenario.from_dict) 실제 날짜·시각으로 바꿔 저장.
        수면·마신 것은 '화면에 있는 기간'의 기존 기록을 지우고 새로 넣는다(고친 내용이 그대로 반영).
  불러오기: 기본 정보 + 최근 연속된 수면(최대 7밤) + 오늘 마신 것 + 오늘(없으면 최근) 목표.
"""
import hashlib
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from caffeine_engine import params
from caffeine_engine.convert import cup_ml
from caffeine_engine.notify import local_tz, to_datetime
from caffeine_engine.scenario import from_dict
from caffeine_engine.timeutil import h_to_hhmm

from account import Session, Transport, rest

ENGINE_VERSION = "step4"   # 엔진 계산 방식이 바뀌면 올린다 (예측을 나중에 비교할 때 구분용)
MAX_NIGHTS = 7
PROFILE_FIELDS = ("smoker", "oral_contraceptive", "pregnancy_trimester", "breastfeeding", "liver_disease",
                  "cyp1a2_inhibitor", "heart_or_anxiety", "sensitivity", "chronotype", "daily_cap_mg")


def params_hash() -> str:
    """parameters.yaml 내용의 지문 — 어떤 숫자로 계산한 플랜인지 기록."""
    return hashlib.sha256(params.PARAMS_PATH.read_bytes()).hexdigest()[:12]


def _ts(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _q(dt: datetime) -> str:
    """주소창에 넣을 시각 (+09:00의 +가 공백으로 바뀌지 않게)."""
    return quote(_ts(dt), safe="")


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(local_tz())


# ── 기본 정보 ──
def profile_to_row(user_id: str, profile: Dict, sex: str, sip_ml: float, year: int) -> Dict:
    row = {"user_id": user_id, "birth_year": year - int(profile["age"]), "weight_kg": profile["weight_kg"],
           "sex": "female" if sex == "여성" else "male", "sip_ml": sip_ml}
    row.update({k: profile.get(k) for k in PROFILE_FIELDS})
    row["sensitivity"] = row["sensitivity"] or "normal"
    row["chronotype"] = row["chronotype"] or "neutral"
    for k in ("smoker", "oral_contraceptive", "breastfeeding", "liver_disease", "cyp1a2_inhibitor",
              "heart_or_anxiety"):
        row[k] = bool(row[k])
    return row


def row_to_profile(row: Dict, year: int) -> Tuple[Dict, str, Optional[float]]:
    """→ (엔진 profile, 화면 성별 "남성"/"여성", 한 모금 ml)"""
    profile = {"age": year - row["birth_year"], "weight_kg": float(row["weight_kg"])}
    profile.update({k: row[k] for k in PROFILE_FIELDS if row.get(k) is not None})
    if "daily_cap_mg" in profile:
        profile["daily_cap_mg"] = float(profile["daily_cap_mg"])
    sip = float(row["sip_ml"]) if row.get("sip_ml") is not None else None
    return profile, ("여성" if row.get("sex") == "female" else "남성"), sip


# ── 수면 ──
def sleeps_to_rows(scenario_dict: Dict, start: datetime) -> List[Dict]:
    sc = from_dict(scenario_dict)
    # 엔진 수면 기록은 시간순 = 화면 표 순서(오래된 밤부터)라 같은 순서로 '잠들기' 피드백을 붙인다
    latency = [n.get("latency_min") if isinstance(n, dict) else None for n in scenario_dict["sleep"]]
    return [{"slept_at": _ts(to_datetime(e.start_h, start)), "woke_at": _ts(to_datetime(e.end_h, start)),
             "quality": e.quality, "sleep_latency_min": lat} for e, lat in zip(sc.sleeps, latency)]


def rows_to_sleeps(rows: List[Dict]) -> List:
    """서버 수면 기록 → 화면 형식. 마지막 밤부터 거꾸로, 날짜가 하루씩 이어진 밤만 (빠진 날이 있으면 거기까지)."""
    nights = sorted(rows, key=lambda r: _parse_ts(r["woke_at"]))
    out, expected = [], None
    for r in reversed(nights):
        woke, slept = _parse_ts(r["woke_at"]), _parse_ts(r["slept_at"])
        if expected is not None and woke.date() != expected:
            break
        night = {"time": f"{slept.strftime('%H:%M')}-{woke.strftime('%H:%M')}"}
        if r.get("quality"):
            night["quality"] = r["quality"]
        if r.get("sleep_latency_min") is not None:
            night["latency_min"] = r["sleep_latency_min"]
        out.append(night if len(night) > 1 else night["time"])
        expected = woke.date() - timedelta(days=1)
        if len(out) == MAX_NIGHTS:
            break
    return list(reversed(out))


# ── 마신 것 ──
def intakes_to_rows(scenario_dict: Dict, start: datetime) -> List[Dict]:
    sc = from_dict(scenario_dict)
    entries = scenario_dict["today"].get("already", [])
    rows = []
    for entry, dose in zip(entries, sc.already):
        ml = entry["cups"] * (entry.get("cup_ml") or cup_ml(entry.get("size", "기본"))) if "cups" in entry else None
        rows.append({"taken_at": _ts(to_datetime(dose.time_h, start)), "mg": round(dose.mg, 1),
                     "sips": entry.get("sips"), "ml": ml, "beverage_label": sc.beverage.name})
    return rows


def rows_to_intakes(rows: List[Dict]) -> List[Dict]:
    out = []
    for r in sorted(rows, key=lambda r: _parse_ts(r["taken_at"])):
        t = _parse_ts(r["taken_at"]).strftime("%H:%M")
        out.append({"time": t, "sips": float(r["sips"])} if r.get("sips") else {"time": t, "mg": float(r["mg"])})
    return out


# ── 플랜 ──
def plan_summary(result) -> Dict:
    """엔진 결과 중 나중에 '예측 vs 실제' 비교에 쓸 것만."""
    plan = result.plan
    out = {"notes": list(result.notes), "sleep_debt_h": round(result.sleep_debt_h, 2),
           "personal": {"half_life_h": result.personal.half_life_h, "daily_cap_mg": result.personal.daily_cap_mg,
                        "residual_limit_mg": result.personal.residual_limit_mg}}
    if plan is None:
        return out
    out.update({
        "doses": [{"time": h_to_hhmm(d.time_h), "time_h": round(d.time_h, 3), "mg": round(d.mg, 1),
                   "sips": s.sips, "ml": round(s.ml, 1), "duration_h": d.duration_h, "cup": s.cup}
                  for d, s in zip(plan.new_doses, result.servings)],
        "last_dose": h_to_hhmm(plan.last_dose_h) if plan.last_dose_h is not None else None,
        "cutoff": h_to_hhmm(plan.cutoff_h) if plan.cutoff_h is not None else None,
        "total_mg": round(plan.total_mg, 1), "max_residual_mg": round(plan.max_residual_mg, 2),
        "sleep_loss_min": round(plan.sleep_loss_min, 2),
        "sleepiness_reduction": round(plan.sleepiness_reduction, 4),
        "danger_hours": round(plan.danger_hours, 2), "danger_hours_without": round(plan.danger_hours_without, 2),
    })
    return out


# ── 서버와 주고받기 ──
def _midnight(day: date) -> datetime:
    """그날 0시(한국 시간) = 엔진 시각 0h."""
    return datetime(day.year, day.month, day.day, tzinfo=local_tz())


def save_profile(session: Session, profile: Dict, sex: str, sip_ml: float, year: int,
                 transport: Optional[Transport] = None) -> None:
    rest(session, "POST", "profiles?on_conflict=user_id",
         profile_to_row(session.user_id, profile, sex, sip_ml, year),
         prefer="resolution=merge-duplicates", transport=transport)


def save_day(session: Session, scenario_dict: Dict, sex: str, result, day: date,
             transport: Optional[Transport] = None) -> Dict:
    """고른 날짜(day)의 입력 전체를 저장. 돌려주는 값: 저장한 건수 (화면 안내용)."""
    sc = from_dict(scenario_dict)
    start = _midnight(day)
    send = dict(transport=transport)

    save_profile(session, scenario_dict["profile"], sex, scenario_dict["sip_ml"], day.year, **send)

    sleeps = sleeps_to_rows(scenario_dict, start)
    woke = [_parse_ts(r["woke_at"]) for r in sleeps]
    lo, hi = min(woke) - timedelta(hours=12), max(woke) + timedelta(hours=12)
    rest(session, "DELETE", f"sleep_logs?woke_at=gte.{_q(lo)}&woke_at=lt.{_q(hi)}", **send)
    rest(session, "POST", "sleep_logs", sleeps, **send)

    wake = to_datetime(sc.sleeps[-1].end_h, start)
    rest(session, "DELETE",
         f"intakes?taken_at=gte.{_q(wake)}&taken_at=lt.{_q(wake + timedelta(days=1))}", **send)
    intakes = intakes_to_rows(scenario_dict, start)
    if intakes:
        rest(session, "POST", "intakes", intakes, **send)

    rest(session, "POST", "plans", {"plan_date": day.isoformat(), "engine_version": ENGINE_VERSION,
                                    "params_hash": params_hash(), "inputs": {**scenario_dict, "sex": sex},
                                    "result": plan_summary(result)}, **send)
    return {"nights": len(sleeps), "intakes": len(intakes)}


def recorded_days(session: Session, transport: Optional[Transport] = None) -> List[date]:
    """수면 기록이 있는 날짜(깬 날 기준, 최근 31일치) — 달력 옆 '기록 있는 날' 표시용."""
    rows = rest(session, "GET", "sleep_logs?select=woke_at&order=woke_at.desc&limit=31", transport=transport)
    return sorted({_parse_ts(r["woke_at"]).date() for r in rows})


def load_day(session: Session, day: date, transport: Optional[Transport] = None) -> Tuple[Dict, List[str]]:
    """고른 날짜의 서버 기록 → 화면 시작값과 안내 문구. 저장된 게 없는 항목은 넣지 않는다.

    last_night: 그날 아침에 깬 밤 (없으면 넣지 않음) · prev_nights: 그 전 밤들(하루씩 이어진 것만)
    today: already(그날 마신 것), bed·windows(그날 플랜, 없으면 가장 최근 플랜) · beverage
    """
    send = dict(transport=transport)
    base: Dict = {}
    notes: List[str] = []

    rows = rest(session, "GET", "profiles?select=*", **send)
    if rows:
        profile, sex, sip = row_to_profile(rows[0], day.year)
        base.update(profile=profile, sex=sex)
        if sip:
            base["sip_ml"] = sip
        notes.append("프로필")

    start = _midnight(day)
    rows = rest(session, "GET", f"sleep_logs?select=slept_at,woke_at,quality,sleep_latency_min"
                f"&woke_at=gte.{_q(start - timedelta(days=MAX_NIGHTS))}&woke_at=lt.{_q(start + timedelta(days=1))}"
                f"&order=woke_at.asc", **send)
    if rows:
        nights = rows_to_sleeps(rows)
        last = max(rows, key=lambda r: _parse_ts(r["woke_at"]))
        last_date = _parse_ts(last["woke_at"]).date()
        if last_date == day:
            base["last_night"] = nights[-1] if isinstance(nights[-1], dict) else {"time": nights[-1]}
            base["prev_nights"] = nights[:-1]
            notes.append("어젯밤 잠")
            wake = _parse_ts(last["woke_at"])
            rows = rest(session, "GET", f"intakes?select=taken_at,mg,sips&taken_at=gte.{_q(wake)}"
                        f"&taken_at=lt.{_q(wake + timedelta(days=1))}&order=taken_at.asc", **send)
            base["today"] = {"already": rows_to_intakes(rows)}
            if rows:
                notes.append(f"마신 것 {len(rows)}건")
        elif last_date == day - timedelta(days=1):
            base["prev_nights"] = nights
        if base.get("prev_nights"):
            notes.append(f"그 전 밤 {len(base['prev_nights'])}개")

    # 일정(잘 시각·시간대)과 음료는 그날 플랜, 없으면 가장 최근 플랜에서 (보통 매일 비슷하므로)
    rows = rest(session, "GET", f"plans?select=plan_date,inputs&plan_date=eq.{day.isoformat()}"
                f"&order=created_at.desc&limit=1", **send)
    same_day = bool(rows)
    if not rows:
        rows = rest(session, "GET", "plans?select=plan_date,inputs&order=created_at.desc&limit=1", **send)
    if rows:
        inputs = rows[0]["inputs"]
        goal = {k: inputs["today"][k] for k in ("bed", "windows") if k in inputs.get("today", {})}
        base.setdefault("today", {}).update(goal)
        if "beverage" in inputs:
            base["beverage"] = inputs["beverage"]
        notes.append("그날 일정" if same_day else "최근 일정")
    return base, notes


def add_sleepiness(session: Session, kss: int, note: str = "", transport: Optional[Transport] = None,
                   real_now: Optional[datetime] = None) -> Dict:
    """'지금 얼마나 졸려요?' 1~9 (카롤린스카 졸림 척도) — 엔진의 각성도 예측과 비교할 정답 데이터."""
    at = (real_now or datetime.now(local_tz())).astimezone(local_tz())
    row = {"at": _ts(at), "kind": "sleepiness", "kss": int(kss), "note": note.strip() or None}
    return rest(session, "POST", "feedback", row, transport=transport)[0]


def today_sleepiness(session: Session, transport: Optional[Transport] = None,
                     real_now: Optional[datetime] = None) -> List[Dict]:
    """오늘(한국 시간 0시부터) 남긴 졸림 기록. 서버는 시각을 UTC로 주므로 'time'에 한국 시각을 붙여 준다."""
    now = (real_now or datetime.now(local_tz())).astimezone(local_tz())
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = rest(session, "GET", f"feedback?select=at,kss,note&kind=eq.sleepiness&at=gte.{_q(midnight)}"
                f"&order=at.asc", transport=transport)
    return [{**r, "time": _parse_ts(r["at"]).strftime("%H:%M")} for r in rows]


def range_summary(session: Session, first: date, last: date, transport: Optional[Transport] = None) -> Dict[str, Dict]:
    """달력용: first~last 날짜마다 {sleep: "01:30~08:00", mg: 마신 총량, plan: 추천 잔 수, kss: 졸림 평균}.
    마신 것·졸림은 새벽 4시 전이면 전날로 센다 (밤늦게 마신 것도 그날 하루에 포함)."""
    send = dict(transport=transport)
    lo, hi = _midnight(first), _midnight(last) + timedelta(days=1)
    out: Dict[str, Dict] = {}

    def day_of(ts: str, rollover: bool) -> str:
        t = _parse_ts(ts)
        return ((t - timedelta(hours=4)) if rollover else t).date().isoformat()

    for r in rest(session, "GET", f"sleep_logs?select=slept_at,woke_at&woke_at=gte.{_q(lo)}&woke_at=lt.{_q(hi)}", **send):
        out.setdefault(day_of(r["woke_at"], False), {})["sleep"] = \
            f"{_parse_ts(r['slept_at']).strftime('%H:%M')}~{_parse_ts(r['woke_at']).strftime('%H:%M')}"
    hi4 = hi + timedelta(hours=4)
    for r in rest(session, "GET", f"intakes?select=taken_at,mg&taken_at=gte.{_q(lo + timedelta(hours=4))}"
                  f"&taken_at=lt.{_q(hi4)}", **send):
        cell = out.setdefault(day_of(r["taken_at"], True), {})
        cell["mg"] = cell.get("mg", 0) + float(r["mg"])
    for r in rest(session, "GET", f"plans?select=plan_date,result&plan_date=gte.{first.isoformat()}"
                  f"&plan_date=lte.{last.isoformat()}&order=created_at.asc", **send):
        out.setdefault(r["plan_date"], {})["plan"] = len((r.get("result") or {}).get("doses", []))  # 마지막 저장이 남음
    kss: Dict[str, List[int]] = {}
    for r in rest(session, "GET", f"feedback?select=at,kss&kind=eq.sleepiness&at=gte.{_q(lo + timedelta(hours=4))}"
                  f"&at=lt.{_q(hi4)}", **send):
        kss.setdefault(day_of(r["at"], True), []).append(r["kss"])
    for d, values in kss.items():
        out.setdefault(d, {})["kss"] = round(sum(values) / len(values), 1)
    return out


# ── 앱 알림 (Step 4-5) ──
def push_devices(session: Session, transport: Optional[Transport] = None) -> List[Dict]:
    """알림 받을 기기 목록 (화면 맨 위 '알림 켜기'로 등록한 기기)."""
    return rest(session, "GET", "push_subscriptions?select=id,user_agent,created_at&order=created_at.asc",
                transport=transport)


def _day_window(day: date) -> Tuple[datetime, datetime]:
    """그날 알림 범위: 새벽 4시 ~ 다음 날 새벽 4시 (밤늦게 '금지' 알림도 그날 것)."""
    start = _midnight(day) + timedelta(hours=4)
    return start, start + timedelta(days=1)


def scheduled_notifications(session: Session, day: date, transport: Optional[Transport] = None) -> List[Dict]:
    lo, hi = _day_window(day)
    rows = rest(session, "GET", f"notifications?select=send_at,kind,title,status&send_at=gte.{_q(lo)}"
                f"&send_at=lt.{_q(hi)}&status=neq.cancelled&order=send_at.asc", transport=transport)
    return [{**r, "time": _parse_ts(r["send_at"]).strftime("%H:%M")} for r in rows]


def schedule_push(session: Session, items, day: date, transport: Optional[Transport] = None) -> int:
    """그날 아직 안 보낸 플랜 알림을 취소하고 새 알림으로 바꾼다 (추천을 고쳐 다시 눌러도 중복 없음).
    items: notify.schedule()의 결과 중 보낼 것(send=True)."""
    lo, hi = _day_window(day)
    rest(session, "PATCH", f"notifications?status=eq.pending&kind=in.(drink,stop,feedback)"
         f"&send_at=gte.{_q(lo)}&send_at=lt.{_q(hi)}", {"status": "cancelled"}, transport=transport)
    rows = [{"send_at": _ts(i.at), "kind": i.notification.kind, "title": i.notification.title,
             "body": i.notification.message} for i in items]
    if rows:
        rest(session, "POST", "notifications", rows, transport=transport)
    return len(rows)


def push_test(session: Session, item, transport: Optional[Transport] = None) -> None:
    """item: notify.schedule_test()의 결과."""
    rest(session, "POST", "notifications", {"send_at": _ts(item.at), "kind": "test", "title": item.notification.title,
                                            "body": item.notification.message}, transport=transport)


def report_rows(session: Session, first: date, last: date, transport: Optional[Transport] = None) -> Dict[str, List]:
    """리포트용 원자료: first~last(포함) 날짜의 마신 것·플랜·수면·졸림 기록 (하루 = 새벽 4시 ~ 다음 날 새벽 4시)."""
    send = dict(transport=transport)
    lo, hi = _day_window(first)[0], _day_window(last)[1]
    start, end = _midnight(first), _midnight(last) + timedelta(days=1)
    return {
        "intakes": rest(session, "GET", f"intakes?select=taken_at,mg&taken_at=gte.{_q(lo)}&taken_at=lt.{_q(hi)}"
                        f"&order=taken_at.asc", **send),
        "plans": rest(session, "GET", f"plans?select=plan_date,result,created_at&plan_date=gte.{first.isoformat()}"
                      f"&plan_date=lte.{last.isoformat()}&order=created_at.asc", **send),
        "sleeps": rest(session, "GET", f"sleep_logs?select=slept_at,woke_at,quality,sleep_latency_min"
                       f"&woke_at=gte.{_q(start)}&woke_at=lt.{_q(end)}&order=woke_at.asc", **send),
        "kss": rest(session, "GET", f"feedback?select=at,kss&kind=eq.sleepiness&at=gte.{_q(lo)}&at=lt.{_q(hi)}"
                    f"&order=at.asc", **send),
    }


# ── 앱 의견 보내기 (설정 → 의견 보내기) — 로그인 안 해도 됨 ──
FEEDBACK_CATEGORIES = ["불편", "버그", "기능 요청", "기타"]


def send_app_feedback(session: Optional[Session], category: str, message: str, contact: str = "",
                      page: str = "", user_agent: str = "", transport: Optional[Transport] = None) -> None:
    """app_feedback 표에 한 줄. 표에는 읽기 규칙이 없어 넣은 행을 돌려받지 않는다(returning=False)."""
    message = message.strip()
    if category not in FEEDBACK_CATEGORIES:
        raise ValueError("의견 종류를 골라 주세요")
    if not message:
        raise ValueError("내용을 적어 주세요")
    row = {"category": category, "message": message[:2000], "contact": contact.strip()[:200] or None,
           "page": page[:100] or None, "user_agent": user_agent[:500] or None}
    rest(session, "POST", "app_feedback", row, transport=transport, returning=False)
