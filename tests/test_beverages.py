"""음료 카페인 DB(beverages.yaml) 검사 — 형식·출처·상식 범위."""
import pytest

from caffeine_engine import params
from caffeine_engine.convert import load_beverage_db, to_serving

DB = load_beverage_db()


def test_db_has_all_groups():
    brands = {d.brand for d in DB}
    for b in ["스타벅스", "투썸플레이스", "할리스", "커피빈", "메가MGC커피", "컴포즈커피", "빽다방",
              "이디야커피", "더벤티", "레드불", "몬스터", "핫식스"]:
        assert b in brands, b
    assert len(DB) >= 100


def test_every_row_has_source_and_sane_values():
    for d in DB:
        assert d.source_type in {"공식", "2차", "공공", "학술"}, d.label
        assert d.source_url.startswith("https://"), d.label
        assert 0 <= d.mg <= 600, d.label
        assert d.ml is None or 20 <= d.ml <= 1000, d.label
        if d.ml:  # 1ml당 카페인: 에스프레소(최대 ~4.5mg/ml) 외에는 1mg/ml 아래여야 상식적
            limit = 5.0 if "에스프레소" in d.menu else 1.0
            assert d.mg / d.ml <= limit, d.label


def test_official_values_match_spot_checks():
    # 원본 페이지와 직접 대조한 값 (2026-11-01)
    def find(brand, menu, temp, size):
        return next(d for d in DB if (d.brand, d.menu, d.temp, d.size) == (brand, menu, temp, size))
    assert find("스타벅스", "카페 아메리카노", "HOT", "Tall").mg == 150
    assert find("스타벅스", "카페 라떼", None, "Tall").mg == 75
    assert find("빽다방", "아메리카노", "HOT", "기본").mg == 197


def test_decaf_is_low():
    assert all(d.mg <= 25 for d in DB if "디카페인" in d.menu)


def test_coffee_concentration_close_to_gardiner_reference():
    # Gardiner 2023 인용 '커피 107mg/250ml'(0.43mg/ml)과 같은 범위인지 — 브랜드 아메리카노 대부분 0.2~0.5mg/ml
    ref = params.value("conversion", "coffee_mg_per_ml")
    americanos = [d.mg / d.ml for d in DB if d.ml and d.menu.endswith("아메리카노") and "디카페인" not in d.menu]
    assert len(americanos) >= 15
    assert min(americanos) > 0.15 and max(americanos) < 0.7
    assert min(americanos) < ref < max(americanos)


def test_entries_convert_to_sips():
    tall = next(d for d in DB if d.brand == "스타벅스" and d.menu == "카페 아메리카노" and d.size == "Tall")
    s = to_serving(75, tall.beverage())
    assert s.ml == pytest.approx(355 / 2, abs=params.value("conversion", "sip_ml"))
    unknown_volume = next(d for d in DB if d.ml is None)
    assert unknown_volume.beverage() is None


def test_some_single_drinks_exceed_daily_cap():
    cap = params.value("limits", "daily_mg_adult")
    big = [d.label for d in DB if d.mg > cap]
    assert big  # 컴포즈 빅포즈 카페라떼(495mg), 더벤티 점보 라떼(532mg) — 앱에서 경고할 대상
