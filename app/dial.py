"""다이얼 입력 (iOS 휠 · 끌어서 정하는 선) + 직접 입력 — components/dial/index.html을 Python에서 쓰기 쉽게 감싼 것.

  time_wheel("잠든 시각", "01:30", key)        → "01:30"   (시 · 분 휠, 분은 5분 단위 / 직접 입력 "1:37")
  date_wheel("날짜", date, today, key)          → date      (최근 60일 ~ 내일 / 직접 입력 "11/3", "2026-11-03")
  number_wheel("잠들기", 15, range(0, 121, 5), "분", key) → 15   (직접 입력은 목록에 없는 수도 됨: 7)
  span_wheel("시간", "14:00", "16:00", key)      → ("14:00", "16:00")   (직접 입력 "14:00-16:30")
  amount_wheel("양", units, unit, idx, key)      → (unit, 값)   단위를 바꾸면 숫자 목록이 바뀜 (직접 입력 "250")
  line("잠의 질", 0.5, labels, key)             → 0~1          (직접 입력은 1~칸 수: "4")
모든 휠·선의 제목 옆 [직접 입력]을 누르면 글자로 넣을 수 있고, 잘못 넣으면 안내를 보여주고 원래 값을 쓴다.
테스트(AppTest)에서는 부품이 그려지지 않아 기본값이 그대로 돌아온다.
"""
import re
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import streamlit as st
import streamlit.components.v1 as components

_dial = components.declare_component("dial", path=str(Path(__file__).resolve().parent / "components" / "dial"))

HOURS = [f"{h:02d}" for h in range(24)]
MINUTES = [f"{m:02d}" for m in range(0, 60, 5)]
WEEKDAY = "월화수목금토일"
_TIME = r"(\d{1,2})\s*(?:[:.]|시)?\s*(?:(\d{1,2})\s*분?)?"


def _typed(value) -> Optional[str]:
    return value["text"] if isinstance(value, dict) and "text" in value else None


def _bad(label: str, text: str, hint: str) -> None:
    st.caption(f":orange[‘{text}’은(는) {label}(으)로 읽을 수 없어요 — 예: {hint}]")


