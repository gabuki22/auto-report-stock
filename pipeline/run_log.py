# -*- coding: utf-8 -*-
"""실행 기록 — 8단계 전체를 한 파일에 (6주차 Day4 실습 C, 프롬프트 7).

왜 이렇게 상세해야 하는가
    **3개월 뒤 "이 숫자 어떻게 나왔나요"라는 질문을 이 파일 하나로 답해야 한다.**
    어느 파일, 어느 정의, 어느 승인으로 나온 값인지가 다 들어 있어야 한다.

★ 읽기·쓰기를 이 모듈이 독점한다
    각자 `json.load`하고 각자 키를 박으면 단계 구분이 금세 무너진다.
    구조를 바꿀 때도 여기 한 곳만 고치면 된다.

구조
    {"_meta": {...}, "0_카탈로그": {...}, "1_투입": {...}, ..., "8_확정": {...}}
    각 단계에 `시각`이 자동으로 들어가고, 그 차이로 `소요초`를 계산한다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

FILENAME = "run_log.json"

# 단계 키와 화면에 보일 이름. 순서가 곧 표시 순서다.
STEPS: list[tuple[str, str]] = [
    ("0_카탈로그", "0. 카탈로그"),
    ("1_투입", "1. 데이터 파일 투입"),
    ("2_판정", "2. 스키마 판정"),
    ("2_계산", "2. 지표 계산"),
    ("게이트1", "게이트 1 — 판정 확정"),
    ("3_검증", "3. 검증"),
    ("게이트2", "게이트 2 — 내용 확인"),
    ("6_리포트", "6. 리포트 생성"),
    ("7_이메일", "7. 이메일 초안"),
    ("8_확정", "게이트 3 — 발송 확정"),
]
_ORDER = [k for k, _ in STEPS]
_LABEL = dict(STEPS)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def env() -> dict:
    """실행 환경 — 같은 결과가 안 나올 때 **버전 차이부터** 의심하게 된다."""
    out = {"python": sys.version.split()[0]}
    for mod in ("streamlit", "pandas", "google.cloud.bigquery", "fpdf"):
        try:
            m = __import__(mod, fromlist=["__version__"])
            out[mod.split(".")[-1]] = getattr(m, "__version__", "?")
        except Exception:                              # noqa: BLE001 — 없으면 없는 대로
            out[mod.split(".")[-1]] = "미설치"
    return out


def path(run_dir) -> Path:
    return Path(run_dir) / FILENAME


def load(run_dir) -> dict:
    p = path(run_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(run_dir, log: dict) -> None:
    path(run_dir).write_text(json.dumps(log, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def record(run_dir, step: str, **fields) -> dict:
    """한 단계를 기록한다. **시각은 자동으로 붙는다.**

    같은 단계를 다시 기록하면 덮어쓴다(재계산·재생성). 다만 **다른 단계 기록은
    건드리지 않는다** — 게이트 3에서 8단계를 쓰면서 게이트 1·2 기록이 사라지면
    "언제 무엇을 승인했는지"가 없어진다.
    """
    log = load(run_dir)
    log.setdefault("_meta", {}).update({"실행폴더": Path(run_dir).name, "환경": env()})
    log[step] = {"시각": now(), **fields}
    save(run_dir, log)
    return log


def field(log: dict, name: str, default=None):
    """단계를 몰라도 값을 찾는다.

    ⚠️ **편의 함수다.** 어느 단계 값인지 아는 곳에서는 `log["2_판정"]["테이블"]`처럼
      직접 읽는 게 낫다. 이 함수만 쓰면 단계 구분이 있으나 마나 해진다.
      평평했던 옛 기록도 읽히도록 최상위 키도 함께 본다.
    """
    if name in log and not isinstance(log[name], dict):
        return log[name]
    for k in _ORDER:
        blk = log.get(k)
        if isinstance(blk, dict) and name in blk:
            return blk[name]
    return default


def elapsed(log: dict) -> dict:
    """단계별 소요 초 — **앞 단계 시각과의 차.**

    첫 단계는 기준이 없어 None이다. 0으로 두면 "즉시 끝났다"로 읽힌다.
    """
    times = []
    for k in _ORDER:
        blk = log.get(k)
        if isinstance(blk, dict) and blk.get("시각"):
            try:
                times.append((k, datetime.fromisoformat(blk["시각"])))
            except ValueError:
                continue
    out = {}
    for i, (k, t) in enumerate(times):
        out[k] = None if i == 0 else round((t - times[i - 1][1]).total_seconds(), 1)
    return out


def rows(log: dict) -> list[dict]:
    """화면 표용 — [{단계, 시각, 소요초, 내용}]. 기록이 없는 단계는 빼지 않는다.

    빈 단계를 빼면 **어디까지 진행됐는지**가 표에서 사라진다.
    """
    el = elapsed(log)
    out = []
    for k in _ORDER:
        blk = log.get(k)
        if not isinstance(blk, dict):
            out.append({"단계": _LABEL[k], "시각": "—", "소요초": "—", "내용": "미실행"})
            continue
        body = " · ".join(
            f"{kk} {_short(vv)}" for kk, vv in blk.items() if kk != "시각")
        sec = el.get(k)
        out.append({"단계": _LABEL[k], "시각": blk.get("시각", "—")[11:19] or "—",
                    "소요초": "—" if sec is None else f"{sec:,.1f}",
                    "내용": body or "—"})
    return out


def _short(v, limit: int = 60) -> str:
    if isinstance(v, list):
        s = f"{len(v)}건" + (f" ({', '.join(map(str, v[:3]))}…)" if v else "")
    elif isinstance(v, dict):
        s = ", ".join(f"{k}={v[k]}" for k in list(v)[:3])
    else:
        s = str(v)
    return s if len(s) <= limit else s[:limit - 1] + "…"
