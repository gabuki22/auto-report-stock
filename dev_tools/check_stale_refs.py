# -*- coding: utf-8 -*-
"""app.py 가 **하위 모듈의 새 이름**을 부르지 않는지 검사한다.

왜 필요한가
    Streamlit Cloud 는 `app.py` 를 매번 다시 읽지만, 이미 import 된 하위 모듈
    (`pipeline.*`·`common`·`config`)은 **옛 버전을 붙들고** 있을 수 있다.
    그 상태에서 app.py 가 새로 추가한 이름을 부르면 화면이 통째로 죽는다.

        AttributeError: module 'pipeline.report' has no attribute 'unwritten'

    같은 함정에 **두 번** 빠졌다 — `vd.MOM_CHECK`, `rp.unwritten`.
    로컬은 매번 재시작되므로 이 어긋남이 절대 보이지 않는다.

무엇을 하나
    app.py 가 `<별칭>.<이름>` 으로 부르는 **모듈 속성**을 모으고,
    그 이름이 **배포본이 돌고 있는 코드(`origin/main`)에도 있었는지** 본다.
    없으면 = 이번 push 로 새로 들어가는 이름 = 배포본이 죽을 수 있는 자리.

    ★ 기준을 `HEAD` 로 잡으면 안 된다. 방금 커밋했으면 이미 HEAD 에 있으므로
      **심어 둔 결함도 통과한다**(실제로 통과시켰다). 배포본이 보는 것은 `origin/main` 이다.

무엇을 검사하지 않나
    · 함수 호출의 인자·반환 모양이 바뀐 경우. 이름이 같으면 통과한다.
    · ★ **한 번보다 오래된 staleness.** 배포 프로세스가 세 번 전 커밋에서 떠 있으면
      `origin/main` 기준으로는 "이미 있는 이름"이라 놓친다.
      그 경우의 답은 코드가 아니라 **Manage app → Reboot** 다.

어떻게 고치나
    ① app.py 안에서 직접 계산하거나(가장 안전 — app.py 는 늘 새것이다)
    ② `getattr(mod, "새이름", 기본값)` 으로 물러설 자리를 두거나
    ③ 배포 후 **Manage app → Reboot** 로 프로세스를 새로 띄운다.

실행
    py -X utf8 dev_tools/check_stale_refs.py
종료 코드  0 = 안전 · 1 = 새 이름 참조 발견 · 2 = 검사 불가(git 아님)
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent
APP = BASE / "app.py"


def _alias_map(tree: ast.AST) -> dict[str, str]:
    """`from pipeline import report as rp` → {"rp": "pipeline/report.py"}"""
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                mod = f"{n.module}.{a.name}".replace(".", "/") + ".py"
                out[a.asname or a.name] = mod
        elif isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name.split(".")[0]] = a.name.replace(".", "/") + ".py"
    return out


def _git_prefix() -> str:
    """저장소 루트에서 이 폴더까지의 경로.

    ★ `git show HEAD:<경로>` 는 **저장소 루트 기준**이다. 폴더 기준 경로를 그대로
      넘기면 전부 "그런 파일 없음"이 되어 **모든 모듈이 새 파일로** 보인다
      (실측: 볼트 안에 있어 접두사가 `raw/학습/auto-report-재고/` 였다).
      검사기가 없는 결함을 만들면 진짜 결함이 묻힌다.
    """
    r = subprocess.run(["git", "rev-parse", "--show-prefix"], cwd=BASE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


_PREFIX = _git_prefix()

# ★ 배포본이 돌고 있는 코드가 기준이다 — 내 작업 트리도, 방금 만든 커밋도 아니다.
_BASELINE = "origin/main"


def _head_source(rel: str) -> str | None:
    """직전 커밋의 파일 내용. 새 파일이면 None."""
    for ref in (_BASELINE, "HEAD"):          # 원격이 없으면 HEAD 로 물러선다
        r = subprocess.run(["git", "show", f"{ref}:{_PREFIX}{rel}"], cwd=BASE,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return r.stdout
    return None


def _top_names(src: str) -> set[str]:
    """모듈 최상위에 정의된 이름(함수·클래스·상수)."""
    out: set[str] = set()
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
    return out


def main() -> int:
    if not (BASE / ".git").exists() and subprocess.run(
            ["git", "rev-parse"], cwd=BASE, capture_output=True).returncode:
        print("★ git 저장소가 아니라 직전 커밋과 비교할 수 없습니다.")
        return 2

    tree = ast.parse(APP.read_text(encoding="utf-8"))
    alias = _alias_map(tree)

    # app.py 가 부르는 <별칭>.<이름> 전부
    used: dict[str, set[str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            if n.value.id in alias:
                used.setdefault(n.value.id, set()).add(n.attr)

    hits = []
    for al, attrs in sorted(used.items()):
        rel = alias[al]
        if not (BASE / rel).exists():          # 외부 패키지는 대상 아님
            continue
        old = _head_source(rel)
        if old is None:
            hits += [(al, rel, a, "모듈 자체가 새 파일") for a in sorted(attrs)]
            continue
        try:
            old_names = _top_names(old)
        except SyntaxError:
            continue
        hits += [(al, rel, a, "직전 커밋에 없던 이름")
                 for a in sorted(attrs) if a not in old_names]

    print(f"■ app.py 가 참조하는 하위 모듈 {len(used)}개")
    for al, rel, attr, why in hits:
        print(f"  X {al}.{attr}  ({rel}) — {why}")
    if hits:
        print("\n★ 배포본이 옛 모듈을 붙들면 AttributeError 로 화면이 죽습니다.")
        print("  app.py 안에서 계산하거나, getattr(mod, 이름, 기본값) 으로 물러설 자리를 두세요.")
    else:
        print("\n안전 — 새로 만든 이름을 app.py 가 직접 부르지 않습니다.")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
