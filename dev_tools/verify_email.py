# -*- coding: utf-8 -*-
"""이메일 초안 검증 — 클라이언트 제약을 **기계적으로** 확인한다 (Day4 실습 B).

왜 눈으로 보면 안 되는가
    브라우저 미리보기는 `<style>` 태그도, flexbox도 멀쩡히 그린다. **메일에서만 깨진다.**
    "미리보기에서 잘 보였다"는 통과 기준이 아니다 — 금지 요소가 들어갔는지는 코드로 본다.

    py -X utf8 dev_tools/verify_email.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import config  # noqa: E402
from dev_tools.build_report_offline import load_ctx  # noqa: E402
from pipeline import email_draft as ed  # noqa: E402
from pipeline import phrasing as ph  # noqa: E402

# 개념 3절 — 이메일에서 안 되는 것들
BANNED_HTML = {
    "<style> 태그": r"<style[\s>]",
    "flexbox·grid": r"display\s*:\s*(flex|grid)",
    "외부 이미지": r"<img[\s>]|url\(\s*['\"]?https?:",
    "웹폰트": r"@font-face|fonts\.googleapis",
    "JavaScript": r"<script[\s>]|on(click|load|error)\s*=",
}

ok = fail = 0


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok, fail
    ok, fail = ok + passed, fail + (not passed)
    print(f"  {'✅' if passed else '❌'} {label}{('  ' + detail) if detail else ''}")


def main() -> None:
    runs = sorted((BASE / "outputs").glob("run_*"))
    if not runs:
        sys.exit("outputs/run_* 가 없습니다.")
    run = runs[-1]
    ctx = load_ctx(run)
    ctx["run_dir"] = str(run)
    md_path = run / "report.md"
    if not md_path.exists():
        md_path = run / "report_offline.md"
    md = md_path.read_text(encoding="utf-8")

    e = ed.build_email(ctx, md)
    html = e["body_html"]

    print(f"실행 폴더: {run.name} · 리포트 {md_path.name}\n")
    print("── 메일 헤더 ─────────────────────────────────────────────")
    print(f"  제목  {e['subject']}")
    print(f"  수신  {', '.join(e['to'])}")
    print(f"  발신  {e['from']}")

    print("\n── 제목 규칙 ─────────────────────────────────────────────")
    v = ctx["validation"]
    check("경고 있으면 (확인 필요)",
          bool(v["경고수"]) == ("(확인 필요)" in e["subject"]),
          f"경고 {v['경고수']}건")
    todo = ed.unwritten(md)
    check("미작성 있으면 (초안)",
          bool(todo) == ("(초안)" in e["subject"]),
          f"미작성 {len(todo)}장")

    print("\n── HTML 클라이언트 제약 ──────────────────────────────────")
    for label, pat in BANNED_HTML.items():
        hit = re.search(pat, html, re.I)
        check(f"{label} 없음", not hit, f"← {hit.group(0)!r}" if hit else "")
    check("인라인 style= 사용", html.count("style=") >= 10,
          f"{html.count('style=')}곳")
    check("표 레이아웃(<table>)", html.count("<table") >= 2,
          f"{html.count('<table')}개")
    check(f"최대 폭 {config_width()}px 명시", f"width:{config_width()}px" in html)

    print("\n── 화면과 같은 색을 쓰는가 ───────────────────────────────")
    import common
    for kind, (color, _) in common.STATUS.items():
        if color.lower() in html.lower():
            print(f"  · {kind:<4} {color} 사용됨")
    used = [c for c, _ in common.STATUS.values() if c.lower() in html.lower()]
    check("STATUS 색만 상태 표시에 사용", bool(used), f"{len(used)}종")

    print("\n── 본문 내용 ─────────────────────────────────────────────")
    km = ed.key_metrics(ctx)
    check("핵심 지표 4~6개", 4 <= len(km) <= 6, f"{len(km)}개")
    check("표에 당월·전월·변화 모두", all(k["당월"] and k["전월"] and k["변화"] for k in km))
    check("한계는 소절 제목만(본문 미포함)",
          all(len(t) < 40 for t in ed.limit_titles(md)),
          f"{len(ed.limit_titles(md))}개")
    check("리포트 전문 미포함", len(html) < len(md), f"HTML {len(html):,} < 리포트 {len(md):,}")
    check("금지 표현 0건(텍스트)", not ph.check_forbidden(e["body_text"]))
    check("첨부 목록 있음", bool(e["attachments"]),
          ", ".join(a["filename"] for a in e["attachments"]))
    check("실제 발송 코드 없음",
          not re.search(r"smtplib|SMTP\(|sendmail", (BASE / "pipeline" / "email_draft.py")
                        .read_text(encoding="utf-8") + html))

    # 미리보기 파일 — 브라우저로 열어 눈으로도 본다(기계 검사와 별개)
    out = run / "email_preview.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n미리보기: {out}")
    print(f"결과: 통과 {ok} / 실패 {fail}")
    sys.exit(1 if fail else 0)


def config_width() -> int:
    from pipeline import email_html
    return email_html.WIDTH


if __name__ == "__main__":
    main()
