# -*- coding: utf-8 -*-
"""추이 데이터 준비 — 앱 4단계 차트 입력 (6주차 Day2 실습 D).

    end_period      ← 업로드 파일 (스테이징 테이블)
    그 이전 달들      ← 원본 테이블

★ 유효구간 밖인 달을 **0으로 채우지 않는다.** 값을 None으로 두고 선을 끊는다.
  0으로 그리면 그래프가 급락한 것처럼 보이고, 보는 사람은 그것을 사건으로 읽는다.
  "데이터 없음"과 "값이 0"은 다르다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from pipeline import calculate as calc  # noqa: E402


def months_back(end_period: str, n: int) -> list[str]:
    """end_period를 끝으로 하는 n개월 목록(오름차순)."""
    y, m = map(int, str(end_period).split("-")[:2])
    total = y * 12 + (m - 1)
    return [f"{(total - k) // 12}-{(total - k) % 12 + 1:02d}" for k in range(n - 1, -1, -1)]


def periods_back(end_period: str, n: int, client=None) -> list[str]:
    """추이에 쓸 기간 목록 — **주간이면 실제 스냅샷 날짜를 데이터에서 가져온다.**

    ★ 왜 데이터에서 가져오는가
      주간 스냅샷은 간격이 불규칙하다(실측 5·8·14일). "N개월 전"으로 계산하면
      실제 스냅샷이 없는 날짜가 나오고, 그 기간은 **값이 없어 선이 통째로 비어 버린다.**
      실제로 재고 차트가 전부 빈 채로 그려졌다.

    조회 SQL은 `config.TREND_PERIODS_SQL`에 둔다. 설정이 없거나(월 단위 프로젝트)
    기간이 월 형식이면 달력 계산으로 돌아간다.
    """
    p = str(end_period).strip()
    sql = getattr(config, "TREND_PERIODS_SQL", None)
    if p.count("-") < 2 or not sql or client is None:
        return months_back(p, n)

    from google.cloud import bigquery
    try:
        q = sql.format(project=client.project, dataset=config.BQ_DATASET, n=n)
        cfg = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("end", "DATE", p.split("~")[0].strip())])
        rows = [str(r[0]) for r in client.query(q, job_config=cfg,
                                                location=config.BQ_LOCATION).result()]
        if not rows:
            return months_back(p, n)
        # ★ 당월(업로드 기간)을 **반드시 포함**한다.
        #   업로드분은 아직 원본 테이블에 없으므로 위 조회에 안 잡힌다. 빠뜨리면
        #   추이 차트의 **마지막 점이 없어** 이번 주가 그래프에서 사라진다.
        return sorted(set(rows) | {p})[-n:]
    except Exception:
        return months_back(p, n)


def build_trend(metric_ids: list[str], end_period: str, months: int,
                staging_map: dict, client, catalog: dict,
                override_current: bool = False,
                on_progress=None) -> pd.DataFrame:
    """최근 months개월 추이를 long format으로 만든다.

    반환 컬럼: metric_id · 지표명 · 유형 · month · value · status

    · **당월만 스테이징**을 쓴다. 그 이전 달은 원본 테이블에 이미 있다.
    · 이미 계산한 (metric_id, month)은 다시 조회하지 않는다. 6개월 × 지표 수만큼
      쿼리가 나가면 화면이 멈춘다.
    · **유효구간 확장 승인은 당월에만 적용한다.** 사용자가 승인한 것은 업로드한 그 달이지
      과거 6개월이 아니다. 과거 달이 정의서 구간 밖이면 값 None + status 유지 →
      차트에서 선이 끊긴다. 모든 달에 override를 걸면 정의서가 의미를 잃는다.
    · `on_progress(i, total, period)`를 주면 진행률을 알린다(Streamlit 진행바 연결).
    """
    periods = periods_back(end_period, months, client)
    seen: dict[tuple[str, str], dict] = {}
    frames = []

    for i, p in enumerate(periods, 1):
        todo = [m for m in metric_ids if (m, p) not in seen]
        if todo:
            # 당월만 업로드분을 본다. 과거는 원본.
            smap = staging_map if p == end_period else {}
            ov = override_current and p == end_period
            df = calc.calculate(todo, p, smap, client, override=ov, catalog=catalog)
            df["month"] = p
            for _, r in df.iterrows():
                seen[(r["metric_id"], p)] = r.to_dict()
            frames.append(df)
        if on_progress:
            on_progress(i, len(periods), p)

    if not frames:
        return pd.DataFrame(columns=["metric_id", "지표명", "유형", "month", "value", "status"])

    out = pd.concat(frames, ignore_index=True)
    # 유효구간 밖·계산 실패는 값이 이미 NaN이다 — 0으로 바꾸지 않는다
    return out[["metric_id", "지표명", "유형", "month", "value", "status"]].sort_values(
        ["metric_id", "month"]).reset_index(drop=True)
