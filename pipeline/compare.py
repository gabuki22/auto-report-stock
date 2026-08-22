# -*- coding: utf-8 -*-
"""당월 ↔ 전월 비교 — 앱 3단계 입력 (6주차 Day2 실습 A).

전월 값을 어디서 가져오는가
    위키의 outputs/metrics_*.csv 를 읽기   → 파일이 없는 달이 있고, **앱이 위키에 의존**하게 된다
    BigQuery에서 전월을 다시 계산          → ★채택

    2025-01  ← 업로드 파일 (스테이징 테이블)
    2024-12  ← 원본 테이블에서 계산 (staging_map을 빈 dict로 넘긴다)

★ 전월 값이 없으면 **0으로 채우지 않는다.** "비교 불가"로 남긴다.
  0으로 채우면 "매출이 100% 늘었다" 같은 거짓 문장이 자동 생성된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import calculate as calc  # noqa: E402


# ── 함수 1 ────────────────────────────────────────────────────────────
def previous_period(period: str, client=None) -> str:
    """이전 기간 — 월이면 달력으로, **주간이면 직전 스냅샷을 데이터에서 찾는다.**

    ★ 왜 데이터에서 찾는가 (2026-08-22 재고 이식에서 드러남)
      주간 스냅샷은 간격이 **7일 고정이 아니다.** 실측에 5일·8일·14일(주차 건너뜀)이
      섞여 있다. "7일 전"으로 계산하면 스냅샷이 없는 날짜가 나와 전주 값이 0행이 되고,
      달력 전월로 계산하면 **한 달치 여러 주가 합산돼** 전주 대비가 3~4배로 부푼다
      (실측 14.9억짜리 주간 재고가 44억으로 나왔다 — 전부 "-67%" 경고가 떴다).

    ★ 조회 SQL은 `config.PREV_PERIOD_SQL`에 둔다. 앱은 테이블·컬럼 이름을 모른다.
      설정이 없거나(월 단위 프로젝트) 클라이언트가 없으면 달력 기준으로 돌아간다.
    """
    p = str(period).strip()
    sql = getattr(config, "PREV_PERIOD_SQL", None)
    if p.count("-") < 2 or not sql or client is None:
        return previous_month(p)

    from google.cloud import bigquery
    try:
        q = sql.format(project=client.project, dataset=config.BQ_DATASET)
        cfg = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("start", "DATE", p.split("~")[0].strip())])
        rows = list(client.query(q, job_config=cfg,
                                 location=config.BQ_LOCATION).result())
        got = rows[0][0] if rows else None
        return str(got) if got else previous_month(p)
    except Exception:
        # 조회 실패는 비교 불가로 이어질 뿐이므로 달력 기준으로 물러선다.
        return previous_month(p)


def previous_month(period: str) -> str:
    """"2025-01" → "2024-12". 연도 경계를 개월 수로 환산해 넘긴다.

    y*12 + (m-1) 로 펼쳤다가 되돌리면 1월→전년 12월이 자동으로 처리된다.
    if m == 1 같은 분기를 쓰면 12개월 이상 시차가 필요해질 때 또 고쳐야 한다.
    """
    y, m = map(int, str(period).split("-")[:2])
    total = y * 12 + (m - 1) - 1
    return f"{total // 12}-{total % 12 + 1:02d}"


# ── 함수 2 ────────────────────────────────────────────────────────────
def calc_previous(metric_ids: list[str], prev_period: str, client,
                  catalog: dict | None = None,
                  sql_log: dict | None = None,
                  dep_values: dict | None = None,
                  override: bool = False) -> pd.DataFrame:
    """전월 값을 **원본 테이블에서** 계산한다.

    · `staging_map={}` — 전월 데이터는 이미 원본에 있으므로 스테이징을 쓰지 않는다.
    · `override` — **당월과 같은 승인을 전월에도 적용한다.**
      ★ 처음에는 전월을 항상 `False`로 두었다("전월은 구간 안에 있을 것이다").
        2025-02를 돌려 보니 전월(2025-01)이 구간 밖이라 **비교가 통째로 사라졌다** —
        유효구간을 넘긴 뒤 두 번째 달부터는 전월 대비가 영구히 없어진다.
        승인은 *실행 단위*이므로(`--approve-extension`은 이 실행에 대한 승인이다)
        같은 실행 안의 전월에도 같은 승인이 적용되는 것이 맞다.
      ★ 다만 **조용히 넘어가지 않는다** — 전월도 구간 밖이었다는 사실은
        `compare()`가 비교표 `이유` 칸에 남기고, 리포트 한계 절이 그것을 인용한다.
    · 계산 자체는 `calculate.calculate()`를 그대로 재사용한다 — 당월과 전월을 다른 코드로
      계산하면 두 값이 다른 정의로 나올 수 있다.
    """
    if catalog is None:
        catalog, _ = common.load_catalog("metrics_catalog")
    df = calc.calculate(metric_ids, prev_period, {}, client, override, catalog,
                        sql_log=sql_log, dep_values=dep_values)
    return fill_from_runs(df, prev_period)


def previous_from_runs(prev_period: str,
                       outputs_dir: str | Path | None = None) -> tuple[pd.DataFrame, str]:
    """이전 실행 결과에서 전월 값을 읽는다 — **원본 테이블에 없는 달**의 대비를 위해.

    ★ 왜 필요한가 (2025-02 실행에서 드러남)
      업로드분은 **스테이징 테이블에만** 올라가고 원본에는 들어가지 않는다(DML 없음).
      스테이징은 실행마다 덮어쓴다. 그래서 1월을 올려 리포트를 낸 **다음 달에 2월을 올리면
      1월은 어디에도 없다** — BigQuery로 전월을 다시 계산하면 0행이 조회된다.
      COUNT는 **0을**, SUM은 NULL을 낸다. 0은 "전월 활성 사용자 0명"이라는 거짓으로 이어진다.

    ★ 왜 이전 실행 결과가 맞는가
      지난달 리포트는 이미 나갔고 그 숫자가 확정본이다. 이번 달 리포트의 "전월" 칸이
      지난달 리포트와 다르면 그것이 더 큰 사고다. **확정본을 쓰는 것이 오히려 정확하다.**
      이 파일 맨 위에서 기각한 "위키의 CSV 읽기"와는 다르다 — 위키가 아니라
      **앱 자신의 실행 기록**이므로 외부 의존이 생기지 않는다.

    ★ 한계
      그 실행이 쓴 정의서가 지금과 다를 수 있다. 그래서 **어느 실행에서 가져왔는지**를
      함께 돌려주고, 비교표 `이유` 칸과 리포트 한계 절이 그 출처를 밝힌다.
    """
    base = Path(outputs_dir) if outputs_dir else Path(__file__).resolve().parent.parent / "outputs"
    if not base.exists():
        return pd.DataFrame(), ""
    for run in sorted(base.glob("run_*"), reverse=True):
        f = run / "metrics.csv"
        if not f.exists():
            continue
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        months = df["month"].dropna().astype(str) if "month" in df.columns else []
        if len(months) and str(months.iloc[0]) == str(prev_period):
            return df, run.name
    return pd.DataFrame(), ""


def fill_from_runs(df: pd.DataFrame, prev_period: str,
                   outputs_dir: str | Path | None = None) -> pd.DataFrame:
    """BigQuery가 값을 못 낸 전월 지표를 이전 실행 결과로 메운다.

    · **비어 있거나 0인 지표만** 채운다. 진짜 0이었다면 이전 실행도 0이므로 결과가 같다.
      반대로 이전 실행에는 값이 있는데 지금 0이 나왔다면 그것이 곧 "원본에 없다"는 증거다.
    · 채운 지표는 `status`에 **출처 실행 이름**을 남긴다. 조용히 채우면 그 숫자가
      이번 달과 같은 방식으로 계산된 것처럼 보인다.
    """
    if not len(df) or "value" not in df.columns:
        return df
    prev, src = previous_from_runs(prev_period, outputs_dir)
    if not len(prev) or "metric_id" not in prev.columns:
        return df
    vals = prev.set_index("metric_id")["value"].to_dict()
    for i, r in df.iterrows():
        cur = r.get("value")
        old = vals.get(r.get("metric_id"))
        if (pd.isna(cur) or cur == 0) and old is not None and not pd.isna(old):
            df.at[i, "value"] = old
            df.at[i, "status"] = f"이전 실행({src})"
    return df


def _num(v):
    """숫자로 읽을 수 있으면 float, 아니면 None."""
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


# ── 함수 3 ────────────────────────────────────────────────────────────
def _is_ratio(row) -> bool:
    """이 지표가 비율인가 — 퍼센트포인트 변화를 따로 낼지 정한다.

    `유형` 문자열만 믿지 않는다(카탈로그에서 avg_data_usage 유형이 금액형인데 실제는 GB 평균).
    화면 서식과 같은 판별기를 쓴다 — 판정이 두 곳에서 갈리면 표와 카드가 어긋난다.
    """
    return common.unit_of(row) == "%"


def compare(current_df: pd.DataFrame, previous_df: pd.DataFrame) -> pd.DataFrame:
    """당월·전월을 metric_id로 맞춰 변화를 계산한다.

    · 절대 변화 = 당월 − 전월
    · 상대 변화율 = (당월 − 전월) / 전월 × 100  ← **분모가 0이거나 없으면 None**
    · 비율 지표는 **퍼센트포인트 변화**를 따로 낸다: (당월 − 전월) × 100
      36.6% → 39.0%는 **+2.4%p**이자 **+6.6%**다. 둘을 섞으면 보고서가 틀린다.
    · 전월 값이 없으면 "비교 불가"와 **이유**를 담는다. 0으로 채우지 않는다.
    """
    cur = current_df.set_index("metric_id")
    prev = previous_df.set_index("metric_id") if len(previous_df) else previous_df

    rows = []
    for mid, c in cur.iterrows():
        p = prev.loc[mid] if (len(prev) and mid in prev.index) else None
        cv = c.get("value")
        pv = p.get("value") if p is not None else None
        cv = None if pd.isna(cv) else cv
        pv = None if (pv is None or pd.isna(pv)) else pv

        rec = {"metric_id": mid, "지표명": c.get("지표명", mid), "유형": c.get("유형", ""),
               # ★ 단위를 비교표에도 실어 나른다. 없으면 문장 생성이 이름으로 추측해
               #   "납기 초과 도번 수 +80명"이 된다(리포트 4-1에서 실제로 그랬다).
               "단위": c.get("단위", ""),
               "당월": cv, "전월": pv,
               "절대변화": None, "상대변화율": None, "퍼센트포인트변화": None,
               "비교상태": "비교 가능", "이유": ""}

        if p is None:
            rec.update(비교상태="비교 불가", 이유=f"전월({prev_label(previous_df)}) 계산 결과에 없음")
        elif pv is None:
            why = str(p.get("status") or "").strip()
            rec.update(비교상태="비교 불가",
                       이유=f"전월 값 없음{f' — {why}' if why and why != 'OK' else ''}")
        elif cv is None:
            rec.update(비교상태="비교 불가",
                       이유=f"당월 값 없음 — {str(c.get('status') or '').strip()}")
        else:
            rec["절대변화"] = cv - pv
            # ★ 허용오차 이내의 값은 **사실상 0**이다. 그걸 분모로 쓰면 안 된다.
            #   실측: 항등식 차이가 당월 1.2e-10 · 전월 -1.1e-11(둘 다 1원의 100억분의 1)인데
            #   변화율이 **-1225%**로 나왔다. 0에서 0으로 갔는데 급변한 것처럼 보인다.
            #   부동소수점 잔차는 어떤 합계 지표에서도 생기므로 일반 규칙으로 둔다.
            tol = _num(c.get("절대허용오차")) or 0
            if tol and abs(pv) <= tol and abs(cv) <= tol:
                rec["절대변화"] = 0.0
                rec["이유"] = f"두 기간 모두 허용오차(±{tol:g}) 안 — 변화율을 내지 않는다"
            elif pv == 0:
                rec.update(비교상태="비교 불가", 이유="전월 값이 0이라 변화율을 낼 수 없음")
            else:
                rec["상대변화율"] = (cv - pv) / pv * 100
                # 비교는 됐지만 **전월 값이 어떻게 구해졌는지**를 남긴다.
                # 남기지 않으면 "전월 대비 -5.0%"가 보증된 값처럼 읽힌다.
                pst = str(p.get("status") or "")
                if pst.startswith("이전 실행"):
                    rec["이유"] = (f"전월 값 출처: {pst} — 원본 테이블에 "
                                 f"{prev_label(previous_df)} 데이터가 없어 확정본을 사용")
                elif "구간확장" in pst:
                    rec["이유"] = f"전월({prev_label(previous_df)})도 유효구간 밖 — 확장 승인 하에 계산"
            if _is_ratio(rec):
                rec["퍼센트포인트변화"] = (cv - pv) * 100
        rows.append(rec)

    return pd.DataFrame(rows, columns=[
        "metric_id", "지표명", "유형", "단위", "당월", "전월",
        "절대변화", "상대변화율", "퍼센트포인트변화", "비교상태", "이유"])


def prev_label(previous_df: pd.DataFrame) -> str:
    """전월 표기 — 결과가 비어 있으면 '전월'."""
    if len(previous_df) and "month" in previous_df.columns:
        return str(previous_df["month"].iloc[0])
    return "전월"
