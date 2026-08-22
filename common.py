# -*- coding: utf-8 -*-
"""화면 공통 요소 — 상태 배지·카탈로그 로딩·CSV 읽기.

색은 CLAUDE.md 7절 / DESIGN.md의 Tailwind 500 계열 대응을 따른다.
배지를 여기 한 곳에 두는 이유: 상태 색이 화면마다 달라지면 사용자가 색을 못 믿는다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config

# ★ 기간 이름은 config 한 곳에서 온다 — 화면·이메일·리포트가 같은 말을 쓰게 한다.
#   ⚠️ 이것은 **표시 문자열**이다. `r["당월"]`·`c.get("전월")`은 DataFrame
#      컬럼 키이므로 바꾸면 안 된다 — 표시와 키를 한꺼번에 치환하면 조용히 깨진다.
_PERIOD = getattr(config, "PERIOD_LABEL", "월간")
_PREV = getattr(config, "PREV_LABEL", "전월")
_CURR = getattr(config, "CURR_LABEL", "당월")

# 상태 → (색, 라벨). CLAUDE.md 7절 대응
STATUS = {
    "통과":   ("#10b981", "emerald"),
    "경고":   ("#f59e0b", "amber"),
    "차단":   ("#f43f5e", "rose"),
    "정보":   ("#64748b", "slate"),
}
# 판정 상태어 → 위 4종 중 하나
STATUS_MAP = {
    "계산가능": "통과", "OK": "통과", "통과": "통과", "완료": "통과",
    "유효구간 확장 필요": "경고", "구간확장": "경고", "표본부족": "경고", "경고": "경고",
    "계산불가": "차단", "판정불가": "차단", "계산오류": "차단", "차단": "차단",
    "이 파일과 무관": "정보", "유효구간 밖": "정보", "대기": "정보", "정보": "정보",
}


def blank_safe(v) -> str:
    """비어 있으면 빈 문자열. **NaN을 "nan"으로 만들지 않는다.**

    CSV로 읽은 표는 빈 칸이 NaN(float)이 되는데, NaN은 falsy가 아니라 `or ""`를
    통과하고 `str()`이 "nan"을 만든다. 그 문자열이 화면 문구에 그대로 실린 적이 있다
    ("customers, nan는 이전 상태" — 2026-08-20). 값이 없는 것과 "nan"은 다르다.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


# ★ 같은 뜻의 색이라도 **바탕에 따라 밝기가 달라야 읽힌다.**
#   slate(#64748b)는 흰 종이에서는 알맞은 회색이지만 어두운 화면에서는 대비 3.63으로
#   AA(4.5)에 못 미친다(실측). 화면에서만 한 단계 밝은 회색을 쓴다.
#   ⚠️ 뜻의 대응(정보=slate)은 그대로다 — CLAUDE.md 7절이 금지한 것은 **대응 변경**이지
#      같은 색을 매체에 맞춰 조절하는 것이 아니다.
#   ⚠️ 전역 스위치로 만들지 않는다. 화면과 메일이 **같은 프로세스**에서 돌기 때문에
#      한쪽이 바꾸면 다른 쪽 배지까지 따라 바뀐다.
SCREEN_TONE = {"정보": "#94a3b8"}


def badge(text: str, kind: str | None = None, dark: bool = False) -> str:
    """상태 배지 HTML. kind를 안 주면 text로 색을 정한다.

    dark=True 는 **어두운 화면용**이다. 메일·PDF(흰 바탕)는 기본값을 쓴다.
    """
    key = STATUS_MAP.get(kind or text, "정보")
    color = (SCREEN_TONE.get(key) if dark else None) or STATUS[key][0]
    return (f'<span style="background:{color}22;color:{color};border:1px solid {color}55;'
            f'border-radius:6px;padding:1px 8px;font-size:0.82em;white-space:nowrap;">{text}</span>')


