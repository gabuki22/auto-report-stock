# -*- coding: utf-8 -*-
"""업로드 파일 판정 — 앱 2단계 전반 (6주차 Day1 실습 D).

5주차 워크플로우 3·4번(Profile·Confirm)에 적어둔 절차를 그대로 옮긴 것이다.
사람이 손으로 하던 점검(어느 테이블인가·필수 컬럼이 다 있나·행수·결측·중복·기간·그레인)을
같은 판정 기준으로 자동화한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# 기간 컬럼 판정 — 패턴은 **config에** 둔다. 컬럼명이 한글인 프로젝트가 있고,
# 코드에 박으면 그런 프로젝트는 2단계에서 통째로 막힌다.
PERIOD_PAT = re.compile(
    getattr(config, "PERIOD_COLUMN_PATTERN", r"^(year_month|.*_date|.*_month)$"), re.I)


# ── 함수 1 — 어느 테이블인가 (Confirm) ────────────────────────────────
def judge_table(df: pd.DataFrame, schema_catalog: dict) -> dict:
    """업로드 파일이 어느 테이블인지 컬럼 대조로 판정한다.

    왜 이렇게 판정하나
      · 파일명은 신뢰하지 않는다. 사람이 바꿔서 올릴 수 있다. **컬럼 구성이 테이블의 신분증**이다.
      · 순서는 무시한다. CSV 저장 도구에 따라 열 순서가 바뀌는 일이 흔하다.
      · 분모를 **카탈로그 컬럼 수**로 둔다. 업로드 파일에 여분 컬럼이 붙어도 일치율이 깎이지
        않아야 하고, 반대로 **정의된 컬럼이 빠지면 반드시 깎여야** 하기 때문이다.
      · MIN_SCHEMA_MATCH(0.8) 미달이면 판정 불가로 둔다 — 카탈로그에 없는 테이블을
        추측해서 통과시키면 잘못된 스키마로 계산이 돌아간다(CLAUDE.md 9절 금지 항목).
    """
    up = [str(c).strip() for c in df.columns]
    up_set = set(up)
    ranked = []
    for table, info in schema_catalog.items():
        cat = [c["컬럼명"] for c in info.get("컬럼", [])]
        if not cat:
            continue
        hit = up_set & set(cat)
        ranked.append({
            "테이블명": table,
            "일치율": len(hit) / len(cat),
            "일치": len(hit), "카탈로그컬럼수": len(cat),
            "누락컬럼": [c for c in cat if c not in up_set],
            "추가컬럼": [c for c in up if c not in set(cat)],
            "테이블명_추정": info.get("테이블명_추정", True),
            "노트명": info.get("노트명", table),
        })
    # ★ 동점이면 **카탈로그 컬럼이 많은 쪽**을 고른다.
    #   한 테이블의 컬럼이 다른 테이블의 부분집합이면 둘 다 일치율 100%가 된다
    #   (마스터 5컬럼이 스냅샷 36컬럼에 전부 들어 있는 경우 — 실제로 겪었다).
    #   그때 이름순으로 고르면 **더 작은 테이블이 이겨** 계산할 지표가 하나도 없게 된다.
    #   컬럼이 많은 쪽이 파일을 더 많이 설명하므로 그쪽이 맞다.
    ranked.sort(key=lambda r: (-r["일치율"], -r["카탈로그컬럼수"], r["테이블명"]))
    if not ranked:
        return {"판정가능": False, "이유": "스키마 카탈로그가 비어 있음", "후보": []}

    best = ranked[0]
    best["판정가능"] = best["일치율"] >= config.MIN_SCHEMA_MATCH
    best["이유"] = ("" if best["판정가능"]
                  else f"일치율 {best['일치율']:.0%} < 기준 {config.MIN_SCHEMA_MATCH:.0%} — 판정 불가")
    best["후보"] = ranked[:3]
    return best


# ── 함수 2 — 이 파일은 어떤 상태인가 (Profile) ────────────────────────
def profile_data(df: pd.DataFrame, table_info: dict) -> dict:
    """행수·결측·기간·그레인을 잰다.

    왜 이렇게 판정하나
      · 결측은 **0인 컬럼을 빼고 있는 것만** 보여준다. 0을 나열하면 진짜 결측이 묻힌다.
      · 기간 컬럼을 이름 패턴으로 찾는다(year_month · *_date · *_month). 파일마다
        기간 컬럼명이 다르므로 하드코딩하지 않는다.
      · 그레인은 **"연결" 절에서 키를 추정**하고 기간 컬럼과 묶어 중복을 본다.
        고객×월이 유일하지 않으면 뒤의 집계가 조용히 부풀어 오른다(5주차 팬아웃 12배 사고).
        키를 못 찾으면 `customer_id`+기간 조합으로 폴백한다.
    """
    nulls = {c: int(n) for c, n in df.isna().sum().items() if n > 0}

    period_cols = [c for c in df.columns if PERIOD_PAT.match(str(c))]
    period = {}
    if period_cols:
        col = period_cols[0]
        s = df[col].dropna().astype(str)
        period = {"컬럼": col, "최소": s.min() if len(s) else None,
                  "최대": s.max() if len(s) else None}

    # 그레인 — 스키마 노트가 **명시한 키**를 먼저 쓰고, 없으면 추정한다.
    #
    # ★ 추정만 하면 컬럼명이 `*_id` 형태가 아닌 도메인에서 통째로 빗나간다.
    #   재고는 그레인이 `사출도번 × 날짜`인데 `*_id`가 하나도 없어 키를 못 찾았고,
    #   결국 `날짜` 하나로만 중복을 세어 **3,689건 중복(전부 같은 날짜니까)**이라는
    #   오탐이 나왔다. 오탐은 차단으로 이어져 파이프라인을 멈춘다.
    #   → 스키마 노트 프론트매터에 `그레인키: [사출도번, 날짜]` 로 적으면 그걸 쓴다.
    declared = table_info.get("그레인키") or table_info.get("grain_keys")
    if isinstance(declared, str):
        declared = [x.strip() for x in declared.strip("[]").split(",") if x.strip()]
    keys = [k for k in (declared or []) if k in df.columns]
    if not keys:
        linked = re.findall(r"`?(\w+_id)`?", str(table_info.get("연결", "")))
        keys = [k for k in dict.fromkeys(linked) if k in df.columns]
    if not keys and "customer_id" in df.columns:
        keys = ["customer_id"]
    grain_cols = keys + ([period["컬럼"]] if period and period["컬럼"] not in keys else [])
    grain = {}
    if grain_cols:
        dup = int(df.duplicated(subset=grain_cols).sum())
        grain = {"키": grain_cols, "중복": dup, "유일": dup == 0}

    return {
        "행수": len(df),
        "컬럼수": df.shape[1],
        "결측": nulls,
        "결측합계": int(sum(nulls.values())),
        "기간": period,
        "그레인": grain,
    }


# ── 함수 3 — 어느 지표를 계산할 수 있는가 (Model 연결) ────────────────
def _sources(spec: dict, catalog: dict, seen: set | None = None) -> set:
    """지표가 실제로 건드리는 **원천 테이블 집합**을 구한다(파생형은 재귀).

    · 단일 집계 → 계산.원천 (우리 위키는 계산.대상)
    · 비율형   → 계산.분자.원천 + 계산.분모.원천
    · 파생형   → 의존지표를 따라 내려간다. 재귀하지 않으면 arpu가 "무관"으로 빠진다
                (교안 §다르게 나오면에서 지목한 그 증상).
    · "+"로 이어진 다중 원천을 분리한다.
    """
    seen = seen or set()
    out: set[str] = set()
    calc = spec.get("계산", {}) or {}

    def add(v):
        for t in str(v or "").split("+"):
            t = t.strip()
            if t:
                out.add(t)

    add(calc.get("원천") or calc.get("대상"))
    for side in ("분자", "분모"):
        blk = calc.get(side)
        if isinstance(blk, dict):
            add(blk.get("원천") or blk.get("대상"))

    for dep in spec.get("의존지표") or []:
        if dep in seen or dep not in catalog:
            continue
        out |= _sources(catalog[dep], catalog, seen | {dep})
    return out


def _in_range(valid: str, period: str) -> bool | None:
    """유효구간 "2024-01 ~ 2024-12" 안에 period(YYYY-MM)가 있는가. 못 읽으면 None."""
    m = re.match(r"\s*(\d{4}-\d{2})\s*~\s*(\d{4}-\d{2})", str(valid or ""))
    if not m or not period:
        return None
    return m.group(1) <= period[:7] <= m.group(2)


def _calc_text(spec: dict, catalog: dict, seen: set | None = None) -> str:
    """지표가 실제로 참조하는 SQL 조각을 전부 이어붙인다(파생형은 재귀).

    누락 컬럼을 찾으려면 **의존 지표까지 내려가야** 한다. `arpu`는 자기 계산 블록에
    `billing_amount`가 없지만 `billed_revenue_active`를 통해 그 컬럼에 의존한다 —
    직접 참조만 보면 arpu가 "계산가능"으로 통과해 버린다.
    """
    seen = seen or set()
    import json as _json
    txt = _json.dumps(spec.get("계산", {}) or {}, ensure_ascii=False)
    for dep in spec.get("의존지표") or []:
        if dep in seen or dep not in catalog:
            continue
        txt += " " + _calc_text(catalog[dep], catalog, seen | {dep})
    return txt


def judge_metrics(table_name: str, period: str, metrics_catalog: dict,
                  missing_cols: list[str] | None = None) -> list[dict]:
    """지표별로 이 파일로 계산할 수 있는지 판정한다.

    왜 이렇게 판정하나
      · 비교 기준은 schema_catalog의 **테이블명**이다(노트명이 아니다). 여기서 이름이
        어긋나면 계산 대상이 0개가 된다 — 교안이 "가장 흔한 원인"으로 꼽은 지점.
      · 유효구간 밖이라고 **바로 계산불가로 두지 않는다.** 새 데이터가 도착한 정상 상황이므로
        "유효구간 확장 필요"로 표시하고 **사용자가 게이트에서 승인**하게 한다(실행 단위 오버라이드).
      · 원천이 여럿인데 그중 업로드된 것이 일부뿐이면 **부분 갱신**으로 표시한다.
        계산은 되지만 나머지 테이블은 옛 상태이므로 그 사실을 밝혀야 한다.
    """
    rows = []
    for mid, spec in metrics_catalog.items():
        srcs = _sources(spec, metrics_catalog)
        src_txt = " + ".join(sorted(srcs)) or "—"
        base = {"metric_id": mid, "지표명": spec.get("지표명", mid),
                "유형": spec.get("유형", ""), "원천": src_txt}

        if table_name not in srcs:
            rows.append({**base, "상태": "이 파일과 무관", "이유": "", "부분갱신": ""})
            continue

        # 업로드 파일에 없는 컬럼을 쓰는 지표는 계산할 수 없다.
        # 어느 컬럼이 없어서인지 이유에 남긴다 — "계산불가"만 쓰면 고칠 방법을 모른다.
        if missing_cols:
            txt = _calc_text(spec, metrics_catalog)
            lack = [c for c in missing_cols if c in txt]
            if lack:
                rows.append({**base, "상태": "계산불가",
                             "이유": f"업로드 파일에 `{'`, `'.join(lack)}` 컬럼이 없음",
                             "부분갱신": ""})
                continue

        others = sorted(srcs - {table_name})
        partial = ", ".join(others)
        inr = _in_range(spec.get("유효구간"), period)
        if inr is False:
            state = "유효구간 확장 필요"
            why = f"정의서 유효구간 {spec.get('유효구간')} · 파일 {period}"
        elif inr is None:
            state = "계산가능"
            why = "유효구간을 읽지 못함 — 확인 필요"
        else:
            state, why = "계산가능", ""
        if partial:
            why = (why + " · " if why else "") + f"{partial}는 갱신되지 않음"
        rows.append({**base, "상태": state, "이유": why, "부분갱신": partial})

    order = {"계산가능": 0, "유효구간 확장 필요": 1, "계산불가": 2, "이 파일과 무관": 3}
    rows.sort(key=lambda r: (order.get(r["상태"], 9), r["metric_id"]))
    return rows
