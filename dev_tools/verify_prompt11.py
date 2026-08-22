# -*- coding: utf-8 -*-
"""프롬프트 11 검증 — 지표별 임계값이 실제 계산에 반영되는지 (6주차 Day2 실습 E).

앱을 띄우지 않고 파이프라인만 그대로 호출한다. 화면 없이도 **계산 → 전월 대비 → 검증**이
한 줄로 이어지므로, 임계값 변경이 판정을 어떻게 바꾸는지 교안 기댓값과 직접 대조할 수 있다.

    py -X utf8 scripts/verify_prompt11.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import calculate as calc  # noqa: E402
from pipeline import compare as cmp  # noqa: E402
from pipeline import validate as vd  # noqa: E402

# 교안 p.27 기댓값 — 지표별 임계값 적용 후
EXPECTED = {
    "active_customers_contract": ("1.0% (정의서)", "경고"),
    "avg_data_usage":            ("10.0% (정의서)", "통과"),
    "low_usage_customer_rate":   ("5.0% (기본값)", "경고"),
    "billed_revenue":            ("5.0% (기본값)", "통과"),
}


def main() -> None:
    run = sorted((BASE / "outputs").glob("run_*"))[-1]
    src = run / "usage_history_2025-01.csv"
    catalog, _ = common.load_catalog("metrics_catalog")
    df = pd.read_csv(src, encoding="utf-8-sig")

    # 이전 실행이 무엇을 계산 대상으로 삼았는지 그대로 재현한다
    prev_metrics = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
    to_run = [m for m in prev_metrics["metric_id"]
              if not str(prev_metrics.set_index("metric_id").loc[m].get("포함사유") or "")] \
        if "포함사유" in prev_metrics else list(prev_metrics["metric_id"])
    period = str(prev_metrics["month"].iloc[0])

    print(f"입력   : {src.name} ({len(df):,}행)")
    print(f"대상 월 : {period} · 직접 계산 {len(to_run)}종")
    print(f"임계값  : 기본 {config.MOM_THRESHOLD:g}% · 필드 `{config.MOM_THRESHOLD_FIELD}`\n")

    client = calc.make_client()
    stg = calc.load_staging(df, "usage_history", client).split(".")[-1]

    res = calc.calculate(to_run, period, {"usage_history": stg}, client,
                         True, catalog, include_deps=True)
    n_dep = int((res["포함사유"] != "").sum())
    print(f"계산 완료: {len(res)}종 (직접 {len(res) - n_dep} + 의존 {n_dep})")
    for _, r in res[res["포함사유"] != ""].iterrows():
        print(f"  ⤷ 의존 계산으로 포함: {r['metric_id']} = {r['value']:,.2f}")

    prev = cmp.calc_previous(list(res["metric_id"]), cmp.previous_month(period),
                             client, catalog, override=True)
    comp = cmp.compare(res, prev)
    v = vd.validate_all(res, comp, catalog, override=True)

    print("\n── 전월 대비 판정 vs 교안 기댓값 ──────────────────────────")
    print(f"{'metric_id':<28}{'변화율':>9}  {'적용 임계값':<16}{'판정':<6}{'교안':<6}")
    mom = {x["대상지표"]: x for x in v["항목"] if x["검증명"] == "전월 대비"}
    name2id = {r["지표명"]: r["metric_id"] for _, r in res.iterrows()}
    ok = miss = 0
    for name, x in mom.items():
        mid = name2id.get(name, name)
        rate = x.get("값")
        rate_s = f"{rate:+.2f}%" if isinstance(rate, (int, float)) else "—"
        basis = str(x.get("기준") or "—")
        exp = EXPECTED.get(mid)
        if exp is None:
            print(f"{mid[:27]:<28}{rate_s:>9}  {basis:<16}{x['판정']:<6}{'—':<6}")
            continue
        good = exp[1] == x["판정"] and exp[0].replace(".0", "") in basis.replace(".0", "")
        ok, miss = ok + good, miss + (not good)
        print(f"{mid[:27]:<28}{rate_s:>9}  {basis:<16}{x['판정']:<6}{exp[1]:<6}"
              f"{'  ✅' if good else '  ❌ 기대 ' + exp[0]}")

    print(f"\n교안 기댓값 4종 중 일치 {ok} / 불일치 {miss}")
    print(f"전체 판정: {v['전체판정']} (차단 {v['차단수']} · 경고 {v['경고수']} · 점검 {len(v['항목'])})")


if __name__ == "__main__":
    main()