def load_catalog(name: str) -> tuple[dict, dict]:
    """catalog/{name}.json → (본문, _meta). 없으면 ({}, {})."""
    p = config.CATALOG_DIR / f"{name}.json"
    if not p.exists():
        return {}, {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    meta = doc.pop("_meta", {})
    return doc, meta


def read_csv(file) -> pd.DataFrame:
    """utf-8-sig 우선, 실패하면 cp949. (한글 CSV가 두 인코딩으로 온다)"""
    for enc in ("utf-8-sig", "cp949"):
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc)
        except UnicodeDecodeError:
            continue
    file.seek(0)
    return pd.read_csv(file, encoding="utf-8", errors="replace")


# 화면 카드와 이메일 본문이 보여줄 핵심 지표.
# ★ 두 곳에서 각자 고르면 **메일에는 있는 지표가 화면에는 없는** 상태가 된다.
#   받는 사람은 메일을 보고 화면을 열어보므로 목록이 같아야 한다.
# ⚠️ 아직 코드에 있다. 판정 기준(임계값)은 정의서로 옮겼지만 **무엇을 보여줄지**는
#   남아 있다 — 정의서에 `대시보드표시` 같은 필드를 두는 것이 같은 원칙의 다음 단계다.
# ★ 화면·메일 카드 지표는 **config에** 둔다. 코드에 두면 이식할 때
#   남의 도메인 지표가 카드에 떠서 빈 값이 나온다.
CARD_METRICS = getattr(config, "CARD_METRICS", None) or [
    "billed_revenue", "active_customers_contract", "arpu", "avg_data_usage"]

# 8단계 — CLAUDE.md 2절
STEPS = [
    (1, "데이터 파일 투입", "사용자"),
    (2, "스키마 점검 → 지표 계산", "시스템"),
    (3, "검증 실행", "시스템"),
    (4, "대시보드 렌더링", "시스템"),
    (5, "내용·검증 결과 확인", "사용자"),
    (6, "리포트 생성", "시스템"),
    (7, "이메일 초안 생성", "시스템"),
    (8, "발송 확정", "사용자"),
]


def unit_of(row) -> str:
    """지표의 표시 단위를 정한다.

    ★ `유형` 문자열만 믿지 않는다. 카탈로그에서 `avg_data_usage`의 유형이 **금액형**인데
      실제 값은 GB 평균이다. 유형대로 서식하면 `21.7 GB`가 `22원`으로 표시된다.
      그래서 **지표명·metric_id를 먼저 보고** 유형은 마지막 폴백으로 쓴다.
      순서도 중요하다 — `usage_decline_rate_3m`은 이름에 rate와 usage가 둘 다 들어 있어
      비율을 먼저 판정해야 한다.
    """
    # ★ 정의서가 `단위`를 선언하면 **그것을 쓴다.** 아래 추측 규칙은 폴백이다.
    #   추측은 도메인이 바뀌면 반드시 틀린다 — 재고 수량이 "명"으로 표시된 적이 있다.
    declared = str(row.get("단위") or "").strip()
    if declared:
        return declared

    mid = str(row.get("metric_id", ""))
    name = str(row.get("지표명", ""))
    typ = str(row.get("유형", ""))
    if "rate" in mid or name.endswith(("율", "비율")):
        return "%"
    if "data_usage" in mid or "데이터 사용량" in name:
        return "GB"
    # 금액을 개수보다 먼저 본다. '고객당 평균 매출'을 "고객"만 보고 명으로 찍는 사고가 있었다
    if "금액" in typ or any(k in name for k in ("매출", "비용", "손실", "수익", "단가", "금액")):
        return "원"
    if typ.startswith("카운트") or name.endswith(("수", "명")) or "사용자" in name:
        return "명"
    return ""


# 정수로 세는 단위 — 여기 빠지면 아래 폴백으로 떨어져 9,612,247이 "9.612e+06"으로 찍힌다.
COUNT_UNITS = ("명", "원", "개", "건", "종", "대", "kg", "EA")


