# -*- coding: utf-8 -*-
"""배포 전 의존성 검사 — `requirements.txt`만으로 앱이 import 되는가.

왜 필요한가
    로컬에는 온갖 패키지가 이미 깔려 있어 **빠진 의존성이 보이지 않는다.**
    배포본에서만 `ModuleNotFoundError`가 나고, 그것도 **한 번에 하나씩** 드러난다.
    (2026-08-22 실제: `plotly` 누락을 4단계 차트에서야 발견 — 그 전에 이미 두 번
     다른 이유로 배포본이 죽었다. 매번 고쳐 push 하고 다시 눌러 보는 왕복이었다.)

    ★ **한 번에 전부 잡는 방법은 배포 환경과 같은 조건을 만드는 것뿐이다.**
      깨끗한 venv에 `requirements.txt`만 설치하고 앱 전 모듈을 import 한다.
      여기서 통과하면 거기서도 통과한다.

무엇을 검사하나
    1. `pipeline/*.py` + `common` + `config` 전 모듈 import
    2. `app.py`의 최상위 import 이름 (streamlit 런타임이 필요해 실행은 못 하므로 AST로)

무엇을 검사하지 못하나
    - **함수 안에서 import 하는 패키지** — 실행 경로를 타야 드러난다
    - `to_dataframe()`처럼 **import 문 없이 요구되는 것**(`db-dtypes`)
    - 자격증명·네트워크가 필요한 동작
    검사기가 통과했다고 배포가 반드시 뜨는 것은 아니다. **import 실패만** 없앤다.

실행
    py -X utf8 dev_tools/deploy_preflight.py
    py -X utf8 dev_tools/deploy_preflight.py <venv경로>     # 재사용해 빠르게

종료 코드
    0 = 통과 · 1 = 누락 있음 (커밋 전 게이트로 쓸 수 있다)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

APP = Path(__file__).resolve().parent.parent          # 경로를 박지 않는다
VENV = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "deploy_venv"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    req = APP / "requirements.txt"
    if not req.exists():
        print(f"★ {req} 가 없습니다")
        return 1

    py = VENV / ("Scripts" if sys.platform == "win32" else "bin") / (
        "python.exe" if sys.platform == "win32" else "python")
    if not py.exists():
        print(f"■ venv 생성 — {VENV}")
        r = run([sys.executable, "-m", "venv", str(VENV)])
        if r.returncode:
            print(f"★ venv 실패: {r.stderr[-500:]}")
            return 1
    else:
        print(f"■ venv 재사용 — {VENV}")

    print(f"■ {req.name} 설치 (배포본과 같은 목록)")
    r = run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check",
             "-r", str(req)])
    if r.returncode:
        print(f"★ 설치 실패:\n{r.stdout[-600:]}\n{r.stderr[-600:]}")
        return 1
    print("  완료")

    mods = ["common", "config",
            *[f"pipeline.{p.stem}" for p in sorted((APP / "pipeline").glob("*.py"))
              if p.stem != "__init__"]]
    probe = (
        "import sys\n"
        f"sys.path.insert(0, r'{APP}')\n"
        f"mods = {mods!r}\n"
        "bad = []\n"
        "for m in mods:\n"
        "    try:\n"
        "        __import__(m)\n"
        "    except Exception as e:\n"
        "        bad.append((m, type(e).__name__, str(e)[:110]))\n"
        "for m, t, e in bad:\n"
        "    print(f'  X {m:<26} {t}: {e}')\n"
        "print(f'RESULT {len(mods) - len(bad)}/{len(mods)}')\n")
    print(f"\n■ 모듈 import ({len(mods)}종)")
    r = run([str(py), "-X", "utf8", "-c", probe])
    print(r.stdout.rstrip() or r.stderr[-600:])
    mods_ok = "RESULT" in r.stdout and (lambda a, b: a == b)(
        *r.stdout.split("RESULT ")[1].split("\n")[0].split("/"))

    # app.py 는 streamlit 런타임이 필요해 import 로 못 본다 → AST 로 최상위 import 만
    # ★ 앱 경로를 먼저 넣는다 — 로컬 모듈(common·config·pipeline)을 외부 패키지로
    #   오인해 '누락'이라 부르면, 검사기가 없는 결함을 만들어 진짜 결함을 묻는다.
    probe2 = (
        "import ast, sys, importlib.util\n"
        f"sys.path.insert(0, r'{APP}')\n"
        f"src = open(r'{APP / 'app.py'}', encoding='utf-8').read()\n"
        "names = set()\n"
        "for n in ast.walk(ast.parse(src)):\n"
        "    if isinstance(n, ast.Import):\n"
        "        names |= {a.name.split('.')[0] for a in n.names}\n"
        "    elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:\n"
        "        names.add(n.module.split('.')[0])\n"
        "miss = [m for m in sorted(names) if importlib.util.find_spec(m) is None]\n"
        "print(f'  app.py 최상위 import {len(names)}종 · 누락 {len(miss)}', miss or '')\n")
    r2 = run([str(py), "-X", "utf8", "-c", probe2])
    print(r2.stdout.rstrip() or r2.stderr[-500:])

    ok = mods_ok and "누락 0" in r2.stdout
    print(f"\n{'통과 — 배포본에서도 import 된다' if ok else '★ 실패 — 위 항목을 requirements.txt 에 추가'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
