"""입력 화면 ↔ 시나리오 형식(dict) 변환. 화면 코드와 분리해 테스트할 수 있게 둔다."""
from datetime import time
from typing import Iterable, List, Optional

KIND_LABELS = ["깨어 있기", "졸면 안 됨", "집중"]
SENSITIVITY_LABEL = {"sensitive": "민감", "normal": "보통", "tolerant": "둔감"}
CHRONOTYPE_LABEL = {"morning": "아침형", "neutral": "보통", "evening": "저녁형"}
# 카롤린스카 졸림 척도(KSS) — 홀수 단계에만 설명이 있는 원래 척도를 그대로 따름
KSS_LABEL = {1: "매우 또렷함", 3: "또렷함", 5: "또렷하지도 졸리지도 않음", 7: "졸림 (깨어 있기는 어렵지 않음)",
             9: "매우 졸림 (잠과 싸우는 중)"}


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


LATENCY_COL = "잠들기 (분)"


def _num(x) -> Optional[int]:
    return None if x is None or x != x else int(x)


def sleep_rows_to_list(rows: Iterable[dict]) -> List:
    """수면 표 행 [{잠든 시각, 깬 시각, 수면 질, 잠들기 (분)}] → 시나리오 sleep 목록 (빈 행은 건너뜀).
    잠들기 = 누워서 잠들 때까지 걸린 시간 (매일 피드백, 엔진 계산에는 안 쓰고 저장만)."""
    out = []
    for r in rows:
        start, wake = hhmm(r.get("잠든 시각")), hhmm(r.get("깬 시각"))
        if not (start and wake):
            continue
        quality, latency = _num(r.get("수면 질")), _num(r.get(LATENCY_COL))
        if quality is None and latency is None:
            out.append(f"{start}-{wake}")
        else:
            night = {"time": f"{start}-{wake}"}
            if quality is not None:
                night["quality"] = quality
            if latency is not None:
                night["latency_min"] = latency
            out.append(night)
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
        night = {"time": night} if isinstance(night, str) else night
        start, wake = (x.strip() for x in night["time"].split("-"))
        rows.append({"잠든 시각": to_time(start), "깬 시각": to_time(wake), "수면 질": night.get("quality"),
                     LATENCY_COL: night.get("latency_min")})
    return rows


def intake_list_to_rows(already: Iterable[dict]) -> List[dict]:
    return [{"시각": to_time(a["time"]), "양": a.get("mg", a.get("sips")),
             "단위": "mg" if "mg" in a else "모금"} for a in already]


def window_list_to_rows(windows: Iterable[dict]) -> List[dict]:
    kind_name = {"stay_awake": "깨어 있기", "must_not_sleep": "졸면 안 됨", "focus": "집중"}
    return [{"종류": kind_name.get(w["kind"], w["kind"]), "시작": to_time(w["from"]), "끝": to_time(w["to"])}
            for w in windows]


# ── 음료 DB에서 고르기 (beverages.yaml) ──
def beverage_choices(db) -> dict:
    """{브랜드: {메뉴: [음료, ...]}} — 용량(ml)을 모르는 음료는 모금으로 바꿀 수 없어 뺀다. 브랜드는 DB 순서."""
    out: dict = {}
    for d in db:
        if d.ml:
            out.setdefault(d.brand, {}).setdefault(d.menu, []).append(d)
    return out


def size_label(d) -> str:
    temp = f"{d.temp} · " if d.temp else ""
    return f"{temp}{d.size} {d.ml:g}ml · {d.mg:g}mg"


def beverage_spec(d) -> dict:
    """시나리오 beverage 형식. db에 원래 이름을 남겨 다음에 같은 음료를 다시 골라 준다."""
    return {"name": d.label, "mg": d.mg, "ml": d.ml, "db": d.label}


# ── 음료 카페인 보기 ──
DRINK_GROUPS = {"에너지음료": {"레드불", "몬스터", "핫식스"},
                "편의점 커피": {"맥심", "레쓰비", "스타벅스 RTD", "바리스타룰스"},
                "차·탄산·믹스": {"일반", "코카콜라", "펩시"}}


def drink_group(brand: str) -> str:
    """브랜드 → 분류 (카페 / 편의점 커피 / 에너지음료 / 차·탄산·믹스)."""
    return next((g for g, brands in DRINK_GROUPS.items() if brand in brands), "카페")


# ── 하루 입력 다이얼 ──
LATENCY_OPTIONS = ["모름"] + list(range(0, 125, 5))           # 잠들기까지 (분)
WINDOW_HINT = {"졸면 안 됨": "시험·수업·운전", "집중": "가장 어려운 과목·발표"}
# 양 휠: 오른쪽 단위를 바꾸면 왼쪽 숫자 목록이 바뀜. start = 그 단위로 바꿨을 때 처음 가리킬 칸
_CUPS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
_SIPS = list(range(1, 41))
_MG = list(range(10, 410, 10))


def amount_units(brand=None) -> List[dict]:
    """잔 단위는 브랜드 컵 크기로 (스타벅스면 Short·Tall·Venti 잔, 모르면 스몰·기본·빅 잔) + 모금 + mg."""
    from caffeine_engine.convert import cup_sizes
    cups = [{"name": f"{c.name} 잔" if brand else f"{c.key} 잔", "options": [f"{x:g}" for x in _CUPS], "start": 1,
             "values": _CUPS, "cup": {"size": c.key, "cup_ml": c.ml, "cup_name": c.name}}
            for c in cup_sizes(brand)]
    return cups + [{"name": "모금", "options": [str(x) for x in _SIPS], "start": 7, "values": _SIPS},
                   {"name": "mg", "options": [str(x) for x in _MG], "start": 9, "values": _MG}]


AMOUNT_UNITS = amount_units()


def amount_entry(time_text: str, unit: int, value: float, units: Optional[List[dict]] = None) -> dict:
    """양 휠의 (단위, 값) → 시나리오 already 한 줄. 잔이면 {"cups", "size", "cup_ml", "cup_name"}, 아니면 {"sips"} / {"mg"}."""
    u = (units or AMOUNT_UNITS)[unit]
    if "cup" in u:
        return {"time": time_text, "cups": float(value), **u["cup"]}
    return {"time": time_text, "sips" if u["name"] == "모금" else "mg": float(value)}


def amount_text(a: dict) -> str:
    if "cups" in a:
        name = a.get("cup_name") or a.get("size", "기본")
        size = f"{name} 사이즈" if name in ("스몰", "기본", "빅") else name
        return f"{size} {a['cups']:g}잔"
    return f"{a['sips']:g}모금" if "sips" in a else f"{a['mg']:g}mg"