def fmt_unit(v: float, unit: str) -> str:
    """숫자 + 단위 표기 — **fmt_value와 fmt_delta가 같은 규칙을 쓴다.**

    ★ 두 곳에 같은 규칙을 두면 반드시 갈라진다. 실제로 fmt_value만 고치고
      fmt_delta를 빠뜨려 변화 칸에만 "5.581e+04"가 남았다.
    """
    if unit in COUNT_UNITS:
        return f"{v:,.0f}{unit}"
    if unit == "GB":
        return f"{v:,.1f} GB"
    if unit:
        return f"{v:,.2f} {unit}"       # 모르는 단위도 지수 표기로 떨어뜨리지 않는다
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.4g}"


def fmt_value(row) -> str:
    """값을 단위에 맞춰 표시한다. 값이 없으면 —."""
    import math
    v = row.get("value")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    unit = unit_of(row)
    if unit == "%":
        return f"{v * 100:,.1f}%"
    if unit == "GB":
        return f"{v:,.1f} GB"
    return fmt_unit(v, unit)


def fmt_delta(row) -> str:
    """변화 칸 — 비율 지표는 %p, 나머지는 절대값 + 방향 화살표.

    ★ **증가가 좋은 지표인지 나쁜 지표인지는 판단하지 않는다.** 방향만 표시하고
      해석은 리포트가 한다. 대시보드가 좋고 나쁨을 칠하기 시작하면 보는 사람이
      화면의 판단을 그대로 옮겨 적게 된다.
    """
    import math
    pp = row.get("퍼센트포인트변화")
    if pp is not None and not (isinstance(pp, float) and math.isnan(pp)):
        return f"{pp:+.1f}%p"
    d = row.get("절대변화")
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return "—"
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "—")
    a, unit = abs(d), unit_of(row)
    body = f"{a * 100:,.1f}%p" if unit == "%" else fmt_unit(a, unit)
    return f"{arrow} {body}"


def fmt_rate(row) -> str:
    """변화율 칸 — 부호에 따라 색만 준다(증가 emerald / 감소 rose)."""
    import math
    r = row.get("상대변화율")
    if r is None or (isinstance(r, float) and math.isnan(r)):
        return "—"
    color = STATUS["통과"][0] if r > 0 else (STATUS["차단"][0] if r < 0 else STATUS["정보"][0])
    return f'<span style="color:{color};font-weight:600">{r:+.1f}%</span>'


def fmt_compact(row) -> str:
    """카드용 축약 서식 — 금액이 백만 이상이면 "27.8백만원".

    표에는 전체 자릿수를 쓰고 카드에만 축약을 쓴다. 카드는 훑어보는 자리라
    자릿수를 세게 만들면 안 되고, 표는 대조하는 자리라 값이 잘리면 안 된다.
    """
    import math
    v = row.get("value")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if unit_of(row) == "원" and abs(v) >= 1_000_000:
        return f"{v / 1_000_000:,.1f}백만원"
    return fmt_value(row)


def fmt_metric_delta(row) -> str | None:
    """st.metric의 delta 문자열 — "+314,819 (+1.15%)".

    ⚠️ `delta_color`는 항상 "normal"로 둔다. 값이 오른 게 좋은 일인지 나쁜 일인지
      **앱이 판단하지 않는다.** 화살표와 색은 방향 표시일 뿐이다.
    """
    import math
    d, r = row.get("절대변화"), row.get("상대변화율")
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return None
    pp = row.get("퍼센트포인트변화")
    if pp is not None and not (isinstance(pp, float) and math.isnan(pp)):
        head = f"{pp:+.1f}%p"
    elif unit_of(row) == "GB":
        head = f"{d:+,.2f}"
    elif unit_of(row) in ("원", "명"):
        head = f"{d:+,.0f}"
    else:
        head = f"{d:+,.4g}"
    tail = "" if r is None or (isinstance(r, float) and math.isnan(r)) else f" ({r:+.2f}%)"
    return head + tail


