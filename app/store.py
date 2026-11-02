"""기록 저장·불러오기 (Step 4-3) — 입력 화면의 내용 ↔ 서버 표(profiles, sleep_logs, intakes, plans).

화면은 '시각만'(예: "01:30-08:00") 다루고 서버는 '날짜+시각'(timestamptz)을 저장한다.
그날의 기준(D)은 어젯밤 기록의 깬 날짜이고, 엔진 시각 h는 D 0시(한국 시간) + h시간이다.

  저장: 화면 내용을 엔진 형식으로 바꾼 뒤(scenario.from_dict) 실제 날짜·시각으로 바꿔 저장.
        수면·마신 것은 '화면에 있는 기간'의 기존 기록을 지우고 새로 넣는다(고친 내용이 그대로 반영).
  불러오기: 기본 정보 + 최근 연속된 수면(최대 7밤) + 오늘 마신 것 + 오늘(없으면 최근) 목표.
"""
import hashlib
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from caffeine_engine import params
from caffeine_engine.notify import day_start, local_tz, to_datetime
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
    return [{"slept_at": _ts(to_datetime(e.start_h, start)), "woke_at": _ts(to_datetime(e.end_h, start)),
             "quality": e.quality} for e in sc.sleeps]


def rows_to_sleeps(rows: List[Dict]) -> List:
    """서버 수면 기록 → 화면 형식. 마지막 밤부터 거꾸로, 날짜가 하루씩 이어진 밤만 (빠진 날이 있으면 거기까지)."""
    nights = sorted(rows, key=lambda r: _parse_ts(r["woke_at"]))
    out, expected = [], None
    for r in reversed(nights):
        woke, slept = _parse_ts(r["woke_at"]), _parse_ts(r["slept_at"])
        if expected is not None and woke.date() != expected:
            break
        text = f"{slept.strftime('%H:%M')}-{woke.strftime('%H:%M')}"
        out.append({"time": text, "quality": r["quality"]} if r.get("quality") else text)
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
        rows.append({"taken_at": _ts(to_datetime(dose.time_h, start)), "mg": round(dose.mg, 1),
                     "sips": entry.get("sips"), "beverage_label": sc.beverage.name})
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
                   "sips": s.sips, "ml": round(s.ml, 1)} for d, s in zip(plan.new_doses, result.servings)],
        "last_dose": h_to_hhmm(plan.last_dose_h) if plan.last_dose_h is not None else None,
        "cutoff": h_to_hhmm(plan.cutoff_h) if plan.cutoff_h is not None else None,
        "total_mg": round(plan.total_mg, 1), "max_residual_mg": round(plan.max_residual_mg, 2),
        "sleep_loss_min": round(plan.sleep_loss_min, 2),
        "sleepiness_reduction": round(plan.sleepiness_reduction, 4),
        "danger_hours": round(plan.danger_hours, 2), "danger_hours_without": round(plan.danger_hours_without, 2),
    })
    return out


# ── 서버와 주고받기 ──
def save_day(session: Session, scenario_dict: Dict, sex: str, result, transport: Optional[Transport] = None,
             real_now: Optional[datetime] = None) -> Dict:
    """화면 내용 전체를 저장. 돌려주는 값: 저장한 건수 (화면 안내용)."""
    sc = from_dict(scenario_dict)
    start = day_start(sc.now_h, real_now)
    send = dict(transport=transport)

    rest(session, "POST", "profiles?on_conflict=user_id",
         profile_to_row(session.user_id, scenario_dict["profile"], sex, scenario_dict["sip_ml"], start.year),
         prefer="resolution=merge-duplicates", **send)

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

    rest(session, "POST", "plans", {"plan_date": start.date().isoformat(), "engine_version": ENGINE_VERSION,
                                    "params_hash": params_hash(), "inputs": {**scenario_dict, "sex": sex},
                                    "result": plan_summary(result)}, **send)
    return {"nights": len(sleeps), "intakes": len(intakes)}


def load_day(session: Session, transport: Optional[Transport] = None,
             real_now: Optional[datetime] = None) -> Tuple[Dict, List[str]]:
    """서버 기록 → 화면 시작값(시나리오 형식 일부 + 'sex') 과 안내 문구.
    저장된 게 없는 항목은 넣지 않는다(화면이 예시값을 그대로 씀)."""
    send = dict(transport=transport)
    now = (real_now or datetime.now(local_tz())).astimezone(local_tz())
    base: Dict = {}
    notes: List[str] = []

    rows = rest(session, "GET", "profiles?select=*", **send)
    if rows:
        profile, sex, sip = row_to_profile(rows[0], now.year)
        base.update(profile=profile, sex=sex)
        if sip:
            base["sip_ml"] = sip
        notes.append("기본 정보")

    since = now - timedelta(days=MAX_NIGHTS + 1)
    rows = rest(session, "GET", f"sleep_logs?select=slept_at,woke_at,quality&woke_at=gte.{_q(since)}"
                f"&woke_at=lte.{_q(now)}&order=woke_at.asc", **send)
    sleep = rows_to_sleeps(rows) if rows else []
    if sleep:
        base["sleep"] = sleep
        notes.append(f"수면 {len(sleep)}밤")
        wake = max(_parse_ts(r["woke_at"]) for r in rows)
        rows = rest(session, "GET", f"intakes?select=taken_at,mg,sips&taken_at=gte.{_q(wake)}"
                    f"&taken_at=lt.{_q(wake + timedelta(days=1))}&order=taken_at.asc", **send)
        base["today"] = {"already": rows_to_intakes(rows)}
        if rows:
            notes.append(f"오늘 마신 것 {len(rows)}건")
        today: Optional[date] = wake.date()
    else:
        today = None

    # 목표(시간대·취침)와 음료는 오늘 플랜, 없으면 가장 최근 플랜에서 (보통 매일 비슷하므로)
    rows = rest(session, "GET", "plans?select=plan_date,inputs&order=created_at.desc&limit=1", **send)
    if rows:
        inputs = rows[0]["inputs"]
        goal = {k: inputs["today"][k] for k in ("bed", "windows") if k in inputs.get("today", {})}
        base.setdefault("today", {}).update(goal)
        if "beverage" in inputs:
            base["beverage"] = inputs["beverage"]
        notes.append("오늘 목표" if today and rows[0]["plan_date"] == today.isoformat() else "최근 목표")
    return base, notes
