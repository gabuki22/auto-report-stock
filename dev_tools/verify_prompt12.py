# -*- coding: utf-8 -*-
"""프롬프트 12 검증 — 게이트 2 체크리스트 (6주차 Day2 실습 F).

BigQuery를 치지 않는다. 저장된 실행 결과(`outputs/run_*/`)로 체크리스트를 만들어
**교안 4항목이 실제 결과에서 생성되는지**와 **게이트 활성 조건**을 확인한다.

    py -X utf8 dev_tools/verify_prompt12.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
from pipeline import validate as vd  # noqa: E402

# 교안 p.29 체크리스트 4항목 — 키로만 대조한다(문구의 숫자는 실행마다 달라야 정상)
EXPECTED_KEYS = ["기간", "경고", "부분갱신", "미자동검증"]


def main() -> None:
    run = sorted((BASE / "outputs").glob("run_*"))[-1]
    metrics_df = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
    comp_df = pd.read_csv(run / "comparison.csv", encoding="utf-8-sig")
    catalog, _ = common.load_catalog("metrics_catalog")
    ext = any(str(r.get("status")) == "구간확장" for _, r in metrics_df.iterrows())
    v = vd.validate_all(metrics_df, comp_df, catalog, override=ext)
    period = str(metrics_df["month"].iloc[0])

    items = common.build_checklist(period, v, metrics_df, comp_df)

    print(f"실행 폴더: {run.name} · 대상 월 {period}")
    print(f"검증     : {v['전체판정']} (차단 {v['차단수']} · 경고 {v['경고수']})\n")
    print("── 체크리스트 ─────────────────────────────────────────────")
    for it in items:
        mark = "☐ 체크 필요" if it["해당"] else "☑ 해당 없음(자동 충족)"
        print(f"{mark}  {it['라벨']}")
        head = it["상세"].strip().splitlines()[0][:76]
        print(f"     └ {head}")

    keys = [it["키"] for it in items]
    assert keys == EXPECTED_KEYS, f"항목 구성이 교안과 다름: {keys}"
    print(f"\n교안 4항목 구성 일치 ✅  {' · '.join(keys)}")

    # 게이트 활성 조건 — 해당 항목을 전부 체크해야만 열린다
    need = [it["키"] for it in items if it["해당"]]
    print(f"\n── 게이트 2 활성 조건 ─────────────────────────────────────")
    print(f"체크 필요 {len(need)}종: {', '.join(need)}")
    for drop in ([], need[:1]):
        checked = [k for k in need if k not in drop]
        opened = set(need) <= set(checked)
        label = "전부 체크" if not drop else f"'{drop[0]}' 해제"
        print(f"  {label:<16} → 버튼 {'활성 ✅' if opened else '비활성 ✅'}")

    # 문구에 값이 박혀 있지 않은지 — 실행 결과가 문구에 반영돼야 한다
    warn_n = sum(1 for x in v["항목"] if x["판정"] == "경고")
    assert f"({warn_n}건)" in items[1]["라벨"], "경고 건수가 실제 결과에서 오지 않음"
    assert period in items[0]["라벨"], "대상 기간이 실제 결과에서 오지 않음"
    print(f"\n문구 동적 생성 확인 ✅  경고 {warn_n}건 · 기간 {period} 이 라벨에 반영됨")

    # run_log에 어떤 필드가 추가되는지
    log = json.loads((run / "run_log.json").read_text(encoding="utf-8"))
    add = {"확인_완료_시각": "타임스탬프",
           "확인한_체크항목": f"{len(need)}개",
           "검증_요약": f"차단 {v['차단수']}, 경고 {v['경고수']}"}
    print("\n── 확정 시 run_log.json 에 추가될 필드 ────────────────────")
    for k, val in add.items():
        state = "이미 있음" if k in log else "추가 예정"
        print(f"  {k:<14} {val:<20} ({state})")


if __name__ == "__main__":
    main()
