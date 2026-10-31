"""Step 1-6 데모: 시나리오 파일을 읽어 결과 카드 출력 + 그래프 저장.

사용법
  .venv/bin/python scripts/demo.py                          # scenarios/ 폴더의 시나리오 전부
  .venv/bin/python scripts/demo.py scenarios/exam_day.yaml  # 하나만

시나리오를 바꾸려면 scenarios/*.yaml 파일을 열어 숫자·시각을 고치고 다시 실행하면 된다.
"""
import sys
from pathlib import Path

from daychart import ROOT, render

from caffeine_engine.pipeline import format_card, run_day
from caffeine_engine.scenario import load
from caffeine_engine.timeutil import h_to_hhmm

LABEL = {"must_not_sleep": "졸면 안 됨", "focus": "집중"}


def run(path: Path) -> None:
    sc = load(path)
    result = run_day(sc.profile, sc.sleeps, sc.windows, bed_h=sc.bed_h, now_h=sc.now_h,
                     already=sc.already, beverage=sc.beverage, sip_ml=sc.sip_ml)
    print(f"\n━━━━ {sc.name} ━━━━")
    print(format_card(result))

    # 그래프: 가장 중요한 구간(졸면 안 됨 → 집중 순)을 강조
    key = next((w for kind in ("must_not_sleep", "focus") for w in sc.windows if w.kind == kind), None)
    highlight = (key.start_h, key.end_h) if key else None
    label = f"{LABEL[key.kind]} {h_to_hhmm(key.start_h)}–{h_to_hhmm(key.end_h)}" if key else ""
    plan = result.plan
    out = render(f"demo_{path.stem}.png", sc.sleeps, plan.all_doses if plan else sc.already, sc.bed_h,
                 start=sc.sleeps[-1].end_h, highlight=highlight, highlight_label=label,
                 title=sc.name, cutoff=plan.cutoff_h if plan else None,
                 planned=plan.new_doses if plan else (),
                 half_life_h=result.personal.half_life_h, chronotype=result.personal.chronotype,
                 residual_limit=result.personal.residual_limit_mg)["out"]
    print(f"📈 그래프: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted((ROOT / "scenarios").glob("*.yaml"))
    for p in paths:
        run(p)
