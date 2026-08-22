# -*- coding: utf-8 -*-
"""기계적 검증 — 앱 3단계 (6주차 Day2 실습 B).

★ 이 모듈이 하는 일은 **기계적으로 판정 가능한 것만**이다.
  혼입 변수 층화·역인과 검토·가설 검정은 하지 않고, **하지 않았다는 사실을 함께 반환**한다.
  그 목록이 Day3 리포트의 한계 절로 그대로 들어간다.

  화면에 "검증 통과 ✅"만 띄우면 보는 사람은 분석이 검증됐다고 믿는다.
  실제로는 기계적 점검만 통과한 것이다 — **검증하지 않은 것을 밝히지 않으면
  검증 표시 자체가 거짓말이 된다.**
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import config  # noqa: E402

# ★ 이 문자열은 **화면에 보이는 이름이자 조회 키**다(report.py·app.py가 이 값으로
#   경고를 골라낸다). 두 곳에 따로 적으면 한쪽만 고쳤을 때 조용히 0건이 된다.
MOM_CHECK = f'{getattr(config, "PREV_LABEL", "전월")} 대비'


# 자동으로 하지 않는 검증 — 반드시 함께 내보낸다
# ⚠️ 문구에 "필요하다·해야 한다"를 쓰지 않는다. 자동화하지 않은 **이유를 적는 자리**이지
#    무엇을 하라는 자리가 아니고, 리포트 7장에 그대로 실려 자체 검사에 걸린다.
NOT_AUTOMATED = [
    "혼입 변수 층화 — 어느 변수가 혼입인지는 업무 지식에 달려 있다",
    "역인과 검토 — 판단이 개입한다",
    "가설 검정 — 사전 정의된 가설이 없으면 다중비교를 통제할 수 없다",
]


def _r(name: str, target: str, verdict: str, detail: str = "", value=None, **extra) -> dict:
    """공통 반환 형태 — 검증명·대상지표·판정·상세·값.

    `extra`로 검증별 추가 열을 붙인다(전월 대비의 `기준`처럼). 화면 렌더러는 없는 열을
    빈칸으로 그리므로, 열을 쓰지 않는 검증은 아무것도 하지 않아도 된다.
    """
    return {"검증명": name, "대상지표": target, "판정": verdict,
            "상세": detail, "값": value, **extra}


def _num(v):
    """숫자로 못 읽으면 None.

    정의서의 `최소표본`은 30 같은 숫자일 때도 있고 **"해당 없음"** 문자열일 때도 있다.
    사람이 쓰는 필드라 타입이 섞이는 것을 전제하고 읽는다 —
    float()에 그대로 넘기면 검증기가 ValueError로 죽는다(실제로 겪음).
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 1. 유효구간 ───────────────────────────────────────────────────────
def check_valid_range(metrics_df: pd.DataFrame, catalog: dict, override: bool) -> list[dict]:
    """유효구간 밖은 차단, 승인받은 구간확장은 경고로 남긴다.

    승인을 받았어도 **정의서 구간 밖이라는 사실 자체는 사라지지 않는다.**
    경고로 남겨야 리포트에 "정의서 구간을 넘어선 계산"이 적힌다.
    """
    out = []
    for _, r in metrics_df.iterrows():
        st = str(r.get("status", ""))
        valid = str((catalog.get(r["metric_id"]) or {}).get("유효구간", "?"))
        if st == "유효구간 밖":
            out.append(_r("유효구간", r["지표명"], "차단",
                          f"정의서 구간 {valid} 밖인데 승인이 없다", valid))
        elif st == "구간확장":
            out.append(_r("유효구간", r["지표명"], "경고",
                          f"승인받아 계산했으나 정의서 구간 {valid} 밖이다", valid))
    if not out:
        out.append(_r("유효구간", "전체", "통과", "전부 정의서 구간 안"))
    return out


