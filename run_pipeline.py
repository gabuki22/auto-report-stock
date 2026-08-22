# -*- coding: utf-8 -*-
"""파이프라인 CLI — 1~7단계를 명령 한 번으로 (6주차 Day4 실습 D).

★ **8단계(발송 확정)는 CLI로 할 수 없다.** 화면에서만 한다.
    | 방식                  | 문제                                       |
    |-----------------------|--------------------------------------------|
    | CLI에서 게이트 자동 통과 | **게이트가 무의미해진다.** 승인 없이 발송까지 간다 |
    | CLI를 아예 안 만듦     | 8주차 자동 실행을 할 수 없다                |
    | **7단계까지만 자동**    | **채택**                                    |

    *"자동화가 편의를 위해 안전장치를 지우면 자동화가 아니라 방치가 된다."*

    · 유효구간 확장은 `--approve-extension`으로 받되 **그 사실이 기록에 남는다**
      (화면 승인과 구분해서 적는다 — 누가 승인했는지가 달라진다).
    · 검증에 **차단이 있으면 그 자리에서 멈춘다**(exit 1).

★ 단계 순서가 `app.py`와 두 곳에 있다
    화면은 단계마다 게이트가 끼어 있어 한 함수로 묶이지 않는다. 대신 **각 단계는
    파이프라인 모듈의 같은 함수**를 부르므로 계산·검증·문장 규칙은 공유된다.
    두 경로가 같은 결과를 내는지는 `tests/test_reproducible.py`가 확인한다.

사용법
    py -X utf8 run_pipeline.py --file _data/usage_history_2025-01.csv --approve-extension
    py -X utf8 run_pipeline.py --file xxx.csv --month 2025-01 --skip-pdf

exit code: 정상 0 · 검증 차단 1 · 오류 2
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import calculate as calc  # noqa: E402
from pipeline import compare as cmp  # noqa: E402
from pipeline import email_draft as ed  # noqa: E402
from pipeline import manual_sections as ms  # noqa: E402
from pipeline import pdf_render as pr  # noqa: E402
from pipeline import profile as pf  # noqa: E402
from pipeline import report as rp  # noqa: E402
from pipeline import run_log as rl  # noqa: E402
from pipeline import validate as vd  # noqa: E402

TOTAL = 6
EXIT_OK, EXIT_BLOCKED, EXIT_ERROR = 0, 1, 2


def log(step: int, name: str, msg: str) -> None:
    print(f"[{step}/{TOTAL}] {name:<10} {datetime.now():%H:%M:%S}  {msg}", flush=True)


def die(msg: str, code: int, detail: list[str] = ()) -> None:
    """중단 — **왜 멈췄는지 먼저 쓰고** 무엇을 하면 되는지 이어 쓴다."""
    print(f"\n❌ {msg}", file=sys.stderr)
    for d in detail:
        print(f"   {d}", file=sys.stderr)
    sys.exit(code)


def main() -> int:
    ap = argparse.ArgumentParser(description="월간 리포트 파이프라인 (1~7단계)")
    ap.add_argument("--file", required=True, help="업로드할 CSV 경로")
    ap.add_argument("--month", help="대상 월(YYYY-MM). 생략하면 파일에서 판정")
    ap.add_argument("--approve-extension", action="store_true",
                    help="유효구간 확장을 승인한다(없으면 확장 필요 시 중단)")
    ap.add_argument("--output-dir", default=str(config.OUTPUTS_DIR))
    ap.add_argument("--skip-pdf", action="store_true", help="PDF 생성 생략")
    a = ap.parse_args()

    src = Path(a.file)
    if not src.exists():
        die(f"파일이 없습니다: {src}", EXIT_ERROR)

    metrics, m_meta = common.load_catalog("metrics_catalog")
    schema, _ = common.load_catalog("schema_catalog")
    insights, _ = common.load_catalog("insights_catalog")
    if not metrics or not schema:
        die("카탈로그가 없습니다.", EXIT_ERROR,
            ["py -X utf8 catalog/export_catalog.py 를 먼저 실행하세요."])

    # ── 1. 파일 읽기 ──────────────────────────────────────────────────
    with src.open("rb") as f:
        df = common.read_csv(f)
    raw = src.read_bytes()
    log(1, "파일 읽기", f"{src.name} ({len(df):,}행, {df.shape[1]}컬럼)")

    # ── 2. 판정 ───────────────────────────────────────────────────────
    t = pf.judge_table(df, schema)
    if not t.get("판정가능"):
        die(f"테이블을 판정하지 못했습니다: {t.get('이유', '')}", EXIT_ERROR)
    p = pf.profile_data(df, schema.get(t["테이블명"], {}))
    per = p["기간"] or {}
    period = a.month or (per.get("최소") or "")[:7]
    if not period:
        die("대상 월을 판정하지 못했습니다.", EXIT_ERROR, ["--month 2025-01 처럼 지정하세요."])
    log(2, "판정", f"{t['테이블명']} 일치율 {t.get('일치율', 0):.0%}, 기간 {period}")

    rows = pf.judge_metrics(t["테이블명"], period, metrics, t.get("누락컬럼"))
    related = [r for r in rows if r["상태"] != "이 파일과 무관"]
    blocked = [r for r in related if r["상태"] == "계산불가"]
    target = [r for r in related if r["상태"] != "계산불가"]
    ext = [r for r in target if r["상태"] == "유효구간 확장 필요"]
    if not target:
        die("이 파일로 계산할 수 있는 지표가 없습니다.", EXIT_ERROR,
            [f"누락 컬럼: {', '.join(t.get('누락컬럼') or []) or '없음'}"])

    # ★ 승인 없이 조용히 계산하지 않는다. 어느 지표가 왜 확장이 필요한지 밝히고 멈춘다.
    if ext and not a.approve_extension:
        die(f"유효구간 확장이 필요한 지표 {len(ext)}종이 있습니다.", EXIT_ERROR,
            [f"- {r['지표명']} ({r['metric_id']}) — {r['이유']}" for r in ext]
            + ["", "승인하려면 --approve-extension 을 붙여 다시 실행하세요.",
               "승인 사실은 실행 기록에 남습니다."])

    # ── 3. 계산 ───────────────────────────────────────────────────────
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    # ★ 같은 분에 두 번 돌리면 **폴더가 겹쳐 앞 실행을 덮어쓴다.**
    #   과거 주차를 연달아 돌려 정상범위 표본을 쌓으려 했더니 5회가 2회로 줄었다.
    #   "실행마다 새 폴더를 만들고 이전 것을 덮어쓰지 않는다"는 원칙이 분 단위 이름 때문에
    #   조용히 깨져 있었다. 겹치면 접미사를 붙인다.
    run_dir = Path(a.output_dir) / f"run_{stamp}"
    _n = 2
    while run_dir.exists():
        run_dir = Path(a.output_dir) / f"run_{stamp}_{_n}"
        _n += 1
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / src.name).write_bytes(raw)

    rl.record(run_dir, "0_카탈로그", 카탈로그_생성일시=m_meta.get("생성일시"),
              지표수=len(metrics), 테이블수=len(schema), 인사이트수=len(insights))
    rl.record(run_dir, "1_투입", 파일명=src.name, 크기=len(raw),
              행수=p["행수"], 컬럼수=p["컬럼수"])
    rl.record(run_dir, "2_판정", 테이블=t["테이블명"], 테이블명_추정=t.get("테이블명_추정"),
              일치율=round(t.get("일치율", 0), 4), 기간=f"{period} ~ {period}",
              누락_컬럼=t.get("누락컬럼") or [], 결측=p["결측합계"],
              그레인_중복=(p["그레인"] or {}).get("중복"))

    try:
        client = calc.make_client()
        stg = calc.load_staging(df, t["테이블명"], client, schema).split(".")[-1]
        res = calc.calculate([r["metric_id"] for r in target], period,
                             {t["테이블명"]: stg}, client,
                             a.approve_extension, metrics, include_deps=True)
    except Exception as e:                              # noqa: BLE001
        die(f"계산 실패: {type(e).__name__} — {e}", EXIT_ERROR)

    res.to_csv(run_dir / "metrics.csv", index=False, encoding="utf-8-sig")
    n_ext = int((res["status"] == "구간확장").sum())
    log(3, "계산", f"지표 {len(res)}종 계산 (구간확장 {n_ext}종)")

    rl.record(run_dir, "2_계산", 스테이징_테이블=stg, 지표수=len(res),
              지표별={r["metric_id"]: {"값": None if pd.isna(r["value"])
                                     else round(float(r["value"]), 4),
                                     "상태": r["status"]} for _, r in res.iterrows()})
    # ★ CLI에서 승인했다는 사실을 남긴다 — 화면 승인과 **누가 승인했는지가 다르다**
    rl.record(run_dir, "게이트1", 확정_시각=rl.now(), 승인경로="CLI",
              계산_대상_지표=[r["metric_id"] for r in target],
              계산불가_지표=[{"metric_id": r["metric_id"], "사유": r["이유"]} for r in blocked],
              일부만_계산=bool(blocked),
              유효구간_확장_승인=bool(ext) and a.approve_extension,
              유효구간_확장_대상=[r["metric_id"] for r in ext],
              부분_갱신_지표=[r["metric_id"] for _, r in res.iterrows()
                        if common.blank_safe(r.get("부분갱신"))])

    # ── 4. 검증 (대시보드는 화면 전용이므로 건너뛴다) ────────────────
    prev = cmp.calc_previous(list(res["metric_id"]), cmp.previous_period(period, client),
                             client, metrics, override=a.approve_extension)
    comp = cmp.compare(res, prev)
    comp.to_csv(run_dir / "comparison.csv", index=False, encoding="utf-8-sig")
    prev_rows = None
    try:
        import json as _json
        _runs = sorted((run_dir.parent).glob('run_*'), reverse=True)
        for _r0 in _runs[1:]:
            _f = _r0 / 'run_log.json'
            if _f.exists():
                _l = _json.loads(_f.read_text(encoding='utf-8'))
                for _b in _l.values():
                    if isinstance(_b, dict) and '행수' in _b:
                        prev_rows = _b['행수']; break
            if prev_rows: break
    except Exception:
        prev_rows = None
    v = vd.validate_all(res, comp, metrics, override=a.approve_extension,
                        run_log=rl.load(run_dir), prev_rows=prev_rows)
    import json
    (run_dir / "validation.json").write_text(
        json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
    rl.record(run_dir, "3_검증", 전체판정=v["전체판정"], 차단수=v["차단수"],
              경고수=v["경고수"], 점검항목수=len(v["항목"]),
              자동검증_안한_항목=v["자동검증하지_않은_것"])
    log(4, "검증", f"{v['전체판정']} (차단 {v['차단수']}, 경고 {v['경고수']})")

    # ★ 차단이 있으면 여기서 멈춘다. 화면과 같은 규칙이다.
    if v["차단수"]:
        die(f"검증에서 차단 {v['차단수']}건이 나와 중단합니다.", EXIT_BLOCKED,
            [f"- {x['대상지표']} · {x['검증명']} — {x['상세']}"
             for x in v["항목"] if x["판정"] == "차단"]
            + ["", f"실행 폴더: {run_dir}"])

    # ── 5. 리포트 (manual 병합 포함) ──────────────────────────────────
    ctx = {"파일명": src.name, "판정테이블": t["테이블명"], "기간": period,
           "행수": p["행수"], "metrics": res, "comparison": comp, "validation": v,
           "metrics_catalog": metrics, "schema_catalog": schema,
           "insights_catalog": insights, "카탈로그_메타": m_meta,
           "run_log": rl.load(run_dir), "run_dir": str(run_dir),
           "생성일시": rl.now()}
    md = rp.build_report(ctx)
    md, minfo = ms.merge_into_report(md, ms.load_manual(period))
    (run_dir / "report.md").write_text(md, encoding="utf-8")

    secs = [s for s in rp.split_sections(md) if s["번호"]]
    todo = [s for s in secs if s["미작성"]]
    log(5, "리포트", f"{len(secs)}장 생성, 미작성 {len(todo)}장"
                    + (f", 병합 {len(minfo['병합'])}장" if minfo["병합"] else ""))
    for w in minfo["경고"]:
        print(f"        ⚠️ {w}")

    if not a.skip_pdf:
        ok_font, missing = pr.font_status()
        if ok_font:
            try:
                (run_dir / "report.pdf").write_bytes(pr.build_pdf(md, ctx))
            except Exception as e:                      # noqa: BLE001 — PDF 실패로 멈추지 않는다
                print(f"        ⚠️ PDF 생성 실패: {type(e).__name__} — {e}")
        else:
            print(f"        ⚠️ 폰트 없음({', '.join(missing)}) — PDF를 건너뜁니다. "
                  f"py -X utf8 dev_tools/get_fonts.py")

    rl.record(run_dir, "6_리포트", 장수=len(secs),
              자동생성_장=[s["번호"] for s in secs if not s["미작성"]],
              미작성_장=[f"{s['번호']}장 {s['제목']}" for s in todo],
              병합된_장=minfo["병합"], 금지표현_검사=len(rp.ph.check_forbidden(md)))

    # ── 6. 이메일 초안 ────────────────────────────────────────────────
    mail = ed.build_email(ctx, md)
    (run_dir / "email.html").write_text(mail["body_html"], encoding="utf-8")
    (run_dir / "email.txt").write_text(mail["body_text"], encoding="utf-8")
    (run_dir / "email_meta.json").write_text(json.dumps(
        {k: mail[k] for k in ("subject", "to", "from", "attachments")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    rl.record(run_dir, "7_이메일", 제목=mail["subject"], 수신자=mail["to"],
              첨부_목록=[x["filename"] for x in mail["attachments"]])
    log(6, "이메일 초안", mail["subject"])

    # ── 요약 ──────────────────────────────────────────────────────────
    print(f"\n완료: {run_dir}")
    print(f"  계산 지표 {len(res)}종 · 검증 {v['전체판정']}"
          f"(차단 {v['차단수']}, 경고 {v['경고수']}) · 미작성 {len(todo)}장")
    # ★ 게이트 2·3은 **사람이 하는 단계**라 CLI가 통과시키지 않는다.
    #   실행 기록에도 "미실행"으로 남아, 화면에서 이어받을 때 그 자리부터 시작한다.
    print("\n이메일 초안이 준비되었습니다.")
    print("  내용 확인(게이트 2)과 **발송 확정(게이트 3)은 화면에서** 진행하세요 — "
          "CLI는 사람이 하는 단계를 대신하지 않습니다.")
    print(f"  py -m streamlit run app.py    (run 폴더: {run_dir.name})")
    return EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n중단됨", file=sys.stderr)
        raise SystemExit(EXIT_ERROR)
