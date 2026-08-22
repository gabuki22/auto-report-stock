# -*- coding: utf-8 -*-
"""이메일 초안 — 앱 7단계 (6주차 Day4 실습 B).

**실제로 보내지 않는다.** SMTP 코드를 쓰지 않고, 8단계가 하는 일은
"발송 준비된 최종본을 확정하는 것"이다. 8주차에 이 자리에 SMTP를 꽂으면 완성된다.

★ 확정된 최종본이 **실제로 보낼 수 있는 형태**여야 한다
    "나중에 형식을 맞추면 되지"라고 두면 8주차에 다시 만들게 된다.

★ 본문에 담지 않는 것
    · 리포트 전문 — 첨부로 보낸다. 메일에 다 넣으면 아무도 안 읽는다
    · 차트 이미지 — 이메일에서 외부 이미지는 **기본 설정에서 차단**되고,
      kaleido도 불안정하다(DESIGN.md). 애초에 이미지 없는 설계가 맞다
    · 해석·제안 문장 — 리포트 5·6장에 있고 **미작성일 수 있다.**
      비어 있는 장을 메일이 대신 채우면 앱이 판단을 쓴 것이 된다

★ 제목에 상태를 드러낸다
    경고가 있으면 `(확인 필요)`, 미작성 장이 있으면 `(초안)`.
    받는 사람이 **열기 전에** 이 문서의 상태를 알아야 한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import phrasing as ph  # noqa: E402
from pipeline import report as rp  # noqa: E402


def subject(ctx: dict, report_md: str) -> str:
    """`[월간 리포트] CS 지표 리포트 2025-01 (확인 필요) (초안)`"""
    v = ctx.get("validation") or {}
    parts = [config.EMAIL_SUBJECT_PREFIX,
             f"{getattr(config, 'REPORT_SUBJECT', '지표 리포트')} {ctx.get('기간', '')}"]
    if v.get("경고수"):
        parts.append("(확인 필요)")
    if unwritten(report_md):
        parts.append("(초안)")
    return " ".join(p for p in parts if p).strip()


def unwritten(report_md: str) -> list[dict]:
    """아직 사람이 안 쓴 장. **장 번호가 아니라 자리표시자 존재로** 판정한다."""
    return [s for s in rp.split_sections(report_md) if s["미작성"]]


def key_metrics(ctx: dict) -> list[dict]:
    """본문에 실을 핵심 지표 — 화면 카드와 **같은 목록**을 쓴다.

    메일에는 있는 지표가 화면에 없으면 받는 사람이 확인하러 들어가서 못 찾는다.
    계산되지 않은 지표는 빼지 않고 "값 없음"으로 싣는다 — 빼면 그 지표를
    **안 본 것인지 없는 것인지** 구분되지 않는다.
    """
    m: pd.DataFrame = ctx["metrics"]
    comp = ctx.get("comparison")
    cmap = {r["metric_id"]: r for _, r in comp.iterrows()} if comp is not None and len(comp) else {}
    mmap = {r["metric_id"]: r for _, r in m.iterrows()}

    out = []
    for mid in common.CARD_METRICS:
        row = mmap.get(mid)
        if row is None:
            continue
        c = cmap.get(mid)
        base = row.to_dict()
        out.append({
            "metric_id": mid,
            "지표명": row["지표명"],
            "당월": ph.fmt_value(row.get("value"), base.get("유형", ""), row["지표명"], mid,
                                base.get("단위", "")),
            "전월": ph.fmt_value(c.get("전월") if c is not None else None,
                                base.get("유형", ""), row["지표명"], mid, base.get("단위", "")),
            "변화": ph.fmt_change({**base, **(c.to_dict() if c is not None else {})}),
        })
    return out


def flagged(ctx: dict) -> list[str]:
    """전월 대비 임계값을 넘은 지표 — 리포트와 **같은 함수**로 문장을 만든다."""
    return rp._flag_sentences(ctx)


def limit_titles(report_md: str) -> list[str]:
    """리포트 7장의 **소절 제목만.** 본문은 첨부에서 읽는다.

    한계를 통째로 옮기면 메일이 리포트가 되고, 빼면 한계가 없는 것처럼 보인다.
    제목만 싣고 "자세한 내용은 첨부"로 잇는 것이 그 사이다.
    """
    return [re.sub(r"^###\s*7-\d+\.\s*", "", l).strip()
            for l in report_md.splitlines() if l.startswith("### 7-")]


def attachments(run_dir, only_existing: bool = True) -> list[dict]:
    """첨부 **목록만** 만든다. 실제 첨부는 8주차.

    ★ 두 쓰임이 다르다.
      · 메일에 실을 목록(`only_existing=True`) — 없는 파일을 적으면 **첨부한 줄 알게 된다.**
      · 화면에 보일 목록(`False`) — 없는 파일도 보여야 **왜 빠졌는지** 알 수 있다.
        (PDF를 안 만들었으면 그 자리에 "없음"이 떠야 한다)
    """
    d = Path(run_dir)
    out = []
    for name in config.EMAIL_ATTACHMENTS:
        p = d / name
        exists = p.exists()
        if exists or not only_existing:
            out.append({"filename": name, "path": str(p), "존재": exists,
                        "size": p.stat().st_size if exists else 0})
    return out


def body_text(ctx: dict, report_md: str) -> str:
    """HTML을 지원하지 않는 클라이언트용 본문. **같은 재료로 같은 순서.**"""
    v = ctx.get("validation") or {}
    todo = unwritten(report_md)
    L = [f"{ctx.get('기간', '')} 월간 지표 리포트",
         f"생성일시 {ctx.get('생성일시', '—')}", ""]

    L += ["[핵심 지표]"]
    for k in key_metrics(ctx):
        L.append(f"  - {k['지표명']}: {k['당월']} (전월 {k['전월']} · {k['변화']})")

    fl = flagged(ctx)
    L += ["", "[전월 대비 변동이 큰 지표]"]
    L += [f"  - {s}" for s in fl] or ["  - 임계값을 넘는 변동이 있는 지표가 없다."]

    L += ["", f"[검증] 차단 {v.get('차단수', 0)}건, 경고 {v.get('경고수', 0)}건"
              f" (전체 판정 {v.get('전체판정', '—')})"]

    lim = limit_titles(report_md)
    if lim:
        L += ["", "[한계] " + " · ".join(lim), "  자세한 내용은 첨부 리포트 7장을 보세요."]

    if todo:
        L += ["", f"[미작성] {len(todo)}개 장 — "
                  + " · ".join(f"{s['번호']}장 {s['제목']}" for s in todo)]

    at = attachments(ctx.get("run_dir", "."))
    L += ["", "[첨부]"] + [f"  - {a['filename']} ({a['size'] / 1024:,.0f} KB)" for a in at]

    meta = ctx.get("카탈로그_메타") or {}
    L += ["", f"생성 도구 auto-report · 카탈로그 {meta.get('생성일시', '?')}",
          "이 메일은 자동 생성된 초안입니다. 발송 전 사람이 확인합니다."]
    return "\n".join(L)


def _html_placeholder(text: str) -> str:
    """텍스트 본문을 그대로 감싼 최소 HTML.

    ⚠️ 임시다. 이메일 클라이언트 제약(인라인 스타일·표 레이아웃·이미지 없음)을 적용한
    본문은 **다음 단계(`email_html.py`)**에서 만든다. 여기서 대충 꾸며두면
    그 스타일이 어디까지 먹는지 확인하지 않은 채 남는다.
    """
    esc = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<div style="font-family:\'Malgun Gothic\',sans-serif;font-size:14px">'
            f'<pre style="white-space:pre-wrap;margin:0">{esc}</pre></div>')


def build_email(run_context: dict, report_md: str) -> dict:
    """발송 준비된 초안 한 벌. **여기서 메일을 보내지 않는다.**"""
    text = body_text(run_context, report_md)
    try:
        from pipeline import email_html      # 프롬프트 4에서 HTML을 맡는다
        html = email_html.render(run_context, report_md)
    except ImportError:
        html = _html_placeholder(text)

    to = config.EMAIL_TO if isinstance(config.EMAIL_TO, list) else [config.EMAIL_TO]
    return {
        "subject": subject(run_context, report_md),
        "to": list(to),
        "from": config.EMAIL_FROM,
        "body_html": html,
        "body_text": text,
        "attachments": attachments(run_context.get("run_dir", ".")),
    }