def validation_table(items: list[dict]) -> str:
    """검증 항목 표 HTML — 3단계와 4단계가 **같은 함수**를 쓴다.

    두 곳에서 각자 그리면 색이나 열 구성이 갈라진다. 같은 검증 결과가 화면마다
    다르게 보이면 사용자가 어느 쪽을 믿어야 할지 알 수 없다.
    """
    # "기준" = 판정에 쓴 값과 그 출처. 이 열을 쓰는 검증(전월 대비)만 채운다
    has_basis = any(x.get("기준") for x in items)
    basis_th = "<th align='left'>기준</th>" if has_basis else ""
    head = (f"<tr><th align='left'>검증</th><th align='left'>대상</th>"
            f"<th align='left'>판정</th>{basis_th}<th align='left'>상세</th></tr>")

    def basis_td(x):
        """기준이 없는 행은 빈칸. **"기본값"은 회색으로 낮춰** 정의서 값과 구분한다.

        어느 임계값으로 판정했는지가 안 보이면 왜 경고가 났는지 알 수 없고,
        그것이 근거를 갖고 정한 값인지 손대지 않은 기본값인지도 구분돼야 한다.
        """
        if not has_basis:
            return ""
        v = str(x.get("기준") or "")
        color = "var(--tk-text-faint)" if "기본값" in v else "var(--tk-text)"
        return f"<td style='font-size:0.88em;color:{color};white-space:nowrap'>{v}</td>"

    body = "".join(
        f"<tr><td>{x['검증명']}</td><td>{x['대상지표']}</td>"
        f"<td>{badge(x['판정'])}</td>{basis_td(x)}"
        f"<td style='font-size:0.88em;color:var(--tk-text-dim)'>{x['상세']}</td></tr>" for x in items)
    return f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>"


# ── 게이트 2 체크리스트 ───────────────────────────────────────────────
def build_checklist(period: str, validation: dict, metrics_df, comparison_df) -> list[dict]:
    """5단계 확인 체크리스트를 **이번 실행 결과에서** 만든다.

    ★ 항목 문구에 값을 박지 않는다. "경고 2건"이라고 적어두면 다음 달에 3건이어도
      2건이라고 쓴다. 체크리스트가 실제와 어긋나면 읽는 사람이 그 순간부터 안 읽는다.

    ★ 해당 사항이 없는 항목은 **지우지 않고 "해당 없음"으로 남긴다.**
      항목이 사라지면 "이번엔 부분 갱신이 없었다"는 사실도 함께 사라진다.
      다만 체크는 요구하지 않는다 — 없는 것을 확인하라고 시키면 형식적 클릭이 된다.

    반환: [{키, 라벨, 상세, 해당}] — `해당=False`면 자동 충족(체크 불필요)
    """
    items = []

    # ① 기간 — 의도한 달을 계산했는가
    months = sorted({str(m) for m in metrics_df["month"]}) if len(metrics_df) else []
    items.append({
        "키": "기간",
        "라벨": f"계산 대상 기간이 의도한 기간인가 ({period})",
        "상세": (f"결과표의 대상 월: {', '.join(months) or '—'}\n\n"
                 "업로드 파일에서 판정한 기간입니다. 파일이 다른 달의 데이터였다면 "
                 "여기서 드러납니다."),
        "해당": True,
    })

    # ② 경고 — 무엇이 걸렸는지 읽었는가
    warns = [x for x in validation["항목"] if x["판정"] == "경고"]
    detail = "\n".join(
        f"- **{x['대상지표']}** · {x['검증명']} — {x['상세']}"
        + (f"  \n  적용 기준: {x['기준']}" if x.get("기준") else "")
        for x in warns) or "경고 항목이 없습니다."
    items.append({
        "키": "경고",
        "라벨": f"경고 항목을 확인했는가 ({len(warns)}건)",
        "상세": detail,
        "해당": bool(warns),
    })

    # ③ 부분 갱신 — 옛 상태인 테이블이 섞였는가
    partial = {}
    if len(metrics_df) and "부분갱신" in metrics_df:
        for _, r in metrics_df.iterrows():
            # ⚠️ CSV로 읽으면 빈 칸이 NaN(float)이 된다. NaN은 falsy가 아니라
            #    `or ""`를 통과하고 str()이 "nan"을 만든다 — 그 문자열이 그대로
            #    체크리스트 문구에 실려 "customers, nan는 이전 상태"가 됐다.
            for t in str(blank_safe(r.get("부분갱신"))).split(","):
                if t.strip():
                    partial.setdefault(t.strip(), []).append(r["지표명"])
    p_txt = "\n".join(f"- `{t}` — {', '.join(ms)}" for t, ms in sorted(partial.items()))
    items.append({
        "키": "부분갱신",
        "라벨": ("부분 갱신 지표의 한계를 이해했는가 "
                 + (f"({', '.join(sorted(partial))}는 이전 상태)" if partial else "(해당 없음)")),
        "상세": (p_txt + "\n\n이 지표들은 계산은 되지만 위 테이블이 **이번에 갱신되지 않은 "
                 "옛 상태**입니다. 값이 틀린 것은 아니고, 시점이 섞여 있습니다."
                 if partial else "이번 실행에서 부분 갱신된 지표가 없습니다."),
        "해당": bool(partial),
    })

    # ④ 자동 검증하지 않은 것 — 검증 통과가 무엇을 뜻하지 않는지
    items.append({
        "키": "미자동검증",
        "라벨": (f"자동 검증하지 않은 항목을 인지했는가 "
                 f"({len(validation['자동검증하지_않은_것'])}종)"),
        "상세": "\n".join(f"- {s}" for s in validation["자동검증하지_않은_것"])
                + "\n\n**검증 통과는 이 항목들을 통과했다는 뜻이 아닙니다.** "
                  "판단이 필요해 자동화하지 않았고, 리포트 한계 절에 명시됩니다.",
        "해당": True,
    })
    return items


