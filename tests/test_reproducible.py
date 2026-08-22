# -*- coding: utf-8 -*-
"""재현성 검증 — 같은 파일이면 같은 결과 (6주차 Day4 실습 E).

왜 지금 확인하는가
    · **검증 가능성** — 결과가 매번 다르면 무엇이 맞는지 알 수 없다.
    · **감사 대응** — "이 숫자 어떻게 나왔나요"에 답할 수 있어야 한다.
    · **8주차 자동 실행** — 사람 없이 도는데 결과가 흔들리면 쓸 수 없다.
      ★ **아무도 지켜보지 않으므로, 재현되지 않는 계산은 발견되지 않은 채 리포트로 나간다.**

    생성일시는 당연히 매번 다르다. 재현성 검증에서 **그 필드는 비교 대상에서 제외**한다.

    py -m pytest tests/ -v          # pytest로
    py -X utf8 tests/test_reproducible.py   # pytest 없이도 돈다
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import calculate as calc  # noqa: E402
from pipeline import report as rp  # noqa: E402
from pipeline import run_log as rl  # noqa: E402
from pipeline import validate as vd  # noqa: E402

# 생성일시처럼 **매번 달라야 정상인** 것들. 비교 전에 지운다.
VOLATILE = re.compile(r"(생성일시|계산 시각|실행 시각|확정_시각|시각)\s*[|:]?.*")

# ★ 계산에 관여하는 모듈 — 여기에 현재 시각이 있으면 **실패**다.
#   모듈의 성격은 코드로 유추할 수 없어 사람이 분류한다. 나머지(기록·표현)는
#   시각을 써도 되지만 **어디에 있는지는 출력**한다.
CALC_MODULES = {"calculate.py", "compare.py", "validate.py", "charts.py", "profile.py"}
TIME_CALLS = {"datetime.now", "date.today", "datetime.today", "time.time"}


def _dotted(node) -> str:
    """`datetime.now` 같은 호출 이름을 문자열로."""
    import ast
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def find_time_calls(src: str) -> list[tuple[int, str]]:
    """소스에서 **실제 호출**만 찾는다 — 주석·docstring은 제외.

    ★ 정규식으로 훑었더니 `report.py`의 **docstring에 적어둔 설명 문장**
      (*"`datetime.now()`를 여기서 부르면…"*)이 잡혔다. 검사기가 자기 문서를 위반으로
      본 셈이다. AST는 실행되는 코드만 보므로 그런 오탐이 없다.

    ★★ **뒤에서 두 조각으로 판정한다.** 처음엔 전체 이름을 비교했는데
      `import datetime as _d` → `_d.datetime.now()`를 **놓쳤다**(자가검증에서 발각).
      `import datetime` → `datetime.datetime.now()`도 같은 이유로 새어 나간다.
      호출 형태는 import 방식에 따라 앞이 계속 달라지므로 **끝을 본다.**
    """
    import ast
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            tail = ".".join(name.split(".")[-2:])
            if tail in TIME_CALLS:
                out.append((node.lineno, tail))
    return sorted(out)


# ── 공용 ──────────────────────────────────────────────────────────────
def _latest_runs(n: int = 2) -> list[Path]:
    runs = sorted((BASE / "outputs").glob("run_*"), reverse=True)
    return [r for r in runs if (r / "metrics.csv").exists()][:n]


def _load_ctx(run: Path) -> dict:
    m = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
    if "포함사유" in m:
        m["포함사유"] = m["포함사유"].fillna("")
    c = pd.read_csv(run / "comparison.csv", encoding="utf-8-sig")
    cat, meta = common.load_catalog("metrics_catalog")
    sch, _ = common.load_catalog("schema_catalog")
    ins, _ = common.load_catalog("insights_catalog")
    log = rl.load(run)
    ext = any(str(r.get("status")) == "구간확장" for _, r in m.iterrows())
    return {"파일명": rl.field(log, "파일명"), "판정테이블": rl.field(log, "테이블"),
            "기간": str(m["month"].iloc[0]), "행수": rl.field(log, "행수", 0),
            "metrics": m, "comparison": c,
            "validation": vd.validate_all(m, c, cat, override=ext),
            "metrics_catalog": cat, "schema_catalog": sch, "insights_catalog": ins,
            "카탈로그_메타": meta, "run_log": log, "run_dir": str(run)}


def _strip_volatile(text: str) -> list[str]:
    return [l for l in text.splitlines() if not VOLATILE.search(l)]


# ── 테스트 1 — 계산 재현성 ────────────────────────────────────────────
def test_calc_reproducible():
    """같은 파일을 두 번 계산하면 value가 완전히 일치한다.

    BigQuery를 두 번 친다. 연결이 안 되면 **저장된 두 실행을 비교**한다 —
    그것도 "두 번 실행한 결과"이고, 없으면 그때는 검사를 건너뛴다.
    """
    runs = _latest_runs(2)
    if len(runs) < 2:
        print("  실행 폴더가 2개 미만 — 건너뜀")
        return
    a, b = (pd.read_csv(r / "metrics.csv", encoding="utf-8-sig") for r in runs)
    key = ["metric_id", "value"]
    da = a[key].sort_values("metric_id").reset_index(drop=True)
    db = b[key].sort_values("metric_id").reset_index(drop=True)
    diff = [(r.metric_id, r.value, db.loc[i, "value"])
            for i, r in da.iterrows()
            if not (pd.isna(r.value) and pd.isna(db.loc[i, "value"]))
            and r.value != db.loc[i, "value"]]
    assert not diff, f"값이 다른 지표: {diff}\n  {runs[0].name} vs {runs[1].name}"
    print(f"  {runs[0].name} vs {runs[1].name} — 지표 {len(da)}종 value 일치")


# ── 테스트 2 — 리포트 재현성 ──────────────────────────────────────────
def test_report_reproducible():
    """같은 run_context로 두 번 생성하면 생성일시 줄 말고는 같다."""
    runs = _latest_runs(1)
    if not runs:
        print("  실행 폴더 없음 — 건너뜀")
        return
    ctx = _load_ctx(runs[0])
    a = rp.build_report({**ctx, "생성일시": "2026-01-01T00:00:00+09:00"})
    b = rp.build_report({**ctx, "생성일시": "2026-12-31T23:59:59+09:00"})
    la, lb = _strip_volatile(a), _strip_volatile(b)
    if la != lb:
        d = "\n".join(list(difflib.unified_diff(la, lb, "1회", "2회", lineterm=""))[:20])
        raise AssertionError(f"리포트가 다릅니다:\n{d}")
    print(f"  생성일시만 다르고 {len(la)}줄 동일")


# ── 테스트 3 — 현재 시각 의존성 ───────────────────────────────────────
def test_no_clock_in_calculation():
    """**계산 로직에 현재 시각이 있으면 실패.** 기록용은 어디 있는지만 알린다."""
    bad, noted = [], []
    for py in sorted((BASE / "pipeline").glob("*.py")):
        src = py.read_text(encoding="utf-8")
        lines = src.splitlines()
        for lineno, name in find_time_calls(src):
            where = f"{py.name}:{lineno}  {name}()  {lines[lineno - 1].strip()[:46]}"
            (bad if py.name in CALC_MODULES else noted).append(where)
    for n in noted:
        print(f"  (기록용) {n}")
    assert not bad, "계산 로직에 현재 시각이 있습니다:\n  " + "\n  ".join(bad)
    print(f"  계산 모듈 {len(CALC_MODULES)}개에 시각 사용 없음")


# ── 테스트 4 — 정렬 안정성 ────────────────────────────────────────────
def test_row_order_stable():
    """두 번 실행의 **행 순서**가 같은지. 다르면 정렬 기준이 없다는 뜻이다."""
    runs = _latest_runs(2)
    if len(runs) < 2:
        print("  실행 폴더가 2개 미만 — 건너뜀")
        return
    a, b = (pd.read_csv(r / "metrics.csv", encoding="utf-8-sig") for r in runs)
    assert list(a["metric_id"]) == list(b["metric_id"]), (
        f"행 순서가 다릅니다:\n  {list(a['metric_id'])}\n  {list(b['metric_id'])}")
    print(f"  {len(a)}행 순서 동일")


# ── pytest 없이도 돈다 ────────────────────────────────────────────────
def main() -> int:
    tests = [("계산 재현성", test_calc_reproducible),
             ("리포트 재현성", test_report_reproducible),
             ("현재 시각 의존성", test_no_clock_in_calculation),
             ("정렬 안정성", test_row_order_stable)]
    fails = 0
    for name, fn in tests:
        print(f"\n── {name} " + "─" * (44 - len(name)))
        try:
            fn()
            print("  ✅ 통과")
        except AssertionError as e:
            fails += 1
            print(f"  ❌ 실패 — {e}")
        except Exception as e:                          # noqa: BLE001
            fails += 1
            print(f"  ❌ 오류 — {type(e).__name__}: {e}")
    print(f"\n결과: 통과 {len(tests) - fails} / 실패 {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
