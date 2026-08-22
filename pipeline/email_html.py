# -*- coding: utf-8 -*-
"""이메일 HTML 본문 — 20년 전 웹처럼 (6주차 Day4 실습 B, 프롬프트 4).

★ 이메일 클라이언트는 브라우저가 아니다 (개념 3절)
    | 항목            | 웹  | 이메일                              |
    |-----------------|-----|-------------------------------------|
    | `<style>` 태그  | 됨  | **지우는 클라이언트가 있다**        |
    | 인라인 `style=` | 됨  | **됨 → 이걸 쓴다**                  |
    | Flexbox·Grid    | 됨  | **안 됨 → `<table>`로 레이아웃**    |
    | 외부 이미지     | 됨  | **기본 설정에서 차단**              |
    | 웹폰트          | 됨  | 대체로 안 됨 → 시스템 폰트 목록     |
    | JavaScript      | 됨  | **전부 차단**                       |

    브라우저에서 멀쩡히 보인다고 메일에서도 되는 게 아니다. **미리보기가 통과 기준이 아니다.**

★ 색은 화면과 같은 것을 쓴다
    `common.STATUS`에서 가져온다. 화면에서 경고인 항목이 메일에서 정상으로 보이면
    같은 실행 결과가 두 얼굴을 갖는다(DESIGN.md: 화면과 문서의 시각 언어 일치).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402

# 이메일 표준 폭. 이보다 넓으면 모바일 클라이언트에서 가로 스크롤이 생긴다.
WIDTH = 600
# 웹폰트를 못 쓰므로 **설치돼 있을 법한 폰트를 나열**한다. 없으면 마지막 sans-serif로 떨어진다.
FONT = "'Malgun Gothic','맑은 고딕',Dotum,sans-serif"

INK = "#0f172a"
MUTED = "#64748b"
LINE = "#e2e8f0"
HEAD_BG = "#f1f5f9"


def _esc(s) -> str:
    return (common.blank_safe(s).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _color(kind: str) -> str:
    """상태 → 색. 화면과 같은 표(`common.STATUS`)를 본다."""
    return common.STATUS.get(kind, common.STATUS["정보"])[0]


def _badge(text: str, kind: str) -> str:
    c = _color(kind)
    return (f'<span style="display:inline-block;background:{c}1f;color:{c};'
            f'border:1px solid {c}55;border-radius:4px;padding:2px 8px;'
            f'font-size:12px;font-weight:bold">{_esc(text)}</span>')


def _section(title: str, inner: str) -> str:
    return (f'<tr><td style="padding:18px 24px 0 24px">'
            f'<div style="font-size:13px;font-weight:bold;color:{INK};'
            f'padding-bottom:6px">{_esc(title)}</div>{inner}</td></tr>')


def _list(items: list[str], color: str = MUTED) -> str:
    if not items:
        return f'<div style="font-size:13px;color:{MUTED}">해당 없음</div>'
    lis = "".join(f'<li style="margin:3px 0">{_esc(s)}</li>' for s in items)
    return (f'<ul style="margin:0;padding-left:18px;font-size:13px;'
            f'color:{color};line-height:1.6">{lis}</ul>')


def _metrics_table(rows: list[dict]) -> str:
    """핵심 지표 표 — **레이아웃이 아니라 진짜 표**다. 테두리를 셀마다 인라인으로 준다.

    `border-collapse`만으로는 일부 클라이언트에서 테두리가 사라져
    `cellspacing="0"`와 셀별 `border-bottom`을 함께 쓴다.
    """
    head = "".join(
        f'<th style="text-align:{a};padding:7px 10px;font-size:12px;color:{MUTED};'
        f'background:{HEAD_BG};border-bottom:1px solid {LINE}">{h}</th>'
        for h, a in (("지표", "left"), ("당월", "right"),
                     ("전월", "right"), ("변화", "right")))
    body = ""
    for r in rows:
        body += (
            f'<tr>'
            f'<td style="padding:7px 10px;font-size:13px;color:{INK};'
            f'border-bottom:1px solid {LINE}">{_esc(r["지표명"])}</td>'
            f'<td align="right" style="padding:7px 10px;font-size:13px;color:{INK};'
            f'font-weight:bold;border-bottom:1px solid {LINE}">{_esc(r["당월"])}</td>'
            f'<td align="right" style="padding:7px 10px;font-size:13px;color:{MUTED};'
            f'border-bottom:1px solid {LINE}">{_esc(r["전월"])}</td>'
            f'<td align="right" style="padding:7px 10px;font-size:13px;color:{INK};'
            f'border-bottom:1px solid {LINE}">{_esc(r["변화"])}</td></tr>')
    return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;border:1px solid {LINE}">'
            f'<tr>{head}</tr>{body}</table>')


def render(ctx: dict, report_md: str) -> str:
    """이메일 HTML 본문 한 벌."""
    from pipeline import email_draft as ed          # 재료는 초안 모듈이 만든다

    v = ctx.get("validation") or {}
    meta = ctx.get("카탈로그_메타") or {}
    period = common.blank_safe(ctx.get("기간"))
    todo = ed.unwritten(report_md)
    blocked, warned = v.get("차단수", 0), v.get("경고수", 0)
    kind = "차단" if blocked else ("경고" if warned else "통과")

    rows = [_section("핵심 지표", _metrics_table(ed.key_metrics(ctx)))]

    flags = ed.flagged(ctx)
    rows.append(_section("전월 대비 변동이 큰 지표",
                         _list(flags or ["임계값을 넘는 변동이 있는 지표가 없다."],
                               _color("경고") if flags else MUTED)))

    lim = ed.limit_titles(report_md)
    if lim:
        rows.append(_section(
            "한계",
            _list(lim) + f'<div style="font-size:12px;color:{MUTED};margin-top:6px">'
                         f'자세한 내용은 첨부 리포트 7장을 보세요.</div>'))

    if todo:
        rows.append(_section(
            "미작성",
            _list([f"{s['번호']}장 {s['제목']}" for s in todo], _color("경고"))
            + f'<div style="font-size:12px;color:{MUTED};margin-top:6px">'
              f'이 장들은 사람이 작성합니다. 제목에 (초안)이 표시됩니다.</div>'))

    at = ed.attachments(ctx.get("run_dir", "."))
    rows.append(_section(
        "첨부",
        _list([f"{a['filename']} ({a['size'] / 1024:,.0f} KB)" for a in at])))

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:{FONT}">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#f8fafc;padding:20px 0">
<tr><td align="center">
<table width="{WIDTH}" cellpadding="0" cellspacing="0" border="0"
       style="width:{WIDTH}px;max-width:100%;background:#ffffff;
              border:1px solid {LINE};border-radius:8px">

  <tr><td style="background:{HEAD_BG};padding:18px 24px;border-radius:8px 8px 0 0">
    <div style="font-size:17px;font-weight:bold;color:{INK}">
      월간 지표 리포트 &mdash; {_esc(period)}</div>
    <div style="font-size:12px;color:{MUTED};padding-top:4px">
      생성일시 {_esc(ctx.get('생성일시', '—'))}</div>
  </td></tr>

  <tr><td style="padding:16px 24px 0 24px">
    {_badge(f'검증 {v.get("전체판정", "—")}', kind)}
    <span style="font-size:12px;color:{MUTED};padding-left:8px">
      차단 {blocked}건 &middot; 경고 {warned}건</span>
  </td></tr>

  {''.join(rows)}

  <tr><td style="padding:20px 24px 22px 24px">
    <div style="border-top:1px solid {LINE};padding-top:12px;
                font-size:11px;color:{MUTED};line-height:1.6">
      생성 도구 auto-report &middot; 카탈로그 {_esc(meta.get('생성일시', '?'))}<br>
      이 메일은 자동 생성된 초안입니다. 발송 전 사람이 확인합니다.
      <b>이 앱은 실제로 메일을 보내지 않습니다.</b>
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""