# ── 2. 최소표본 ───────────────────────────────────────────────────────
def check_min_sample(metrics_df: pd.DataFrame) -> list[dict]:
    """표본이 기준에 못 미치면 경고. 값은 내되 결론 근거로 쓰지 않는다.

    ⚠️ `sample_size`는 **개수를 세는 집계일 때만** 채워진다(계산 모듈에서 그렇게 둔다).
      GB 평균 같은 값을 표본 수와 비교하면 오탐이 난다 — 5주차에 실제로 겪었다.
    """
    out = []
    for _, r in metrics_df.iterrows():
        ms, ss = _num(r.get("min_sample")), _num(r.get("sample_size"))
        if ms is None or ss is None:
            continue                                   # 검사 대상 아님
        if ss < ms:
            out.append(_r("최소표본", r["지표명"], "경고",
                          f"표본 {ss:,.0f} < 기준 {ms:,.0f} — 결론 근거로 쓰지 않는다", ss))
    if not out:
        out.append(_r("최소표본", "전체", "통과", "기준 미달 지표 없음"))
    return out


# ── 3. 파생지표 정합성 ────────────────────────────────────────────────
def _link(s) -> str | None:
    m = re.search(r"\[\[([^\]]+)\]\]", str(s or ""))
    return m.group(1) if m else None


def check_derived_consistency(metrics_df: pd.DataFrame, catalog: dict) -> list[dict]:
    """파생형을 기초지표로 **재조합해** 저장된 값과 대조한다.

    분자·분모 metric_id는 계산 블록의 위키링크에서 뽑고, 없으면 `의존지표` 순서를 쓴다.
    분모 지표가 결과표에 없으면 `sample_size`(계산 모듈이 분모를 넣어둔다)로 대조한다 —
    그것도 없으면 **"검사 불가" 경고**로 둔다. 조용히 통과시키지 않는다.
    """
    vals = {r["metric_id"]: _num(r.get("value")) for _, r in metrics_df.iterrows()}
    out = []
    for _, r in metrics_df.iterrows():
        mid = r["metric_id"]
        spec = catalog.get(mid) or {}
        calc = spec.get("계산", {}) or {}
        deps = spec.get("의존지표") or []
        if not isinstance(calc.get("분자"), str) or len(deps) < 2:
            continue                                   # 분자/분모 구조의 파생형만 대상
        num_id = _link(calc.get("분자")) or deps[0]
        den_id = _link(calc.get("분모")) or deps[1]
        got = _num(r.get("value"))
        num, den = vals.get(num_id), vals.get(den_id)
        if den is None:
            den = _num(r.get("sample_size"))           # 계산 모듈이 분모를 여기 넣어둔다
        if got is None or num is None or den in (None, 0):
            out.append(_r("파생 정합성", r["지표명"], "경고",
                          f"검사 불가 — 의존 지표({num_id} / {den_id})가 계산되지 않음"))
            continue
        expect = num / den
        err = abs(expect - got) / abs(expect) * 100 if expect else 0.0
        if err <= 0.01:
            out.append(_r("파생 정합성", r["지표명"], "통과",
                          f"{num_id}/{den_id} 재조합 = {expect:,.4f} (오차 {err:.4f}%)", err))
        else:
            out.append(_r("파생 정합성", r["지표명"], "차단",
                          f"재조합 {expect:,.4f} ≠ 저장값 {got:,.4f} (오차 {err:.3f}%)", err))
    if not out:
        out.append(_r("파생 정합성", "전체", "통과", "대상 파생지표 없음"))
    return out


