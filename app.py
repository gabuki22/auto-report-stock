# -*- coding: utf-8 -*-
"""기간 리포트 자동화 — 8단계 앱 (6주차 Day1: 1~2단계 전반)

사용자는 넣기 한 번, 승인 세 번만 한다. 승인 없이 다음 단계로 넘어가지 않는다.
실행: py -m streamlit run app.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import pandas as pd

import common
import config

# ★ 기간 이름은 config 한 곳에서 온다 — 화면·이메일·리포트가 같은 말을 쓰게 한다.
#   ⚠️ 이것은 **표시 문자열**이다. `r["당월"]`·`c.get("전월")`은 DataFrame
#      컬럼 키이므로 바꾸면 안 된다 — 표시와 키를 한꺼번에 치환하면 조용히 깨진다.
_PERIOD = getattr(config, "PERIOD_LABEL", "월간")
_PREV = getattr(config, "PREV_LABEL", "전월")
_CURR = getattr(config, "CURR_LABEL", "당월")
from pipeline import calculate as calc
from pipeline import manual_sections as ms
from pipeline import charts as ch
from pipeline import email_draft as ed
from pipeline import compare as cmp
from pipeline import profile as pf
from pipeline import pdf_render as pr
from pipeline import report as rp
from pipeline import run_log as rl
from pipeline import validate as vd

st.set_page_config(page_title=config.APP_TITLE, layout="wide")


@st.cache_data(show_spinner="PDF 만드는 중…")
def make_pdf_cached(md: str, ctx: dict) -> bytes:
    """리포트 마크다운 → PDF. **문자열·dict만 인자로 받아** 캐시가 먹게 한다.

    DataFrame을 넘기면 Streamlit이 해시하지 못해 캐시가 매번 빗나가고,
    rerun마다 7쪽을 다시 그려 화면이 눈에 띄게 느려진다.
    """
    return pr.build_pdf(md, ctx)

def restore_run(run_dir: Path) -> None:
    """저장된 실행 폴더를 화면 상태로 되살린다 — **CLI가 만든 것도 포함.**

    ★ **게이트를 건너뛰지 않는다.** 파일이 있다고 해서 승인이 있었던 것은 아니다.
      게이트 2 통과 여부는 실행 기록의 `게이트2` 블록으로 판단한다 — CLI로 만든
      실행은 그 블록이 없으므로 화면에서 사람이 5단계를 확인해야 6단계가 열린다.
      "사람이 하는 단계를 CLI가 대신하지 않는다"가 불러오기에서도 유지된다.
    """
    ss = st.session_state
    log = rl.load(run_dir)
    # 추이는 BigQuery로 다시 계산하지 않고 **저장된 것을 읽는다**(배포본 대응).
    _tf = run_dir / "trend.csv"
    ss.trend_df = (pd.read_csv(_tf, encoding="utf-8-sig") if _tf.exists() else None)
    ss.run_dir = str(run_dir)
    ss.filename = rl.field(log, "파일명")

    # 업로드 원본은 run 폴더에 복사돼 있다(재현성용) — 그대로 되읽는다
    src = run_dir / str(ss.filename or "")
    ss.df = common.read_csv(src.open("rb")) if src.exists() else None
    ss.raw = src.read_bytes() if src.exists() else None
    ss.upload_sig = None
    # 업로더 위젯을 새로 만들어 남아 있던 파일을 떨군다 — 위 uploader_key 주석 참고
    ss.uploader_key = ss.get("uploader_key", 0) + 1

    def _csv(name):
        p = run_dir / name
        if not p.exists():
            return None
        d = pd.read_csv(p, encoding="utf-8-sig")
        if "포함사유" in d:
            d["포함사유"] = d["포함사유"].fillna("")
        return d

    ss.metrics_df, ss.comparison_df = _csv("metrics.csv"), _csv("comparison.csv")
    vp = run_dir / "validation.json"
    ss.validation = json.loads(vp.read_text(encoding="utf-8")) if vp.exists() else None

    # ★ `field()`로 읽는다 — 단계별 구조 도입 전에 만들어진 실행은 기록이 평평해
    #   `log["게이트2"]`가 없다. 블록으로만 보면 **이미 확인한 실행을 미확인으로**
    #   판정해 사람에게 같은 확인을 두 번 시킨다.
    ss.confirmed_at = rl.field(log, "확인_완료_시각")
    ss.override_at = rl.field(log, "확정_시각")

    rp_path = run_dir / "report.md"
    ss.report_md = rp_path.read_text(encoding="utf-8") if rp_path.exists() else None
    ss.merge_info = None            # 병합 내역은 기록에서 다시 읽지 않는다(표시용일 뿐)
    ss.pdf_ctx = {"기간": str(ss.metrics_df["month"].iloc[0]) if ss.metrics_df is not None else "",
                  "생성일시": (log.get("6_리포트") or {}).get("시각", "—"),
                  "파일명": ss.filename,
                  "카탈로그_메타": {"생성일시": rl.field(log, "카탈로그_생성일시", "?")}}

    mp = run_dir / "email_meta.json"
    if mp.exists() and ss.report_md:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        ss.email = {**meta,
                    "body_html": (run_dir / "email.html").read_text(encoding="utf-8"),
                    "body_text": (run_dir / "email.txt").read_text(encoding="utf-8")}
    else:
        ss.email = None

    # 어디까지 왔는지 — **파일 존재가 아니라 승인 상태로** 정한다
    if (run_dir / "APPROVED").exists():
        ss.step = 8
    elif not ss.confirmed_at:
        ss.step = 5                 # CLI 결과: 산출물은 있지만 사람 확인이 없다
    elif ss.email:
        ss.step = 8
    else:
        ss.step = 6


ss = st.session_state
ss.setdefault("step", 1)
ss.setdefault("df", None)
ss.setdefault("filename", None)
ss.setdefault("raw", None)          # 업로드 원본 바이트 — 재현성용 복사에 쓴다
ss.setdefault("run_dir", None)      # 확정 후 생성된 실행 폴더
ss.setdefault("override_at", None)  # 유효구간 확장 승인 시각
ss.setdefault("metrics_df", None)   # 계산 결과 (재실행 방지)
ss.setdefault("upload_sig", None)   # (파일명, 크기) — 같은 파일의 rerun과 새 파일을 가른다
ss.setdefault("comparison_df", None)  # 전월 대비 결과
ss.setdefault("validation", None)     # 검증 결과
ss.setdefault("sql_log", None)        # 실제 실행된 SQL (지표별)
ss.setdefault("dep_values", None)     # 재귀로 계산된 의존 지표 값
ss.setdefault("trend_df", None)       # 최근 N개월 추이
ss.setdefault("confirmed_at", None)   # 게이트 2 — 사람이 확인을 끝낸 시각
ss.setdefault("report_md", None)      # 6단계 — 생성된 리포트 마크다운
ss.setdefault("pdf_ctx", None)        # PDF 표지용 (직렬화 가능한 값만)
ss.setdefault("merge_info", None)     # 사람 작성분 병합 결과 (병합·미작성·경고)
ss.setdefault("email", None)          # 7단계 — 이메일 초안 (subject·to·body·첨부)
# ★ 업로더 위젯 키. 기존 실행을 불러온 뒤 이 값을 올려 **위젯을 새로 만든다.**
#   그러지 않으면 업로더에 남아 있던 파일이 다음 rerun에서 다시 읽혀
#   방금 불러온 상태를 통째로 덮어쓴다(조용히 1단계로 되감긴다).
ss.setdefault("uploader_key", 0)

metrics, m_meta = common.load_catalog("metrics_catalog")
schema, s_meta = common.load_catalog("schema_catalog")
insights, i_meta = common.load_catalog("insights_catalog")

# ── 사이드바 ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 카탈로그")
    if not metrics or not schema:
        st.error("카탈로그가 없습니다. export를 먼저 실행하세요.")
        st.code("py -X utf8 catalog/export_catalog.py", language="bash")
    else:
        st.markdown(f"- 지표 **{len(metrics)}종**\n- 테이블 **{len(schema)}종**")
        st.caption(f"생성 {m_meta.get('생성일시', '?')}")
        st.caption(f"위키 {config.WIKI_PATH.name if config.WIKI_PATH else '미지정'}")

    # ★ 이 두 칸은 **지금 채우지 않는다.** 사이드바는 스크립트 맨 위에서 그려지는데
    #   계산·검증은 아래에서 일어나므로, 여기서 값을 읽으면 **한 박자 전 상태**가 찍힌다
    #   (검증이 끝났는데 사이드바엔 안 보이는 현상). 자리만 잡아두고 맨 끝에서 채운다.
    run_slot = st.empty()

    # ── 기존 실행 불러오기 ────────────────────────────────────────────
    # ★ 8주차 그림: **CLI가 밤에 초안까지 만들어두고, 사람이 아침에 화면에서
    #   확인하고 보낸다.** 그 흐름을 지금 만들어 둔다.
    st.markdown("---")
    st.markdown("### 기존 실행 불러오기")
    runs_all = sorted(config.OUTPUTS_DIR.glob("run_*"), reverse=True) \
        if config.OUTPUTS_DIR.exists() else []
    if not runs_all:
        st.caption("아직 실행 기록이 없습니다.")
    else:
        def _label(d: Path) -> str:
            mark = "✔" if (d / "APPROVED").exists() else "·"
            return f"{mark} {d.name}"
        pick = st.selectbox("실행 폴더", ["(선택 안 함)"] + [_label(d) for d in runs_all],
                            label_visibility="collapsed", key="pick_run")
        if pick != "(선택 안 함)":
            picked = next(d for d in runs_all if d.name == pick.split(" ", 1)[1])
            if st.button("이 실행 불러오기", key="load_run", width="stretch"):
                restore_run(picked)
                st.rerun()
        st.caption("✔ = 발송 확정된 실행")

    st.markdown("---")
    st.markdown("### 진행 단계")
    step_slot = st.empty()

st.title(config.APP_TITLE)
st.caption("파일을 넣으면 판정·계산·검증·리포트까지 흐릅니다. 사용자는 넣기 1회 + 승인 3회.")

# ── 1단계 — 데이터 파일 투입 ──────────────────────────────────────────
st.markdown("---")
done1 = ss.df is not None
st.markdown(f"## 1단계 — 데이터 파일 투입 "
            f"{common.badge('완료' if done1 else '진행중', '통과' if done1 else '경고')}",
            unsafe_allow_html=True)

# ★ 자격증명이 없으면 업로드를 **아예 막는다.**
#   1~4단계는 BigQuery로 계산하므로 인증 없이는 '스테이징 적재 중...'에서 멈춘다.
#   되지 않을 일을 시작하게 두고 오류로 알려주는 것보다, 시작 전에 막고 되는 길을 가리키는 편이 낫다.
#   결과를 세션에 캐시한다 — 매 rerun마다 자격증명을 찾으면 화면이 느려진다.
if "bq_auth" not in ss:
    ss.bq_auth = calc.auth_available()

if not ss.bq_auth:
    st.info("🔒 **읽기 전용으로 열려 있습니다** — 이 배포본에는 BigQuery 자격증명이 없어 "
            "새 파일을 계산할 수 없습니다.\n\n"
            "왼쪽 **기존 실행 불러오기**에서 **✔ 표시된 실행**을 고르면 "
            "1~8단계 전 과정과 리포트·이메일 확정본을 그대로 볼 수 있습니다.")
    st.caption("새 파일로 직접 돌려 보려면 저장소를 내려받아 로컬에서 실행합니다 — README 참고.")
    up = None
else:
    up = st.file_uploader("CSV 파일을 올리세요", type=["csv"],
                          label_visibility="collapsed",
                          key=f"uploader_{ss.uploader_key}")
if up is not None:
    # ★ file_uploader는 **새 파일을 고를 때만이 아니라 모든 rerun마다** 같은 파일 객체를
    #   계속 돌려준다. 그래서 이 블록을 조건 없이 실행하면 확정 직후의 rerun에서
    #   run_dir이 지워져 게이트가 미확정으로 되감기고, 계산이 영영 시작되지 않는다
    #   (오류가 아니라 조용히 되돌아가서 화면에 아무 메시지도 안 뜬다 — 2026-08-18 실제 사고).
    #   파일이 **실제로 바뀐 경우에만** 다시 읽고 이전 확정을 무효화한다.
    sig = (up.name, up.size)
    if ss.upload_sig != sig:
        ss.df, ss.filename, ss.raw = common.read_csv(up), up.name, up.getvalue()
        ss.upload_sig = sig
        ss.step = max(ss.step, 2)
        ss.run_dir = ss.metrics_df = ss.comparison_df = ss.validation = ss.sql_log = ss.dep_values = ss.trend_df = None
        ss.confirmed_at = ss.report_md = ss.pdf_ctx = ss.merge_info = ss.email = None   # 새 파일이면 게이트 2·리포트·초안 무효

if ss.df is not None:
    df = ss.df
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("파일", ss.filename)
    c2.metric("크기", f"{df.memory_usage(deep=True).sum() / 1024:,.1f} KB")
    c3.metric("행수", f"{len(df):,}")
    c4.metric("컬럼 수", f"{df.shape[1]}")
    with st.expander("컬럼 목록 · 앞 5행 미리보기", expanded=False):
        st.code(", ".join(df.columns), language=None)
        st.dataframe(df.head(), width='stretch')

# ── 2단계 — 스키마 점검 → 지표 계산 (전반: 판정) ──────────────────────
st.markdown("---")
if ss.df is None:
    st.markdown(f"## 2단계 — 스키마 점검 → 지표 계산 {common.badge('대기', '정보')}",
                unsafe_allow_html=True)
    st.caption("1단계에서 파일을 올리면 판정이 시작됩니다.")
else:
    st.markdown(f"## 2단계 — 스키마 점검 → 지표 계산 {common.badge('진행중', '경고')}",
                unsafe_allow_html=True)
    df = ss.df

    # 1. 테이블 판정
    t = pf.judge_table(df, schema)
    ok = t.get("판정가능")
    st.markdown(f"### 1. 테이블 판정 &nbsp; {common.badge(t.get('테이블명', '판정 불가'), '통과' if ok else '차단')} "
                f"&nbsp; 일치율 **{t.get('일치율', 0):.0%}** ({t.get('일치', 0)}/{t.get('카탈로그컬럼수', 0)})",
                unsafe_allow_html=True)
    if not ok:
        st.error(t.get("이유", "판정 불가"))
    if t.get("누락컬럼"):
        st.markdown(f"{common.badge('누락 컬럼', '경고')} &nbsp; `{'`, `'.join(t['누락컬럼'])}`",
                    unsafe_allow_html=True)
    if t.get("추가컬럼"):
        st.markdown(f"{common.badge('추가 컬럼', '정보')} &nbsp; 카탈로그에 없음 · `{'`, `'.join(t['추가컬럼'])}`",
                    unsafe_allow_html=True)
    if t.get("테이블명_추정"):
        st.caption(f"테이블명은 노트명 `{t.get('노트명')}`에서 유도한 **추정값**입니다. "
                   f"확정하려면 위키 프론트매터에 `bq_table`을 추가하세요.")

    # 2. Profile
    p = pf.profile_data(df, schema.get(t.get("테이블명"), {}))
    st.markdown("### 2. Profile")
    per, gr = p["기간"], p["그레인"]
    cells = [
        ("행수", f"{p['행수']:,}", "통과"),
        ("컬럼 수", str(p["컬럼수"]), "통과"),
        ("기간", f"{per.get('최소', '?')} ~ {per.get('최대', '?')}" if per else "기간 컬럼 없음",
         "통과" if per else "경고"),
        ("결측", "없음" if not p["결측"] else f"{p['결측합계']:,}건",
         "통과" if not p["결측"] else "경고"),
        ("그레인 중복", f"{gr.get('중복', 0)}건" if gr else "검사 불가",
         "통과" if gr and gr.get("유일") else "경고"),
    ]
    cols = st.columns(len(cells))
    for col, (label, cellval, kind) in zip(cols, cells):
        col.markdown(f"**{label}**<br>{cellval} {common.badge('통과' if kind == '통과' else '경고', kind)}",
                     unsafe_allow_html=True)
    if gr:
        st.caption(f"그레인 키: {' × '.join(gr['키'])}")
    if p["결측"]:
        st.caption("결측 컬럼: " + ", ".join(f"{c} {n}건" for c, n in p["결측"].items()))

    # 3. 지표 판정
    # ★ 기간을 무조건 월(앞 7자)로 접지 않는다.
    #   주간 스냅샷은 한 파일이 **한 날짜**만 담는다. 월로 접으면 그 주가 아니라
    #   그 달 전체를 계산하게 되어, 전주 대비가 한 달치와 비교된다(14.9억이 44억으로).
    #   파일이 한 시점만 담고 있으면 그 날짜를 그대로 쓰고, 여러 시점이면 월로 접는다.
    _lo = (per.get("최소") or "") if per else ""
    _hi = (per.get("최대") or "") if per else ""
    period = _lo if (_lo and _lo == _hi and str(_lo).count("-") >= 2) else str(_lo)[:7]
    rows = pf.judge_metrics(t.get("테이블명"), period, metrics, t.get("누락컬럼"))
    related = [r for r in rows if r["상태"] != "이 파일과 무관"]
    unrelated = [r for r in rows if r["상태"] == "이 파일과 무관"]
    blocked = [r for r in related if r["상태"] == "계산불가"]
    target = [r for r in related if r["상태"] != "계산불가"]      # 실제로 돌릴 것
    ext = [r for r in target if r["상태"] == "유효구간 확장 필요"]
    partial = [r for r in target if r["부분갱신"]]

    st.markdown("### 3. 지표 판정")

    def table(rs: list[dict]) -> str:
        head = ("<tr><th align='left'>지표명</th><th align='left'>metric_id</th>"
                "<th align='left'>상태</th><th align='left'>이유</th><th align='left'>원천</th></tr>")
        body = "".join(
            f"<tr><td>{r['지표명']}</td><td><code>{r['metric_id']}</code></td>"
            f"<td>{common.badge(r['상태'])}</td>"
            f"<td style='font-size:0.88em;color:#475569'>{r['이유'] or '—'}</td>"
            f"<td style='font-size:0.88em;color:#475569'>{r['원천']}</td></tr>" for r in rs)
        return (f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>")

    st.markdown(table(related), unsafe_allow_html=True)
    with st.expander(f"이 파일과 무관한 지표 {len(unrelated)}종", expanded=False):
        st.markdown(table(unrelated), unsafe_allow_html=True)

    # 4. 요약 한 줄
    st.markdown("---")
    st.info(f"**계산 대상 {len(target)}종** (그중 유효구간 확장 필요 {len(ext)}종"
            + (f", 부분 갱신 {len(partial)}종" if partial else "")
            + (f") · **계산불가 {len(blocked)}종**" if blocked else ")")
            + f", 무관 {len(unrelated)}종")

    # ── 게이트 1 — 사용자 승인 ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🚦 게이트 1 — 이 판정으로 계산할까요")

    # 차단 조건 — 누락 컬럼이 있다고 무조건 막지 않는다.
    # 그 컬럼을 쓰는 지표만 떨어뜨리고, 남은 게 있으면 "일부만 계산"을 고르게 한다.
    # 전부 불가일 때만 막는다.
    blockers = []
    if not ok:
        blockers.append(t.get("이유") or "테이블을 판정하지 못했습니다")
    if not target:
        blockers.append(
            f"이 파일로 계산할 수 있는 지표가 없습니다"
            + (f" — 누락 컬럼 {', '.join(t['누락컬럼'])}" if t.get("누락컬럼") else ""))

    with st.container(border=True):
        g1, g2 = st.columns(2)
        g1.markdown("<br>".join([
            f"**대상 파일** {ss.filename}",
            f"**판정 테이블** <code>{t.get('테이블명', '—')}</code> (일치율 {t.get('일치율', 0):.0%})",
            f"**기간** {period or '—'}",
            f"**행수** {p['행수']:,}",
        ]), unsafe_allow_html=True)
        g2.markdown("<br>".join([
            f"**계산 대상** {len(target)}종",
            f"**유효구간 확장 필요** {len(ext)}종",
            f"**부분 갱신** {len(partial)}종",
            f"**카탈로그 생성** {m_meta.get('생성일시', '?')}",
        ]), unsafe_allow_html=True)

    if blockers:
        for b in blockers:
            st.error(b)

    partial_ok = True
    if blocked and target:
        st.markdown(f"{common.badge('계산불가', '차단')} &nbsp; **{len(blocked)}종** — "
                    + " · ".join(f"{r['지표명']}" for r in blocked), unsafe_allow_html=True)
        partial_ok = st.checkbox(
            f"**일부만 계산**합니다 — 가능한 {len(target)}종만 돌리고 {len(blocked)}종은 건너뜁니다",
            key="partial_ok")
        st.caption(f"누락 컬럼 `{'`, `'.join(t.get('누락컬럼') or [])}` 때문입니다. "
                   "건너뛴 지표는 실행 기록에 사유와 함께 남고, 리포트에서 빈칸이 아니라 "
                   "**계산불가**로 표시됩니다.")

    approved = True
    if ext:
        approved = st.checkbox(
            f"유효구간 확장을 승인합니다 (이번 실행에만 적용) — {len(ext)}종",
            key="override_ok")
        st.caption(
            "위키 정의서는 변경되지 않습니다. 이번 실행 기록에만 남고 리포트에 "
            "\"정의서 구간을 넘어선 계산\"으로 명시됩니다. **다음 실행에서 다시 승인해야 합니다.**")

    if partial:
        st.warning("부분 갱신: " + " · ".join(
            f"{r['지표명']}({r['부분갱신']})" for r in partial)
            + " — 계산은 되지만 해당 테이블은 옛 상태입니다.")

    can_go = not blockers and approved and partial_ok
    b1, b2 = st.columns([1, 3])
    if b1.button("이 판정으로 계산 진행", type="primary", disabled=not can_go):
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        # ★ 같은 분에 두 번 돌리면 **폴더가 겹쳐 앞 실행을 덮어쓴다.**
        #   과거 주차를 연달아 돌려 정상범위 표본을 쌓으려 했더니 5회가 2회로 줄었다.
        #   "실행마다 새 폴더를 만들고 이전 것을 덮어쓰지 않는다"는 원칙이 분 단위 이름 때문에
        #   조용히 깨져 있었다. 겹치면 접미사를 붙인다.
        run_dir = config.OUTPUTS_DIR / f"run_{stamp}"
        _n = 2
        while run_dir.exists():
            run_dir = config.OUTPUTS_DIR / f"run_{stamp}_{_n}"
            _n += 1
        run_dir.mkdir(parents=True, exist_ok=True)
        ss.override_at = datetime.now().astimezone().isoformat(timespec="seconds")
        # ★ 단계별로 나눠 기록한다. 3개월 뒤 "이 숫자 어떻게 나왔나요"에
        #   이 파일 하나로 답해야 하고, 그때 필요한 건 "어느 단계의 무엇"이다.
        rl.record(run_dir, "0_카탈로그",
                  카탈로그_생성일시=m_meta.get("생성일시"),
                  # ⚠️ 이름을 `테이블`로 두면 2_판정의 테이블명과 충돌해
                  #    `field(log, "테이블")`이 카탈로그 개수(12)를 돌려준다(실측).
                  지표수=len(metrics), 테이블수=len(schema), 인사이트수=len(insights))
        rl.record(run_dir, "1_투입",
                  파일명=ss.filename, 크기=len(ss.raw or b""),
                  행수=p["행수"], 컬럼수=p["컬럼수"])
        rl.record(run_dir, "2_판정",
                  테이블=t.get("테이블명"), 테이블명_추정=t.get("테이블명_추정"),
                  일치율=round(t.get("일치율", 0), 4),
                  기간=f"{period} ~ {period}" if period else None,
                  누락_컬럼=t.get("누락컬럼") or [],
                  결측=p["결측합계"], 그레인_중복=(p["그레인"] or {}).get("중복"))
        rl.record(run_dir, "게이트1",
                  확정_시각=ss.override_at,
                  계산_대상_지표=[r["metric_id"] for r in target],
                  계산불가_지표=[{"metric_id": r["metric_id"], "사유": r["이유"]}
                             for r in blocked],
                  일부만_계산=bool(blocked),
                  유효구간_확장_승인=bool(ext) and approved,
                  유효구간_확장_대상=[r["metric_id"] for r in ext],
                  부분_갱신_지표=[r["metric_id"] for r in partial])
        if ss.raw:                                   # 원본 그대로 복사 — 재현성
            (run_dir / ss.filename).write_bytes(ss.raw)
        ss.run_dir = str(run_dir)
        ss.step = max(ss.step, 3)
        st.rerun()

    if ss.run_dir:
        st.success(f"확정됨 · 실행 폴더 `{Path(ss.run_dir).name}` — 3단계 준비됨")
        if b2.button("확정 취소"):
            # 2단계로 되돌리면 3단계 이후 결과는 전부 폐기한다.
            # 게이트 2 확인도 함께 푼다 — 옛 결과에 대한 확인이 새 결과에 남으면
            # 확인하지 않은 숫자가 확인된 것으로 발행된다.
            ss.run_dir, ss.override_at, ss.confirmed_at, ss.report_md = None, None, None, None
            ss.pdf_ctx = ss.merge_info = ss.email = None
            ss.metrics_df = ss.comparison_df = ss.validation = ss.sql_log = ss.dep_values = ss.trend_df = None
            ss.step = 2
            st.rerun()

        # ── 스테이징 적재 + 계산 ──────────────────────────────────────
        st.markdown("---")
        st.markdown("### 4. 지표 계산")

        if ss.metrics_df is None:
            try:
                with st.spinner("스테이징 적재 중…"):
                    client = calc.make_client()
                    full = calc.load_staging(df, t["테이블명"], client, schema)
                    stg = full.split(".")[-1]
                with st.spinner("지표 계산 중…"):
                    log: dict = {}
                    dv: dict = {}
                    res = calc.calculate([r["metric_id"] for r in target], period,
                                         {t["테이블명"]: stg}, client,
                                         bool(ext) and approved, metrics,
                                         sql_log=log, dep_values=dv,
                                         include_deps=True)
                ss.metrics_df, ss.sql_log, ss.dep_values = res, log, dv
                rl.record(ss.run_dir, "2_계산",
                          스테이징_테이블=stg, 지표수=len(res),
                          지표별={r["metric_id"]: {"값": None if pd.isna(r["value"])
                                                 else round(float(r["value"]), 4),
                                                 "상태": r["status"]}
                                for _, r in res.iterrows()})
                res.to_csv(Path(ss.run_dir) / "metrics.csv", index=False,
                           encoding="utf-8-sig")
            except Exception as e:                                  # noqa: BLE001
                msg = str(e)
                if "credential" in msg.lower() or "default" in msg.lower() and "auth" in msg.lower():
                    st.error("BigQuery 인증 실패 — 아래 명령을 한 번 실행하세요.")
                    st.code("gcloud auth application-default login", language="bash")
                else:
                    st.error(f"계산을 시작하지 못했습니다: {type(e).__name__} {msg[:300]}")
                st.stop()

        res = ss.metrics_df
        n_ok = int((res["status"] == "OK").sum())
        n_ext = int((res["status"] == "구간확장").sum())
        n_err = int(res["status"].str.contains("오류|실패|없음", regex=True).sum())
        k1, k2, k3 = st.columns(3)
        k1.metric("계산 성공", f"{n_ok + n_ext}종")
        k2.metric("구간확장", f"{n_ext}종")
        k3.metric("오류", f"{n_err}종")

        head = ("<tr><th align='left'>지표명</th><th align='right'>값</th>"
                "<th align='right'>표본</th><th align='left'>상태</th>"
                "<th align='left'>원천</th></tr>")
        body = ""
        for _, r in res.iterrows():
            mark = (" <span style='color:#f59e0b;font-size:0.8em'>◍ 부분갱신</span>"
                    if r["부분갱신"] else "")
            # 위 판정표에서 "이 파일과 무관"이던 지표가 여기 나오는 이유를 밝힌다.
            # 밝히지 않으면 두 표가 어긋난 것처럼 보인다.
            if str(r.get("포함사유") or ""):
                mark += (" <span style='color:#64748b;font-size:0.8em'>"
                         f"({r['포함사유']})</span>")
            samp = f"{r['sample_size']:,.0f}" if pd.notna(r["sample_size"]) else "—"
            body += (f"<tr><td>{r['지표명']}{mark}</td>"
                     f"<td align='right'><b>{common.fmt_value(r)}</b></td>"
                     f"<td align='right' style='color:#64748b'>{samp}</td>"
                     f"<td>{common.badge(r['status'])}</td>"
                     f"<td style='font-size:0.86em;color:#475569'>{r['원천']}</td></tr>")
        st.markdown(f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>",
                    unsafe_allow_html=True)
        n_dep = int((res["포함사유"] != "").sum()) if "포함사유" in res else 0
        if n_dep:
            st.caption(f"**의존 계산 {n_dep}종** — 파생지표를 계산하느라 함께 계산된 지표입니다. "
                       "업로드 파일의 원천은 아니지만, 화면에 값이 나오는 이상 검증도 함께 받아야 "
                       "하므로 결과표에 싣습니다.")
        st.caption(f"저장: `{Path(ss.run_dir).name}/metrics.csv`")

        # 실행된 SQL — 기본은 접어둔다. 스테이징 치환이 실제로 됐는지는 SQL을 봐야 안다
        logs = ss.sql_log or {}
        n_q = sum(len(v) for v in logs.values())
        with st.expander(f"실행된 SQL 보기 — 지표 {len(logs)}종 · 쿼리 {n_q}건", expanded=False):
            st.caption("정의서(카탈로그)로 조립한 실제 쿼리입니다. "
                       "`staging_` 로 시작하면 업로드분, 그 외는 원본 테이블입니다. "
                       "원본은 월 컬럼 타입을 맞추려 서브쿼리로 감쌉니다.")
            names = {r["metric_id"]: r["지표명"] for _, r in res.iterrows()}
            for mid in sorted(logs):
                label = names.get(mid, mid)
                extra = "" if mid in names.keys() else "  ·  (의존 지표)"
                st.markdown(f"**{label}** &nbsp;<code>{mid}</code>{extra}",
                            unsafe_allow_html=True)
                for e in logs[mid]:
                    st.code(f"-- [{e['블록']}] 대상 월 {e['월']}\n"
                            f"-- @month = '{e['월']}'  @month_start / @month_end = 그 달의 1일 / 말일\n"
                            + e["sql"], language="sql")

        err = res[res["status"].str.contains("오류|실패|없음", regex=True)]
        for _, r in err.iterrows():
            st.warning(f"**{r['지표명']}** — {r['status']}")

        # ── 전월 대비 ─────────────────────────────────────────────────
        # ★ 전 기간 라벨을 만드는 데 **BigQuery 클라이언트를 무조건 만들지 않는다.**
        #   여기서 make_client()를 조건 없이 부르면, 인증이 없는 환경(배포본에서
        #   기존 실행을 불러보는 경우)에서 TransportError로 화면이 통째로 죽는다.
        #   비교표가 이미 있으면 그 안의 전 기간 값을 쓰고, 없을 때만 조회한다.
        #   조회에 실패해도 달력 기준으로 물러선다 — 라벨 하나 때문에 앱이 멈추면 안 된다.
        if ss.comparison_df is not None and len(ss.comparison_df):
            prev_period = cmp.prev_label_from(ss.comparison_df, period)
        else:
            try:
                prev_period = cmp.previous_period(period, calc.make_client())
            except Exception:                                   # noqa: BLE001
                prev_period = cmp.previous_month(period)
        st.markdown("---")
        st.markdown(f"### 5. 전월 대비 &nbsp;<span style='font-size:0.72em;color:#64748b'>"
                    f"{period} vs {prev_period}</span>", unsafe_allow_html=True)

        if ss.comparison_df is None:
            try:
                with st.spinner(f"{_PREV}({prev_period}) 계산 중…"):
                    client = calc.make_client()
                    plog: dict = {}
                    pdv: dict = {}
                    prev = cmp.calc_previous(list(res["metric_id"]), prev_period,
                                             client, metrics, sql_log=plog,
                                             dep_values=pdv,
                                             override=bool(ext) and approved)
                    (ss.dep_values or {}).update(pdv)
                    for k, v2 in plog.items():
                        (ss.sql_log or {}).setdefault(k, []).extend(v2)
                    comp = cmp.compare(res, prev)
                ss.comparison_df = comp
                comp.to_csv(Path(ss.run_dir) / "comparison.csv", index=False,
                            encoding="utf-8-sig")
            except Exception as e:                                  # noqa: BLE001
                st.error(f"{_PREV} 계산 실패: {type(e).__name__} {str(e)[:300]}")
                ss.comparison_df = pd.DataFrame()

        comp = ss.comparison_df
        if len(comp):
            head = (f"<tr><th align='left'>지표명</th><th align='right'>{_CURR}</th>"
                    f"<th align='right'>{_PREV}</th><th align='right'>변화</th>"
                    "<th align='right'>변화율</th></tr>")
            body = ""
            for _, r in comp.iterrows():
                cur_v = common.fmt_value({**r, "value": r["당월"]})
                prv_v = common.fmt_value({**r, "value": r["전월"]})
                if r["비교상태"] != "비교 가능":
                    cell = (f"<td colspan='2' align='right'>{common.badge('비교 불가', '정보')}"
                            f" <span style='font-size:0.82em;color:#64748b'>{r['이유']}</span></td>")
                else:
                    cell = (f"<td align='right'>{common.fmt_delta(r)}</td>"
                            f"<td align='right'>{common.fmt_rate(r)}</td>")
                body += (f"<tr><td>{r['지표명']}</td>"
                         f"<td align='right'>{cur_v}</td>"
                         f"<td align='right' style='color:#64748b'>{prv_v}</td>{cell}</tr>")
            st.markdown(f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>",
                        unsafe_allow_html=True)
            st.caption("방향만 표시합니다 — 증가가 좋은지 나쁜지는 판단하지 않습니다. "
                       "해석은 리포트(6단계)의 몫입니다. "
                       f"저장: `{Path(ss.run_dir).name}/comparison.csv`")

        # ── 3단계 검증은 여기서 돌리고, 화면은 아래 3단계 절에서 그린다 ──
        if ss.validation is None:
            with st.spinner("검증 실행 중…"):
                ss.validation = vd.validate_all(res, comp, metrics,
                                                 override=bool(ext) and approved)
            (Path(ss.run_dir) / "validation.json").write_text(
                json.dumps(ss.validation, ensure_ascii=False, indent=2), encoding="utf-8")
            rl.record(ss.run_dir, "3_검증",
                      전체판정=ss.validation["전체판정"],
                      차단수=ss.validation["차단수"], 경고수=ss.validation["경고수"],
                      점검항목수=len(ss.validation["항목"]),
                      자동검증_안한_항목=ss.validation["자동검증하지_않은_것"])
            ss.step = max(ss.step, 3)

# ── 3~8단계 — 대기 ────────────────────────────────────────────────────
# ── 3단계 — 검증 실행 ─────────────────────────────────────────────────
st.markdown("---")
v = ss.validation
if v is None:
    st.markdown(f"## 3단계 — 검증 실행 {common.badge('대기', '정보')}", unsafe_allow_html=True)
    st.caption("2단계 게이트를 확정하면 검증이 자동으로 돕니다.")
else:
    kind = {"통과": "통과", "경고": "경고", "차단": "차단"}[v["전체판정"]]
    st.markdown(f"## 3단계 — 검증 실행 {common.badge('완료', '통과')}", unsafe_allow_html=True)

    # 1. 전체 판정 — 상단 크게
    color = common.STATUS[kind][0]
    st.markdown(
        f"<div style='border:2px solid {color};background:{color}14;border-radius:10px;"
        f"padding:14px 18px;margin:6px 0 14px'>"
        f"<span style='font-size:1.55em;font-weight:700;color:{color}'>{v['전체판정']}</span>"
        f"<span style='margin-left:14px;color:#475569'>차단 <b>{v['차단수']}건</b> · "
        f"경고 <b>{v['경고수']}건</b> · 점검 {len(v['항목'])}건</span></div>",
        unsafe_allow_html=True)

    # 2. 항목별 결과 — 통과는 접어둔다
    attn = [x for x in v["항목"] if x["판정"] in ("차단", "경고")]
    rest = [x for x in v["항목"] if x["판정"] not in ("차단", "경고")]
    if attn:
        st.markdown(common.validation_table(attn), unsafe_allow_html=True)
    else:
        st.success("경고·차단 항목 없음")
    with st.expander(f"통과·정보 항목 {len(rest)}건", expanded=False):
        st.markdown(common.validation_table(rest), unsafe_allow_html=True)

    # 3. 자동 검증하지 않은 항목
    st.markdown(common.not_automated_box(v["자동검증하지_않은_것"]), unsafe_allow_html=True)
    st.caption(f"저장: `{Path(ss.run_dir).name}/validation.json`")

    # 4. 결과 파일 — 화면에서 바로 받아 대조할 수 있게.
    #    Streamlit은 로컬 파일 링크를 열지 못하므로 다운로드 버튼으로 낸다.
    #    화면 표만 있으면 "이 숫자가 정말 저장된 값인가"를 확인할 방법이 없다.
    common.result_files(ss.run_dir, key="s3")

# ── 4~8단계 ───────────────────────────────────────────────────────────
blocked_here = bool(v and v["차단수"])
for n, name, who in common.STEPS[3:]:
    st.markdown("---")
    if n == 4 and blocked_here:
        st.markdown(f"## 4단계 — {name} {common.badge('차단', '차단')}", unsafe_allow_html=True)
        st.error(f"검증에서 차단 {v['차단수']}건이 나와 진행할 수 없습니다. "
                 "위 3단계에서 차단 항목을 확인하고, **데이터나 정의를 고친 뒤 다시 계산**하세요.")
        for x in v["항목"]:
            if x["판정"] == "차단":
                st.markdown(f"- **{x['대상지표']}** · {x['검증명']} — {x['상세']}")
        # ★ "차단을 무시하고 진행" 버튼을 만들지 않는다.
        #   우회로를 두면 게이트가 아니라 장식이 된다.
        break
    if n == 4 and v:
        st.markdown(f"## 4단계 — {name} {common.badge('진행중', '경고')}", unsafe_allow_html=True)
        comp = ss.comparison_df
        cmap = {r["metric_id"]: r for _, r in comp.iterrows()} if comp is not None and len(comp) else {}
        mmap = {r["metric_id"]: r for _, r in ss.metrics_df.iterrows()}
        dep = ss.dep_values or {}

        # ── 한눈에 ────────────────────────────────────────────────────
        vk = v["전체판정"]
        st.markdown(
            f"{common.badge(vk)} &nbsp; <b>차단 {v['차단수']}</b> / 경고 {v['경고수']}"
            f" &nbsp;<span style='color:#94a3b8'>·</span>&nbsp; "
            f"<span style='color:#64748b;font-size:0.9em'>대상 기간 {ss.metrics_df['month'].iloc[0]}"
            f" · 카탈로그 {m_meta.get('생성일시', '?')}</span>", unsafe_allow_html=True)

        signals = [x for x in v["항목"] if x["검증명"] == vd.MOM_CHECK and x["판정"] == "경고"]
        if signals:
            st.markdown("**이상 신호 " + str(len(signals)) + "건**")
            for x in signals:
                st.markdown(f"- {x['대상지표']} — {x['상세']}")

        # ── 핵심 지표 카드 4개 ────────────────────────────────────────
        st.markdown("#### 핵심 지표")
        # 이메일 본문과 같은 목록을 쓴다 — common 한 곳에서 온다
        CARDS = common.CARD_METRICS
        cols4 = st.columns(4)
        note_partial = []
        for col, mid in zip(cols4, CARDS):
            spec = metrics.get(mid, {})
            row = mmap.get(mid)
            if row is None:                       # 결과표에 없으면 의존 계산 캐시에서
                per_now = ss.metrics_df["month"].iloc[0]
                cur = (dep.get(f"{mid}|{per_now}") or [None])[0]
                prv = (dep.get(f"{mid}|{cmp.previous_month(per_now)}") or [None])[0]
                row = {"metric_id": mid, "지표명": spec.get("지표명", mid),
                       "유형": spec.get("유형", ""), "value": cur}
                d = None if (cur is None or prv in (None, 0)) else {
                    **row, "절대변화": cur - prv,
                    "상대변화율": (cur - prv) / prv * 100, "퍼센트포인트변화": None}
            else:
                c = cmap.get(mid)
                d = None if c is None else {**row, **{k: c.get(k) for k in
                                                      ("절대변화", "상대변화율", "퍼센트포인트변화")}}
            col.metric(spec.get("지표명", mid), common.fmt_value(row),
                       delta=common.fmt_metric_delta(d) if d else None,
                       delta_color="normal")
            if row.get("부분갱신") or (mmap.get(mid) is not None
                                    and common.blank_safe(mmap[mid].get("부분갱신"))):
                note_partial.append(spec.get("지표명", mid))
        if note_partial:
            st.caption("◍ 부분 갱신: " + ", ".join(note_partial)
                       + " — 원천 중 일부 테이블은 이전 상태입니다.")
        st.caption("증가·감소는 방향만 표시합니다. 좋고 나쁨은 판단하지 않으며 해석은 리포트의 몫입니다.")

        # ── 전체 지표 표 ──────────────────────────────────────────────
        st.markdown("#### 전체 지표")
        amber, slate2 = common.STATUS["경고"][0], common.STATUS["정보"][0]
        head = (f"<tr><th align='left'>지표명</th><th align='right'>{_CURR}</th>"
                f"<th align='right'>{_PREV}</th><th align='right'>변화</th>"
                "<th align='right'>변화율</th><th align='right'>표본</th>"
                "<th align='left'>상태</th></tr>")
        body = ""
        partial_names = []
        for _, r in ss.metrics_df.iterrows():
            mid = r["metric_id"]
            c = cmap.get(mid, {})
            merged = {**r, **{k: c.get(k) for k in
                              ("절대변화", "상대변화율", "퍼센트포인트변화")}}
            rate = c.get("상대변화율")
            over = rate is not None and pd.notna(rate) and abs(rate) >= config.MOM_THRESHOLD
            bg = f" style='background:{amber}1f'" if over else ""
            pmark = ""
            if common.blank_safe(r.get("부분갱신")):
                partial_names.append(r["지표명"])
                pmark = (f" <span title='원천 중 {r['부분갱신']}는 이번에 갱신되지 않았습니다' "
                         f"style='color:{amber};font-size:0.8em'>◍</span>")
            samp = f"{r['sample_size']:,.0f}" if pd.notna(r.get("sample_size")) else "—"
            if str(c.get("비교상태", "")) != "비교 가능":
                mid_cells = (f"<td colspan='3' align='right'>{common.badge('비교 불가', '정보')}"
                             f" <span style='font-size:0.8em;color:#64748b'>{c.get('이유', '')}</span></td>")
            else:
                mid_cells = (f"<td align='right' style='color:#64748b'>"
                             f"{common.fmt_value({**r, 'value': c.get('전월')})}</td>"
                             f"<td align='right'>{common.fmt_delta(merged)}</td>"
                             f"<td align='right'>{common.fmt_rate(merged)}</td>")
            body += (f"<tr{bg}><td>{r['지표명']}{pmark}</td>"
                     f"<td align='right'><b>{common.fmt_value(r)}</b></td>"
                     f"{mid_cells}"
                     f"<td align='right' style='color:#64748b'>{samp}</td>"
                     f"<td>{common.badge(r['status'])}</td></tr>")
        st.markdown(f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>",
                    unsafe_allow_html=True)
        st.caption(f"옅은 주황 배경 = {_PREV} 대비 변화율이 임계값 {config.MOM_THRESHOLD:g}% 이상인 행")

        # 부분 갱신 안내
        if partial_names:
            srcs = sorted({s for _, r in ss.metrics_df.iterrows()
                           for s in common.blank_safe(r.get("부분갱신")).split(", ") if s})
            st.markdown(
                f"<div style='border:1px solid {slate2}55;background:{slate2}12;"
                f"border-radius:10px;padding:12px 18px;margin-top:10px;color:#475569'>"
                f"<b style='color:{slate2}'>부분 갱신</b><br>"
                f"{', '.join(partial_names)}는 <code>{', '.join(srcs)}</code> 테이블을 함께 "
                f"사용합니다. 업로드된 것은 <code>{t.get('테이블명')}</code>뿐이므로 "
                f"{', '.join(srcs)}는 <b>이전 상태</b>를 반영합니다.</div>",
                unsafe_allow_html=True)

        # 계산하지 않은 지표
        with st.expander(f"이번 실행에서 계산하지 않은 지표 {len(unrelated)}종", expanded=False):
            uhead = ("<tr><th align='left'>지표명</th><th align='left'>metric_id</th>"
                     "<th align='left'>쓰는 테이블</th></tr>")
            ubody = "".join(
                f"<tr><td>{u['지표명']}</td><td><code>{u['metric_id']}</code></td>"
                f"<td style='color:#475569;font-size:0.9em'>{u['원천']}</td></tr>"
                for u in unrelated)
            st.markdown(f"<table style='width:100%;border-collapse:collapse'>{uhead}{ubody}</table>",
                        unsafe_allow_html=True)
            st.caption(f"업로드 파일이 `{t.get('테이블명')}`이라 이 지표들의 원천과 겹치지 않습니다.")

        # ── 추이 차트 ─────────────────────────────────────────────────
        st.markdown(f"#### 최근 {config.TREND_MONTHS}개월 추이")
        # ★ 추이로 계산할 지표는 **차트 스펙에서 뽑는다.**
        #   여기 목록을 따로 두면 config의 CHART_SPECS와 갈라진다 — 실제로 갈라져서
        #   재고 카탈로그에 없는 CS 지표 6종을 계산하다 추이가 0행이 됐고,
        #   차트 루프가 통째로 건너뛰어 **그래프가 하나도 안 그려졌다.**
        #   그릴 것만 계산하면 되므로 스펙이 유일한 출처가 되는 것이 맞다.
        TREND_IDS = list(dict.fromkeys(
            s[0] for spec in common.CHART_SPECS
            for s in spec["left"] + spec["right"]))
        per_now = ss.metrics_df["month"].iloc[0]
        if ss.trend_df is None:
            bar, txt = st.progress(0.0), st.empty()
            try:
                ss.trend_df = ch.build_trend(
                    TREND_IDS, per_now, config.TREND_MONTHS,
                    {t.get("테이블명"): f"{config.STAGING_PREFIX}{t.get('테이블명')}"},
                    calc.make_client(), metrics, override_current=bool(ext) and approved,
                    on_progress=lambda i, n2, p2: (bar.progress(i / n2),
                                                   txt.caption(f"추이 계산 {i}/{n2} — {p2}")))
            except Exception as e:                                  # noqa: BLE001
                st.error(f"추이 계산 실패: {type(e).__name__} {str(e)[:250]}")
                ss.trend_df = pd.DataFrame()
            bar.empty(); txt.empty()
            # ★ 추이를 실행 폴더에 남긴다. 배포본(BigQuery 인증 없음)에서 이 실행을
            #   불러왔을 때 차트가 그려지려면 계산 결과가 파일로 있어야 한다.
            #   없으면 4단계 자리에 "추이 계산 실패"만 뜬다.
            try:
                if ss.trend_df is not None and len(ss.trend_df):
                    ss.trend_df.to_csv(Path(ss.run_dir) / "trend.csv",
                                       index=False, encoding="utf-8-sig")
            except Exception:                                   # noqa: BLE001
                pass

        tr = ss.trend_df
        if len(tr):
            for spec in common.CHART_SPECS:
                fig = common.trend_chart(tr, spec, per_now)
                if fig is None:
                    continue
                st.plotly_chart(fig, width='stretch',
                                key=f"chart_{spec['key']}")
                st.caption(spec["caption"] + f"  ·  {per_now}은 업로드 파일로 계산, "
                           "그 이전은 기존 테이블입니다.")

            # ── 학습용 비교(축 범위) 블록은 이 앱에서 **제거했다** ──────────
            #   원본 auto-report에는 남아 있다. 그 블록은 강의 CS 지표에 묶여 있어
            #   (`usage` 차트 키 · `avg_data_usage`) 재고 카탈로그에서는 StopIteration으로
            #   화면이 죽었다. 조건문으로 감싸 살려 두는 방법도 있으나,
            #   **재고 앱에 남의 도메인 학습 자료가 있을 이유가 없어** 지우는 쪽을 택했다.

        # ── 검증 상세 (3단계와 같은 내용을 여기서도 본다) ─────────────
        # 중복이 아니다. 두 화면은 목적이 다르다.
        #   3단계 = **검증 전용 화면** — 문제를 찾는 곳. 경고·차단만 펼쳐 보인다.
        #   4단계 = **결과 확인 화면** — 전체를 보는 곳. 숫자와 검증을 함께 본다.
        # 게이트 2에서 사람이 "발행해도 되는가"를 판단할 때 **한 화면에서 다 보여야** 한다.
        # 스크롤을 올려 3단계로 돌아가야 한다면 그 사람은 확인하지 않고 승인한다.
        with st.expander(f"검증 상세 — {v['전체판정']} · 차단 {v['차단수']} / 경고 {v['경고수']}",
                         expanded=False):
            st.markdown(common.validation_table(v["항목"]), unsafe_allow_html=True)
            st.markdown(common.not_automated_box(v["자동검증하지_않은_것"]),
                        unsafe_allow_html=True)
        ss.step = max(ss.step, 4)
        continue

    # ── 5단계 — 사람이 확인한다 + 게이트 2 ────────────────────────────
    if n == 5 and v is not None and not blocked_here:
        done = bool(ss.confirmed_at)
        st.markdown(f"## 5단계 — {name} "
                    f"{common.badge('완료' if done else '확인 필요', '통과' if done else '경고')}",
                    unsafe_allow_html=True)
        st.caption("여기서부터는 시스템이 아니라 **사람이 판단합니다.** "
                   "아래 항목을 확인하고 리포트를 발행할지 결정하세요.")

        checklist = common.build_checklist(
            str(ss.metrics_df["month"].iloc[0]), v, ss.metrics_df, ss.comparison_df)

        # ★ "확인 완료" 버튼 하나만 두면 내용을 보지 않고 누른다.
        #   무엇을 확인해야 하는지 항목으로 제시하면 최소한 그 항목은 읽는다.
        #   완벽한 장치는 아니지만 아무것도 없는 것보다 낫다.
        checked = []
        for it in checklist:
            if not it["해당"]:
                # 해당 없는 항목은 자동 충족. 없는 것을 확인하라고 시키지 않는다.
                st.markdown(f"<span style='color:#64748b'>☑ {it['라벨']}</span>",
                            unsafe_allow_html=True)
                st.caption(it["상세"])
                continue
            c = st.checkbox(it["라벨"], key=f"chk_{it['키']}", disabled=done)
            if c:
                checked.append(it["키"])
            with st.expander("무엇을 확인하는가", expanded=False):
                st.markdown(it["상세"])

        need = [it["키"] for it in checklist if it["해당"]]
        all_checked = set(need) <= set(checked)

        st.markdown("---")
        # 확인 직전에 원본을 대조할 수 있어야 한다 —
        # 화면 숫자만 보고 승인하면 체크리스트가 형식이 된다.
        common.result_files(ss.run_dir, key="s5")

        st.markdown("### 🚦 게이트 2 — 이 결과로 리포트를 발행할까요")
        st.caption("게이트 1이 *재료를 받아들이는가*였다면, 게이트 2는 "
                   "**이 결과를 발행해도 되는가**입니다.")

        if not done:
            if not all_checked:
                st.info(f"확인 항목 {len(checked)}/{len(need)} — 남은 항목을 확인하면 "
                        "버튼이 활성화됩니다.")
            if st.button("확인 완료, 리포트 생성 단계로", type="primary",
                         disabled=not all_checked):
                ss.confirmed_at = rl.now()
                rl.record(ss.run_dir, "게이트2",
                          확인_완료_시각=ss.confirmed_at,
                          확인한_체크항목=[it["라벨"] for it in checklist
                                     if it["키"] in checked],
                          # 해당 없어 자동 충족된 항목도 남긴다 — 확인을 건너뛴 것과 구분된다
                          해당없음_체크항목=[it["라벨"] for it in checklist if not it["해당"]])
                ss.step = max(ss.step, 6)
                st.rerun()
        else:
            st.success(f"확인 완료 · {ss.confirmed_at} — 6단계 준비됨")
            st.caption(f"기록: `{Path(ss.run_dir).name}/run_log.json` "
                       "(확인_완료_시각 · 확인한_체크항목 · 검증_요약)")
            if st.button("확인 취소"):
                # 되돌리면 6단계 이후는 다시 잠긴다. 확인 기록도 지운다 —
                # 남겨두면 "확인했다가 취소한 상태"가 확인한 것처럼 읽힌다.
                ss.confirmed_at = ss.report_md = ss.merge_info = ss.email = None
                ss.step = 5
                log = rl.load(ss.run_dir)
                # 게이트 2 이후 단계 기록도 함께 지운다 — 리포트·이메일 기록만 남으면
                # "확인 안 했는데 리포트는 나온" 이력이 된다
                for k in ("게이트2", "6_리포트", "7_이메일"):
                    log.pop(k, None)
                rl.save(ss.run_dir, log)
                st.rerun()
        ss.step = max(ss.step, 5)
        continue

    # ── 6단계 — 리포트 생성 ───────────────────────────────────────────
    if n == 6 and ss.confirmed_at:
        made = bool(ss.report_md)
        st.markdown(f"## 6단계 — {name} "
                    f"{common.badge('완료' if made else '준비됨', '통과')}",
                    unsafe_allow_html=True)
        st.caption("화면이 아니라 **문서**를 만듭니다. 자동 생성되는 장은 계산·검증 결과를 "
                   "그대로 서술하고, 2·5·6장은 자리를 비워 사람이 쓰도록 남깁니다.")

        def generate_report():
            """생성 → 병합 → 저장. **버튼과 '사람 작성분 저장' 양쪽에서 쓴다.**

            ★ 병합을 `report.py` 안에서 하지 않는 이유: `manual_sections`가 이미
              `report`를 import한다(헤딩·분할을 공유). 반대 방향 import를 더하면
              **순환 참조**가 된다. 호출 순서를 여기서 정하면 두 모듈 다 단방향으로 남는다.

            자체 검사는 `build_report` 안에서 **병합 전에** 돈다. 사람이 쓴 글에는
            인과·제안이 들어가는 게 정상이고, 금지 규칙은 **앱이 쓴 문장**에만 적용된다.
            """
            log = rl.load(ss.run_dir)
            period = str(ss.metrics_df["month"].iloc[0])
            ctx = {
                "파일명": ss.filename,
                "판정테이블": rl.field(log, "테이블"),
                "기간": period,
                "행수": len(ss.df) if ss.df is not None else 0,
                "metrics": ss.metrics_df,
                "comparison": ss.comparison_df,
                "validation": v,
                "metrics_catalog": metrics,
                "schema_catalog": schema,
                "insights_catalog": insights,
                "카탈로그_메타": m_meta,
                "run_log": log,
                # ★ 생성 시각은 앱이 넘긴다. report.py가 직접 now()를 읽으면
                #   같은 입력에 매번 다른 문서가 나온다(재현성).
                "생성일시": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            md = rp.build_report(ctx)
            md, info = ms.merge_into_report(md, ms.load_manual(period))
            (Path(ss.run_dir) / "report.md").write_text(md, encoding="utf-8")
            ss.report_md, ss.merge_info = md, info
            ss.email = None          # 리포트가 바뀌면 초안도 다시 만든다
            secs_ = rp.split_sections(md)
            rl.record(ss.run_dir, "6_리포트",
                      장수=len([s for s in secs_ if s["번호"]]),
                      자동생성_장=[s["번호"] for s in secs_ if s["번호"] and not s["미작성"]],
                      미작성_장=[f"{s['번호']}장 {s['제목']}" for s in secs_ if s["미작성"]],
                      병합된_장=info["병합"],
                      금지표현_검사=len(rp.check_generated(md)))
            ss.pdf_ctx = {k: ctx[k] for k in ("기간", "생성일시", "파일명", "카탈로그_메타")}
            ss.step = max(ss.step, 6)

        if st.button("리포트 생성" if not made else "다시 생성", type="primary"):
            generate_report()
            st.rerun()

        if ss.report_md:
            secs = rp.split_sections(ss.report_md)
            todo = [s for s in secs if s["미작성"]]

            # 1. 생성 정보 — 어느 정의로 만든 문서인지 나중에 추적할 수 있어야 한다
            log = json.loads((Path(ss.run_dir) / "run_log.json").read_text(encoding="utf-8"))
            i1, i2, i3 = st.columns(3)
            i1.metric("대상 기간", str(ss.metrics_df["month"].iloc[0]))
            i2.metric("장", f"{len([s for s in secs if s['번호']])}장")
            i3.metric("카탈로그", m_meta.get("생성일시", "?")[:10])

            # 2. 미작성 경고 — 숫자만 있는 문서가 완결된 분석으로 오해되지 않게
            if todo:
                st.warning(f"**{len(todo)}개 장이 미작성 상태입니다** — "
                           + " · ".join(f"{s['번호']}장 {s['제목']}" for s in todo)
                           + ". 이 장들은 사람이 작성해야 합니다.")
            else:
                st.success("모든 장이 작성되었습니다.")

            # 3. 병합 결과 — 무엇이 채워졌고 무엇이 남았는지
            mi = ss.merge_info or {}
            if mi.get("병합"):
                st.markdown(
                    common.badge(f"병합됨 {len(mi['병합'])}장", "통과")
                    + " &nbsp; " + " · ".join(
                        f"{n}장 {rp.HUMAN_SECTIONS[n]['제목']}" for n in mi["병합"]),
                    unsafe_allow_html=True)
            for w in mi.get("경고", []):
                st.warning(w)

            # 4. 사람 작성분 편집 — 화면에서 바로 고치고 저장하면 즉시 재생성된다
            with st.expander("사람 작성분 편집 — `manual/sections.md`", expanded=False):
                st.caption("2·5·6장을 여기에 씁니다. **리포트를 다시 만들어도 이 파일은 남습니다.** "
                           "저장하면 작성일·대상기간이 현재 값으로 갱신되고 리포트가 재생성됩니다.")
                cur = ms.MANUAL_PATH.read_text(encoding="utf-8") if ms.MANUAL_PATH.exists() \
                    else ms.template(str(ss.metrics_df["month"].iloc[0]))
                edited = st.text_area("내용", cur, height=340, key="manual_edit",
                                      label_visibility="collapsed")
                e1, e2 = st.columns([1, 4])
                if e1.button("저장하고 재생성", type="primary", key="save_manual"):
                    ms.save_manual(edited, str(ss.metrics_df["month"].iloc[0]))
                    generate_report()
                    st.rerun()
                e2.caption(f"경로: `{ms.MANUAL_PATH.relative_to(config.BASE_DIR)}`")

            # 3. 장별 expander — 자동 생성 장은 펼치고, 사람이 쓸 장은 배지와 함께 접는다
            for s in secs:
                if not s["번호"]:
                    continue
                mark = " · 작성 필요" if s["미작성"] else ""
                with st.expander(f"{s['번호']}. {s['제목']}{mark}",
                                 expanded=not s["미작성"]):
                    if s["미작성"]:
                        st.markdown(common.badge("작성 필요", "경고"),
                                    unsafe_allow_html=True)
                    # 마크다운 표는 st.markdown이 그대로 그린다.
                    # st.dataframe으로 바꾸면 리포트 파일과 화면이 다른 모양이 된다.
                    st.markdown(s["본문"])

            # 4. 다운로드 (마크다운 + PDF)
            st.markdown("---")
            d1, d2, d3 = st.columns([1, 1, 2])
            d1.download_button("report.md ↓", ss.report_md.encode("utf-8"),
                               file_name="report.md", mime="text/markdown",
                               key="dl_report", width="stretch")

            # ★ 폰트가 없어도 **앱이 죽지 않는다.** PDF만 못 만드는 것과 앱이 멈추는 것은
            #   전혀 다른 실패다 — 멈추면 마크다운 리포트까지 못 보게 된다.
            pdf_ctx = ss.pdf_ctx or {"기간": str(ss.metrics_df['month'].iloc[0])}
            font_ok, missing = pr.font_status()
            saved_pdf = Path(ss.run_dir) / "report.pdf"

            # ★ **확정된 실행은 열어보기만 해도 바뀌면 안 된다.**
            #   아래 생성 블록은 게이트 밖이라 화면을 다시 그릴 때마다 PDF를 새로 만들어
            #   덮어썼다. fpdf2가 문서에 **생성 시각을 박기 때문에** 내용이 같아도 바이트가
            #   달라진다 — 확정 실행을 불러보기만 했는데 git이 '수정됨'으로 잡았다(실측).
            #   확정 = 그 시점의 산출물이 그대로 남아 있다는 뜻이므로, 있는 것을 그대로 낸다.
            if (Path(ss.run_dir) / "APPROVED").exists() and saved_pdf.exists():
                d2.download_button("report.pdf ↓", saved_pdf.read_bytes(),
                                   file_name="report.pdf", mime="application/pdf",
                                   key="dl_pdf_final", width="stretch")
                d3.caption(f"확정본 PDF ({saved_pdf.stat().st_size / 1024:,.0f}KB) — "
                           f"**확정된 실행이라 다시 만들지 않습니다.**")
            elif font_ok:
                try:
                    pdf_bytes = make_pdf_cached(ss.report_md, pdf_ctx)
                    (Path(ss.run_dir) / "report.pdf").write_bytes(pdf_bytes)
                    d2.download_button("report.pdf ↓", pdf_bytes,
                                       file_name="report.pdf", mime="application/pdf",
                                       key="dl_pdf", width="stretch")
                    d3.caption(f"저장: `{Path(ss.run_dir).name}/` "
                               f"report.md({len(ss.report_md):,}자 · {len(secs) - 1}장) · "
                               f"report.pdf({len(pdf_bytes) / 1024:,.0f}KB)")
                except Exception as e:                 # noqa: BLE001
                    d2.button("report.pdf ↓", disabled=True, key="dl_pdf_off",
                              width="stretch")
                    d3.error(f"PDF 생성 실패: {type(e).__name__} — {e}")
            else:
                # ★ 폰트가 없어 **새로 만들지는 못해도**, 이 실행에서 이미 만들어 둔 PDF가
                #   있으면 그것을 내려받게 한다 — 결과물이 있는데 못 받는 것은 손해다.
                if saved_pdf.exists():
                    d2.download_button("report.pdf ↓", saved_pdf.read_bytes(),
                                       file_name="report.pdf", mime="application/pdf",
                                       key="dl_pdf_saved", width="stretch")
                    d3.caption(f"이 실행에서 생성된 PDF "
                               f"({saved_pdf.stat().st_size / 1024:,.0f}KB) — "
                               f"한글 폰트가 없어 **새로 만들지는 않았습니다.**")
                else:
                    d2.button("report.pdf ↓", disabled=True, key="dl_pdf_off",
                              width="stretch")
                    d3.warning(f"한글 폰트 없음 — {', '.join(missing)}")
                    with st.expander("폰트 받는 방법", expanded=False):
                        st.markdown(pr.MISSING_FONT_HELP)
        ss.step = max(ss.step, 6)
        continue

    # ── 7단계 — 이메일 초안 ───────────────────────────────────────────
    if n == 7 and ss.report_md:
        drafted = bool(ss.email)
        st.markdown(f"## 7단계 — {name} "
                    f"{common.badge('완료' if drafted else '준비됨', '통과')}",
                    unsafe_allow_html=True)
        st.caption("**실제로 보내지 않습니다.** 발송 준비된 최종본을 만들고, "
                   "8주차에 이 자리에 SMTP를 꽂으면 완성됩니다.")

        if st.button("이메일 초안 생성" if not drafted else "다시 생성",
                     type="primary", key="mk_email"):
            ectx = {**(ss.pdf_ctx or {}), "run_dir": ss.run_dir,
                    "metrics": ss.metrics_df, "comparison": ss.comparison_df,
                    "validation": v}
            mail = ed.build_email(ectx, ss.report_md)
            rd = Path(ss.run_dir)
            (rd / "email.html").write_text(mail["body_html"], encoding="utf-8")
            (rd / "email.txt").write_text(mail["body_text"], encoding="utf-8")
            (rd / "email_meta.json").write_text(json.dumps(
                {k: mail[k] for k in ("subject", "to", "from", "attachments")},
                ensure_ascii=False, indent=2), encoding="utf-8")
            ss.email = mail
            rl.record(ss.run_dir, "7_이메일",
                      제목=mail["subject"], 수신자=mail["to"],
                      첨부_목록=[a["filename"] for a in mail["attachments"]])
            ss.step = max(ss.step, 7)
            st.rerun()

        if ss.email:
            mail = ss.email
            todo = ed.unwritten(ss.report_md)

            # 1. 상태 경고 — 제목에 왜 꼬리표가 붙었는지 화면에서 설명한다
            if todo:
                st.warning(f"**리포트 {len(todo)}개 장이 미작성 상태입니다** — "
                           + " · ".join(f"{s['번호']}장 {s['제목']}" for s in todo)
                           + ". 제목에 **(초안)**이 붙습니다.")
            if v["경고수"]:
                st.warning(f"**검증 경고 {v['경고수']}건** — 제목에 **(확인 필요)**가 붙습니다.")

            # 2. 메일 헤더
            with st.container(border=True):
                st.markdown(
                    f"**제목** &nbsp; {mail['subject']}<br>"
                    f"<span style='color:#64748b'>**수신** {', '.join(mail['to'])} "
                    f"&nbsp;·&nbsp; **발신** {mail['from']}</span>",
                    unsafe_allow_html=True)

            # 3. 본문 미리보기 — 높이를 주지 않으면 iframe이 접힌다
            st.markdown("#### 본문 미리보기")
            components.html(mail["body_html"], height=600, scrolling=True)
            with st.expander("텍스트 버전 보기 (HTML 미지원 클라이언트용)", expanded=False):
                st.code(mail["body_text"], language=None)

            # 4. 첨부 — **없는 파일도 보여준다.** 빠진 이유를 알 수 있어야 한다
            st.markdown("#### 첨부")
            head = ("<tr><th align='left'>파일명</th><th align='right'>크기</th>"
                    "<th align='left'>상태</th></tr>")
            body = ""
            for a in ed.attachments(ss.run_dir, only_existing=False):
                size = f"{a['size'] / 1024:,.0f} KB" if a["존재"] else "—"
                mark = common.badge("있음", "통과") if a["존재"] \
                    else common.badge("없음", "차단")
                body += (f"<tr><td><code>{a['filename']}</code></td>"
                         f"<td align='right'>{size}</td><td>{mark}</td></tr>")
            st.markdown(f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>",
                        unsafe_allow_html=True)
            st.caption("실제 첨부는 하지 않습니다 — 파일명·크기만 목록으로 담습니다(8주차 범위).")

            # 5. 다운로드
            st.markdown("---")
            f1, f2, f3 = st.columns([1, 1, 2])
            f1.download_button("email.html ↓", mail["body_html"].encode("utf-8"),
                               file_name="email.html", mime="text/html",
                               key="dl_mail_html", width="stretch")
            f2.download_button("email.txt ↓", mail["body_text"].encode("utf-8"),
                               file_name="email.txt", mime="text/plain",
                               key="dl_mail_txt", width="stretch")
            f3.caption(f"저장: `{Path(ss.run_dir).name}/` email.html · email.txt · email_meta.json")
        ss.step = max(ss.step, 7)
        continue

    # ── 8단계 — 발송 확정 (게이트 3) ──────────────────────────────────
    if n == 8 and ss.email:
        rd = Path(ss.run_dir)
        approved_path = rd / "APPROVED"
        done8 = approved_path.exists()
        st.markdown(f"## 8단계 — {name} "
                    f"{common.badge('완료' if done8 else '확인 필요', '통과' if done8 else '경고')}",
                    unsafe_allow_html=True)

        if done8:
            info = json.loads(approved_path.read_text(encoding="utf-8"))
            st.success(f"**확정 완료** · {info.get('발송확정_시각', '')}")
            st.markdown(f"제목 **{info.get('제목', '')}**<br>"
                        f"<span style='color:#64748b'>수신 {', '.join(info.get('수신자', []))}</span>",
                        unsafe_allow_html=True)
            st.caption(f"저장: `{rd.name}/APPROVED` · `{rd.name}/email_final.html` "
                       "— 확정본은 이후 재생성해도 바뀌지 않습니다.")
            # ── 8주차에 SMTP를 꽂을 자리 ──────────────────────────────
            #   from pipeline import send
            #   result = send.send_email(info, ed.attachments(ss.run_dir))
            #   rl.record(ss.run_dir, "9_발송", **result)
            # ★ 지금은 **호출하지 않는다.** send.py는 NotImplementedError만 던진다 —
            #   실수로 부르면 확정 완료 화면이 예외로 죽는다.
            st.caption("이 앱은 **메일을 보내지 않습니다.** 발송은 8주차에 "
                       "`pipeline/send.py`를 채워 붙입니다.")
            # ★ 되돌리기 버튼을 만들지 않는다.
            #   확정을 되돌릴 수 있으면 **확정의 의미가 없다.** 잘못했으면 새 실행을
            #   시작해 새 확정본을 만들고, 이전 확정 기록은 그대로 남긴다.
            st.info("확정은 되돌릴 수 없습니다. 다시 하려면 **새 실행**을 시작하세요 — "
                    "이전 확정 기록은 그대로 남습니다.")
            if st.button("새 실행 시작", key="new_run"):
                for k in ("df", "filename", "raw", "upload_sig", "run_dir", "override_at",
                          "metrics_df", "comparison_df", "validation", "sql_log",
                          "dep_values", "trend_df", "confirmed_at", "report_md",
                          "pdf_ctx", "merge_info", "email"):
                    ss[k] = None
                ss.step = 1
                st.rerun()
            ss.step = 8
            continue

        st.caption("**되돌릴 수 없는 게이트입니다.** 게이트 1·2는 다시 계산하면 되지만, "
                   "발송은 회수할 수 없습니다 — 그래서 확인 항목이 더 많습니다.")

        # 검증 차단이 있으면 **확정 버튼을 만들지 않는다**
        if v["차단수"]:
            st.error(f"검증에서 차단 {v['차단수']}건이 나와 확정할 수 없습니다. "
                     "데이터나 정의를 고친 뒤 다시 계산하세요.")
            for x in v["항목"]:
                if x["판정"] == "차단":
                    st.markdown(f"- **{x['대상지표']}** · {x['검증명']} — {x['상세']}")
            ss.step = 8
            continue

        mail = ss.email
        todo8 = ed.unwritten(ss.report_md)
        at8 = ed.attachments(ss.run_dir, only_existing=False)
        checklist = common.build_send_checklist(
            {**mail, "기간": str(ss.metrics_df["month"].iloc[0])}, v, todo8, at8)

        checked8 = []
        for it in checklist:
            if not it["해당"]:
                st.markdown(f"<span style='color:#64748b'>☑ {it['라벨']}</span>",
                            unsafe_allow_html=True)
                st.caption(it["상세"])
                continue
            if st.checkbox(it["라벨"], key=f"send_{it['키']}"):
                checked8.append(it["키"])
            with st.expander("무엇을 확인하는가", expanded=False):
                st.markdown(it["상세"])

        need8 = [it["키"] for it in checklist if it["해당"]]
        all8 = set(need8) <= set(checked8)

        st.markdown("---")
        st.markdown("### 🚦 게이트 3 — 발송 확정")
        st.warning("확정하면 **발송 준비 최종본**이 저장됩니다. "
                   "이 앱은 **실제로 메일을 보내지 않습니다**(8주차에 구현).")
        if not all8:
            st.info(f"확인 항목 {len(checked8)}/{len(need8)} — 남은 항목을 확인하면 "
                    "버튼이 활성화됩니다.")

        # rose = 되돌릴 수 없음을 시각적으로
        rose = common.STATUS["차단"][0]
        st.markdown(f"<style>div[data-testid='stButton'] button[kind='primary']"
                    f"{{background:{rose};border-color:{rose}}}</style>",
                    unsafe_allow_html=True)
        if st.button("발송 확정", type="primary", disabled=not all8, key="send_gate"):
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            record = {
                "발송확정_시각": stamp,
                "확인한_체크항목": [it["라벨"] for it in checklist if it["키"] in checked8],
                "제목": mail["subject"],
                "수신자": mail["to"],
                "미작성_장_목록": [f"{s['번호']}장 {s['제목']}" for s in todo8],
                "검증_경고수": v["경고수"],
                "첨부_목록": [a["filename"] for a in at8 if a["존재"]],
            }
            approved_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
            # 확정본 고정 — 이후 리포트를 다시 만들어도 **이 파일은 그대로 남는다**
            (rd / "email_final.html").write_text(mail["body_html"], encoding="utf-8")
            rl.record(ss.run_dir, "8_확정", **record)
            ss.step = 8
            st.rerun()
        ss.step = max(ss.step, 8)
        continue

    # 나머지 단계는 게이트 2를 통과해야 열린다
    if n >= 6 and ss.confirmed_at:
        label, kind2 = ("준비됨", "통과")
    else:
        label, kind2 = ("대기", "정보")
    st.markdown(f"## {n}단계 — {name} {common.badge(label, kind2)}", unsafe_allow_html=True)


# ── 사이드바 채우기 (계산·검증이 끝난 뒤의 상태로) ────────────────────
with step_slot.container():
    for n, name, who in common.STEPS:
        mark, color = ("✓", "#10b981") if n < ss.step else                       ("▶", "#f59e0b") if n == ss.step else ("·", "#64748b")
        weight = "600" if n == ss.step else "400"
        st.markdown(
            f'<div style="color:{color};font-weight:{weight};font-size:0.9em;line-height:1.7">'
            f'{mark} {n}. {name}<span style="color:#94a3b8;font-size:0.85em"> · {who}</span></div>',
            unsafe_allow_html=True)

if ss.run_dir:
    with run_slot.container():
        st.markdown("---")
        st.markdown("### 이번 실행")
        st.markdown(f"- 파일 **{ss.filename}**")
        st.markdown(f"- 폴더 `{Path(ss.run_dir).name}`")
        if ss.metrics_df is not None:
            st.caption(f"지표 {len(ss.metrics_df)}종 · 대상 월 "
                       f"{ss.metrics_df['month'].iloc[0]}")
        if ss.validation:
            vv = ss.validation
            st.markdown(f"검증 {common.badge(vv['전체판정'])} &nbsp; "
                        f"<span style='color:#475569;font-size:0.9em'>차단 {vv['차단수']} / "
                        f"경고 {vv['경고수']}</span>", unsafe_allow_html=True)

# ── 실행 기록 ─────────────────────────────────────────────────────────
# ★ 3개월 뒤 "이 숫자 어떻게 나왔나요"에 이 표 하나로 답한다.
#   어느 파일·어느 정의·어느 승인으로 나온 값인지가 단계별로 들어 있다.
if ss.run_dir:
    st.markdown("---")
    with st.expander("실행 기록 보기 — `run_log.json`", expanded=False):
        log = rl.load(ss.run_dir)
        head = ("<tr><th align='left'>단계</th><th align='left'>시각</th>"
                "<th align='right'>소요</th><th align='left'>내용</th></tr>")
        body = ""
        for r in rl.rows(log):
            gray = " style='color:#94a3b8'" if r["내용"] == "미실행" else ""
            body += (f"<tr{gray}><td>{r['단계']}</td><td>{r['시각']}</td>"
                     f"<td align='right'>{r['소요초']}</td>"
                     f"<td style='font-size:0.86em;color:#475569'>{r['내용']}</td></tr>")
        st.markdown(f"<table style='width:100%;border-collapse:collapse'>{head}{body}</table>",
                    unsafe_allow_html=True)
        envd = (log.get("_meta") or {}).get("환경") or {}
        if envd:
            st.caption("실행 환경 — " + " · ".join(f"{k} {v}" for k, v in envd.items()))
        st.download_button("run_log.json ↓",
                           json.dumps(log, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="run_log.json", mime="application/json",
                           key="dl_runlog")
