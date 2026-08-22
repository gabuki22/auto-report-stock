# -*- coding: utf-8 -*-
"""기존 실행 불러오기 검증 — CLI 결과를 화면에서 이어받기 (Day4 프롬프트 9).

무엇을 확인하는가
    ★ **파일이 있다고 승인이 있었던 것은 아니다.** CLI로 만든 실행은 6·7단계 산출물이
      다 있지만 게이트 2를 통과하지 않았다. 불러왔을 때 그 사실이 유지되는지 본다.
      여기가 무너지면 CLI가 게이트를 우회한 것과 같아진다.

    py -X utf8 dev_tools/verify_restore.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from pipeline import run_log as rl  # noqa: E402

ok = fail = 0


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok, fail
    ok, fail = ok + passed, fail + (not passed)
    print(f"  {'✅' if passed else '❌'} {label}{('  ' + detail) if detail else ''}")


def expected_step(run: Path) -> int:
    """app.restore_run과 **같은 규칙**으로 복원 단계를 계산한다.

    앱 코드를 import하면 Streamlit 런타임이 필요해 여기서 규칙만 재현한다.
    규칙이 갈라지지 않게 app.py의 해당 블록을 함께 대조한다(아래 소스 확인).
    """
    log = rl.load(run)
    confirmed = rl.field(log, "확인_완료_시각")
    has_mail = (run / "email_meta.json").exists() and (run / "report.md").exists()
    if (run / "APPROVED").exists():
        return 8
    if not confirmed:
        return 5
    return 8 if has_mail else 6


def main() -> None:
    runs = sorted((BASE / "outputs").glob("run_*"), reverse=True)
    if not runs:
        sys.exit("outputs/run_* 가 없습니다.")

    print("── 실행 폴더별 복원 단계 ─────────────────────────────────")
    print(f"  {'폴더':<22}{'승인경로':<8}{'게이트2':<10}{'APPROVED':<10}복원")
    cli_run = None
    for r in runs[:8]:
        log = rl.load(r)
        route = rl.field(log, "승인경로") or "화면"
        g2 = "통과" if rl.field(log, "확인_완료_시각") else "미통과"
        ap = "있음" if (r / "APPROVED").exists() else "—"
        step = expected_step(r)
        print(f"  {r.name:<22}{route:<8}{g2:<10}{ap:<10}{step}단계")
        if route == "CLI" and cli_run is None:
            cli_run = r

    print("\n── CLI 실행을 불러왔을 때 ────────────────────────────────")
    if cli_run is None:
        check("CLI 실행 존재", False, "run_pipeline.py 를 먼저 돌리세요")
    else:
        log = rl.load(cli_run)
        check("6·7단계 산출물 있음",
              all((cli_run / f).exists() for f in ("report.md", "email.html", "email_meta.json")))
        check("게이트 2는 미통과로 남는다", not rl.field(log, "확인_완료_시각"))
        check("복원 단계 = 5 (사람 확인부터)", expected_step(cli_run) == 5,
              f"{expected_step(cli_run)}단계")
        check("APPROVED 없음", not (cli_run / "APPROVED").exists())
        check("승인경로 CLI 기록", rl.field(log, "승인경로") == "CLI")

    print("\n── 화면에서 확정한 실행 ──────────────────────────────────")
    done = [r for r in runs if (r / "APPROVED").exists()]
    if not done:
        print("  (아직 확정된 실행이 없습니다 — 8단계를 통과하면 여기에 나옵니다)")
    else:
        r = done[0]
        check("복원 단계 = 8 (완료)", expected_step(r) == 8, r.name)
        rec = json.loads((r / "APPROVED").read_text(encoding="utf-8"))
        check("확정 기록 읽힘", "발송확정_시각" in rec, rec.get("제목", "")[:40])

    print("\n── 앱 코드 대조 ──────────────────────────────────────────")
    src = (BASE / "app.py").read_text(encoding="utf-8")
    check("restore_run 존재", "def restore_run" in src)
    check("게이트2를 기록에서 읽는다", 'rl.field(log, "확인_완료_시각")' in src)
    check("APPROVED면 8단계", '(run_dir / "APPROVED").exists()' in src)
    check("미확인이면 5단계", "elif not ss.confirmed_at:" in src)
    check("업로더 키 리셋", "uploader_key" in src and 'key=f"uploader_' in src)

    print(f"\n결과: 통과 {ok} / 실패 {fail}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