# ── 4. 전월 대비 이상 변동 ────────────────────────────────────────────
def threshold_of(metric_id: str, catalog: dict | None,
                 default: float | None = None) -> tuple[float, str]:
    """이 지표에 적용할 임계값과 그 **출처**를 함께 낸다.

    ★ 지표명이 이 함수에 등장하지 않는다. 코드가 아는 것은 `config.MOM_THRESHOLD_FIELD`
      필드 이름 하나뿐이고, 어느 지표가 몇 %인지는 전부 정의서가 정한다.
      `if mid == "avg_data_usage": th = 10` 같은 분기를 두면 임계값이 위키와 코드 두 곳에
      살게 되고, 위키만 고친 다음 날 화면이 옛 값으로 판정한다.

    출처를 함께 내는 이유: **왜 경고가 났는지/안 났는지**는 임계값을 봐야 알 수 있고,
    그 임계값이 근거를 갖고 정한 값인지 손대지 않은 기본값인지는 다시 출처를 봐야 안다.
    """
    default = config.MOM_THRESHOLD if default is None else default
    spec = (catalog or {}).get(metric_id) or {}
    v = _num(spec.get(config.MOM_THRESHOLD_FIELD))
    return (default, "기본값") if v is None else (v, "정의서")


def check_month_over_month(comparison_df: pd.DataFrame, catalog: dict | None = None,
                           default_threshold: float | None = None) -> list[dict]:
    """상대변화율이 **그 지표의** 임계값 이상이면 경고. 비교 불가는 **경고가 아니라 정보**다.

    비교할 수 없다는 것과 이상하다는 것은 다르다. 섞으면 경고 개수가 부풀어
    진짜 경고가 묻힌다.

    ★ 다른 검증과 달리 **통과한 지표도 행을 남긴다.** 판정 기준이 지표마다 다르기 때문이다.
      경고만 보여주면 "활성 고객이 2.2% 줄었는데 왜 경고가 없지?"에 화면이 답하지 못한다.
      기준이 공통일 때는 통과를 접어도 되지만, 기준이 지표마다 다르면 **기준 자체가 결과**다.
    """
    out = []
    if comparison_df is None or not len(comparison_df):
        return [_r(MOM_CHECK, "전체", "통과", "비교 데이터 없음")]

    for _, r in comparison_df.iterrows():
        mid = r.get("metric_id")
        th, src = threshold_of(mid, catalog, default_threshold)
        if str(r.get("비교상태", "")) != "비교 가능":
            # 비교를 못 했으면 임계값이 적용된 바 없다 — 기준 열을 비워 둔다
            out.append(_r(MOM_CHECK, r["지표명"], "정보",
                          f"비교 불가 — {r.get('이유', '')}"))
            continue
        rate = _num(r.get("상대변화율"))
        if rate is None:
            continue
        over = abs(rate) >= th
        out.append(_r(MOM_CHECK, r["지표명"], "경고" if over else "통과",
                      f"전월 대비 {rate:+.1f}% — 임계값 {th:g}% "
                      f"{'이상' if over else '미만'}", rate,
                      기준=f"{th:g}% ({src})"))
    return out


# ── 5. 합계 대조 ──────────────────────────────────────────────────────
def check_totals(metrics_df: pd.DataFrame, catalog: dict | None = None) -> list[dict]:
    """세그먼트 지표의 그룹 합이 전체와 맞는지 본다.

    지금 데이터에 세그먼트로 계산된 지표가 없으면 **"해당 없음"으로 통과**를 낸다.
    검사를 안 한 것과 통과한 것을 구분하려고 상세에 그 사실을 적는다.
    """
    catalog = catalog or {}
    grouped = [r["metric_id"] for _, r in metrics_df.iterrows()
               if (catalog.get(r["metric_id"]) or {}).get("계산", {}).get("그룹핑")
               or (catalog.get(r["metric_id"]) or {}).get("계산", {}).get("채널별")]
    if not grouped:
        return [_r("합계 대조", "전체", "통과", "해당 없음 — 세그먼트로 계산된 지표가 없다")]
    return [_r("합계 대조", ", ".join(grouped), "경고",
               "세그먼트 지표가 있으나 그룹별 값이 결과표에 없어 대조하지 못했다")]


