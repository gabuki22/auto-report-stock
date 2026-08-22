# -*- coding: utf-8 -*-
"""검증 결과 미리보기 — 앱을 띄우지 않고 3·5단계 화면을 HTML로 확인한다.

왜 필요한가
    검증 결과를 터미널 출력으로만 보면 **실제 화면에서 어떻게 보이는지** 알 수 없다.
    색이 맞는지, 기준 열이 나오는지, 체크리스트 문구가 자연스러운지는 렌더를 봐야 안다.
    그렇다고 확인할 때마다 앱을 띄워 CSV를 올리는 건 느리다(BigQuery 왕복도 생긴다).

무엇을 보장하는가
    ★ **앱과 같은 함수로 그린다.** `common.validation_table` · `not_automated_box` ·
      `build_checklist`를 그대로 호출한다. 여기서 예쁘게 보이려고 별도 HTML을 짜면
      미리보기와 실제 화면이 갈라지고, 그때부터 이 도구는 거짓말을 한다.

    py -X utf8 dev_tools/preview_validation.py            # 최신 실행 폴더
    py -X utf8 dev_tools/preview_validation.py run_2026...  # 특정 실행 폴더
"""
from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import common  # noqa: E402
import config  # noqa: E402
from pipeline import validate as vd  # noqa: E402

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: 'Malgun Gothic','Segoe UI',system-ui,sans-serif; margin:0;
       background:#f8fafc; color:#0f172a; line-height:1.6; }
