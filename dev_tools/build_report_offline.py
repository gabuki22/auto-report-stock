# -*- coding: utf-8 -*-
"""리포트를 앱 없이 생성한다 — 문장을 고칠 때마다 앱을 다시 돌리지 않기 위해 (Day3).

저장된 실행 결과(`outputs/run_*/`)로 `report.build_report()`를 그대로 호출한다.
문장 규칙을 손볼 때 반복이 빨라야 하는데, 그때마다 CSV를 올리고 BigQuery를 치면 느리다.

    py -X utf8 dev_tools/build_report_offline.py            # 최신 실행 폴더
    py -X utf8 dev_tools/build_report_offline.py --check    # 금지 표현 검사도 함께
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
from pipeline import manual_sections as ms  # noqa: E402
from pipeline import phrasing as ph  # noqa: E402
from pipeline import report as rp  # noqa: E402
from pipeline import run_log as rl  # noqa: E402
from pipeline import validate as vd  # noqa: E402

# 금지 표현 목록은 pipeline/phrasing.py 하나에만 둔다.
# 사본을 두면 규칙이 갈라져 앱은 통과시키고 이 도구는 잡거나, 그 반대가 된다.


def load_ctx(run: Path) -> dict:
    metrics_df = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
    comp_df = pd.read_csv(run / "comparison.csv", encoding="utf-8-sig")
    if "포함사유" in metrics_df:
        metrics_df["포함사유"] = metrics_df["포함사유"].fillna("")
    catalog, meta = common.load_catalog("metrics_catalog")
    schema, _ = common.load_catalog("schema_catalog")
    insights, _ = common.load_catalog("insights_catalog")
    log = rl.load(run)
    ext = any(str(r.get("status")) == "구간확장" for _, r in metrics_df.iterrows())
    src = run / str(rl.field(log, "파일명") or "")
    return {
        "파일명": rl.field(log, "파일명"),
        "판정테이블": rl.field(log, "테이블"),
        "기간": str(metrics_df["month"].iloc[0]),
        "행수": len(pd.read_csv(src, encoding="utf-8-sig")) if src.exists() else rl.field(log, "행수", 0),
        "metrics": metrics_df,
        "comparison": comp_df,
        "validation": vd.validate_all(metrics_df, comp_df, catalog, override=ext),
        "metrics_catalog": catalog,
        "schema_catalog": schema,
        "insights_catalog": insights,
        "카탈로그_메타": meta,
        "run_log": log,
        # 재현 가능하게 고정 — 앱에서는 실제 시각이 들어간다
        "생성일시": "(오프라인 생성)",
    }


def main() -> None:
    runs = sorted((BASE / "outputs").glob("run_*"))
    if not runs:
        sys.exit("outputs/run_* 가 없습니다.")
    run = runs[-1]
    ctx = load_ctx(run)
    md = rp.build_report(ctx)

    # ★ 앱과 같은 순서로 병합한다. 여기서 빼면 이 도구가 앱보다 미작성 장을 더 많이
    #   보고하고, "화면에선 2개인데 도구는 3개"가 되어 어느 쪽을 믿을지 알 수 없게 된다.
    md, info = ms.merge_into_report(md, ms.load_manual(ctx["기간"]))

    out = run / "report_offline.md"
    out.write_text(md, encoding="utf-8")
    print(f"생성: {out}  ({len(md):,}자 · {len(md.splitlines())}줄)")
    if info["병합"]:
        print(f"  병합된 장: {info['병합']}")
    for w in info["경고"]:
        print(f"  ⚠️ {w}")

    # ★ 장 번호(2·5·6)로 판정하지 않는다. 병합된 뒤에도 계속 "사람"으로 찍혀
    #   화면(2개)과 이 도구(3개)가 어긋난다 — 화면에서 이미 같은 이유로 고쳤다.
    secs = [s for s in rp.split_sections(md) if s["번호"]]
    print(f"\n장 구성 {len(secs)}개")
    for s in secs:
        print(f"  {s['번호']}. {s['제목']:<22}{'작성 필요' if s['미작성'] else '자동/작성됨'}")

    todo = [s["번호"] for s in secs if s["미작성"]]
    print(f"\n미작성 장: {len(todo)}개 {todo or ''}")

    # Day4 시작 전 확인 항목 — "한계 절 소절 5개"
    subs = [l for l in md.splitlines() if l.startswith("### 7-")]
    print(f"한계 소절: {len(subs)}개")
    for s in subs:
        print(f"  {s[4:]}")

    if "--check" in sys.argv:
        hits = rp.check_generated(md)
        print(f"\n── 금지 표현 검사 ({len(ph.FORBIDDEN)}종) ──────────────────")
        if not hits:
            print("  걸린 표현 없음 ✅")
        for h in hits:
            print(f"  ❌ {h['줄']}행 [{h['유형']}] '{h['표현']}'  …{h['문장'][:56]}")


if __name__ == "__main__":
    main()