# ── 요약 ──────────────────────────────────────────────────────────────
# ── 검증 6 — 값 자체를 본다 (전월 대비가 아니라) ──────────────────────
def check_expected_value(metrics_df: pd.DataFrame, catalog: dict | None) -> list[dict]:
    """정의서에 `기대값`이 있으면 **값 자체**를 검사한다.

    ★ 왜 필요한가 (2026-08-22 재고 이식에서 드러남)
      검증 5종은 전부 **전월 대비**나 **표본·구간**을 본다. 그런데 어떤 지표는
      *"이 값은 항상 0이어야 한다"*가 판정 기준이다(재고 항등식 차이).
      전월 대비로는 잡히지 않는다 — 전월이 0이면 변화율을 낼 수 없어
      **"비교 불가"로 조용히 넘어간다.** 실제로 항등식이 93,304원 어긋난 실행이
      "경고 0"으로 통과했다.

    · `기대값`  — 이 값이어야 한다 (보통 0)
    · `절대허용오차` — 이만큼까지는 같은 것으로 본다 (없으면 0)
      재고 항등식의 운영 기준은 `abs(diff) < 1`이므로 1을 쓴다.
    """
    out = []
    for _, r in metrics_df.iterrows():
        spec = (catalog or {}).get(r["metric_id"]) or {}
        if "기대값" not in spec:
            continue
        exp = _num(spec.get("기대값"))
        tol = _num(spec.get("절대허용오차")) or 0
        got = _num(r.get("value"))
        if exp is None:
            continue
        if got is None:
            out.append(_r("기대값", r["지표명"], "경고",
                          f"값이 없어 기대값({exp:,.0f})과 대조하지 못했다", None))
            continue
        gap = got - exp
        ok = abs(gap) <= tol
        out.append(_r("기대값", r["지표명"], "통과" if ok else "차단",
                      f"기대 {exp:,.0f} · 실제 {got:,.0f} · 차이 {gap:,.0f}"
                      + (f" (허용 ±{tol:,.0f})" if tol else ""),
                      got))
    return out


# ── 검증 7 — 변하지 않는 것도 신호다 ──────────────────────────────────
def check_no_change(comparison_df: pd.DataFrame, catalog: dict | None) -> list[dict]:
    """전 기간 대비 변화가 **정확히 0**이면 경고한다 — 정의서가 `무변동주의`를 켠 지표만.

    ★ 왜 필요한가
      임계값은 "많이 변하면 알려달라"는 장치라 **0.00%는 절대 걸리지 않는다.**
      그러나 금액이 억 단위인 지표가 소수점까지 똑같다면 그것은 안정이 아니라
      **소스 갱신이 멈춘 것**일 수 있다.
      실측 근거: 2026-07-31, 실제 재고 파일의 `AS사출금액`이 **10주 내내
      87,962,751.0으로 완전히 동일**했다. 정지인지 실제 무변동인지 지금도 미확인이다.
      Day5 트랙 A에서도 "활성 고객 441명 무변화"가 세 신호 중 하나였다.

    ★ 이 검사는 **한 주만 보고 판정하지 않는다.** 한 번 같을 수는 있다.
      연속 몇 주인지는 이 실행만으로 알 수 없으므로 **경고까지만** 하고
      "몇 주째인지 확인하라"고 남긴다. 차단하지 않는다.
    """
    out = []
    if comparison_df is None or not len(comparison_df):
        return out
    for _, r in comparison_df.iterrows():
        spec = (catalog or {}).get(r["metric_id"]) or {}
        if str(spec.get("무변동주의", "")).strip().lower() not in ("true", "yes", "on", "1"):
            continue
        if r.get("비교상태") != "비교 가능":
            continue
        delta = _num(r.get("절대변화"))
        if delta is None:
            continue
        if delta == 0:
            out.append(_r("무변동", r["지표명"], "경고",
                          "전 기간 대비 변화가 **정확히 0**이다 — 값이 안 변한 것인지 "
                          "**소스 갱신이 멈춘 것인지** 확인이 필요하다. 몇 주째인지 함께 본다.",
                          _num(r.get("당월"))))
        else:
            out.append(_r("무변동", r["지표명"], "통과",
                          f"변화 있음 ({delta:,.0f})", _num(r.get("당월"))))
    return out


