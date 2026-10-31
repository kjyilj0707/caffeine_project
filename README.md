# 카페인 측정기 — 계산 엔진

설계: 노션 「카페인 측정기 > 계산 엔진 설계서 v1」

## 폴더
| 경로 | 내용 |
| --- | --- |
| `parameters.yaml` | 엔진의 모든 숫자 + 출처 + 확정/임시 상태 |
| `caffeine_engine/` | 계산 엔진 (`fatigue.py` = ② 피로도, `pk.py` = ③ 체내 카페인, `effect.py` = 카페인 → 각성 효과) |
| `tests/` | 논문 결과를 재현하는지 검사 |
| `scripts/` | 확인용 그래프 스크립트 |
| `figures/` | 그래프 결과물 |
| `papers/` | 논문 원문 PDF·그림 (저장소엔 목록만, 파일은 로컬 전용) |

## 실행
```bash
.venv/bin/python -m pytest -q                      # 테스트
.venv/bin/python scripts/plot_body_caffeine.py     # 체내 카페인 그래프
.venv/bin/python scripts/plot_day_overview.py      # 각성 점수 + 체내 카페인 그래프
```

처음 받은 컴퓨터라면 먼저 환경을 만든다:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
