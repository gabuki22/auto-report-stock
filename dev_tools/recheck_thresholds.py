# -*- coding: utf-8 -*-
"""저장된 실행 결과에 검증만 다시 돌려 임계값 변경 전후를 대조한다 (6주차 Day2 실습 E).

BigQuery를 다시 치지 않는다. `outputs/run_*/`의 metrics.csv·comparison.csv를 그대로 읽어
`validate_all`만 재실행하므로, **같은 입력에 판정 규칙만 바뀐 효과**를 분리해서 볼 수 있다.
계산까지 다시 하면 값이 달라졌는지 규칙이 달라졌는지 구분되지 않는다.

    py -X utf8 scripts/recheck_thresholds.py            # 최신 실행 폴더
    py -X utf8 scripts/recheck_thresholds.py run_2026...  # 특정 실행 폴더
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import validate as vd  # noqa: E402


def latest_run() -> Path:
    runs = sorted((BASE / "outputs").glob("run_*"))
    if not runs:
        sys.exit("outputs/run_* 가 없습니다. 앱에서 한 번 실행한 뒤 다시 돌리세요.")
    return runs[-1]


def main() -> None:
    run = (BASE / "outputs" / sys.argv[1]) if len(sys.argv) > 1 else latest_run()
    if not run.is_dir():
        sys.exit(f"실행 폴더 없음: {run}")

    metrics_df = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
    comp_df = pd.read_csv(run / "comparison.csv", encoding="utf-8-sig")
    catalog, meta = common.load_catalog("metrics_catalog")
    before = json.loads((run / "validation.json").read_text(encoding="utf-8"))

    print(f"실행 폴더 : {run.name}")
    print(f"카탈로그  : 지표 {len(catalog)}종 · 갱신 {meta.get('생성시각', '?')}")
    print(f"기본 임계값: {config.MOM_THRESHOLD:g}%  (필드 `{config.MOM_THRESHOLD_FIELD}`가 있으면 그 값)\n")

    # override는 저장된 판정을 그대로 따른다 — 승인 상태까지 재현해야 전후가 비교된다
    ext = any(str(r.get("status")) == "구간확장" for _, r in metrics_df.iterrows())
    after = vd.validate_all(metrics_df, comp_df, catalog, override=ext)

    print("── 전월 대비 판정 ──────────────────────────────────────────")
    print(f"{'지표':<22}{'변화율':>9}  {'임계값':<16}{'이전':<6}{'이후':<6}")
    prev = {x["대상지표"]: x["판정"] for x in before["항목"] if x["검증명"] == "전월 대비"}
    changed = 0
    for x in after["항목"]:
        if x["검증명"] != "전월 대비":
            continue
        rate = x.get("값")
        rate_s = f"{rate:+.2f}%" if isinstance(rate, (int, float)) else "—"
        was = prev.get(x["대상지표"], "없음")
        mark = "  ←" if was != x["판정"] else ""
        changed += was != x["판정"]
        print(f"{x['대상지표'][:21]:<22}{rate_s:>9}  {str(x.get('기준') or '—'):<16}"
              f"{was:<6}{x['판정']:<6}{mark}")

    print("\n── 전체 판정 ──────────────────────────────────────────────")
    for lbl, v in (("이전", before), ("이후", after)):
        print(f"{lbl}: {v['전체판정']}  (차단 {v['차단수']} · 경고 {v['경고수']} · 점검 {len(v['항목'])})")
    print(f"\n판정이 바뀐 지표: {changed}종")


if __name__ == "__main__":
    main()
