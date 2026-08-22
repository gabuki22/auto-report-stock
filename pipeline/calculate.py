# -*- coding: utf-8 -*-
"""스테이징 적재 + 지표 계산 — 앱 2단계 후반 (6주차 Day1 실습 F).

5주차 calc_metrics.py와 같은 원리이고 두 가지가 추가된다.
    명세 원천 : 06_metrics/*.md      →  metrics_catalog.json
    대상 테이블 : 원본 테이블          →  스테이징 테이블로 치환
    유효구간 밖 : 계산하지 않음        →  승인이 있으면 계산하고 "구간확장"으로 표시

원본 테이블은 건드리지 않는다. 적재는 INSERT가 아니라 **로드 잡**이다
(DML은 샌드박스에서 403 Billing으로 차단된다 — 우리 환경에서 실측 확인).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from pipeline import profile as pf  # noqa: E402


# ── 함수 1 — 업로드 파일을 스테이징에 올린다 ──────────────────────────
def coerce_types(df: pd.DataFrame, table_name: str,
                 schema_catalog: dict | None) -> pd.DataFrame:
    """업로드 DataFrame의 컬럼 타입을 **카탈로그가 아는 타입에 맞춘다.**

    ★ 왜 필요한가 (2026-08-22 재고 이식에서 드러남)
      CSV는 날짜도 숫자도 일단 문자열로 읽힌다. 그대로 적재하면 스테이징의 `날짜`가
      STRING이 되고, 원본 테이블은 DATE이므로 **같은 조건식을 쓸 수 없다**
      (`No matching signature for operator BETWEEN: STRING, DATE, DATE`).
      전월은 원본에서 계산되어 성공하고 **당월만 실패**하므로,
      비교표가 통째로 "당월 값 없음"이 되면서 조용히 사라진다.

    ★ 타입을 코드에 적지 않는다. 컬럼별 타입은 스키마 노트에 있고, 여기서는
      **카탈로그가 말하는 대로** 변환만 한다. 변환에 실패한 값은 NaT/NaN이 되며
      그 자체가 데이터 문제이므로 조용히 원래 값으로 되돌리지 않는다.
    """
    info = (schema_catalog or {}).get(table_name) or {}
    for col in info.get("컬럼", []):
        name, typ = col.get("컬럼명"), str(col.get("타입", "")).upper()
        if not name or name not in df.columns:
            continue
        try:
            if typ == "DATE":
                df[name] = pd.to_datetime(df[name], errors="coerce").dt.date
            elif typ in ("TIMESTAMP", "DATETIME"):
                df[name] = pd.to_datetime(df[name], errors="coerce")
            elif typ in ("INTEGER", "INT64"):
                df[name] = pd.to_numeric(df[name], errors="coerce").astype("Int64")
            elif typ in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
                df[name] = pd.to_numeric(df[name], errors="coerce")
        except Exception:
            pass          # 변환 불가는 원래 타입으로 두고 적재 단계에서 드러나게 한다
    return df


def load_staging(df: pd.DataFrame, table_name: str, client,
                 schema_catalog: dict | None = None) -> str:
    """업로드 DataFrame을 staging_<table> 테이블로 적재하고 전체 경로를 반환한다.

    왜 이렇게 하나
      · **로드 잡을 쓴다.** INSERT/UPDATE/MERGE 같은 DML은 원본을 오염시키고,
        샌드박스에서는 아예 차단된다(403 Billing). 로드 잡은 DML이 아니라 통과한다.
      · WRITE_TRUNCATE — 매 실행 교체한다. 누적되면 같은 달을 두 번 올렸을 때
        값이 조용히 두 배가 된다(5주차 중복 적재 방지 원칙).
      · 적재 후 **행수를 다시 세어 원본과 대조**한다. 적재는 성공했는데 행이 빠지는
        경우가 있어서, 숫자를 내기 전에 여기서 잡는다.
      · **타입을 카탈로그에 맞춘다**(`coerce_types`) — 안 맞추면 원본과 조건식이 갈라진다.
    """
    from google.cloud import bigquery

    df = coerce_types(df.copy(), table_name, schema_catalog)
    full = f"{client.project}.{config.BQ_DATASET}.{config.STAGING_PREFIX}{table_name}"
    job = client.load_table_from_dataframe(
        df, full,
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
        location=config.BQ_LOCATION)
    job.result()

    got = list(client.query(f"SELECT COUNT(*) AS n FROM `{full}`",
                            location=config.BQ_LOCATION).result())[0]["n"]
    if got != len(df):
        raise RuntimeError(f"적재 행수 불일치: 원본 {len(df):,} ≠ 적재 {got:,}")
    return full


# ── 함수 2 — 명세로 SQL을 조립한다 ────────────────────────────────────
def resolve_table(logical: str, staging_map: dict) -> str:
    """카탈로그의 논리 테이블명 → 실제 BigQuery 테이블명.

    1) staging_map에 있으면 스테이징 테이블 (업로드분)
    2) 없으면 원본 테이블. 우리 적재본은 이름에 접두어가 붙어 있어 config에서 붙인다
       (강사 project1_day1은 usage_history, 우리 study는 data_usage_history).
       테이블별 매핑을 코드에 박지 않고 **접두어 하나만 설정으로 둔다.**
    """
    if logical in staging_map:
        return staging_map[logical]
    return f"{config.BQ_TABLE_PREFIX}{logical}"


_COMPAT: dict[str, list[str]] = {}      # {테이블: 문자열로 맞춰야 할 DATE 월 컬럼}


def prepare_compat(client, dataset: str) -> None:
    """정의서가 문자열로 전제하는 월 컬럼이 실제로 DATE인 테이블을 한 번 조사해 캐시한다.

    왜 필요한가: 강사 정의서는 `year_month = @month`처럼 **문자열 비교**로 쓰여 있고,
    `PARSE_DATE('%Y-%m', year_month)`까지 등장한다. 우리 적재본은 그 컬럼이 DATE라
    원본을 조회하는 순간 깨진다(업로드 스테이징은 CSV라 문자열이어서 안 걸렸다).
    테이블 목록을 코드에 박지 않고 **컬럼 이름 규칙 + 실제 타입 조회**로 판단한다.
    """
    cols = config.BQ_STRING_MONTH_COLUMNS
    if not cols:
        return
    names = ", ".join(f"'{c}'" for c in cols)
    rows = client.query(
        f"SELECT table_name, column_name FROM "
        f"`{config.BQ_PROJECT}.{dataset}.INFORMATION_SCHEMA.COLUMNS` "
        f"WHERE column_name IN ({names}) AND data_type = 'DATE'",
        location=config.BQ_LOCATION).result()
    _COMPAT.clear()
    for r in rows:
        _COMPAT.setdefault(r["table_name"], []).append(r["column_name"])


def _table_ref(logical: str, staging_map: dict, dataset: str) -> str:
    """FROM 절에 넣을 참조. 원본이고 타입이 어긋나면 서브쿼리로 감싼다."""
    real = resolve_table(logical, staging_map)
    full = f"`{config.BQ_PROJECT}.{dataset}.{real}`"
    if logical in staging_map:                       # 업로드분 — CSV 타입 그대로 쓴다
        return full
    fix = _COMPAT.get(real)
    if not fix:
        return full
    conv = ", ".join(f"FORMAT_DATE('%Y-%m', {c}) AS {c}" for c in fix)
    return f"(SELECT * EXCEPT({', '.join(fix)}), {conv} FROM {full})"


def build_sql(metric_spec: dict, dataset: str, staging_map: dict,
              block: dict | None = None) -> str:
    """계산 블록 하나(원천·집계·조인·조건)를 SQL로 만든다.

    ★ 유형 문자열이 아니라 **계산 블록의 구조**로 분기한다. 5주차에 유형으로 분기했다가
      새 유형을 추가하는 순간 KeyError로 죽었다 — 유형 이름은 사람이 붙이는 라벨이고
      기계가 볼 것은 구조다.
    """
    calc = block if block is not None else metric_spec.get("계산", {})
    src = str(calc.get("원천") or calc.get("대상") or "").strip()
    if not src:
        raise ValueError("원천이 없는 블록은 SQL로 만들 수 없다")

    tables = [t.strip() for t in src.split("+") if t.strip()]
    frm = f"{_table_ref(tables[0], staging_map, dataset)} AS {tables[0]}"
    for t in tables[1:]:
        frm += f" JOIN {_table_ref(t, staging_map, dataset)} AS {t}"
        join_on = calc.get("조인")
        frm += f" ON {join_on}" if join_on else " ON TRUE"

    sql = f"SELECT {calc['집계']} AS value FROM {frm}"
    if calc.get("조건"):
        sql += f" WHERE {calc['조건']}"
    return sql


def _params(period: str):
    """기간 자리표시자를 바인딩한다. **월과 주(구간) 둘 다 받는다.**

    받는 형태
        "2025-01"                  월        → @start·@end = 그 달의 1일·말일
        "2026-08-18"               하루      → @start·@end = 그 날 (주간 스냅샷)
        "2026-08-12~2026-08-18"    구간      → @start·@end = 양 끝

    ★ 다섯 개를 **항상 함께** 바인딩한다.
      BigQuery는 쿼리에 없는 파라미터를 넘겨도 오류가 아니지만, 쿼리에 있는데 없으면
      오류다. 월 지표(`@month`)와 주간 지표(`@start`/`@end`)가 한 카탈로그에 섞여
      있으므로, 어느 쪽이 올지 모른 채 계산이 돌아간다. 둘 다 넣어 두면 섞여도 깨지지 않는다.

    ★ `@month`·`@month_start`·`@month_end`는 **그 기간이 속한 달**로 채운다.
      주간 파일을 넣었을 때 월 지표가 "그 주가 속한 달"로 계산되는 것이 자연스럽고,
      비워 두면 월 지표가 전부 계산 실패로 떨어진다.
    """
    from google.cloud import bigquery

    p = str(period).strip()
    if "~" in p:                                   # 구간
        a, b = (x.strip() for x in p.split("~", 1))
        start, end = pd.Timestamp(a).date(), pd.Timestamp(b).date()
    elif p.count("-") >= 2:                        # 하루 (YYYY-MM-DD)
        start = end = pd.Timestamp(p).date()
    else:                                          # 월 (YYYY-MM)
        y, m = map(int, p.split("-")[:2])
        start = pd.Timestamp(year=y, month=m, day=1).date()
        end = (pd.Timestamp(start) + pd.offsets.MonthEnd(1)).date()

    month = f"{start:%Y-%m}"
    m_start = pd.Timestamp(year=start.year, month=start.month, day=1).date()
    m_end = (pd.Timestamp(m_start) + pd.offsets.MonthEnd(1)).date()
    return [bigquery.ScalarQueryParameter("month", "STRING", month),
            bigquery.ScalarQueryParameter("month_start", "DATE", m_start),
            bigquery.ScalarQueryParameter("month_end", "DATE", m_end),
            bigquery.ScalarQueryParameter("start", "DATE", start),
            bigquery.ScalarQueryParameter("end", "DATE", end)]


# ── 함수 3 — 지표를 계산한다 ──────────────────────────────────────────
def _shift(period: str, n: int) -> str:
    y, m = map(int, period.split("-")[:2])
    total = y * 12 + (m - 1) + n
    return f"{total // 12}-{total % 12 + 1:02d}"


def _in_range(valid: str, period: str) -> bool | None:
    mm = re.match(r"\s*(\d{4}-\d{2})\s*~\s*(\d{4}-\d{2})", str(valid or ""))
    return None if not mm else (mm.group(1) <= period[:7] <= mm.group(2))


def _counts(calc: dict) -> bool:
    """이 집계가 개수를 세는가 — 최소표본 비교는 개수에만 의미가 있다."""
    return str(calc.get("집계", "")).upper().lstrip("(").startswith("COUNT")


def calculate(metrics_to_run: list[str], period: str, staging_map: dict,
              client, override: bool, catalog: dict,
              sql_log: dict | None = None,
              dep_values: dict | None = None,
              include_deps: bool = False) -> pd.DataFrame:
    """지표 목록을 계산해 표로 돌려준다.

    · 파생형은 의존 지표를 먼저 계산한다(재귀 + 캐시). 같은 지표를 두 번 계산하지 않는다.
    · 유효구간 밖이면 override가 없으면 **계산하지 않고** "유효구간 밖"으로 둔다.
      0을 반환하면 "3월 이탈률 0%" 같은 거짓 문장이 자동 생성된다.
    · 한 지표가 실패해도 나머지는 계속 간다. 하나 때문에 전체가 멈추면 운영에서 못 쓴다.
    · `sql_log`를 주면 **실제로 실행한 SQL**을 지표별로 담아준다. 스테이징 치환이 정말
      적용됐는지, 어느 테이블을 봤는지는 생성된 SQL을 봐야 확인된다.
    · `dep_values`를 주면 **재귀로 계산한 의존 지표 값까지** 담아준다.
      같은 값을 두 번 조회하지 않기 위한 캐시 전달용이다.
    · `include_deps=True`면 그렇게 계산된 의존 지표를 **결과표에도 싣는다**(`포함사유="의존 계산"`).
      화면에만 보이고 검증은 못 받는 값이 생기지 않게 하려면 이쪽이 기본이어야 한다.
      추이 차트처럼 지정한 지표만 필요한 호출은 False로 둔다.
    """
    prepare_compat(client, config.BQ_DATASET)
    cache: dict[tuple[str, str], tuple[float | None, str, float | None]] = {}

    def run_sql(sql: str, p: str) -> float | None:
        """★ 파라미터는 **그 지표를 계산하는 달**로 바인딩한다.

        처음엔 최상위 period로 고정했다가 시차 지표가 0.0으로 나왔다 —
        3개월 전을 조회해도 @month가 당월이라 같은 값끼리 비교하고 있었다.
        """
        from google.cloud import bigquery
        cfg = bigquery.QueryJobConfig(query_parameters=_params(p))
        rows = list(client.query(sql, location=config.BQ_LOCATION, job_config=cfg).result())
        return None if not rows else rows[0]["value"]

    def logged(sql: str, p: str, mid: str, block: str) -> float | None:
        """SQL을 기록하고 실행한다 — 화면에서 열어볼 수 있게 남긴다."""
        if sql_log is not None:
            sql_log.setdefault(mid, []).append({"블록": block, "월": p, "sql": sql})
        return run_sql(sql, p)

    def compute(mid: str, p: str) -> tuple[float | None, str, float | None]:
        """(값, 상태, 표본크기)"""
        key = (mid, p)
        if key in cache:
            return cache[key]
        spec = catalog.get(mid)
        if not spec:
            return (None, "정의서 없음", None)

        inr = _in_range(spec.get("유효구간"), p)
        if inr is False and not override:
            cache[key] = (None, "유효구간 밖", None)
            return cache[key]
        status = "구간확장" if inr is False else "OK"

        calc = spec.get("계산", {}) or {}
        try:
            if calc.get("원천") or calc.get("대상"):            # 단일 집계
                val = logged(build_sql(spec, config.BQ_DATASET, staging_map), p, mid, "단일 집계")
                sample = val if _counts(calc) else None
            elif isinstance(calc.get("분자"), dict):             # 비율형 — 두 집계
                num = logged(build_sql(spec, config.BQ_DATASET, staging_map, calc["분자"]), p, mid, "분자")
                den = logged(build_sql(spec, config.BQ_DATASET, staging_map, calc["분모"]), p, mid, "분모")
                if not den:
                    cache[key] = (None, "분모 0", None)
                    return cache[key]
                val, sample = num / den, (den if _counts(calc["분모"]) else None)
            elif calc.get("기준지표"):                           # 변화율형 — 시차
                base = (spec.get("의존지표") or [_wiki_link(calc["기준지표"])])[0]
                lag = int(calc.get("시차", -1))
                cur, st_c, _ = compute(base, p)
                prev, st_p, _ = compute(base, _shift(p, lag))
                if cur is None or prev in (None, 0):
                    cache[key] = (None, f"기준지표 {base} 계산 실패", None)
                    return cache[key]
                val = (prev - cur) / prev if calc.get("방향") == "감소" else (cur - prev) / prev
                sample = None
            else:                                                # 파생형 — 지표 참조
                deps = spec.get("의존지표") or []
                if len(deps) < 2:
                    cache[key] = (None, "파생 참조를 해석하지 못함", None)
                    return cache[key]
                num, _, _ = compute(deps[0], p)
                den, _, den_s = compute(deps[1], p)
                if num is None or den in (None, 0):
                    cache[key] = (None, f"의존지표 계산 실패({deps})", None)
                    return cache[key]
                val, sample = num / den, den
        except Exception as e:                                   # noqa: BLE001
            cache[key] = (None, f"계산오류: {type(e).__name__} {str(e)[:120]}", None)
            return cache[key]

        # 최소표본 — 개수일 때만 의미가 있다
        ms = spec.get("최소표본")
        if isinstance(ms, (int, float)) and sample is not None and sample < ms:
            status = "표본부족"
        cache[key] = (float(val) if val is not None else None, status, sample)
        return cache[key]

    def row(mid: str, val, status, sample, reason: str = "") -> dict:
        spec = catalog.get(mid, {})
        calc = spec.get("계산", {}) or {}
        srcs = str(calc.get("원천") or calc.get("대상") or "")
        return {
            "metric_id": mid,
            "지표명": spec.get("지표명", mid),
            "유형": spec.get("유형", ""),
            # ★ 단위를 정의서에서 그대로 실어 나른다. 이름·유형으로 추측하면
            #   같은 "수"라도 도메인마다 달라 반드시 틀린다(재고 수량이 "명"으로 나왔다).
            "단위": spec.get("단위", ""),
            # 비교 단계가 "이 값은 사실상 0인가"를 판단하려면 허용오차를 알아야 한다.
            "절대허용오차": spec.get("절대허용오차", ""),
            "month": period,
            "value": val,
            "sample_size": sample,
            "min_sample": spec.get("최소표본"),
            "status": status,
            "원천": srcs or " + ".join(spec.get("의존지표") or []),
            # ★ 원천을 **재귀로** 구한다. 파생형(arpu)은 계산 블록에 원천이 없고
            #   의존지표를 따라 내려가야 나온다 — 문자열만 쪼개면 arpu의 부분 갱신이
            #   통째로 누락되고, 리포트에 "customers는 옛 상태"가 안 적힌다.
            "부분갱신": ", ".join(sorted(
                pf._sources(spec, catalog) - set(staging_map))),
            "포함사유": reason,
        }

    out = [row(mid, *compute(mid, period)) for mid in metrics_to_run]

    if include_deps:
        # ★ 파생형을 계산하느라 **이미 계산된** 의존 지표를 결과표에 함께 싣는다.
        #   추가 쿼리는 없다(캐시에 있다).
        #
        #   싣지 않으면 어떻게 되나: arpu를 계산하려면 분모인 활성 고객 수가 필요해 실제로
        #   계산되는데, 결과표에 없으니 **검증도 전월 대비도 받지 않는다.** 그런데 화면
        #   카드는 그 값을 캐시에서 꺼내 보여준다 — 화면에는 숫자가 있고 검증에는 없는
        #   사각지대가 생긴다. 게이트를 통과한 숫자만 리포트에 들어간다는 원칙에 어긋난다.
        done = set(metrics_to_run)
        for (dmid, dper), (dval, dstatus, dsample) in sorted(cache.items()):
            if dper != period or dmid in done:
                continue
            out.append(row(dmid, dval, dstatus, dsample, "의존 계산"))
            done.add(dmid)

    if dep_values is not None:
        # 재귀로 계산된 의존 지표까지 전부 — 키는 "metric_id|YYYY-MM"
        dep_values.update({f"{k[0]}|{k[1]}": v for k, v in cache.items()})
    return pd.DataFrame(out)


def _wiki_link(s: str) -> str:
    m = re.search(r"\[\[([^\]]+)\]\]", str(s))
    return m.group(1) if m else str(s).strip()


def make_client():
    """BigQuery 클라이언트 — MCP가 아니라 이 스크립트가 직접 연결한다(무인 실행 요건)."""
    from google.cloud import bigquery
    return bigquery.Client(project=config.BQ_PROJECT) if config.BQ_PROJECT else bigquery.Client()


def auth_available() -> bool:
    """BigQuery 자격증명이 이 환경에 있는가.

    ★ 배포본(Streamlit Cloud)에는 자격증명이 없다. 그래도 **기존 실행 불러오기**는
      전부 파일에서 읽으므로 동작한다. 문제는 사용자가 그 사실을 모르고 새 파일을
      올린 뒤 '스테이징 적재 중...'에서 영문 없이 멈추는 것이다.
      **되지 않을 일은 시작하기 전에 막는다** — 오류로 알려주는 것보다 낫다.

    ★★ `google.auth.default()`를 그대로 부르면 안 된다.
      자격증명을 못 찾으면 마지막에 **GCE 메타데이터 서버(169.254.169.254)에 접속을
      시도**하는데, 그 주소가 응답도 거절도 하지 않는 환경(배포본)에서는 타임아웃까지
      화면이 멈춘다. 실제로 1단계에서 진행이 안 되는 것처럼 보였다 — 오류도 없이.
      **판정 하나가 화면을 세우면 안 된다.**

      여기서 알고 싶은 것은 *"파일이나 환경변수로 준 자격증명이 있는가"* 하나뿐이므로
      **네트워크를 건드리지 않고** 그것만 본다.

    한계
        gcloud SDK 자체 로그인처럼 **비표준 위치**의 자격증명은 못 본다.
        그 경우 `GOOGLE_APPLICATION_CREDENTIALS`를 지정하면 인식한다.
    """
    import os

    if cfg := os.environ.get("CLOUDSDK_CONFIG"):        # gcloud 설정 위치를 옮긴 경우
        return (Path(cfg) / "application_default_credentials.json").exists()
    if p := os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return Path(p).exists()
    base = (Path(os.environ["APPDATA"]) if os.name == "nt" and os.environ.get("APPDATA")
            else Path.home() / ".config")
    return (base / "gcloud" / "application_default_credentials.json").exists()