@media (prefers-color-scheme: dark) {
  body { background:#0f172a; color:#e2e8f0; }
  .card { background:#1e293b !important; border-color:#334155 !important; }
  th { border-color:#334155 !important; color:#94a3b8 !important; }
  td { border-color:#1e293b !important; }
  .muted { color:#94a3b8 !important; }
  code { background:#334155 !important; }
}
.wrap { max-width:1100px; margin:0 auto; padding:28px 22px 60px; }
h1 { font-size:1.5rem; margin:0 0 4px; }
h2 { font-size:1.15rem; margin:32px 0 10px; padding-top:18px;
     border-top:1px solid rgba(100,116,139,.25); }
h3 { font-size:0.98rem; margin:18px 0 8px; }
.muted { color:#64748b; font-size:0.88rem; }
.card { background:#fff; border:1px solid #e2e8f0; border-radius:12px;
        padding:16px 20px; margin:10px 0; }
table { width:100%; border-collapse:collapse; font-size:0.92rem; }
th { text-align:left; font-weight:600; font-size:0.82rem; color:#64748b;
     border-bottom:1px solid #e2e8f0; padding:7px 8px; }
td { padding:7px 8px; border-bottom:1px solid #f1f5f9; vertical-align:top; }
code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:0.88em; }
.chk { display:flex; gap:9px; align-items:flex-start; padding:9px 0;
       border-bottom:1px solid rgba(100,116,139,.15); }
.box { font-family:monospace; font-size:1.05rem; line-height:1.35; }
.files a { color:#3b82f6; text-decoration:none; }
.files a:hover { text-decoration:underline; }
.note { font-size:0.86rem; color:#64748b; margin:6px 0 0 27px; white-space:pre-wrap; }
"""


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def md_lite(s: str) -> str:
    """상세 문구의 **굵게** 와 `코드` 만 살린다 — 미리보기용 최소 변환."""
    import re
    out = esc(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    return out.replace("\n", "<br>")


def main() -> None:
    runs = sorted((BASE / "outputs").glob("run_*"))
    if not runs:
        sys.exit("outputs/run_* 가 없습니다. 앱에서 한 번 실행한 뒤 다시 돌리세요.")
    run = (BASE / "outputs" / sys.argv[1]) if len(sys.argv) > 1 else runs[-1]
    if not run.is_dir():
        sys.exit(f"실행 폴더 없음: {run}")

    metrics_df = pd.read_csv(run / "metrics.csv", encoding="utf-8-sig")
    comp_df = pd.read_csv(run / "comparison.csv", encoding="utf-8-sig")
    catalog, meta = common.load_catalog("metrics_catalog")
    ext = any(str(r.get("status")) == "구간확장" for _, r in metrics_df.iterrows())
    v = vd.validate_all(metrics_df, comp_df, catalog, override=ext)
    period = str(metrics_df["month"].iloc[0])
    log = json.loads((run / "run_log.json").read_text(encoding="utf-8"))

    attn = [x for x in v["항목"] if x["판정"] in ("차단", "경고")]
    rest = [x for x in v["항목"] if x["판정"] not in ("차단", "경고")]
    color = common.STATUS[v["전체판정"]][0]

    # ── 3단계 ────────────────────────────────────────────────────────
    parts = [
        f"<h1>검증 결과 미리보기</h1>",
        f"<div class='muted'>실행 <code>{run.name}</code> · 대상 월 {period} · "
        f"파일 {esc(log.get('파일명', '?'))} · 카탈로그 {esc(meta.get('생성일시', '?'))}</div>",
        "<h2>3단계 — 검증 실행</h2>",
        f"<div class='card' style='border:2px solid {color};background:{color}14'>"
        f"<span style='font-size:1.5em;font-weight:700;color:{color}'>{v['전체판정']}</span>"
        f"<span style='margin-left:14px'>차단 <b>{v['차단수']}건</b> · 경고 <b>{v['경고수']}건</b>"
        f" · 점검 {len(v['항목'])}건</span></div>",
        f"<h3>확인이 필요한 항목 {len(attn)}건</h3>",
        f"<div class='card'>{common.validation_table(attn)}</div>",
        f"<h3>통과·정보 항목 {len(rest)}건</h3>",
        f"<div class='card'>{common.validation_table(rest)}</div>",
        common.not_automated_box(v["자동검증하지_않은_것"]),
    ]

    # ── 5단계 체크리스트 ─────────────────────────────────────────────
    items = common.build_checklist(period, v, metrics_df, comp_df)
    need = [i for i in items if i["해당"]]
    rows = []
    for it in items:
        mark = "☐" if it["해당"] else "☑"
        tone = "" if it["해당"] else " style='color:#64748b'"
        tail = "" if it["해당"] else " <span class='muted'>(해당 없음 · 자동 충족)</span>"
        rows.append(f"<div class='chk'><span class='box'{tone}>{mark}</span>"
                    f"<div><div{tone}>{esc(it['라벨'])}{tail}</div>"
                    f"<div class='note'>{md_lite(it['상세'])}</div></div></div>")
    parts += [
        "<h2>5단계 — 내용·검증 결과 확인 (게이트 2)</h2>",
        f"<div class='card'>{''.join(rows)}</div>",
        f"<div class='muted'>체크 필요 <b>{len(need)}종</b> — 전부 체크해야 "
        f"“확인 완료, 리포트 생성 단계로” 버튼이 활성화됩니다. "
        f"{'차단이 있어 버튼 자체가 생성되지 않습니다.' if v['차단수'] else ''}</div>",
    ]

    # ── 파일 링크 ────────────────────────────────────────────────────
    files = [("metrics.csv", "계산 결과"), ("comparison.csv", "전월 대비"),
             ("validation.json", "검증 결과(확정 시점)"), ("run_log.json", "실행 기록"),
             (log.get("파일명", ""), "업로드 원본")]
    lis = "".join(
        f"<li><a href='{n}'>{n}</a> <span class='muted'>— {d}"
        f" · {(run / n).stat().st_size:,}B</span></li>"
        for n, d in files if n and (run / n).exists())
    parts += ["<h2>이 실행의 파일</h2>",
              f"<div class='card files'><ul style='margin:0;padding-left:20px'>{lis}</ul></div>",
              "<div class='muted'>앱과 <b>같은 렌더 함수</b>로 그렸습니다 "
              "(<code>validation_table</code> · <code>not_automated_box</code> · "
              "<code>build_checklist</code>). 미리보기용 HTML을 따로 짜면 "
              "실제 화면과 갈라져 이 페이지가 거짓말을 하게 됩니다.</div>"]

    html = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>검증 미리보기 · {run.name}</title><style>{CSS}</style></head>"
            f"<body><div class='wrap'>{''.join(parts)}</div></body></html>")

    out = run / "preview_validation.html"
    out.write_text(html, encoding="utf-8")
    print(f"미리보기 생성: {out}")
    print(f"  판정 {v['전체판정']} · 차단 {v['차단수']} · 경고 {v['경고수']} · 점검 {len(v['항목'])}")
    print(f"  체크리스트 {len(items)}항목 (체크 필요 {len(need)})")
    if "--open" in sys.argv:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
