"""시나리오 파일(.yaml) → 엔진 입력. 사람이 쓰기 쉬운 형식을 엔진 형식으로 바꾼다.

시각 규칙
  수면: 오래된 밤부터 적고 마지막 줄이 어젯밤. "00:30-07:30"처럼 '잠든-깬' 시각.
        잠든 시각이 깬 시각보다 늦으면(예: 23:30-07:00) 전날 밤으로 본다.
  오늘: 오늘 일어난 시각(어젯밤 기록의 깬 시각)보다 이른 시각은 다음 날(자정 넘김)로 본다.
        예: 08:00 기상이면 bed 01:00 → 다음 날 01:00, 시간대 23:00-01:00 → 23시~다음 날 1시
        단, 기상 전에 시작해 기상 후에 끝나는 시간대(08:30 기상, 08:00-23:00)는 기상 시각부터로 본다.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

from .convert import Beverage, cup_ml, default_beverages, from_ml, from_sips
from .fatigue import SleepEpisode
from .optimizer import Window
from .pk import Dose
from .profile import Profile
from .timeutil import hhmm_to_h

KIND_NAMES = {"깨어 있기": "stay_awake", "졸면 안 됨": "must_not_sleep", "집중": "focus",
              "stay_awake": "stay_awake", "must_not_sleep": "must_not_sleep", "focus": "focus"}


@dataclass
class Scenario:
    name: str
    profile: Profile
    sleeps: List[SleepEpisode]
    windows: List[Window]
    now_h: float
    bed_h: float
    already: List[Dose]
    beverage: Beverage
    sip_ml: Optional[float]


def _parse_sleeps(nights) -> List[SleepEpisode]:
    out = []
    for k, night in enumerate(reversed(nights)):  # k = 0 이 어젯밤
        text, quality = (night, None) if isinstance(night, str) else (night["time"], night.get("quality"))
        start_txt, wake_txt = (x.strip() for x in text.split("-"))
        wake = hhmm_to_h(wake_txt) - 24 * k
        start = hhmm_to_h(start_txt) - 24 * k
        if start > wake:
            start -= 24
        out.append(SleepEpisode(start, wake, quality))
    return sorted(out, key=lambda e: e.start_h)


def _today(text: str, wake_h: float) -> float:
    t = hhmm_to_h(text)
    return t + 24 if t < wake_h else t


def _parse_beverage(spec) -> Beverage:
    if spec is None:
        return default_beverages()["coffee"]
    if isinstance(spec, str):
        return default_beverages()[spec]
    return Beverage.from_serving(spec["name"], spec["mg"], spec["ml"])


def load(path) -> Scenario:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    data.setdefault("name", Path(path).stem)
    return from_dict(data)


def from_dict(data: dict) -> Scenario:
    """시나리오 내용(dict) → 엔진 입력. 입력 화면도 이 형식으로 만들어 넘긴다."""
    sleeps = _parse_sleeps(data["sleep"])
    wake = sleeps[-1].end_h
    today = data["today"]
    beverage = _parse_beverage(data.get("beverage"))
    sip_ml = data.get("sip_ml")

    windows = []
    for w in today.get("windows", []):
        start, end = _today(w["from"], wake), _today(w["to"], wake)
        if start > end:  # 기상 전에 시작한 시간대 (예: 08:30 기상, 08:00-23:00) → 일어난 때부터
            start = max(start - 24, wake)
        if start < end:
            windows.append(Window(start, end, KIND_NAMES[w["kind"]]))

    already = []
    for a in today.get("already", []):
        drink = _parse_beverage(a["beverage"]) if a.get("beverage") else beverage
        if "mg" in a:
            mg = a["mg"]
        elif "cups" in a:     # 카페 잔 크기 (스몰·기본·빅, 브랜드별 ml) × 잔 수 → ml → mg
            mg = from_ml(a["cups"] * (a.get("cup_ml") or cup_ml(a.get("size", "기본"))), drink)
        else:
            mg = from_sips(a["sips"], drink, sip_ml)
        already.append(Dose(_today(a["time"], wake), mg))

    return Scenario(
        name=data.get("name", "오늘"),
        profile=Profile(**data.get("profile", {})),
        sleeps=sleeps,
        windows=windows,
        now_h=_today(today["now"], wake),
        bed_h=_today(today["bed"], wake),
        already=already,
        beverage=beverage,
        sip_ml=sip_ml,
    )