# ── 검증 8 — 계산이 실패한 지표가 있는가 ──────────────────────────────
def check_calc_failed(metrics_df: pd.DataFrame) -> list[dict]:
    """**계산 실패를 검증 결과로 올린다.**

    ★ 왜 필요한가 (2026-08-22 재고 이식에서 드러남)
      지표 7종이 **전부 계산에 실패했는데 검증은 "통과 · 경고 0"으로 나왔다.**
      검증 5종이 모두 "값이 있는 지표"만 보기 때문이다. 값이 없으면 검사 대상에서
      빠지고, 빠진 것은 통과처럼 보인다. **가장 위험한 형태의 조용한 실패다.**

      리포트 4장은 "계산 지표 7종"이라고 쓰고 검증은 "통과"라고 쓰는데
      실제로는 아무것도 계산되지 않은 상태가 된다.
    """
    if not len(metrics_df) or "status" not in metrics_df:
        return []
    bad = [r for _, r in metrics_df.iterrows()
           if "오류" in str(r.get("status") or "") or "실패" in str(r.get("status") or "")]
    if not bad:
        return [_r("계산 성공", "전체", "통과", f"{len(metrics_df)}종 모두 계산됨")]
    return [_r("계산 성공", r["지표명"], "차단",
               f"계산되지 않았다 — {str(r.get('status'))[:80]}") for r in bad]


# ── 검증 9 — 받은 파일 자체의 품질 ────────────────────────────────────
def check_input_quality(run_log: dict | None, prev_rows: int | None = None,
                        drop_pct: float = 3.0) -> list[dict]:
    """**입력 파일의 상태를 검증으로 올린다** — 판정 화면에만 두지 않는다.

    ★ 왜 필요한가
      Day5 트랙 A에서 매출 감소의 78%가 **고객 20명 누락**이었고, 그것은 1단계
      행수(500→480)에 드러나 있었다. 그러나 검증 5종은 전부 *계산된 지표 값*만 보므로
      **행이 빠진 것 자체는 검증을 통과한다.** 사람이 화면을 유심히 봐야만 걸린다.
      재고에서도 같은 일이 났다 — 140행(4,374만원)이 빠졌는데 총재고 변화는
      임계값 아래라 경고가 나지 않았다.

    ★ 무엇을 보는가 (전부 2단계 판정이 이미 낸 값이다 — 새로 계산하지 않는다)
      · 직전 실행 대비 **행수 변화** — `drop_pct`% 이상 줄면 경고
      · **결측** 건수 — 있으면 경고(합계에서 그 행은 0으로 취급된다)
      · **그레인 중복** — 있으면 차단(같은 키가 여러 행이면 합계가 부풀려진다)
      · 정의서 대비 **누락 컬럼**

    ★ 행수 기준(3%)은 잠정이다. Day5 트랙 A가 −4.0%였고 이 값에 걸린다.
      운영하며 오탐·미탐을 세어 다시 정해야 한다.
    """
    out: list[dict] = []
    if not run_log:
        return out

    def field(name, default=None):
        if name in run_log and not isinstance(run_log[name], dict):
            return run_log[name]
        for blk in run_log.values():
            if isinstance(blk, dict) and name in blk:
                return blk[name]
        return default

    rows = field("행수")
    if rows and prev_rows:
        d = rows - prev_rows
        pct = d / prev_rows * 100
        out.append(_r("입력 행수", "업로드 파일",
                      "경고" if pct <= -drop_pct else "통과",
                      f"{rows:,}행 — 직전 실행 {prev_rows:,}행 대비 {d:+,}행({pct:+.1f}%)"
                      + (f" · 기준 −{drop_pct:.0f}%" if pct <= -drop_pct else ""),
                      rows))
    elif rows:
        out.append(_r("입력 행수", "업로드 파일", "통과",
                      f"{rows:,}행 (직전 실행이 없어 대조하지 않았다)", rows))

    miss = field("결측", 0) or 0
    if miss:
        out.append(_r("결측", "업로드 파일", "경고",
                      f"{miss:,}건 — 합계에서는 그 행이 0인 것과 결과가 같고, "
                      "평균에서는 분모에서도 빠진다", miss))
    else:
        out.append(_r("결측", "업로드 파일", "통과", "없음", 0))

    dup = field("그레인_중복", 0) or 0
    if dup:
        out.append(_r("그레인 중복", "업로드 파일", "차단",
                      f"{dup:,}건 — 같은 키가 여러 행으로 들어와 합계가 부풀려진다", dup))

    lack = field("누락_컬럼") or []
    if lack:
        out.append(_r("누락 컬럼", "업로드 파일", "경고",
                      "정의서에 있으나 파일에 없음: " + ", ".join(map(str, lack))))
    return out


