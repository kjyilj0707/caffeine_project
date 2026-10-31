"""시각 표현: 엔진 안에서는 '그날 00:00부터 지난 시간(h)'을 쓴다.

자정을 넘긴 시각은 24를 더한다. 예: 다음 날 01:00 → 25.0
"""


def hhmm_to_h(text: str, next_day: bool = False) -> float:
    hour, minute = (int(x) for x in text.split(":"))
    return hour + minute / 60 + (24 if next_day else 0)


def h_to_hhmm(hours: float) -> str:
    total_min = round(hours * 60)
    return f"{(total_min // 60) % 24:02d}:{total_min % 60:02d}"
