# -*- coding: utf-8 -*-
"""게이트 3(발송 확정) 검증 — 되돌릴 수 없는 게이트 (Day4 실습 C).

앱을 띄우지 않고 체크리스트 구성·활성 조건·확정 산출물을 확인한다.
**확정 자체는 실행하지 않는다** — 실제 run 폴더에 APPROVED를 만들면 그 실행이
확정된 것으로 남는다. 여기서는 임시 폴더에 써 보고 지운다.

    py -X utf8 dev_tools/verify_gate3.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
from dev_tools.build_report_offline import load_ctx  # noqa: E402
from pipeline import run_log as rl  # noqa: E402
from pipeline import email_draft as ed  # noqa: E402

EXPECTED_KEYS = ["기간", "수신자", "경고", "미작성", "첨부"]
RECORD_KEYS = ["발송확정_시각", "확인한_체크항목", "제목", "수신자",
               "미작성_장_목록", "검증_경고수", "첨부_목록"]

ok = fail = 0


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok, fail
    ok, fail = ok + passed, fail + (not passed)
    print(f"  {'✅' if passed else '❌'} {label}{('  ' + detail) if detail else ''}")


def main() -> None:
    run = sorted((BASE / "outputs").glob("run_*"))[-1]
    ctx = load_ctx(run)
    ctx["run_dir"] = str(run)
    md = (run / "report.md")
    md = md.read_text(encoding="utf-8") if md.exists() else \
        (run / "report_offline.md").read_text(encoding="utf-8")

    mail = ed.build_email(ctx, md)
    v = ctx["validation"]
    todo = ed.unwritten(md)
    at = ed.attachments(run, only_existing=False)
    cl = common.build_send_checklist({**mail, "기간": ctx["기간"]}, v, todo, at)

    print(f"실행 폴더: {run.name}\n")
    print("── 체크리스트 (교안 5항목) ───────────────────────────────")
    for it in cl:
        print(f"  {'☐' if it['해당'] else '☑'} {it['라벨'][:58]}")
    check("항목 구성 일치", [i["키"] for i in cl] == EXPECTED_KEYS,
          " · ".join(i["키"] for i in cl))

    print("\n── 게이트 활성 조건 ──────────────────────────────────────")
    need = [i["키"] for i in cl if i["해당"]]
    check("전부 체크 → 활성", set(need) <= set(need), f"{len(need)}종")
    check("하나 해제 → 비활성", not set(need) <= set(need[1:]), f"'{need[0]}' 해제")

    print("\n── 미작성 장 처리 ────────────────────────────────────────")
    mi = next(i for i in cl if i["키"] == "미작성")
    if todo:
        check("차단하지 않는다(체크 항목으로만)", mi["해당"])
        check("문구가 강하다('비어 있는 상태로 발송')",
              "비어 있는 상태로 발송" in mi["라벨"])
        check("왜 차단 안 하는지 설명", "초안 공유가 목적" in mi["상세"])
        check("제목에 (초안)", "(초안)" in mail["subject"])
    else:
        check("미작성 없으면 자동 충족", not mi["해당"])

    print("\n── 확정 산출물 (임시 폴더에서) ───────────────────────────")
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copy(run / "run_log.json", tmp / "run_log.json")
        record = {
            "발송확정_시각": "2026-08-21T22:00:00+09:00",
            "확인한_체크항목": [i["라벨"] for i in cl if i["해당"]],
            "제목": mail["subject"], "수신자": mail["to"],
            "미작성_장_목록": [f"{s['번호']}장 {s['제목']}" for s in todo],
            "검증_경고수": v["경고수"],
            "첨부_목록": [a["filename"] for a in at if a["존재"]],
        }
        (tmp / "APPROVED").write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        (tmp / "email_final.html").write_text(mail["body_html"], encoding="utf-8")

        # 앱과 같은 경로로 기록한다 — `log.update()`로 평평하게 덮어쓰면
        # 실제 앱 동작과 달라져 검사가 통과해도 의미가 없다
        before = set(rl.load(tmp)) - {"_meta"}
        rl.record(tmp, "8_확정", **record)

        check("APPROVED 마커 생성", (tmp / "APPROVED").exists())
        check("email_final.html 고정본", (tmp / "email_final.html").exists(),
              f"{(tmp / 'email_final.html').stat().st_size:,}B")
        got = rl.load(tmp)
        missing = [k for k in RECORD_KEYS if k not in (got.get("8_확정") or {})]
        check("run_log 기록 7종", not missing, missing or "전부 있음")
        # ★ 8단계를 쓰면서 **앞 단계 기록이 사라지지 않는가.**
        #   사라지면 "언제 무엇을 승인했는지"가 없어진다.
        lost = before - set(got)
        check("이전 단계 기록 보존", not lost,
              f"{len(before)}개 유지" if not lost else f"사라짐: {lost}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n── 되돌리기 없음 ─────────────────────────────────────────")
    src = (BASE / "app.py").read_text(encoding="utf-8")
    i = src.index("8단계 — 발송 확정")
    j = src.index("나머지 단계는 게이트 2를", i)
    gate3 = src[i:j]
    check("확정 취소 버튼 없음", "확정 취소" not in gate3 and "되돌리기 버튼" not in gate3.replace(
        "되돌리기 버튼을 만들지 않는다", ""))
    check("'새 실행 시작' 버튼 있음", "새 실행 시작" in gate3)
    check("차단 시 확정 버튼 미생성", 'if v["차단수"]' in gate3 and "continue" in gate3)

    print(f"\n결과: 통과 {ok} / 실패 {fail}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