# ── 검증 10 — 정상 범위를 데이터에서 만든다 ───────────────────────────
def normal_band(metric_id: str, outputs_dir=None,
                min_n: int = 5, k: float = 2.0) -> tuple[float, float, int] | None:
    """과거 실행들의 값에서 **정상 범위**를 만든다. (하한, 상한, 표본수)

    ★ 왜 필요한가
      *"무출하 1.6%가 높은 수준인지 비교할 정상 범위가 아직 없다"* —
      리포트가 스스로 적은 한계다. 임계값(변동임계값)은 **전 기간 대비 변화**를 보지만,
      *"이 값 자체가 평소와 다른가"*는 답하지 못한다. 둘은 다른 질문이다.

    ★ 왜 정의서에 안 적나
      정상 범위는 **데이터가 쌓이면 바뀐다.** 정의서에 숫자를 박으면 그 순간부터
      낡기 시작하고, 아무도 갱신하지 않는다. 매 실행 데이터에서 다시 만든다.

    ★ 왜 표본이 모자라면 안 만드나
      다섯 번으로 만든 범위는 범위가 아니라 **최근 다섯 값의 우연**이다.
      없으면 "범위 없음"이라고 밝히는 것이 낫다 — 없는 기준을 지어내지 않는다.
    """
    import statistics as st
    base = Path(outputs_dir) if outputs_dir else Path(__file__).resolve().parent.parent / "outputs"
    if not base.exists():
        return None
    vals, seen = [], set()
    for run in sorted(base.glob("run_*"), reverse=True):
        f = run / "metrics.csv"
        if not f.exists():
            continue
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if "metric_id" not in df.columns or "month" not in df.columns:
            continue
        row = df[df["metric_id"] == metric_id]
        if not len(row):
            continue
        per = str(row["month"].iloc[0])
        if per in seen:              # 같은 기간을 여러 번 돌린 실행은 한 번만 센다
            continue
        v = row["value"].iloc[0]
        if v is None or v != v:
            continue
        seen.add(per)
        vals.append(float(v))
    if len(vals) < min_n:
        return None
    # ★ 평균±σ가 아니라 **백분위**를 쓴다.
    #   이상이 몇 주 이어지면 그 값들이 표본에 들어가 σ를 키우고, 결국 **이상이 정상이 된다.**
    #   실측: 도장 달성률이 3주째 62%인데 평균±2σ 범위가 52.8~104%로 벌어져
    #   61.7%가 "정상"으로 통과했다. 백분위는 소수 이상치에 덜 흔들린다.
    q = sorted(vals)
    def pct(x):
        i = (len(q) - 1) * x
        lo_i, hi_i = int(i), min(int(i) + 1, len(q) - 1)
        return q[lo_i] + (q[hi_i] - q[lo_i]) * (i - lo_i)
    mu = st.median(vals)
    sd = (pct(0.9) - pct(0.1)) / 2 if len(vals) > 2 else 0.0

    # ★ 폭이 없는 범위는 범위가 아니다.
    #   수주 지표처럼 **기간 무관 누계**는 매주 같은 값이라 σ가 0이 된다.
    #   그러면 범위가 한 점이 되어 부동소수점 잔차만으로도 "범위 밖"이 뜬다
    #   (실측: A/S 수주 잔량 범위가 9.777e+06 ~ 9.777e+06).
    #   변동이 거의 없는 지표는 **검사 대상이 아니라고 밝히는 것**이 맞다.
    if mu and abs(sd / mu) < 0.005:
        return None

    lo, hi = pct(0.1), pct(0.9)
    # 음수가 될 수 없는 값(수량·금액)의 하한을 음수로 두지 않는다.
    # 실측: 납기 초과 도번 수 하한이 -49.8로 나왔다 — 개수는 음수일 수 없다.
    if min(vals) >= 0:
        lo = max(lo, 0.0)
    return lo, hi, len(vals)


