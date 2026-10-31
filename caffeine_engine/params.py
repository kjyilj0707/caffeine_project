"""parameters.yaml을 읽어 오는 곳. 엔진의 숫자는 전부 여기를 거친다."""
from functools import lru_cache
from pathlib import Path

import yaml

PARAMS_PATH = Path(__file__).resolve().parent.parent / "parameters.yaml"


@lru_cache(maxsize=None)
def load(path: Path = PARAMS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def value(section: str, name: str) -> float:
    """예: value("pk", "half_life_h") → 5.0"""
    return load()[section][name]["value"]
