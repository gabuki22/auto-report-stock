"""6주차 실습 전 BigQuery 사전 점검.

Day1 실습 F(스테이징 적재 + 계산)가 본인 환경에서 실제로 도는지 미리 확인한다.
확인하는 것은 네 가지이며, 하나라도 실패하면 그 단계에서 멈추고 원인을 알려준다.

  ① 인증 — ADC로 BigQuery 클라이언트가 만들어지는가
  ② 로드 잡 — DataFrame을 테이블로 적재할 수 있는가 (샌드박스에서도 되는지)
  ③ 파라미터 바인딩 — @month 같은 쿼리 파라미터가 통하는가
  ④ 정리 — 임시 테이블을 지울 수 있는가 (DDL)

②가 이 점검의 핵심이다. 교안은 "로드 잡은 DML이 아니므로 샌드박스에서도
동작한다"를 전제로 하는데, 그 전제가 본인 환경에서 참인지 확인한다.

이 스크립트는 `staging_preflight_test` 라는 임시 테이블만 건드리고
마지막에 삭제한다. 원본 테이블에는 손대지 않는다.

실행:
    python preflight_bigquery.py
    python preflight_bigquery.py --dataset project1_day1 --project my-project-id

필요 패키지: google-cloud-bigquery, pandas, pyarrow
"""

from __future__ import annotations

import argparse
import sys

TEST_TABLE = "staging_preflight_test"


def step(n: int, title: str) -> None:
    print(f"\n[{n}/4] {title}")


def ok(msg: str) -> None:
    print(f"      통과 — {msg}")


def fail(msg: str, hint: str) -> None:
    print(f"      실패 — {msg}")
    print(f"      대처: {hint}")


def main() -> int:
    parser = argparse.ArgumentParser(description="6주차 실습 전 BigQuery 사전 점검")
    parser.add_argument("--dataset", default="project1_day1", help="데이터셋 ID")
    parser.add_argument("--project", default=None, help="프로젝트 ID (생략 시 ADC 기본값)")
    args = parser.parse_args()

    # ── 패키지 확인 ────────────────────────────────────────────────
    try:
        import pandas as pd
        from google.cloud import bigquery
    except ImportError as e:
        print(f"패키지 없음: {e}")
        print("대처: pip install google-cloud-bigquery pandas pyarrow")
        return 2

    # ── ① 인증 ────────────────────────────────────────────────────
    step(1, "인증 확인")
    try:
        client = bigquery.Client(project=args.project) if args.project else bigquery.Client()
        project = client.project
        ok(f"프로젝트: {project}")
    except Exception as e:
        fail(str(e), "gcloud auth application-default login 을 1회 실행하세요")
        return 1

    table_id = f"{project}.{args.dataset}.{TEST_TABLE}"

    # 데이터셋이 있는지도 함께 확인 — 없으면 이후 단계가 전부 실패한다
    try:
        client.get_dataset(f"{project}.{args.dataset}")
        ok(f"데이터셋 확인: {args.dataset}")
    except Exception as e:
        fail(str(e), f"--dataset 값을 확인하세요. 현재: {args.dataset}")
        return 1

    # ── ② 로드 잡 (이 점검의 핵심) ────────────────────────────────
    step(2, "로드 잡 — DataFrame 적재 (샌드박스 가능 여부)")
    df = pd.DataFrame({
        "customer_id": ["C001", "C002", "C003"],
        "year_month": ["2025-01", "2025-01", "2025-01"],
        "amount": [1000, 2000, 3000],
    })
    try:
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        client.load_table_from_dataframe(df, table_id, job_config=job_config).result()
        loaded = client.get_table(table_id).num_rows
        if loaded == len(df):
            ok(f"{loaded}행 적재. 로드 잡이 이 환경에서 동작합니다")
        else:
            fail(f"적재 행수 불일치: 보낸 {len(df)}행, 저장된 {loaded}행",
                 "로드 잡 자체는 동작하나 데이터가 다릅니다. 스키마 충돌 여부를 확인하세요")
            return 1
    except Exception as e:
        msg = str(e)
        if "billing" in msg.lower() or "free tier" in msg.lower():
            hint = ("샌드박스 제약에 걸렸습니다. 5주차 부록 "
                    "'BigQuery_결제계정_전환가이드'대로 결제 계정을 연결하세요")
        elif "permission" in msg.lower() or "denied" in msg.lower():
            hint = "데이터셋 쓰기 권한이 없습니다. 본인 프로젝트인지 확인하세요"
        elif "pyarrow" in msg.lower():
            hint = "pip install pyarrow"
        else:
            hint = "오류 메시지를 그대로 Claude Code에 붙여넣고 물어보세요"
        fail(msg, hint)
        return 1

    # ── ③ 파라미터 바인딩 ─────────────────────────────────────────
    step(3, "쿼리 파라미터 바인딩 (@month)")
    try:
        sql = f"SELECT COUNT(*) AS n FROM `{table_id}` WHERE year_month = @month"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("month", "STRING", "2025-01")]
        )
        rows = list(client.query(sql, job_config=cfg).result())
        n = rows[0].n if rows else None
        if n == 3:
            ok(f"@month 바인딩 정상 (3행 조회)")
        else:
            fail(f"조회 결과가 예상과 다름: {n} (예상 3)",
                 "바인딩은 되지만 값이 다릅니다. 적재 데이터를 확인하세요")
            return 1
    except Exception as e:
        fail(str(e), "쿼리 파라미터 형식을 확인하세요 (ScalarQueryParameter)")
        return 1

    # ── ④ 정리 (DDL) ──────────────────────────────────────────────
    step(4, "임시 테이블 삭제 (DDL)")
    try:
        client.delete_table(table_id, not_found_ok=True)
        ok(f"{TEST_TABLE} 삭제 완료")
    except Exception as e:
        fail(str(e), f"수동으로 {table_id} 를 삭제하세요")
        return 1

    print("\n" + "=" * 58)
    print("네 항목 모두 통과 — Day1 실습 F를 진행할 수 있습니다.")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