def result_files(run_dir, key: str = "") -> None:
    """이번 실행이 남긴 파일을 **화면에서 바로 받게** 한다.

    Streamlit은 `file://` 링크를 열지 못한다(브라우저가 막는다). 그래서 경로만 적어두면
    사용자는 탐색기를 열어 찾아 들어가야 한다 — 그러면 대부분 확인하지 않는다.
    표에 보이는 숫자가 저장된 값과 같은지 확인할 길을 화면 안에 둔다.

    있는 파일만 버튼을 만든다. 없는 파일 버튼을 회색으로 두면 "아직 안 만들어졌다"와
    "만들다 실패했다"가 구분되지 않는다.
    """
    import streamlit as st
    from pathlib import Path as _P

    d = _P(run_dir)
    specs = [("metrics.csv", "계산 결과", "text/csv"),
             ("comparison.csv", f"{_PREV} 대비", "text/csv"),
             ("validation.json", "검증 결과", "application/json"),
             ("run_log.json", "실행 기록", "application/json")]
    have = [(n, label, mime) for n, label, mime in specs if (d / n).exists()]
    if not have:
        return
    st.caption(f"결과 파일 — `{d.name}/`")
    for col, (n, label, mime) in zip(st.columns(len(have)), have):
        col.download_button(f"{label} ↓", (d / n).read_bytes(), file_name=n,
                            mime=mime, key=f"dl_{key}_{n}", width="stretch")