def check_normal_band(metrics_df: pd.DataFrame, catalog: dict | None = None,
                      outputs_dir=None) -> list[dict]:
    """이번 값이 **평소 범위** 안에 있는가.

    · 정의서가 `정상범위검사: false`면 건너뛴다(항등식처럼 값 자체가 기준인 지표).
    · 표본이 모자라면 "범위 없음"을 **정보로 남긴다** — 검사를 안 한 것과
      통과한 것은 다르고, 그 차이가 리포트 한계 절에 실려야 한다.
    """
    out = []
    for _, r in metrics_df.iterrows():
        mid = r["metric_id"]
        spec = (catalog or {}).get(mid) or {}
        if str(spec.get("정상범위검사", "")).strip().lower() in ("false", "no", "off", "0"):
            continue
        v = _num(r.get("value"))
        if v is None:
            continue
        band = normal_band(mid, outputs_dir)
        if band is None:
            out.append(_r("정상범위", r["지표명"], "정보",
                          "범위를 만들지 못했다(표본 부족 또는 변동이 거의 없음) — "
                          "**검사하지 않았다**", v))
            continue
        lo, hi, n = band
        ok = lo <= v <= hi
        # 큰 수가 "1.907e+06"으로 보이면 읽을 수 없다. 화면·리포트와 같은 서식을 쓴다.
        u = common.unit_of(r)
        f = lambda x: common.fmt_unit(x * 100, "") + "%" if u == "%" else common.fmt_unit(x, u)
        out.append(_r("정상범위", r["지표명"], "통과" if ok else "경고",
                      f"평소 범위 {f(lo)} ~ {f(hi)} (과거 {n}기간 10~90백분위) · 이번 {f(v)}"
                      + ("" if ok else " — **범위 밖**"), v))
    return out


def validate_all(metrics_df: pd.DataFrame, comparison_df: pd.DataFrame,
                 catalog: dict, override: bool = False,
                 run_log: dict | None = None,
                 prev_rows: int | None = None) -> dict:
    """검증 10종을 모두 실행하고 전체 판정을 낸다."""
    items: list[dict] = []
    items += check_valid_range(metrics_df, catalog, override)
    items += check_min_sample(metrics_df)
    items += check_derived_consistency(metrics_df, catalog)
    items += check_month_over_month(comparison_df, catalog)
    items += check_totals(metrics_df, catalog)
    items += check_expected_value(metrics_df, catalog)     # 값 자체 (전월 대비가 아니라)
    items += check_no_change(comparison_df, catalog)       # 변하지 않는 것도 신호다
    items += check_calc_failed(metrics_df)                 # 계산 실패를 통과로 두지 않는다
    items += check_input_quality(run_log, prev_rows)       # 받은 파일 자체의 품질
    items += check_normal_band(metrics_df, catalog)        # 평소 범위 안인가

    blocked = sum(1 for x in items if x["판정"] == "차단")
    warned = sum(1 for x in items if x["판정"] == "경고")
    overall = "차단" if blocked else ("경고" if warned else "통과")

    return {
        "전체판정": overall,
        "차단수": blocked,
        "경고수": warned,
        "항목": items,
        # ★ 이 목록을 빼면 "검증 통과"가 실제보다 강한 신뢰를 준다. 반드시 함께 나간다.
        "자동검증하지_않은_것": list(NOT_AUTOMATED),
    }
