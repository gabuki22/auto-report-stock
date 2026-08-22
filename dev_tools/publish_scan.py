# -*- coding: utf-8 -*-
"""공개 전 민감정보 스캔 — **저장소에 나가면 안 되는 것이 남았는가.**

왜 필요한가
    이 저장소는 공개된다. 2026-08-22 실측: 위키 스키마 노트에서는 외주처 이름을
    일반화해 두고 *"배포본 스캔 0건"*이라고 적었는데, 실제로는
    **카탈로그 JSON 6곳과 CSV 컬럼명 4개**에 그대로 남아 있었다.

    ★ 눈으로 훑은 스캔은 훑은 곳만 본다.
      사람이 "확인했다"고 적는 것과 검사기가 **전 추적 파일을 도는 것**은 다르다.

무엇을 보나
    금지어(거래처·인물·사내 시스템)와 개인 PC 경로·서버 UNC 경로.

★ 금지어 목록은 **저장소에 넣지 않는다.**
    거래처·인물 이름을 파일로 커밋하면 **그 목록 자체가 공개**된다.
    (이 파일도 예외가 아니다 — 여기에 예시로 적었다가 검사기에 잡혔다.)
    목록은 `.publish_deny.txt`(gitignore 대상)에 한 줄 하나씩 둔다.
    파일이 없으면 경로 검사만 하고, **목록이 없다는 사실을 밝힌다** —
    조용히 통과시키면 "검사했다"가 거짓이 된다.

실행
    py -X utf8 dev_tools/publish_scan.py          # 추적 파일 전체
    py -X utf8 dev_tools/publish_scan.py --staged # git add 된 것만

종료 코드
    0 = 깨끗 · 1 = 발견 · 2 = 검사 불가(git 아님 등)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent
DENY_FILE = BASE / ".publish_deny.txt"

# 목록이 없어도 항상 보는 것 — 이건 어느 저장소에나 해당하므로 코드에 둔다
ALWAYS = [
    ("개인 PC 경로", re.compile(r"[A-Za-z]:[/\\]Users[/\\]")),
    ("서버 UNC 경로", re.compile(r"\\\\[A-Za-z0-9._-]+\\")),
    ("개인키", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
]
# 텍스트로 열지 않을 것
SKIP_SUFFIX = {".ttf", ".otf", ".woff", ".woff2", ".pdf", ".png", ".jpg",
               ".jpeg", ".gif", ".ico", ".zip", ".xlsx", ".xls"}


def _tracked(staged: bool) -> list[Path]:
    cmd = (["git", "diff", "--cached", "--name-only"] if staged
           else ["git", "ls-files"])
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(2)
    return [BASE / n for n in r.stdout.splitlines() if n.strip()]


def _deny_terms() -> tuple[list[str], bool]:
    if not DENY_FILE.exists():
        return [], False
    terms = [ln.strip() for ln in DENY_FILE.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    return terms, True


def main() -> int:
    staged = "--staged" in sys.argv
    files = [p for p in _tracked(staged)
             if p.is_file() and p.suffix.lower() not in SKIP_SUFFIX]
    terms, have_list = _deny_terms()

    print(f"■ 대상 {len(files)}개 파일 ({'스테이징' if staged else '추적 전체'})")
    if have_list:
        print(f"  금지어 {len(terms)}개 (.publish_deny.txt · 저장소에 없음)")
    else:
        # ★ 없다는 사실을 밝힌다. 조용히 넘어가면 "검사했다"가 거짓이 된다.
        print("  ⚠ 금지어 목록 없음 — 경로 검사만 수행합니다.")
        print(f"    거래처·인물명까지 보려면 {DENY_FILE.name} 을 만드세요(한 줄 하나).")

    hits = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for label, pat in ALWAYS:
                if pat.search(line):
                    hits.append((p, i, label, line.strip()[:70]))
            for t in terms:
                if t in line:
                    hits.append((p, i, f"금지어 '{t}'", line.strip()[:70]))

    for p, i, label, line in hits[:40]:
        print(f"  X {p.relative_to(BASE)}:{i}  [{label}]  {line}")
    if len(hits) > 40:
        print(f"  … 외 {len(hits) - 40}건")

    print(f"\n{'깨끗 — 공개해도 되는 상태' if not hits else f'★ {len(hits)}건 발견 — 공개 전에 지우세요'}")
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