def build_send_checklist(mail: dict, validation: dict, unwritten: list[dict],
                         attachments: list[dict]) -> list[dict]:
    """게이트 3(발송 확정) 체크리스트 — **게이트 2보다 항목이 많다.**

    ★ 발송은 되돌릴 수 없다. 잘못된 숫자가 담긴 메일이 나가면 회수할 수 없고,
      **받는 사람은 이미 그 숫자를 봤다.** 그래서 확인 항목이 더 많다.

    게이트 2와 같은 규칙: 문구에 값을 박지 않고 **이번 실행 결과에서** 만든다.
    """
    v = validation or {}
    items = [
        {"키": "기간",
         "라벨": f"대상 기간이 맞다 ({mail.get('기간') or '—'})",
         "상세": "리포트·이메일 모두 이 기간으로 계산되었습니다. "
                 "**지난달 리포트를 이번 달로 보내는 사고**가 여기서 걸립니다.",
         "해당": True},
        {"키": "수신자",
         "라벨": f"수신자가 맞다 ({len(mail.get('to') or [])}명)",
         "상세": "\n".join(f"- {a}" for a in (mail.get("to") or []))
                 + f"\n\n발신 `{mail.get('from', '—')}`\n\n"
                   "**잘못된 사람에게 가면 되돌릴 수 없습니다.**",
         "해당": True},
        {"키": "경고",
         "라벨": f"검증 경고 {v.get('경고수', 0)}건을 확인했다",
         "상세": "\n".join(
             f"- **{x['대상지표']}** · {x['검증명']} — {x['상세']}"
             for x in v.get("항목", []) if x.get("판정") == "경고")
             or "경고 항목이 없습니다.",
         "해당": bool(v.get("경고수"))},
    ]

    # ★ 미작성 장이 있어도 **차단하지 않는다.** 초안 공유가 목적일 수 있다.
    #   대신 문구를 강하게 만들어 "모르고 보냈다"가 되지 않게 한다.
    if unwritten:
        names = " · ".join(f"{s['번호']}장 {s['제목']}" for s in unwritten)
        items.append({
            "키": "미작성",
            "라벨": f"{names}이 **비어 있는 상태로 발송**하는 것을 확인했습니다",
            "상세": "초안 공유가 목적일 수 있으므로 차단하지 않습니다. "
                    "대신 **제목에 (초안)이 표시**됩니다.\n\n"
                    "이 장들은 판단이 필요해 앱이 쓰지 않습니다.",
            "해당": True})
    else:
        items.append({"키": "미작성", "라벨": "미작성 장 없음", "상세": "모든 장이 작성되었습니다.",
                      "해당": False})

    lines = [f"- `{a['filename']}` "
             + (f"{a['size'] / 1024:,.0f} KB" if a.get("존재", True) else "**없음**")
             for a in attachments]
    items.append({
        "키": "첨부",
        "라벨": f"첨부 파일 목록을 확인했다 ({sum(1 for a in attachments if a.get('존재', True))}개)",
        "상세": "\n".join(lines) + "\n\n실제 첨부는 8주차에 구현합니다 — "
                "지금은 파일명·크기만 목록으로 담습니다.",
        "해당": True})
    return items


def not_automated_box(items: list[str]) -> str:
    """자동 검증하지 않은 항목 — slate 박스.

    ★ 이 박스를 빼면 "검증 통과"가 실제보다 강한 신뢰를 준다.
      3단계(검증 전용)와 4단계(결과 확인) **양쪽에** 붙인다.
    """
    slate = STATUS["정보"][0]
    lis = "".join(f"<li style='margin:3px 0'>{s}</li>" for s in items)
    return (f"<div style='border:1px solid {slate}55;background:{slate}12;border-radius:10px;"
            f"padding:12px 18px;margin-top:12px'>"
            f"<b style='color:{slate}'>이 검증은 수행되지 않았습니다</b>"
            f"<ul style='margin:8px 0 4px 18px;color:var(--tk-text-dim);font-size:0.92em'>{lis}</ul>"
            f"<div style='color:var(--tk-text-faint);font-size:0.88em'>이 항목들은 판단이 필요해 자동화하지 "
            f"않았습니다. 리포트 한계 절에 명시됩니다.</div></div>")


# ── 추이 차트 ─────────────────────────────────────────────────────────
# DESIGN.md의 Tailwind 500 팔레트
LINE = {"blue": "#3b82f6", "emerald": "#10b981", "amber": "#f59e0b",
        "violet": "#8b5cf6", "rose": "#f43f5e", "slate": "var(--tk-text-faint)"}

# ★ 차트 스펙은 **config에** 둔다. 어떤 지표를 어떤 축에 그릴지는 프로젝트마다 다르고,
#   코드에 두면 이식할 때 화면이 남의 도메인 지표로 덮인다.
CHART_SPECS = getattr(config, "CHART_SPECS", None) or [
    {"key": "revenue", "title": "매출 추이",
     "left": [("billed_revenue", "청구 매출", LINE["blue"]),
              ("billed_revenue_active", "활성 계약 청구 매출", LINE["emerald"])],
     "right": [], "left_title": "원", "right_title": "",
     "caption": "단일 축(원). 축 범위는 데이터 범위에 여유를 준 값이며 0에서 시작하지 않습니다."},
]

