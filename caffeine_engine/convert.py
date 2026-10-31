"""⑤ 변환 엔진 — mg ↔ 음료 ml ↔ 모금.

모금은 정수로 반올림하므로 실제 섭취량(mg_actual)은 목표와 조금 다를 수 있다.
(커피 1모금 ≈ 17.5ml × 0.428mg/ml ≈ 7.5mg)
"""
from dataclasses import dataclass
from typing import Optional

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
