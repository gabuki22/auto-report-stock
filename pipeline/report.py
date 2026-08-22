# -*- coding: utf-8 -*-
"""리포트 생성 — 앱 6단계 (6주차 Day3 실습 A).

화면이 아니라 **문서**를 만든다. 대시보드는 세션이 끝나면 사라지고, 리포트는 파일로 남아
읽는 사람에게 전달된다. 그래서 대시보드보다 문장의 책임이 무겁다.

★ 이 모듈이 쓰지 않는 문장 (Day3 개념 4절)
    | 금지            | 왜                                    | 대신          |
    |-----------------|---------------------------------------|---------------|
    | 인과 단정       | 앱은 인과를 판정할 수 없다            | 변동 사실만   |
    | 제안            | 판단은 사람 몫                        | 5·6장을 비움  |
    | 가치판단        | "개선됐다"는 맥락에 따라 달라진다     | "1.15% 증가"  |
    | 강도 표현       | "우려되는 수준"은 근거가 없다         | 임계값 초과   |
  **앱은 사실과 변동만 쓴다.**

★ 자동 생성하는 장만 남기지 않는다 (개념 1절)
  2·5·6장은 사람이 쓴다. 그 장을 삭제하면 리포트가 "숫자 보고서"가 되고, 받는 사람은
  그것을 **완결된 분석으로 오해한다.** 빈 자리를 남기고 "여기는 사람이 씁니다"라고
  표시해야 이 문서가 아직 완성되지 않았다는 것이 드러난다.

★ 생성 시각을 이 모듈이 직접 읽지 않는다
  `datetime.now()`를 여기서 부르면 같은 입력에 매번 다른 문서가 나온다(CLAUDE.md 5-5
  재현성). 시각은 `run_context["생성일시"]`로 **받는다.**
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
from pipeline import phrasing as ph  # noqa: E402
from pipeline import profile as pf  # noqa: E402

# 지표 하나에 인용할 인사이트 상한. tags 교집합은 흔한 태그 하나로도 걸려서
# ("이탈분석" 하나에 5건) 5장이 목록으로 뒤덮인다. 자를 때는 **몇 건을 줄였는지 밝힌다.**
MAX_INSIGHTS = 3

# ★ 자리표시자 문구는 **여기 한 곳에만** 둔다.
#   화면(미작성 장 판정)과 Day4의 병합이 이 문자열을 찾아 쓰므로, 사본을 두면
#   문구를 다듬는 순간 화면은 "작성됨"으로 보이는데 병합은 안 되는 상태가 된다.
#   "장"과 "소절"을 구분한다 — 1장의 핵심 시사점은 소절이라 미작성 장 수에 세지 않는다.
PLACEHOLDER_SECTION = "이 장은 사람이 작성합니다"
PLACEHOLDER_SUB = "이 소절은 사람이 작성합니다"

# 사람이 써야 하는 장 — 지우지 않고 자리표시자를 남긴다.
# ★ 번호·제목·문구를 **여기 한 곳에** 둔다. 리포트 본문, 화면의 미작성 판정,
#   `manual_sections`의 템플릿이 전부 이 표를 본다. 장 제목을 각자 적으면
#   템플릿의 "## 5. 원인 분석"과 리포트의 "## 5. 원인분석"이 어긋나 **병합이 조용히 실패한다.**
HUMAN_SECTIONS = {
    2: {"제목": "배경·목적",
        "자리표시": "이 분석을 왜 하는지, 어떤 의사결정에 쓰이는지. "
                    "**조직 맥락은 데이터에 없다.**",
        "작성힌트": "이 리포트를 왜 만드는가, 누가 읽는가, 어떤 결정에 쓰이는가"},
    5: {"제목": "원인 분석",
        "자리표시": "4장의 변동이 왜 일어났는지. **인과 판단은 사람이 한다** — "
                    "아래 관련 분석은 재료일 뿐이다.",
        "작성힌트": "아래 \"참고 — 위키에서 찾은 관련 분석\"을 근거로 원인을 판정"},
    6: {"제목": "개선 제안",
        "자리표시": "무엇을 할 것인지. **제안은 판단이므로 앱이 쓰지 않는다.**",
        "작성힌트": "우선순위와 근거. 실행 가능성·비용을 함께"},
}


def heading(n: int) -> str:
    """`## 5. 원인 분석` — 리포트와 템플릿이 **같은 문자열**을 쓰게 한다."""
    return f"## {n}. {HUMAN_SECTIONS[n]['제목']}"


def _log(log: dict, name: str, default=None):
    """실행 기록에서 값 하나. 단계별 구조와 옛 평평한 구조를 **둘 다** 읽는다.

    리포트는 앱이 만든 기록을 읽기만 하므로 `run_log`를 import하지 않고
    같은 규칙만 여기서 쓴다 — 리포트가 기록 모듈에 얽히면 오프라인 생성이 무거워진다.
    """
    if name in log and not isinstance(log[name], dict):
        return log[name]
    for blk in log.values():
        if isinstance(blk, dict) and name in blk:
            return blk[name]
    return default


def _esc(s) -> str:
    """마크다운 표 안에서 값이 열을 깨지 않게 한다.

    값에 `|`가 들어 있으면 그 자리에서 열이 하나 더 생겨 표 전체가 어긋난다.
    줄바꿈도 마찬가지라 공백으로 접는다.
    """
    return common.blank_safe(s).replace("|", "\\|").replace("\n", " ")


def _table(head: list[str], rows: list[list], align: str = "") -> str:
    """마크다운 표. align은 열별 'l'/'r' 문자열(생략하면 전부 좌측)."""
    align = align or "l" * len(head)
    sep = ["---:" if a == "r" else "---" for a in align.ljust(len(head), "l")]
    out = ["| " + " | ".join(_esc(h) for h in head) + " |",
           "|" + "|".join(sep) + "|"]
    out += ["| " + " | ".join(_esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _mom_flagged(ctx) -> list[dict]:
    """임계값을 넘은 지표 — **검증 결과에서 가져온다.**

    여기서 변화율과 임계값을 다시 비교하면 판정이 두 곳에 생긴다. 검증은 지표별
    임계값(정의서 `변동임계값`)을 이미 적용했으므로, 리포트는 그 결과를 인용만 한다.
    """
    v = ctx.get("validation") or {}
    return [x for x in v.get("항목", [])
            if x.get("검증명") == "전월 대비" and x.get("판정") == "경고"]


def _flag_sentences(ctx) -> list[str]:
    """임계값을 넘은 지표를 **문장으로**. 1장과 4장이 같은 함수를 쓴다.

    두 장이 각자 문장을 만들면 요약과 본문이 어긋난다 — 요약엔 2건인데 본문엔 3건이
    적히는 식이다. 같은 재료로 같은 함수를 쓰면 그런 일이 생기지 않는다.
    """
    comp = ctx.get("comparison")
    if comp is None or not len(comp):
        return []
    cmap = {r["지표명"]: r for _, r in comp.iterrows()}
    out = []
    for x in _mom_flagged(ctx):
        row = cmap.get(x["대상지표"])
        if row is None:
            continue
        basis = common.blank_safe(x.get("기준"))          # 예: "5% (기본값)"
        th = float(basis.split("%")[0]) if basis else None
        src = basis.split("(")[-1].rstrip(")") if "(" in basis else ""
        out.append(ph.describe_change(row, th, src))
    return out


# ── 머리말 ────────────────────────────────────────────────────────────
def header(ctx) -> str:
    period = ctx.get("기간", "?")
    meta = ctx.get("카탈로그_메타") or {}
    rows = [
        ["생성일시", ctx.get("생성일시", "—")],
        ["대상 기간", period],
        ["생성 도구", "auto-report"],
        ["카탈로그", f"지표 {len(ctx.get('metrics_catalog') or {})}종 · "
                    f"생성 {meta.get('생성일시', '?')}"],
    ]
    return ("\n".join([
        f"# 월간 지표 리포트 — {period}",
        "",
        _table(["항목", "값"], rows),
        "",
        "> **이 문서는 자동 생성되었으며 2·5·6장은 사람이 작성해야 합니다.**",
        "> 자동 생성된 장은 계산·검증 결과를 그대로 서술하며, "
        "원인·제안·가치판단을 포함하지 않습니다.",
    ]))


# ── 1장 — Executive Summary ───────────────────────────────────────────
def section_1_summary(ctx) -> str:
    """무엇을 계산했는가 / 무엇이 변했는가 / 검증 상태 — 여기까지가 자동이다.

    ★ **"그래서 무엇이 중요한가"는 자리표시자로 남긴다.** 숫자 요약은 기계가 할 수 있지만
      그중 무엇이 이 조직에 중요한지는 목표를 알아야 하고, 그 목표는 데이터에 없다.
      이 소절을 앱이 채우면 요약이 **판단처럼 읽히면서 근거는 없는** 문단이 된다.
    """
    m = ctx["metrics"]
    v = ctx.get("validation") or {}
    n_dep = int((m["포함사유"] != "").sum()) if "포함사유" in m else 0

    lines = ["## 1. Executive Summary", "",
             f"- **대상 기간**: {ctx.get('기간', '—')}",
             f"- **계산 지표**: {len(m) - n_dep}종"
             + (f" (의존 지표 {n_dep}종 포함 {len(m)}종 계산)" if n_dep else ""),
             "", "**전월 대비 변동이 큰 지표**", ""]

    flags = _flag_sentences(ctx)
    lines += [f"- {s}" for s in flags] if flags else \
             ["- 임계값을 넘는 변동이 있는 지표가 없다."]

    lines += ["",
              f"- **검증**: 차단 {v.get('차단수', 0)}건, 경고 {v.get('경고수', 0)}건"
              f" (전체 판정 {v.get('전체판정', '—')})",
              "",
              f"> **핵심 시사점 — {PLACEHOLDER_SUB}.**",
              "> 위 변동 중 무엇이 이번 달 의사결정에 중요한지. "
              "**무엇이 중요한가는 목표에 달렸고, 목표는 데이터에 없다.**"]
    return "\n".join(lines)


# ── 2장 — 사람 ────────────────────────────────────────────────────────
def section_2_background(ctx) -> str:
    return f"{heading(2)}\n\n{_placeholder(2)}"


def _placeholder(n: int) -> str:
    return f"> **{PLACEHOLDER_SECTION}.**\n> {HUMAN_SECTIONS[n]['자리표시']}"


# ── 3장 — 데이터·방법론 (자동) ────────────────────────────────────────
def section_3_method(ctx) -> str:
    m: pd.DataFrame = ctx["metrics"]
    cat = ctx.get("metrics_catalog") or {}
    meta = ctx.get("카탈로그_메타") or {}
    log = ctx.get("run_log") or {}

    src = _table(["항목", "값"], [
        ["대상 파일", ctx.get("파일명", "—")],
        ["판정 테이블", f"`{ctx.get('판정테이블', '—')}`"
         + (" (노트명에서 유도한 추정값)" if _log(log, "테이블명_추정") else "")],
        ["기간", ctx.get("기간", "—")],
        ["행수", f"{ctx.get('행수', 0):,}"],
        ["스키마 일치율", f"{_log(log, '일치율', 0):.0%}"],
    ])

    # 지표 정의 요약 — 정의서에서 **그대로** 가져온다. 리포트가 정의를 새로 쓰지 않는다.
    #
    # ★ 산식을 코드로 재조립하지 않는다. 계산 블록의 모양이 지표마다 다르고
    #   (분자/분모가 위키링크 문자열 · 원천+집계+조건 dict · 기준지표+시차 3종),
    #   각각을 문장으로 옮기는 규칙을 앱에 두면 그게 곧 **두 번째 정의**가 된다.
    #   정의서에는 이미 사람이 읽을 `산식`이 있으므로 그것을 인용한다.
    rows = []
    for _, r in m.iterrows():
        spec = cat.get(r["metric_id"]) or {}
        c = spec.get("계산", {}) or {}
        formula = (common.blank_safe(c.get("산식"))
                   or common.blank_safe(c.get("집계")) or "—")
        note = common.blank_safe(r.get("포함사유"))
        rows.append([
            # ⚠️ 이 값은 PDF로도 나간다. Noto Sans KR에 없는 문자(⤷ 등)를 쓰면
            #    PDF에서 네모로 표시된다 — 화면에서만 확인하면 못 잡는다.
            r["지표명"] + (f" ({note})" if note else ""),
            f"`{r['metric_id']}`",
            formula,
            " + ".join(sorted(pf._sources(spec, cat))) or "—",
            common.blank_safe(spec.get("유효구간")) or "—",
        ])
    defs = _table(["지표", "metric_id", "산식", "원천", "정의서 유효구간"], rows)

    n_dep = int((m["포함사유"] != "").sum()) if "포함사유" in m else 0
    lines = [
        "## 3. 데이터·방법론",
        "",
        "### 3-1. 대상 데이터",
        "",
        src,
        "",
        "### 3-2. 계산한 지표",
        "",
        f"지표 {len(m)}종을 계산했다"
        + (f"(그중 {n_dep}종은 다른 지표를 계산하는 과정에서 함께 계산되었다)." if n_dep else "."),
        "",
        defs,
        "",
        f"지표 정의는 위키 정의서에서 가져왔다 — 카탈로그 지표 {len(cat)}종, "
        f"생성일시 {meta.get('생성일시', '?')}.",
    ]

    # 부분 갱신 — 값이 틀린 것은 아니고 시점이 섞여 있다. 그 사실을 밝힌다.
    partial = {}
    for _, r in m.iterrows():
        for t in common.blank_safe(r.get("부분갱신")).split(","):
            if t.strip():
                partial.setdefault(t.strip(), []).append(r["지표명"])
    if partial:
        lines += ["", "### 3-3. 부분 갱신", "",
                  "아래 지표는 계산되었으나, 원천 테이블 중 일부가 이번 실행에서 "
                  "갱신되지 않았다. 값이 틀린 것이 아니라 **시점이 섞여 있다.**", "",
                  _table(["갱신되지 않은 테이블", "영향받는 지표"],
                         [[f"`{t}`", ", ".join(ms)] for t, ms in sorted(partial.items())])]
    return "\n".join(lines)


# ── 4장 — 현황 (자동) ─────────────────────────────────────────────────
def section_4_status(ctx) -> str:
    comp: pd.DataFrame = ctx["comparison"]
    m: pd.DataFrame = ctx["metrics"]
    mmap = {r["metric_id"]: r for _, r in m.iterrows()}

    rows = []
    for _, r in comp.iterrows():
        base = mmap.get(r["metric_id"], r)
        # 표와 문장이 같은 서식 함수를 쓴다. 표엔 "—", 문장엔 "값 없음"으로 갈리면
        # 같은 지표가 표에서는 빈칸, 문장에서는 미계산으로 읽힌다.
        cur = ph.fmt_value(r.get("당월"), base.get("유형", ""), r["지표명"], r["metric_id"],
                           base.get("단위", ""))
        prv = ph.fmt_value(r.get("전월"), base.get("유형", ""), r["지표명"], r["metric_id"],
                           base.get("단위", ""))
        if str(r.get("비교상태")) != "비교 가능":
            rate = f"비교 불가 — {common.blank_safe(r.get('이유'))}"
        else:
            rate = _rate_text(r)
        rows.append([r["지표명"], cur, prv, rate])

    lines = ["## 4. 현황", "",
             f"{ctx.get('기간', '')} 계산 결과와 전월 대비 변동이다. "
             "증가·감소의 방향만 서술하며, 그것이 좋은 변화인지 나쁜 변화인지는 판단하지 않는다.",
             ""]

    # 표 위 요약 — **임계값을 넘은 지표만.** 전체를 다 서술하면 요약이 아니라 표를
    # 문장으로 옮긴 것이 되고, 읽는 사람은 그중 무엇을 봐야 할지 알 수 없다.
    flags = _flag_sentences(ctx)
    if flags:
        lines += [f"- {s}" for s in flags] + [""]

    lines += [_table(["지표", "당월", "전월", "전월 대비"], rows, "lrrr")]

    flagged = _mom_flagged(ctx)
    lines += ["", "### 4-1. 전월 대비 변동이 큰 지표", ""]
    if flagged:
        lines += [f"아래 {len(flagged)}종은 **그 지표의 임계값**을 넘는 변동이 있었다. "
                  "임계값은 지표마다 다르며 정의서에서 가져온다.", "",
                  _table(["지표", "변동", "적용 임계값"],
                         [[x["대상지표"],
                           f"{x['값']:+.2f}%" if isinstance(x.get("값"), (int, float)) else "—",
                           common.blank_safe(x.get("기준")) or "—"] for x in flagged], "lrl"),
                  "", "이 리포트는 변동이 왜 일어났는지 판정하지 않는다(5장 참조)."]
    else:
        lines += ["임계값을 넘는 변동이 있는 지표가 없다."]
    return "\n".join(lines)


def _rate_text(r) -> str:
    """변화율 — 비율 지표는 **%p와 % 둘 다** 적는다.

    36.6% → 39.0%는 +2.4%p이자 +6.6%다. 둘 중 하나만 쓰면 읽는 사람이 다른 쪽으로
    이해할 수 있고, 그 차이가 보고서의 결론을 바꾼다.
    """
    rate, pp = r.get("상대변화율"), r.get("퍼센트포인트변화")
    if rate is None or pd.isna(rate):
        return "—"
    txt = f"{rate:+.2f}%"
    if pp is not None and not pd.isna(pp):
        txt += f" ({pp:+.1f}%p)"
    return txt


# ── 5·6장 — 사람 ──────────────────────────────────────────────────────
def find_insights(metric_id: str, ctx) -> list[dict]:
    """이 지표와 관련된 인사이트를 찾는다 — **본문 링크 우선, tags 교집합 보조.**

    | 방법        | 근거                              | 정확도 |
    |-------------|-----------------------------------|--------|
    | 본문 위키링크 | 사람이 이 지표를 설명하며 직접 걸었다 | 높음   |
    | tags 교집합  | 같은 주제를 다룬다는 신호일 뿐      | 낮음   |

    ★ tags는 **느슨한 연결**이라 무관한 인사이트가 걸릴 수 있다. 그래서 어느 방법으로
      찾았는지를 결과에 담아 **읽는 사람이 근거의 강도를 알 수 있게** 한다.
      정확한 연결이 필요하면 앱을 고치는 게 아니라 **위키 정의서에 링크를 추가한다.**
    """
    ins = ctx.get("insights_catalog") or {}
    spec = (ctx.get("metrics_catalog") or {}).get(metric_id) or {}
    out, seen = [], set()

    for key in spec.get("관련인사이트_본문링크") or []:
        if key in ins and key not in seen:
            seen.add(key)
            out.append({"id": key, "근거": "본문 링크", **ins[key]})

    mtags = {str(t).strip() for t in (spec.get("tags") or [])}
    if mtags:
        for key, note in sorted(ins.items()):
            if key in seen:
                continue
            common_tags = mtags & {str(t).strip() for t in (note.get("tags") or [])}
            if common_tags:
                seen.add(key)
                out.append({"id": key, "근거": f"tags 교집합: {', '.join(sorted(common_tags))}",
                            **note})
    return out


def section_5_cause(ctx) -> str:
    """원인 분석 — **본문은 비워 두고 재료만 놓는다.**

    ★ 인용은 하되 결론은 쓰지 않는다. "위키에 이런 분석이 있다"까지가 앱의 역할이고,
      그것을 근거로 원인을 판정하는 것은 사람이다. 여기에 앱이 결론을 쓰면
      **인용된 분석의 권위를 빌려 앱의 추측이 사실처럼 읽힌다.**
    """
    lines = [heading(5), "", _placeholder(5), "",
             "### 참고 — 위키에서 찾은 관련 분석", ""]

    flagged = _mom_flagged(ctx)
    if not flagged:
        return "\n".join(lines + ["임계값을 넘는 변동이 없어 찾은 분석이 없다."])

    names = {r["지표명"]: r["metric_id"] for _, r in ctx["metrics"].iterrows()}
    for x in flagged:
        mid = names.get(x["대상지표"], x["대상지표"])
        found = find_insights(mid, ctx)
        lines.append(f"**{x['대상지표']}** (`{mid}`)")
        lines.append("")
        if not found:
            # 못 찾았다는 사실을 적는다. 비워두면 "찾아봤는데 없다"와
            # "찾아보지 않았다"가 구분되지 않는다.
            lines += ["- 관련 분석 없음 — 정의서 본문 링크도, tags가 겹치는 인사이트도 없다.", ""]
            continue
        shown, cut = found[:MAX_INSIGHTS], max(0, len(found) - MAX_INSIGHTS)
        for f in shown:
            conf = common.blank_safe(f.get("confidence")) or "미표기"
            lines.append(f"- **{f.get('제목', f['id'])}** · confidence {conf} "
                         f"· 근거: {f['근거']}")
            # ★ 시사점은 **인용 블록**으로 넣는다. 사람이 쓴 문장에는 인과·제안이
            #   당연히 들어 있고, 그것을 앱의 서술과 같은 모양으로 실으면 읽는 사람이
            #   앱이 한 판단으로 오해한다. 인용 표시가 곧 "이건 남의 말"이라는 신호다.
            for s in _summarize(f.get("_시사점", ""), 3):
                lines.append(f"  > {s}")
            lines.append(f"  - 위키 노트: `{f.get('_노트파일', f['id'] + '.md')}`")
        if cut:
            # 자른 건수를 밝힌다. 조용히 자르면 "이게 전부"로 읽힌다.
            lines.append(f"- _tags로 찾은 후보 {cut}건을 더 줄였다 "
                         f"(상위 {MAX_INSIGHTS}건만 표시). tags는 느슨한 연결이라 "
                         f"무관한 분석이 섞인다 — 정확한 연결은 정의서 본문 링크로 만든다._")
        lines.append("")
    return "\n".join(lines).rstrip()


def _summarize(text: str, n: int) -> list[str]:
    """시사점 절에서 앞 n줄만. **요약하지 않고 잘라낸다.**

    앱이 문장을 다시 쓰면 원문에 없는 뉘앙스가 섞인다. 사람이 쓴 문장을 그대로
    옮기고, 전체는 위키 노트를 열어 보게 한다.

    ⚠️ 소제목(`###`)과 표는 건너뛴다. `#`을 벗기고 본문처럼 실었더니
       "쓸 수 있는 문장** (근거 강도에 맞는 표현)"처럼 **제목 조각이 문장인 척** 나왔다.
    """
    bullets: list[tuple[int, str]] = []      # (들여쓰기, 문장)
    paras: list[str] = []
    for line in common.blank_safe(text).splitlines():
        raw = line.rstrip()
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "|", ">")):
            continue
        # ~~취소선~~은 위키에서 **철회한 문장**이다. 인용하면 철회된 주장이 되살아난다.
        if "~~" in stripped:
            continue
        if stripped.startswith(("-", "*", "+")):
            indent = len(raw) - len(raw.lstrip())
            s = stripped.lstrip("-*+ ").replace("**", "").strip()
            if s:
                bullets.append((indent, s if len(s) <= 120 else s[:117] + "…"))
        else:
            s = stripped.replace("**", "").strip()
            if s:
                paras.append(s if len(s) <= 120 else s[:117] + "…")

    if bullets:
        # ★ 시사점 절은 **중첩 불릿**인 경우가 많다 —
        #     - **쓸 수 있는 문장** (근거 강도에 맞는 표현)   ← 그룹 헤더
        #       - 2024년 하반기 이탈 59명으로 …               ← 실제 문장
        #   들여쓰기를 무시하고 평평하게 읽었더니 헤더가 시사점인 척 인용됐다.
        #   하위 항목이 있으면 그것만, 없으면(평평한 목록) 전부 쓴다.
        top = min(i for i, _ in bullets)
        nested = [s for i, s in bullets if i > top]
        return (nested or [s for _, s in bullets])[:n]
    return paras[:n]


def section_6_proposal(ctx) -> str:
    return f"{heading(6)}\n\n{_placeholder(6)}"


# ── 7·8장 (프롬프트 9에서 구현) ───────────────────────────────────────
def _limit_items(text: str) -> list[str]:
    """"이 지표로 답할 수 없는 것" 절의 항목을 줄 단위로."""
    out = []
    for line in common.blank_safe(text).splitlines():
        s = line.strip()
        if s.startswith(("-", "*", "+")):
            # ⚠️ lstrip("-*+ ")를 쓰면 `- **제목**`의 `**`까지 벗겨져
            #    "임계값의 타당성** — …"처럼 강조가 반쪽만 남는다. 마커 하나만 제거한다.
            out.append(re.sub(r"^[-*+]\s+", "", s).strip())
    return out


def _prev_input(ctx) -> tuple[str | None, int | None]:
    """전월 값을 **어느 실행에서** 가져왔는지와 그 실행의 입력 행수.

    비교표 `이유` 칸에 `compare`가 남긴 출처를 읽는다. 리포트가 outputs 폴더를 스스로
    뒤지지 않게 한다 — 출처를 만든 쪽이 남기고, 이쪽은 읽기만 한다.
    """
    comp = ctx.get("comparison")
    if comp is None or not len(comp) or "이유" not in getattr(comp, "columns", []):
        return None, None
    for s in comp["이유"].dropna().astype(str):
        m = re.search(r"이전 실행\((run_[0-9_]+)\)", s)
        if not m:
            continue
        f = Path(__file__).resolve().parent.parent / "outputs" / m.group(1) / "run_log.json"
        try:
            return m.group(1), _log(json.loads(f.read_text(encoding="utf-8")), "행수")
        except Exception:
            return m.group(1), None
    return None, None


def section_7_limits(ctx) -> str:
    """한계 절 — **재료를 모아서 조립한다.**

    ★ 자동화가 사람보다 나은 드문 지점이다. 한계는 여러 곳에 흩어져 있고
      (계산 결과의 status, 판정 결과의 부분 갱신, 검증이 안 한 항목, 정의서 프론트매터,
      정의서 본문), 사람이 매번 손으로 쓰면 **그중 절반은 빠뜨린다.**
      특히 잠정 임계값은 정의서를 다시 읽지 않으면 기억하기 어렵다.

    ★ **재료가 없는 소절은 만들지 않는다.** 빈 소절은 "확인했는데 없었다"가 아니라
      "이 항목을 안 봤다"로도 읽힌다.
    ★ **한계를 축소하거나 완화하지 않는다.** 그 판단은 사람 몫이고,
      `phrasing.FORBIDDEN`의 "완화" 패턴이 자체 검사에서 이를 잡는다.
    """
    m: pd.DataFrame = ctx["metrics"]
    cat = ctx.get("metrics_catalog") or {}
    v = ctx.get("validation") or {}
    period = ctx.get("기간", "이번 기간")
    subs: list[tuple[str, list[str]]] = []          # (소절 제목, 본문 줄)

    # 1. 유효구간
    ext = [r for _, r in m.iterrows() if common.blank_safe(r.get("status")) == "구간확장"]
    if ext:
        rows = [[r["지표명"], f"`{r['metric_id']}`",
                 common.blank_safe((cat.get(r["metric_id"]) or {}).get("유효구간")) or "—"]
                for r in ext]
        subs.append(("유효구간", [
            f"아래 {len(ext)}종은 **정의서 유효구간을 넘어선 {period}을 계산**했다. "
            "확장은 **이번 실행에만 승인**되었고 위키 정의서는 변경되지 않았다. "
            "승인은 실행 단위이므로 다음 실행으로 이어지지 않는다.", "",
            _table(["지표", "metric_id", "정의서 유효구간"], rows)]))

    # 2. 표본 — 재료가 있을 때만
    low = [r for _, r in m.iterrows() if common.blank_safe(r.get("status")) == "표본부족"]
    if low:
        subs.append(("표본", [
            "아래 지표는 값이 계산되었으나 최소표본 기준에 미달한다. **결론의 근거로 쓰지 않는다.**", "",
            _table(["지표", "표본", "기준"],
                   [[r["지표명"],
                     f"{r.get('sample_size'):,.0f}" if pd.notna(r.get("sample_size")) else "—",
                     common.blank_safe(r.get("min_sample")) or "—"] for r in low], "lrr")]))

    # 3. 데이터 갱신 범위
    partial = {}
    for _, r in m.iterrows():
        for t in common.blank_safe(r.get("부분갱신")).split(","):
            if t.strip():
                partial.setdefault(t.strip(), []).append(r["지표명"])
    if partial:
        subs.append(("데이터 갱신 범위", [
            "아래 원천 테이블은 **이번 실행에서 갱신되지 않았다.** 해당 지표는 계산되었으나 "
            f"{period}의 변경분이 반영되지 않은 이전 상태를 함께 참조한다.", "",
            _table(["갱신되지 않은 테이블", "영향받는 지표"],
                   [[f"`{t}`", ", ".join(ms)] for t, ms in sorted(partial.items())])]))

    # 4. 수행하지 않은 검증
    not_auto = v.get("자동검증하지_않은_것") or []
    if not_auto:
        subs.append(("수행하지 않은 검증", [
            "이 리포트의 검증은 **기계적 점검만** 수행했다. 아래 항목은 판단이 필요해 "
            "자동화하지 않았으며, **검증 통과가 이 항목들을 통과했다는 뜻이 아니다.**", ""]
            + [f"- {s}" for s in not_auto]))

    # 5. 잠정 기준 — 정의서 본문의 설명을 그대로 인용한다.
    #    필드만 옮기면 "잠정이다"까지밖에 못 쓰고, **왜 잠정인지가 빠진다.**
    prov = []
    for _, r in m.iterrows():
        spec = cat.get(r["metric_id"]) or {}
        if str(spec.get("임계값_상태", "")).strip() != "잠정":
            continue
        why = [s for s in _limit_items(spec.get("_답할수없는것", "")) if "임계값" in s]
        prov.append((r["지표명"], r["metric_id"], why))
    if prov:
        lines = ["아래 지표는 **판정 기준이 잠정**이라고 정의서에 선언되어 있다. "
                 "기준이 바뀌면 값의 해석도 바뀐다.", ""]
        for name, mid, why in prov:
            lines.append(f"**{name}** (`{mid}`)")
            lines += [f"> {s}" for s in why] or ["> 정의서에 `임계값_상태: 잠정`으로 선언됨."]
            lines.append("")
        subs.append(("잠정 기준", lines))

    # 6. 지표별 한계 — 계산된 지표에 한해서만
    used = {s for _, _, why in prov for s in why}       # 잠정 기준에서 이미 인용한 문장
    per_metric = []
    for _, r in m.iterrows():
        items = [s for s in _limit_items((cat.get(r["metric_id"]) or {}).get("_답할수없는것", ""))
                 if s not in used]
        if items:
            per_metric.append((r["지표명"], r["metric_id"], items))
    if per_metric:
        lines = ["각 지표 정의서의 **\"이 지표로 답할 수 없는 것\"**을 그대로 옮긴다.", ""]
        for name, mid, items in per_metric:
            lines.append(f"**{name}** (`{mid}`)")
            lines += [f"> {s}" for s in items]
            lines.append("")
        subs.append(("지표별 한계", lines))

    # 7. 입력 데이터 품질 — **2단계 판정에서 이미 본 것**을 리포트로 옮긴다.
    #    ★ 2025-02 실행에서 이 소절이 없다는 것이 드러났다. 파일은 직전 달보다 20행 적었고
    #      결측이 3건 있었다. 둘 다 판정 화면에는 떴지만 **리포트에는 한 줄도 남지 않았다.**
    #      그 20행이 매출 감소의 78%였다. 판정에서 본 것이 리포트로 이어지지 않으면
    #      읽는 사람은 받은 파일이 온전했다고 가정한다.
    rlog = ctx.get("run_log") or {}
    rows = ctx.get("행수") or _log(rlog, "행수")
    miss = _log(rlog, "결측", 0) or 0
    dup = _log(rlog, "그레인_중복", 0) or 0
    lack = _log(rlog, "누락_컬럼", []) or []
    prev_run, prev_rows = _prev_input(ctx)
    q: list[str] = []
    if rows and prev_rows and prev_rows != rows:
        d = rows - prev_rows
        q.append(f"- 입력 행수 **{rows:,}행** — 직전 실행(`{prev_run}`) {prev_rows:,}행 대비 "
                 f"**{d:+,}행**({d / prev_rows * 100:+.1f}%). "
                 "행 수가 다른 만큼 두 기간의 집계 대상이 같지 않다.")
    elif rows:
        q.append(f"- 입력 행수 **{rows:,}행**.")
    if miss:
        # ★ "제외된다"로 뭉뚱그리지 않는다. 합계와 평균에서 작용이 다르다.
        #   SUM은 NULL을 건너뛰므로 **그 행이 0인 것과 결과가 같고**,
        #   AVG는 분모에서도 빠지므로 0으로 치는 것과 **결과가 달라진다.**
        q.append(f"- 결측 **{miss:,}건**"
                 + (f" (합산 대상 {rows - miss:,}행)" if rows else "")
                 + ". 합계에서는 그 행이 0인 것과 결과가 같고, 평균에서는 분모에서도 빠진다.")
    if dup:
        q.append(f"- 그레인 중복 **{dup:,}건**. 같은 키가 여러 행으로 들어와 있다.")
    if lack:
        q.append("- 정의서 대비 누락 컬럼: " + ", ".join(f"`{c}`" for c in lack))
    if len(q) > 1 or miss or dup or lack:      # 행수 한 줄만 있으면 소절을 만들지 않는다
        subs.append(("입력 데이터 품질", [
            "**받은 파일 자체의 상태**다. 아래는 2단계 판정에서 관찰된 것이며, "
            "이것이 각 지표에 얼마나 반영됐는지는 이 리포트에서 판단하지 않는다.", ""] + q))

    # 8. 전월 비교 기준 — 전월 값이 어떻게 구해졌는지
    if prev_run:
        subs.append(("전월 비교 기준", [
            "전월 값은 **원본 테이블에서 다시 계산하지 못했다.** 업로드분은 스테이징 테이블에만 "
            "적재되고 스테이징은 실행마다 덮어쓰므로, 지난달 업로드분은 조회되지 않는다. "
            f"이번 리포트의 전월 값은 **직전 실행 `{prev_run}`의 결과**를 그대로 사용했다.", "",
            "그 실행이 참조한 정의서는 이번 실행의 정의서와 다를 수 있다.", ""]))

    if not subs:
        return ("## 7. 한계\n\n"
                "이번 실행에서 자동으로 수집된 한계 항목이 없다. "
                "**한계가 없다는 뜻이 아니라, 기계적으로 수집 가능한 항목이 없다는 뜻이다.**")

    out = ["## 7. 한계", "",
           "아래는 계산·검증·정의서에서 **자동으로 수집한** 항목이다. "
           "각 항목의 영향이 얼마나 큰지는 이 리포트에서 판단하지 않는다.", ""]
    for i, (title, body) in enumerate(subs, 1):
        out += [f"### 7-{i}. {title}", ""] + body + [""]
    return "\n".join(out).rstrip()


def section_8_appendix(ctx) -> str:
    return "## 8. 부록\n\n_(다음 단계에서 생성)_"


def split_sections(md: str) -> list[dict]:
    """리포트를 `## ` 헤딩 단위로 나눈다.

    화면이 장별로 접었다 펴려면 분할이 필요하고, Day4의 사람 작성분 병합도 같은
    단위로 움직인다. 분할 규칙이 두 곳에 생기면 **화면에서는 8장인데 병합은
    7장만 되는** 어긋남이 생기므로 여기 한 곳에 둔다.

    반환: [{번호, 제목, 본문, 미작성}] — 머리말은 번호 0.
    """
    out, cur = [], {"번호": 0, "제목": "머리말", "본문": []}
    for line in md.splitlines():
        if line.startswith("## "):
            out.append(cur)
            head = line[3:].strip()
            num, _, title = head.partition(".")
            out_num = int(num) if num.strip().isdigit() else 0
            cur = {"번호": out_num, "제목": title.strip() or head, "본문": []}
        else:
            cur["본문"].append(line)
    out.append(cur)
    for s in out:
        s["본문"] = "\n".join(s["본문"]).strip()
        # ★ 장 번호가 아니라 **자리표시자가 남아 있는지**로 판정한다.
        #   번호(2·5·6)로 박으면 Day4에서 사람이 2장을 채워도 계속 "작성 필요"로 보인다.
        s["미작성"] = PLACEHOLDER_SECTION in s["본문"]
    return [s for s in out if s["본문"] or s["번호"]]


def mask_human_sections(md: str) -> str:
    """사람이 쓴 장(2·5·6)을 **빈 줄로 바꾼다.**

    지우지 않고 비우는 이유는 검사 결과의 **행 번호가 원문과 맞아야** 사람이 그 줄을
    찾을 수 있어서다. 분할 규칙은 `split_sections`와 같은 것을 쓴다 — 두 곳이 갈라지면
    어떤 장은 검사되고 어떤 장은 안 되는 상태가 조용히 생긴다.
    """
    out, cur = [], 0
    for line in md.splitlines():
        if line.startswith("## "):
            num, _, _t = line[3:].strip().partition(".")
            cur = int(num) if num.strip().isdigit() else 0
        out.append("" if cur in HUMAN_SECTIONS else line)
    return "\n".join(out)


def check_generated(md: str) -> list:
    """**자동 생성 장만** 금지 표현을 검사한다.

    ★ 이 규칙의 취지는 "**앱이** 판단 문장을 쓰지 않는다"이다. 사람이 원인을 쓰는 5장에서
      "원인은 ~ 때문이다"를 막으면 그 장을 쓸 수가 없다. 검사기가 사람의 문장까지 막으면
      사람은 검사를 통과시키려고 문장을 뭉갠다 — 그러면 리포트가 나빠진다.
      (2025-02 실행에서 5·6장을 채우자 검사가 5건을 잡았는데 **전부 사람이 쓴 문장**이었다.)
    """
    return ph.check_forbidden(mask_human_sections(md))


# ── 조립 ──────────────────────────────────────────────────────────────
SECTIONS = [section_1_summary, section_2_background, section_3_method,
            section_4_status, section_5_cause, section_6_proposal,
            section_7_limits, section_8_appendix]


def build_report(run_context: dict, self_check: bool = True) -> str:
    """8장 구조 리포트를 마크다운으로 만든다.

    ★ 생성 직후 **스스로 금지 표현을 검사한다.** 문장 규칙을 아무리 정해도 문장을
      손보다 보면 "개선됐다"가 슬며시 들어온다. 나가기 전에 잡아야 한다.
      학습 단계라 결과를 문서 끝에 보이게 두지만, 운영에서는 로그로만 남긴다.
    """
    parts = [header(run_context)] + [fn(run_context) for fn in SECTIONS]
    md = "\n\n".join(parts).rstrip() + "\n"
    if not self_check:
        return md

    hits = check_generated(md)
    tail = ["", "---", "",
            f"<!-- 자체 검사: 금지 표현 {len(hits)}건 -->", "",
            f"_개발용 자체 검사 — 금지 표현 **{len(hits)}건**"
            + ("_" if not hits else " (아래 문장을 사실 서술로 고칠 것)_")]
    tail += [f"> - {h['줄']}행 [{h['유형']}] `{h['표현']}` — {h['문장']}" for h in hits]
    return md + "\n".join(tail) + "\n"
