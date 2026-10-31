"""① 개인 파라미터 — 기본 정보로 '이 사람만의 숫자'를 정한다.

반감기 = 기본 5시간 × 흡연·피임약·임신 배수
하루 상한 = min(사용자 설정, 권고량)   성인 400 · 임산부 300 · 수유부 200 · 청소년 2.5mg/kg
1회 상한 = min(200mg, 3mg/kg)
취침 허용 잔량 = 민감도별 20 / 30 / 40mg
간질환·CYP1A2 억제 약 복용자는 계산하지 않고 상담 안내 (분해가 크게 느려짐)
"""
from dataclasses import dataclass, field
from typing import List, Optional

from . import params


@dataclass(frozen=True)
class Profile:
    age: int
    weight_kg: float
    smoker: bool = False
    oral_contraceptive: bool = False
    pregnancy_trimester: Optional[int] = None  # 1~3, 임신 아니면 None
    breastfeeding: bool = False
    liver_disease: bool = False
    cyp1a2_inhibitor: bool = False   # 예: 플루복사민 등 카페인 분해를 막는 약
    heart_or_anxiety: bool = False   # 심장질환·고혈압·불안장애
    sensitivity: str = "normal"      # sensitive / normal / tolerant
    chronotype: str = "neutral"      # morning / neutral / evening
    daily_cap_mg: Optional[float] = None  # 사용자가 정한 하루 최대량


@dataclass
class PersonalParams:
    half_life_h: float
    daily_cap_mg: float
    single_cap_mg: float
    residual_limit_mg: float
    chronotype: str
    blocked: bool = False            # True면 플랜을 만들지 않음
    notes: List[str] = field(default_factory=list)


def personal_params(p: Profile) -> PersonalParams:
    limits = params.load()["limits"]
    mult = params.load()["half_life_multipliers"]
    notes: List[str] = []

    half_life = params.value("pk", "half_life_h")
    if p.smoker:
        half_life *= mult["smoking"]["value"]
    if p.oral_contraceptive:
        half_life *= mult["oral_contraceptive"]["value"]
    if p.pregnancy_trimester:
        half_life *= mult[f"pregnancy_trimester_{p.pregnancy_trimester}"]["value"]

    if p.age < limits["adult_age"]["value"]:
        guideline = limits["daily_mg_per_kg_youth"]["value"] * p.weight_kg
        notes.append(f"청소년 기준 하루 {guideline:.0f}mg (체중 1kg당 2.5mg)")
    elif p.pregnancy_trimester:
        guideline = limits["daily_mg_pregnant"]["value"]
        notes.append("임신 중: 하루 300mg 이하, 분해가 느려 늦은 시간 섭취 주의")
    elif p.breastfeeding:
        guideline = limits["daily_mg_lactating"]["value"]
        notes.append("수유 중: 하루 200mg 이하")
    else:
        guideline = limits["daily_mg_adult"]["value"]
    daily_cap = min(p.daily_cap_mg, guideline) if p.daily_cap_mg else guideline

    single_cap = min(limits["single_dose_mg"]["value"],
                     limits["single_dose_mg_per_kg"]["value"] * p.weight_kg)
    residual = params.load()["sleep_protection"]["bedtime_residual_mg"]["by_sensitivity"][p.sensitivity]

    blocked = p.liver_disease or p.cyp1a2_inhibitor
    if blocked:
        notes.append("간질환 또는 카페인 분해를 늦추는 약 복용 중 → 계산 대신 의사·약사와 상담하세요")
    if p.heart_or_anxiety:
        notes.append("심장질환·고혈압·불안장애가 있으면 카페인이 증상을 악화시킬 수 있어요. 상담 후 사용하세요")

    return PersonalParams(half_life, daily_cap, single_cap, residual, p.chronotype, blocked, notes)
