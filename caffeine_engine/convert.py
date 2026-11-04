"""⑤ 변환 엔진 — mg ↔ 음료 ml ↔ 모금.

모금은 정수로 반올림하므로 실제 섭취량(mg_actual)은 목표와 조금 다를 수 있다.
(커피 1모금 ≈ 17.5ml × 0.428mg/ml ≈ 7.5mg)
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

from . import params


@dataclass(frozen=True)
class Beverage:
    name: str
    mg_per_ml: float
    serving_ml: Optional[float] = None   # 메뉴 한 잔 용량 (알면 '이 메뉴 2/3잔'처럼 안내)

    @classmethod
    def from_serving(cls, name: str, mg: float, ml: float) -> "Beverage":
        """메뉴 정보로 만들기. 예: Beverage.from_serving("아메리카노 톨", 150, 355)"""
        return cls(name, mg / ml, ml)


def default_beverages():
    conv = params.load()["conversion"]
    return {
        "coffee": Beverage("커피", conv["coffee_mg_per_ml"]["value"]),
        "black_tea": Beverage("홍차", conv["black_tea_mg_per_ml"]["value"]),
    }


@dataclass(frozen=True)
class Serving:
    beverage: Beverage
    mg_target: float
    sips: int
    ml: float
    mg_actual: float
    duration_h: float = 0.0
    cup: str = ""        # 예: "스몰 사이즈 1잔", "반 잔"
    pace: str = ""       # 예: "2~3분에 한 모금"

    @property
    def minutes(self) -> int:
        return round(self.duration_h * 60)


def _sip(sip_ml: Optional[float]) -> float:
    return sip_ml if sip_ml is not None else params.value("conversion", "sip_ml")


_FRACTIONS = [(0.25, "1/4"), (1 / 3, "1/3"), (0.5, "반"), (2 / 3, "2/3"), (0.75, "3/4"), (1.0, "1"),
              (1.5, "1.5"), (2.0, "2")]


def cup_text(ml: float, beverage: Beverage) -> str:
    """ml → 사람이 알아듣는 잔 단위. 메뉴 용량을 알면 그 메뉴 기준('2/3잔'), 아니면 카페 컵 크기 기준('스몰 사이즈 1잔')."""
    if beverage.serving_ml:
        prefix, size = "", beverage.serving_ml
    else:   # 그 양이 들어가는 가장 작은 컵(스몰→기본→빅)을 고르고, 그 컵의 몇 분의 몇인지로
        cups = cup_sizes()
        cup = next((c for c in cups if c.ml >= ml * 0.9), cups[-1])
        prefix, size = f"{cup.key} 사이즈 ", cup.ml
    _, text = min(((abs(f * size - ml) / ml + (0 if f == 1 else 0.03), t) for f, t in _FRACTIONS),
                  key=lambda x: x[0])
    return f"{prefix}{text} 잔" if text == "반" else f"{prefix}{text}잔"


def pace_text(sips: int, duration_h: float) -> str:
    """'30분 동안 13모금' → '2~3분에 한 모금' (사람이 세지 않아도 되는 속도 안내)."""
    if duration_h <= 0 or sips <= 1:
        return ""
    per = duration_h * 60 / sips
    if per < 1:
        return f"1분에 {round(1 / per)}모금"
    lo, hi = int(per), int(per) + (0 if per == int(per) else 1)
    return f"{lo}분에 한 모금" if lo == hi else f"{lo}~{hi}분에 한 모금"


def to_serving(mg: float, beverage: Beverage, sip_ml: Optional[float] = None, duration_h: float = 0.0) -> Serving:
    """목표 mg → 마실 양(ml) · 잔 단위 · (나눠 마시면) 속도. 모금 수는 속도 안내용으로만."""
    sip = _sip(sip_ml)
    sips = max(1, round(mg / beverage.mg_per_ml / sip))
    ml = sips * sip
    return Serving(beverage, mg, sips, ml, ml * beverage.mg_per_ml, duration_h, cup_text(ml, beverage),
                   pace_text(sips, duration_h))


def from_sips(sips: float, beverage: Beverage, sip_ml: Optional[float] = None) -> float:
    """'n모금 마셨어요' → mg."""
    return sips * _sip(sip_ml) * beverage.mg_per_ml


def from_ml(ml: float, beverage: Beverage) -> float:
    return ml * beverage.mg_per_ml


# ── 음료 카페인 DB (beverages.yaml, 조사일 2026-11-01) ──
BEVERAGES_PATH = Path(__file__).resolve().parent.parent / "beverages.yaml"
_FIELDS = ("brand", "menu", "temp", "size", "ml", "mg", "source_type", "source", "note")


@dataclass(frozen=True)
class DrinkEntry:
    brand: str
    menu: str
    temp: Optional[str]
    size: str
    ml: Optional[float]
    mg: float
    source_type: str   # 공식 / 2차 / 공공 / 학술
    source_url: str
    note: str

    @property
    def label(self) -> str:
        temp = f" {self.temp}" if self.temp else ""
        ml = f" {self.ml:g}ml" if self.ml else ""
        return f"{self.brand} {self.menu}{temp} ({self.size}{ml})"

    def beverage(self) -> Optional[Beverage]:
        """모금 변환용 Beverage. 용량을 모르면 None (그때는 '1잔' 단위로만 쓴다)."""
        return Beverage(self.label, self.mg / self.ml) if self.ml else None


def load_beverage_db(path: Path = BEVERAGES_PATH) -> List[DrinkEntry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = data["sources"]
    out = []
    for row in data["drinks"]:
        rec = dict(zip(_FIELDS, row))
        key, _, detail = str(rec.pop("source")).partition(" ")
        rec["source_url"] = sources[key] + detail
        rec["ml"] = float(rec["ml"]) if rec["ml"] is not None else None
        rec["mg"] = float(rec["mg"])
        out.append(DrinkEntry(**rec))
    return out


# ── 브랜드별 컵 크기 (beverages.yaml cup_sizes, 조사일 2026-11-04) ──
@dataclass(frozen=True)
class Cup:
    key: str      # 스몰 / 기본 / 빅
    name: str     # 브랜드의 사이즈 이름 (예: Tall)
    ml: float

    @property
    def label(self) -> str:
        """'기본(Tall 355ml)' — 이름이 스몰/기본/빅과 같으면 'ml'만"""
        inner = f"{self.ml:g}ml" if self.name == self.key else f"{self.name} {self.ml:g}ml"
        return f"{self.key}({inner})"


def cup_sizes(brand: Optional[str] = None) -> List[Cup]:
    """브랜드의 스몰·기본·빅 컵 (없는 사이즈는 뺌). 모르는 브랜드면 '그 외'."""
    table = yaml.safe_load(BEVERAGES_PATH.read_text(encoding="utf-8"))["cup_sizes"]
    row = table.get(brand) or table["그 외"]
    return [Cup(k, str(row[k][0]), float(row[k][1])) for k in ("스몰", "기본", "빅") if k in row]


def cup_ml(key: str, brand: Optional[str] = None) -> float:
    cups = {c.key: c.ml for c in cup_sizes(brand)}
    return cups.get(key) or {c.key: c.ml for c in cup_sizes()}[key]
