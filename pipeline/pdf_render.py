# -*- coding: utf-8 -*-
"""마크다운 리포트 → PDF (6주차 Day3 실습 E, 프롬프트 12).

`report.py`가 **무엇을 쓸지**를 정하고, 이 모듈은 **어떻게 보일지**만 맡는다.
둘을 한 파일에 두면 문장 규칙을 고칠 때 레이아웃이 딸려 오고 그 반대도 마찬가지다.

★ fpdf2는 **상태 저장형**이다
    `set_draw_color`·`set_text_color`·`set_font`는 한 번 바꾸면 그 뒤 전부에 적용된다.
    색을 바꾼 뒤 **되돌리지 않으면** 다음 표 테두리가 파란색으로 나온다(교안이 지목한 증상).
    그래서 색을 쓰는 곳은 반드시 `_reset()`으로 되돌린다.

★ 차트 이미지를 넣지 않는다
    `kaleido`(Plotly 정적 이미지)가 이 환경에서 불안정하다(DESIGN.md). 텍스트와 표만 쓴다.

★ 폰트가 없으면 **예외를 던지지 않고 알린다**
    앱이 죽으면 마크다운 리포트까지 못 보게 된다. PDF만 못 만드는 것과
    앱이 멈추는 것은 전혀 다른 실패다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import report as rp  # noqa: E402

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
FONT_NAME = "Noto"

# ★ 서브셋을 **저장소에 담아** 배포본에서도 PDF가 되게 한다.
#   Noto Sans KR 은 SIL Open Font License 라 재배포가 허용된다(Malgun Gothic 은 불가).
#   원본 12MB 중 대부분이 한자라, 한글 음절 전체 + 라틴 + 기호만 남겨 5.4MB 로 줄였다.
#   원본이 있으면 그쪽을 쓴다 — 손으로 받아 둔 사람의 환경을 바꾸지 않는다.
#   서브셋을 다시 만들려면: py -X utf8 dev_tools/subset_fonts.py
_FULL = {"": "NotoSansKR-Regular.ttf", "B": "NotoSansKR-Bold.ttf"}
_SUBSET = {"": "NotoSansKR-Regular-subset.ttf", "B": "NotoSansKR-Bold-subset.ttf"}
FONT_FILES = (_FULL if all((FONT_DIR / n).exists() for n in _FULL.values())
              else _SUBSET)

BLACK = (0, 0, 0)
GRAY = (100, 116, 139)          # slate — CLAUDE.md 7절 "데이터 없음"과 같은 색
LINE = (203, 213, 225)          # 표 테두리
HEAD_BG = (241, 245, 249)       # 표 머리 배경


def _period_label() -> str:
    """표지 제목의 기간 이름 — config 한 곳에서만 온다."""
    return getattr(config, "PERIOD_LABEL", "월간")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font_status() -> tuple[bool, list[str]]:
    """폰트가 준비됐는지와 없는 파일 목록. **앱이 먼저 물어보는 함수다.**"""
    missing = [n for n in FONT_FILES.values() if not (FONT_DIR / n).exists()]
    return (not missing), missing


MISSING_FONT_HELP = (
    "PDF를 만들려면 한글 폰트가 필요합니다. 아래 명령으로 받은 뒤 다시 시도하세요.\n\n"
    "```\npy -X utf8 dev_tools/get_fonts.py\n```\n\n"
    "자동 다운로드가 막히면 fonts.google.com/noto/specimen/Noto+Sans+KR 에서 "
    "**static/ 폴더의** `NotoSansKR-Regular.ttf`·`NotoSansKR-Bold.ttf`를 `fonts/`에 두세요. "
    "최상단의 `NotoSansKR[wght].ttf`는 **가변 폰트라 쓸 수 없습니다.**")


# ── 마크다운 파싱 ─────────────────────────────────────────────────────
def _blocks(md: str) -> list[tuple[str, object]]:
    """마크다운을 (종류, 내용) 블록으로 나눈다.

    종류: h1 · h2 · h3 · table · quote · bullet · text
    표는 연속된 `|` 줄을 한 덩어리로 모은다 — 줄 단위로 흘리면 표가 되지 않는다.
    """
    out: list[tuple[str, object]] = []
    rows: list[list[str]] = []

    def flush_table():
        nonlocal rows
        if rows:
            # 구분선(---|---)은 표 데이터가 아니다
            body = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
            if body:
                out.append(("table", body))
            rows = []

    for raw in md.splitlines():
        s = raw.strip()
        if s.startswith("|"):
            rows.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush_table()
        if not s or s == "---":
            continue
        # ★ 마크다운 주석은 **문서에 찍히면 안 된다.**
        #   화면(st.markdown)은 알아서 숨기지만 이 파서는 몰라서 `<! … >`가 그대로
        #   PDF 마지막 장에 나왔다 — 받는 사람에게 개발 흔적이 보인다.
        if s.startswith("<!--"):
            continue
        if s.startswith("### "):
            out.append(("h3", s[4:]))
        elif s.startswith("## "):
            out.append(("h2", s[3:]))
        elif s.startswith("# "):
            out.append(("h1", s[2:]))
        elif s.startswith(">"):
            out.append(("quote", s.lstrip("> ").strip()))
        elif s.startswith(("- ", "* ", "+ ")):
            out.append(("bullet", s[2:]))
        else:
            out.append(("text", s))
    flush_table()
    return out


def _clean(s: str) -> str:
    """PDF 본문용 정리 — 마크다운 표기를 fpdf2가 아는 형태로 맞춘다.

    ★ **fpdf2의 마크다운은 마크다운이 아니다.**
      `**굵게**`는 같지만 기울임은 `__이렇게__`이고 `*이렇게*`는 모른다.
      맞춰 주지 않으면 별표가 **글자 그대로** 나간다 — 실제로 리포트 2장에
      `*"지금 얼마 있다"*`가 별표째 찍혀 있었다.

    ★ 변형 선택자(U+FE0x)를 지운다.
      `⚠️` = `⚠` + U+FE0F 로, 이모지처럼 보이게 하는 **보이지 않는 표시**다.
      Noto Sans KR **원본에도 없어** PDF에서 네모로 나온다. 화면에서는 멀쩡해
      보이므로 PDF를 열기 전까지 아무도 모른다.
    """
    s = re.sub(r"[︀-️]", "", s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]", r"\1", s)
    # 홑별표 기울임은 **표시를 지운다.** 겹별표(굵게)는 건드리지 않는다.
    #   한글에는 기울임이 없고 Noto Sans KR도 이탤릭을 담고 있지 않다.
    #   억지로 기울이면 글자가 뭉개지므로, 강조는 굵게 하나로 간다.
    #   (원문에서 홑별표가 감싼 곳은 대개 따옴표가 함께 있어 강조가 이미 드러난다.)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)", r"\1", s)
    return s


# ── PDF ───────────────────────────────────────────────────────────────
def _make_pdf():
    from fpdf import FPDF

    class Report(FPDF):
        def footer(self):
            # 쪽번호 — 색을 바꾸므로 여기서도 끝나면 되돌린다
            self.set_y(-15)
            self.set_font(FONT_NAME, "", 8)
            self.set_text_color(*GRAY)
            self.cell(0, 8, f"{self.page_no()} / {{nb}}", align="C")
            self.set_text_color(*BLACK)

    pdf = Report(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    for style, fname in FONT_FILES.items():
        pdf.add_font(FONT_NAME, style, str(FONT_DIR / fname))
    # ★ `markdown=True`를 쓰면 fpdf2가 **네 스타일을 모두 미리 불러온다**
    #   (`_preload_font_styles`). 기울임이 없으면 `Undefined font: notoI`로 죽는다.
    #   한글 폰트에는 이탤릭이 없으므로 **곧은 글자를 그 자리에 넣는다** —
    #   `_clean`이 홑별표를 지우므로 실제로 쓰이지는 않고, 자리만 채운다.
    pdf.add_font(FONT_NAME, "I", str(FONT_DIR / FONT_FILES[""]))
    pdf.add_font(FONT_NAME, "BI", str(FONT_DIR / FONT_FILES["B"]))
    return pdf


def _reset(pdf) -> None:
    """★ 색·글꼴을 기본으로 되돌린다.

    fpdf2는 상태 저장형이라 되돌리지 않으면 **다음 표 테두리가 방금 쓴 색**으로 나온다.
    교안 "다르게 나오면"이 지목한 증상이 정확히 이것이다.
    """
    pdf.set_text_color(*BLACK)
    pdf.set_draw_color(*LINE)
    pdf.set_fill_color(*HEAD_BG)
    pdf.set_font(FONT_NAME, "", 10)


def _cover(pdf, md: str, ctx: dict) -> None:
    secs = rp.split_sections(md)
    todo = [s for s in secs if s["미작성"]]

    pdf.add_page()
    pdf.ln(50)
    pdf.set_font(FONT_NAME, "B", 22)
    pdf.multi_cell(0, 12, f"{_period_label()} 지표 리포트", align="C",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT_NAME, "B", 16)
    pdf.multi_cell(0, 10, str(ctx.get("기간", "")), align="C",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(14)

    pdf.set_font(FONT_NAME, "", 10)
    pdf.set_text_color(*GRAY)
    meta = ctx.get("카탈로그_메타") or {}
    for line in [f"생성일시 {ctx.get('생성일시', '—')}",
                 f"대상 파일 {ctx.get('파일명', '—')}",
                 f"생성 도구 auto-report · 카탈로그 {meta.get('생성일시', '?')}"]:
        pdf.multi_cell(0, 6, _clean(line), align="C", new_x="LMARGIN", new_y="NEXT")
    _reset(pdf)
    pdf.ln(12)

    # 미작성 경고 — 표지에서 바로 보여야 한다. 숫자만 있는 문서를
    # 완결된 분석으로 오해하고 그대로 전달하는 것을 막는 자리다.
    if todo:
        amber = _rgb(common.STATUS["경고"][0])
        pdf.set_text_color(*amber)
        pdf.set_font(FONT_NAME, "B", 11)
        pdf.multi_cell(0, 7, f"{len(todo)}개 장이 미작성 상태입니다", align="C",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(FONT_NAME, "", 9)
        pdf.multi_cell(0, 6, " · ".join(f"{s['번호']}장 {s['제목']}" for s in todo),
                       align="C", new_x="LMARGIN", new_y="NEXT")
        _reset(pdf)                                    # ★ 반드시 복원


def _table(pdf, rows: list[list[str]]) -> None:
    if not rows:
        return
    from fpdf.fonts import FontFace

    ncol = max(len(r) for r in rows)
    pdf.set_font(FONT_NAME, "", 8)
    # 머리행 스타일은 `headings_style`로 준다. `row.cell(style="B")`처럼 문자열을 넘기면
    # fpdf2가 FontFace를 기대해 TypeError로 죽는다(2.8.x에서 실측).
    # ★ `markdown=True`가 없으면 **표 안에서만** 별표가 글자 그대로 나온다.
    #   본문은 되는데 표는 안 되니 눈에 잘 띄지 않는다(실측: 2장 표 2칸).
    #   ⚠️ 이 옵션은 **표 단위**다 — `row.cell(markdown=True)`는 TypeError로 죽는다(2.8.8).
    with pdf.table(line_height=5, padding=1.2, text_align="LEFT",
                   borders_layout="ALL", markdown=True,
                   headings_style=FontFace(emphasis="BOLD", fill_color=HEAD_BG)) as table:
        for r in rows:
            row = table.row()
            for c in (r + [""] * ncol)[:ncol]:
                row.cell(_clean(c).replace("\\|", "|"))
    pdf.ln(2)
    _reset(pdf)


def build_pdf(md: str, ctx: dict) -> bytes:
    """마크다운 리포트를 PDF 바이트로. 폰트가 없으면 `FileNotFoundError`."""
    ok, missing = font_status()
    if not ok:
        raise FileNotFoundError(f"폰트 없음: {', '.join(missing)}")

    pdf = _make_pdf()
    _cover(pdf, md, ctx)
    pdf.add_page()
    _reset(pdf)

    for kind, body in _blocks(md):
        if kind == "table":
            _table(pdf, body)
            continue
        text = _clean(str(body))
        if kind == "h1":
            continue                                   # 표지에 이미 있다
        if kind == "h2":
            pdf.ln(3)
            pdf.set_font(FONT_NAME, "B", 14)
            pdf.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif kind == "h3":
            pdf.set_font(FONT_NAME, "B", 11)
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        elif kind == "quote":
            # 인용 — 왼쪽 여백을 주고 회색으로. 앱이 쓴 문장과 구분된다
            pdf.set_font(FONT_NAME, "", 9)
            pdf.set_text_color(*GRAY)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(0, 5.5, text, markdown=True,
                           new_x="LMARGIN", new_y="NEXT")
            _reset(pdf)                                # ★ 복원
        elif kind == "bullet":
            pdf.set_font(FONT_NAME, "", 10)
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(0, 6, f"· {text}", markdown=True,
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font(FONT_NAME, "", 10)
            pdf.multi_cell(0, 6, text, markdown=True, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
