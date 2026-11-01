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

    @classmethod
    def from_serving(cls, name: str, mg: float, ml: float) -> "Beverage":
        """메뉴 정보로 만들기. 예: Beverage.from_serving("아메리카노 톨", 150, 355)"""
        return cls(name, mg / ml)


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


def _sip(sip_ml: Optional[float]) -> float:
    return sip_ml if sip_ml is not None else params.value("conversion", "sip_ml")


def to_serving(mg: float, beverage: Beverage, sip_ml: Optional[float] = None) -> Serving:
    """목표 mg → 몇 모금 (최소 1모금)."""
    sip = _sip(sip_ml)
    sips = max(1, round(mg / beverage.mg_per_ml / sip))
    ml = sips * sip
    return Serving(beverage, mg, sips, ml, ml * beverage.mg_per_ml)


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