def parse_time(text: str) -> Optional[str]:
    """'1:37' '01:37' '0137' '1시 37분' '7시' → 'HH:MM'"""
    t = text.strip().replace(" ", "")
    if re.fullmatch(r"\d{3,4}", t):
        t = f"{t[:-2]}:{t[-2:]}"
    m = re.fullmatch(_TIME, t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def parse_span(text: str) -> Optional[Tuple[str, str]]:
    """'14:00-16:30' '14:00~16:30' '1400 1630' → ('14:00', '16:30')"""
    parts = [p for p in re.split(r"\s*[-~]\s*|\s+", text.strip()) if p]
    if len(parts) != 2:
        return None
    a, b = parse_time(parts[0]), parse_time(parts[1])
    return (a, b) if a and b else None


def parse_date(text: str, today: date) -> Optional[date]:
    """'11/3' '11-3' '11월 3일' '2026-11-03' '오늘' '어제' → date"""
    t = text.strip()
    if t in ("오늘", "어제", "그제"):
        return today - timedelta(days=("오늘", "어제", "그제").index(t))
    nums = [int(x) for x in re.findall(r"\d+", t)]
    try:
        if len(nums) == 3:
            return date(nums[0] if nums[0] > 31 else 2000 + nums[0], nums[1], nums[2])
        if len(nums) == 2:
            return date(today.year, nums[0], nums[1])
    except ValueError:
        return None
    return None


def parse_number(text: str) -> Optional[float]:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[a-zA-Z가-힣]*\s*", text)
    return float(m.group(1)) if m else None


def _wheel(label: str, columns: List[dict], index: List[int], key: str, typing: str):
    value = _dial(kind="wheel", label=label, columns=columns, index=index, typing=typing, key=key, default=index)
    if _typed(value) is not None:
        return value
    return list(value) if isinstance(value, list) and len(value) == len(index) else index


def _hm_index(hhmm: str) -> List[int]:
    h, m = (int(x) for x in hhmm.split(":"))
    return [h, min(11, round(m / 5))]


def _hm(h_i: int, m_i: int) -> str:
    return f"{HOURS[h_i]}:{MINUTES[m_i]}"


def time_wheel(label: str, hhmm: str, key: str) -> str:
    v = _wheel(label, [{"options": HOURS, "width": 90}, {"sep": ":"}, {"options": MINUTES, "width": 90}],
               _hm_index(hhmm), key, typing="예: 1:37")
    text = _typed(v)
    if text is None:
        return _hm(*v)
    parsed = parse_time(text)
    if parsed is None:
        _bad("시각", text, "1:37, 0137, 7시 30분")
        return hhmm
    return parsed


def span_wheel(label: str, start: str, end: str, key: str) -> Tuple[str, str]:
    cols = [{"options": HOURS}, {"sep": ":"}, {"options": MINUTES}, {"sep": "~"},
            {"options": HOURS}, {"sep": ":"}, {"options": MINUTES}]
    v = _wheel(label, cols, _hm_index(start) + _hm_index(end), key, typing="예: 01:30-08:00")
    text = _typed(v)
    if text is None:
        return _hm(v[0], v[1]), _hm(v[2], v[3])
    parsed = parse_span(text)
    if parsed is None:
        _bad("시작~끝 시각", text, "01:30-08:00")
        return start, end
    return parsed


def date_options(today: date, back: int = 60, ahead: int = 1) -> List[date]:
    return [today + timedelta(days=k) for k in range(-back, ahead + 1)]


def date_label(d: date, today: date) -> str:
    if d == today:
        return "오늘"
    return f"{d.month}월 {d.day}일 ({WEEKDAY[d.weekday()]})"


def date_wheel(label: str, value: date, today: date, key: str) -> date:
    days = date_options(today)
    if value not in days:
        days = sorted(set(days) | {value})
    v = _wheel(label, [{"options": [date_label(x, today) for x in days], "width": 220}], [days.index(value)], key,
               typing="예: 11/3")
    text = _typed(v)
    if text is None:
        return days[v[0]]
    parsed = parse_date(text, today)
    if parsed is None:
        _bad("날짜", text, "11/3, 2026-11-03, 어제")
        return value
    return parsed


def number_wheel(label: str, value, options: Sequence, unit: str, key: str):
    """목록에서 고르거나 직접 숫자를 넣는다. 직접 넣은 수는 목록의 숫자 범위 안이어야 한다."""
    options = list(options)
    start = options.index(value) if value in options else 0
    v = _wheel(label, [{"options": [f"{o:g}" if isinstance(o, float) else str(o) for o in options], "width": 110},
                       {"sep": unit}], [start], key, typing=f"숫자 ({unit})")
    text = _typed(v)
    if text is None:
        return options[v[0]]
    nums = [o for o in options if isinstance(o, (int, float))]
    x = parse_number(text)
    if x is None or not (min(nums) <= x <= max(nums)):
        _bad(label, text, f"{min(nums):g}~{max(nums):g} 사이 숫자")
        return value
    return int(x) if x == int(x) and all(isinstance(o, int) for o in nums) else x


def amount_wheel(label: str, units: List[dict], unit: int, idx: int, key: str) -> Tuple[int, float]:
    """units = [{"name": "기본 잔", "options": ["0.5", "1", ...], "values": [...], "start": 1}, ...] → (단위, 값)"""
    v = _dial(kind="amount", label=label, units=units, value={"unit": unit, "idx": idx}, typing="숫자", key=key,
              default={"unit": unit, "idx": idx})
    if isinstance(v, dict) and "text" in v:
        u = int(v.get("unit", unit))
        x = parse_number(v["text"])
        top = max(units[u]["values"]) * 2
        if x is None or not (0 < x <= top):
            _bad(f"{units[u]['name']} 양", v["text"], f"0보다 크고 {top:g} 이하")
            return unit, units[unit]["values"][idx]
        return u, x
    if isinstance(v, dict) and "unit" in v:
        u = int(v["unit"])
        vals = units[u]["values"]
        return u, vals[min(int(v["idx"]), len(vals) - 1)]
    return unit, units[unit]["values"][idx]


def line(label: str, value: float, labels: Sequence[str], key: str, ends: Sequence[str] = ()) -> float:
    """끌어서 0~1. 직접 입력은 1~칸 수(labels 개수)의 숫자 → 그 칸의 가운데 값."""
    n = len(labels)
    v = _dial(kind="line", label=label, value=float(value), labels=list(labels), ends=list(ends) or None,
              typing=f"1~{n}", key=key, default=float(value))
    text = _typed(v)
    if text is not None:
        x = parse_number(text)
        if x is None or not (1 <= x <= n):
            _bad(label, text, f"1~{n} 사이 숫자")
            return float(value)
        return (x - 0.5) / n
    return float(v) if isinstance(v, (int, float)) else float(value)