def _range(vals: list[float], pad: float = 0.08) -> list[float] | None:
    """축 범위를 데이터에서 정하되 **코드가 명시적으로 계산**한다.

    ★ 자동 범위에 맡기면 데이터가 바뀔 때마다 인상이 달라지고 아무도 눈치채지 못한다.
      범위를 정하고 캡션에 적는 것이 유일한 방어다.
    """
    vals = [v for v in vals if v is not None and v == v]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [lo * 0.9, hi * 1.1] if lo else [0, 1]
    m = (hi - lo) * pad
    return [lo - m, hi + m]


def trend_chart(trend_df, spec: dict, current_period: str,
                left_range: list | None = None,
                right_range: list | None = None,
                title: str | None = None, height: int = 330):
    """추이 차트 하나를 그린다.

    지키는 것
      · **추세선을 넣지 않는다** — 6개월로는 계절성을 판별할 수 없다.
      · 유효구간 밖은 값 None + `connectgaps=False` → **선이 끊긴다.** 0으로 잇지 않는다.
      · 당월 지점에 마커를 키워 **업로드 데이터로 계산한 달**임을 표시한다.
      · 이중 축을 쓸 때는 두 축 범위를 **코드에서 명시**하고 캡션에 경고를 단다.
    """
    import plotly.graph_objects as go

    fig, used = go.Figure(), False
    for side in ("left", "right"):
        for mid, label, color in spec[side]:
            d = trend_df[trend_df["metric_id"] == mid].sort_values("month")
            if d.empty:
                continue
            used = True
            ys = [None if v != v else v for v in d["value"]]
            if mid.endswith("_rate") or unit_of({"metric_id": mid, "지표명": label}) == "%":
                ys = [None if y is None else y * 100 for y in ys]
            # ★ 정규화 — 크기가 다른 지표를 한 축에 놓을 때 절대값은 **큰 값이 작은 변화를 가린다.**
            #   재고 4구분(핸들링 6억 vs A/S창고 2억)이 전부 평평한 선으로 보였다.
            #   실제 주간보고가 읽는 것도 절대액이 아니라 **증감**이다.
            #     "index"  첫 기간 = 100 (상대 추이)
            #     "change" 첫 기간 대비 % 변화 (0 기준선)
            norm = spec.get("normalize")
            if norm in ("index", "change"):
                base = next((y for y in ys if y not in (None, 0)), None)
                if base:
                    ys = [None if y is None else
                          (y / base * 100 if norm == "index" else (y / base - 1) * 100)
                          for y in ys]
            sizes = [11 if m == current_period else 6 for m in d["month"]]
            fig.add_trace(go.Scatter(
                x=list(d["month"]), y=ys, name=label, mode="lines+markers",
                connectgaps=False,                       # ★ 끊긴 곳을 잇지 않는다
                line=dict(color=color, width=2),
                marker=dict(color=color, size=sizes,
                            line=dict(color="white", width=1)),
                yaxis="y2" if side == "right" else "y"))
    if not used:
        return None

    lys = [y for tr in fig.data if tr.yaxis in (None, "y") for y in tr.y]
    rys = [y for tr in fig.data if tr.yaxis == "y2" for y in tr.y]
    fig.update_layout(
        title=dict(text=title or spec["title"], font=dict(size=15)),
        height=height, margin=dict(l=10, r=10, t=44, b=10),
        hovermode="x unified", legend=dict(orientation="h", y=-0.22),
        # 월 문자열을 날짜로 자동 해석하면 눈금이 일부만 찍힌다.
        # 축은 **월 목록**이지 연속 시간축이 아니므로 category로 고정한다.
        xaxis=dict(type="category", tickmode="array",
                   tickvals=sorted(trend_df["month"].unique())),
        yaxis=dict(title=spec["left_title"], range=left_range or _range(lys)),
        yaxis2=dict(title=spec["right_title"], overlaying="y", side="right",
                    range=right_range or _range(rys),
                    showgrid=False) if spec["right"] else None,
        plot_bgcolor="rgba(0,0,0,0)")
    return fig
