# -*- coding: utf-8 -*-
"""프롬프트 4 검증 — 문장 생성 규칙 (6주차 Day3 실습 B).

교안이 예시로 든 문장 형태와 실제 출력을 대조하고, **실제 실행 결과**로도 한 번 돌린다.
예시만 맞고 실데이터에서 깨지는 경우가 있어 둘 다 본다.

    py -X utf8 dev_tools/verify_phrasing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
from pipeline import phrasing as ph  # noqa: E402
from pipeline import validate as vd  # noqa: E402

ok = fail = 0


def check(label: str, got: str, must: list[str], must_not: list[str] = ()) -> None:
    global ok, fail
    miss = [m for m in must if m not in got]
    bad = [m for m in must_not if m in got]
    good = not miss and not bad
    ok, fail = ok + good, fail + (not good)
    print(f"  {'✅' if good else '❌'} {label:<22} {got}")
    if miss:
        print(f"       └ 빠짐: {miss}")
    if bad:
        print(f"       └ 있으면 안 됨: {bad}")


def main() -> None:
    print("── 함수 1  fmt_value ─────────────────────────────────────")
    check("금액형", ph.fmt_value(27804305, "금액형", "청구 매출", "billed_revenue"),
          ["27,804,305원"])
    check("비율형", ph.fmt_value(0.39, "비율형", "저사용 고객 비율", "low_usage_customer_rate"),
          ["39.0%"])
    check("카운트형(명)", ph.fmt_value(441, "카운트형", "계약 기준 활성 고객 수",
                                   "active_customers_contract"), ["441명"])
    check("GB", ph.fmt_value(21.666, "금액형", "평균 데이터 사용량", "avg_data_usage"),
          ["21.7 GB"], ["원"])          # 유형이 금액형이어도 GB로 나와야 한다
    check("None", ph.fmt_value(None, "금액형", "이탈 손실 금액"), ["값 없음"])

    print("\n── 함수 2  fmt_change ────────────────────────────────────")
    check("금액 변화", ph.fmt_change(
        {"절대변화": 314819, "상대변화율": 1.15, "지표명": "청구 매출",
         "metric_id": "billed_revenue"}), ["+314,819원", "(+1.15%)"])
    check("비율 %p", ph.fmt_change(
        {"절대변화": 0.024, "상대변화율": 6.56, "퍼센트포인트변화": 2.4,
         "지표명": "저사용 고객 비율", "metric_id": "low_usage_customer_rate"}),
        ["+2.4%p", "(+6.56%)"])
    check("전월 없음", ph.fmt_change(
        {"절대변화": None, "지표명": "이탈 손실 금액"}), ["비교 불가"])
    check("변화 0", ph.fmt_change(
        {"절대변화": 0, "상대변화율": 0.0, "지표명": "사용 기준 활성 사용자 수",
         "metric_id": "active_users_product"}), ["변화 없음", "0.00%"])

    print("\n── 함수 3  describe_metric (근거 강도) ───────────────────")
    base = {"지표명": "청구 매출", "metric_id": "billed_revenue",
            "유형": "금액형", "value": 27804305}
    check("OK", ph.describe_metric(base, "OK"), ["청구 매출은 27,804,305원이다."])
    check("구간확장", ph.describe_metric(base, "구간확장"),
          ["정의서 유효구간 밖, 확장 승인"])
    check("표본부족", ph.describe_metric({**base, "sample_size": 12}, "표본부족"),
          ["표본 12건", "근거로 쓰지 않는다"])
    check("판정 임계값 잠정", ph.describe_metric(
        {"지표명": "저사용 고객 비율", "metric_id": "low_usage_customer_rate",
         "유형": "비율형", "value": 0.39}, "OK", {"임계값_상태": "잠정"}),
        ["39.0%", "(판정 임계값 잠정)"])

    print("\n── 함수 4  describe_change (가치판단 금지) ───────────────")
    row = {"지표명": "평균 데이터 사용량", "metric_id": "avg_data_usage",
           "절대변화": -1.7, "상대변화율": -7.24}
    check("임계값 이내", ph.describe_change(row, 10.0, "정의서"),
          ["임계값 10% (정의서) 이내다"], ["감소했다는", "개선", "악화", "우려"])
    check("임계값 초과", ph.describe_change(row, 5.0, "기본값"),
          ["임계값 5% (기본값)를 초과했다"], ["개선", "악화", "우려"])

    print("\n── 함수 5  check_forbidden ───────────────────────────────")
    sample = ("청구 매출이 개선됐다. 사용량이 줄었기 때문이다. "
              "대응이 필요하다. 우려되는 수준이다.")
    hits = ph.check_forbidden(sample)
    kinds = sorted({h["유형"] for h in hits})
    check("4종 전부 탐지", " · ".join(f"{h['유형']}:{h['표현']}" for h in hits),
          ["가치판단", "인과", "제안", "강도"])
    print(f"       탐지 {len(hits)}건 / 유형 {kinds}")
    clean = ph.check_forbidden("청구 매출은 27,804,305원이다. 전월 대비 +1.15%다.")
    check("정상 문장 오탐 없음", f"{len(clean)}건", ["0건"])

    # ── 실제 실행 결과로 한 번 더 ────────────────────────────────────
    runs = sorted((BASE / "outputs").glob("run_*"))
    if runs:
        run = runs[-1]
        m = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
        c = pd.read_csv(run / "comparison.csv", encoding="utf-8-sig")
        cat, _ = common.load_catalog("metrics_catalog")
        ext = any(str(r.get("status")) == "구간확장" for _, r in m.iterrows())
        v = vd.validate_all(m, c, cat, override=ext)
        th = {x["대상지표"]: x for x in v["항목"] if x["검증명"] == "전월 대비"}

        print(f"\n── 실제 실행 결과 문장 ({run.name}) ──────────────────")
        for _, r in m.iterrows():
            print("  •", ph.describe_metric(r, spec=cat.get(r["metric_id"])))
        print()
        for _, r in c.iterrows():
            x = th.get(r["지표명"]) or {}
            basis = common.blank_safe(x.get("기준"))
            t = float(basis.split("%")[0]) if basis else None
            src = basis.split("(")[-1].rstrip(")") if "(" in basis else ""
            print("  •", ph.describe_change(r, t, src))

        allsent = "\n".join(
            [ph.describe_metric(r, spec=cat.get(r["metric_id"])) for _, r in m.iterrows()]
            + [ph.describe_change(r) for _, r in c.iterrows()])
        bad = ph.check_forbidden(allsent)
        check("\n실제 문장 금지 표현", f"{len(bad)}건" + (f" {bad}" if bad else ""), ["0건"])

    print(f"\n결과: 통과 {ok} / 실패 {fail}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
