"""입력 화면 ↔ 시나리오 형식(dict) 변환. 화면 코드와 분리해 테스트할 수 있게 둔다."""
from datetime import time
from typing import Iterable, List, Optional

KIND_LABELS = ["깨어 있기", "졸면 안 됨", "집중"]
SENSITIVITY_LABEL = {"sensitive": "민감", "normal": "보통", "tolerant": "둔감"}
CHRONOTYPE_LABEL = {"morning": "아침형", "neutral": "보통", "evening": "저녁형"}


def sensitivity_from_survey(cups_per_day: int, late_coffee_hurts_sleep: str, palpitations: str) -> str:
    """노션 파이프라인 v2의 민감도 설문 3문항 → sensitive / normal / tolerant. (설계값, 임시)

    잠이 안 오거나 두근거림이 '예'면 민감, 하루 3잔 이상 마시는데 둘 다 '아니오'면 둔감.
    """
    if "예" in (late_coffee_hurts_sleep, palpitations):
        return "sensitive"
    if cups_per_day >= 3 and late_coffee_hurts_sleep == palpitations == "아니오":
        return "tolerant"
    return "normal"


def hhmm(t) -> Optional[str]:
    """datetime.time 또는 'HH:MM' → 'HH:MM'. 비어 있으면 None."""
    if t is None or t != t:  # None 또는 NaN
        return None
    if isinstance(t, time):
        return t.strftime("%H:%M")
    text = str(t).strip()
    return text[:5] if text else None


def to_time(text: str) -> time:
    h, m = (int(x) for x in text.split(":"))
    return time(h, m)


def sleep_rows_to_list(rows: Iterable[dict]) -> List:
    """수면 표 행 [{잠든 시각, 깬 시각, 수면 질}] → 시나리오 sleep 목록 (빈 행은 건너뜀)."""
    out = []
    for r in rows:
        start, wake = hhmm(r.get("잠든 시각")), hhmm(r.get("깬 시각"))
        if not (start and wake):
            continue
        quality = r.get("수면 질")
        if quality is None or quality != quality:
            out.append(f"{start}-{wake}")
        else:
            out.append({"time": f"{start}-{wake}", "quality": int(quality)})
    return out


def intake_rows_to_list(rows: Iterable[dict]) -> List[dict]:
    """이미 마신 것 표 행 [{시각, 양, 단위}] → 시나리오 already 목록."""
    out = []
    for r in rows:
        t, amount = hhmm(r.get("시각")), r.get("양")
        if not t or amount is None or amount != amount or amount <= 0:
            continue
        key = "sips" if r.get("단위") == "모금" else "mg"
        out.append({"time": t, key: float(amount)})
    return out


def window_rows_to_list(rows: Iterable[dict]) -> List[dict]:
    """시간대 표 행 [{종류, 시작, 끝}] → 시나리오 windows 목록."""
    out = []
    for r in rows:
        kind, start, end = r.get("종류"), hhmm(r.get("시작")), hhmm(r.get("끝"))
        if kind in KIND_LABELS and start and end:
            out.append({"kind": kind, "from": start, "to": end})
    return out


def sleep_list_to_rows(sleep: Iterable) -> List[dict]:
    rows = []
    for night in sleep:
        text, quality = (night, None) if isinstance(night, str) else (night["time"], night.get("quality"))
        start, wake = (x.strip() for x in text.split("-"))
        rows.append({"잠든 시각": to_time(start), "깬 시각": to_time(wake), "수면 질": quality})
    return rows


def intake_list_to_rows(already: Iterable[dict]) -> List[dict]:
    return [{"시각": to_time(a["time"]), "양": a.get("mg", a.get("sips")),
             "단위": "mg" if "mg" in a else "모금"} for a in already]


def window_list_to_rows(windows: Iterable[dict]) -> List[dict]:
    kind_name = {"stay_awake": "깨어 있기", "must_not_sleep": "졸면 안 됨", "focus": "집중"}
    return [{"종류": kind_name.get(w["kind"], w["kind"]), "시작": to_time(w["from"]), "끝": to_time(w["to"])}
            for w in windows]
