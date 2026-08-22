# -*- coding: utf-8 -*-
"""위키의 정의를 JSON 스냅샷으로 꺼낸다 — 설정층 → 실행층 (6주차 Day1 실습 B).

앱은 위키를 직접 읽지 않는다. 이 스크립트가 만든 catalog/*.json만 읽는다.
  · 배포 환경에 위키가 없다
  · 위키는 사람이 계속 고친다(편집 중 파일을 읽으면 깨진 상태로 계산)
  · 경로가 사람마다 다르다

지표를 추가하려면 위키에 정의서를 만들고 이 스크립트를 다시 돌린다. 앱 코드는 건드리지 않는다.

실행: py -X utf8 catalog/export_catalog.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("pyyaml이 필요합니다: py -m pip install pyyaml")

FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
DIRTY: list[str] = []          # 정리가 필요한 노트


def front_matter(text: str) -> dict | None:
    m = FM.match(text)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None


def section(text: str, *starts: str) -> str:
    """'## 시작어…' 로 시작하는 절의 본문. 제목이 조금 달라도 접두로 찾는다."""
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        if any(head.strip().startswith(s) for s in starts):
            return body.strip()
    return ""


def section_contains(text: str, needle: str) -> str:
    """제목에 needle이 들어간 절의 본문(제목이 조금 달라도 찾는다)."""
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        if needle in head:
            return body.strip()
    return ""


# ── 지표 카탈로그 ─────────────────────────────────────────────────────
def export_metrics(mdir: Path) -> dict:
    out, skipped = {}, []
    files = [p for p in sorted(mdir.glob("*.md"))
             if not p.name.startswith("_") and p.name != "README.md"]
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm = front_matter(text)
        if fm is None:
            skipped.append((p.name, "프론트매터 없음 또는 YAML 파싱 실패"))
            print(f"  ⚠️ {p.name}: 프론트매터 없음/파싱 실패 — 건너뜀")
            continue
        mid = fm.get("metric_id", p.stem)
        # ★ 이 프로젝트의 데이터셋이 아닌 지표는 담지 않는다.
        #   한 위키에 여러 도메인이 함께 살면 화면이 무관한 지표로 덮인다.
        #   "이 파일과 무관"으로 표시되긴 하지만, **다른 데이터셋 지표는 애초에
        #   이 앱이 계산할 수 없으므로** 목록에 있을 이유가 없다.
        want = getattr(config, "METRIC_DATASET_FILTER", None)
        if want and str(fm.get("데이터셋") or "").strip() != str(want):
            skipped.append((p.name, f"데이터셋이 `{want}` 가 아님"))
            continue
        spec = dict(fm)
        # 본문에서 한계 절만 가져온다. 판단 근거·검토한 대안은 넣지 않는다(앱이 안 쓴다)
        limits = section_contains(text, "답할 수 없")
        if limits:
            spec["_답할수없는것"] = limits
        # 본문에서 이 지표를 설명하며 건 인사이트 링크. tags보다 정확한 연결이다.
        spec["관련인사이트_본문링크"] = insight_links(text)
        spec["_노트파일"] = p.name
        out[mid] = spec
    print(f"  metrics: 읽음 {len(out)} / 건너뜀 {len(skipped)}")
    for n, why in skipped:
        print(f"    - {n}: {why}")
    return out


# ── 인사이트 카탈로그 ─────────────────────────────────────────────────
WIKILINK = re.compile(r"\[\[([^\]|#]+)")


def insight_links(text: str) -> list[str]:
    """본문에서 인사이트 노트로 가는 위키링크를 뽑는다.

    ★ **본문 링크가 tags 교집합보다 정확하다.** tags는 "이 지표와 이 인사이트가 같은
      주제를 다룬다"는 느슨한 신호일 뿐이고, 본문 링크는 사람이 **이 지표를 설명하려고
      직접 건 연결**이다. 두 방법을 함께 쓰되 본문 링크를 우선한다.

    프론트매터를 뺀 본문에서만 찾는다 — `source_question` 같은 프론트매터 링크는
    질문 노트를 가리키지 인사이트를 가리키지 않는다.
    """
    body = FM.sub("", text, count=1)
    return sorted({m.group(1).strip() for m in WIKILINK.finditer(body)
                   if m.group(1).strip().lower().startswith(("i-", "insight"))})


def export_insights(idir: Path | None) -> dict:
    """04_insights(또는 06_insights)/*.md → 인사이트 카탈로그."""
    out: dict[str, dict] = {}
    if idir is None:
        print("  insights: 폴더 없음 — 건너뜀 (관련 분석 인용이 비게 된다)")
        return out
    files = [p for p in sorted(idir.glob("*.md"))
             if not p.name.startswith("_") and p.name != "README.md"]
    skipped = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm = front_matter(text)
        if fm is None:
            skipped.append(p.name)
            print(f"  ⚠️ {p.name}: 프론트매터 없음/파싱 실패 — 건너뜀")
            continue
        h1 = re.search(r"^#\s+(.+)$", text, re.M)
        spec = dict(fm)
        spec["제목"] = h1.group(1).strip() if h1 else p.stem
        # 시사점이 없으면 해석 절을 쓴다. 둘 다 없으면 빈 문자열로 두고 **지어내지 않는다.**
        spec["_시사점"] = section(text, "시사점") or section(text, "해석")
        spec["_노트파일"] = p.name
        out[p.stem] = spec
    print(f"  insights: 읽음 {len(out)} / 건너뜀 {len(skipped)}")
    return out


# ── 스키마 카탈로그 ───────────────────────────────────────────────────
def clean_cell(s: str) -> str:
    return s.replace("`", "").strip()


def parse_columns(body: str, note: str) -> list[dict]:
    """마크다운 표 → [{컬럼명, 타입, 설명}].

    컬럼 표는 **기계가 읽는 구역**이다. 편집 표시가 섞이면 앱을 고치지 말고 위키를 정리한다.
    """
    cols = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [clean_cell(c) for c in line.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        if cells[0] in ("컬럼명", "컬럼") or set(cells[0]) <= set("-: "):
            continue                                   # 헤더·구분선
        name = cells[0]
        if "~~" in line:                               # 취소선 = 실물에 없는 컬럼일 가능성
            DIRTY.append(f"{note}: 취소선 셀 — 행 건너뜀 ({name})")
            continue
        if "→" in line or "실물명" in line:            # 이름이 두 개 섞임
            DIRTY.append(f"{note}: 컬럼명이 두 개 섞임 — 파싱 안 함 ({name})")
            continue
        cols.append({"컬럼명": name,
                     "타입": cells[1] if len(cells) > 1 else "",
                     "설명": cells[2] if len(cells) > 2 else ""})
    return cols


def export_schema(ddir: Path) -> dict:
    out, skipped = {}, []
    files = [p for p in sorted(ddir.glob("*.md")) if p.name != "README.md"]
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm = front_matter(text) or {}
        note = str(fm.get("data") or p.stem)

        # 테이블명 — 추측으로 동작시키되 추측임을 드러낸다
        if fm.get("bq_table"):
            table, guessed = str(fm["bq_table"]), False
        else:
            table = re.sub(r"\.csv$", "", re.sub(r"^data_", "", note))
            guessed = True

        body = section(text, "컬럼")                   # "## 컬럼" · "## 컬럼 정의 표"
        cols = parse_columns(body, p.name) if body else []
        if not cols:
            skipped.append((p.name, "컬럼 표를 찾지 못함"))
            print(f"  ⚠️ {p.name}: 컬럼 표 없음")

        out[table] = {
            "노트명": note,
            "테이블명": table,
            "테이블명_추정": guessed,
            "컬럼": cols,
            "연결": section(text, "연결"),             # "## 연결" · "## 연결 키"
            # ★ 그레인 키를 **노트가 선언하면 그대로 담는다.** 추정에만 맡기면
            #   컬럼명이 `*_id` 형태가 아닌 도메인에서 빗나가 중복 오탐이 난다.
            "그레인키": fm.get("그레인키") or fm.get("grain_keys"),
            "_노트파일": p.name,
        }
    print(f"  tables : 읽음 {len(out)} / 컬럼 미검출 {len(skipped)}")
    return out


def _jsonable(o):
    """JSON이 모르는 타입만 문자열로 낮춘다.

    YAML은 `date: 2026-08-14`를 **`datetime.date` 객체로** 읽는다(따옴표가 없으므로).
    지표 정의서에는 date 필드가 없어 지금까지 드러나지 않았고, 인사이트를 담는
    순간 터졌다. `default=str`를 통째로 걸면 어떤 타입이 조용히 문자열이 됐는지
    알 수 없으므로 **날짜 계열만** 명시적으로 처리하고 나머지는 그대로 실패시킨다.
    """
    import datetime as _dt
    if isinstance(o, (_dt.date, _dt.datetime)):
        return o.isoformat()
    raise TypeError(f"JSON으로 못 바꾸는 값: {type(o).__name__} — {o!r}")


def save(obj: dict, path: Path, wiki: Path) -> None:
    """카탈로그를 저장한다.

    ★ 원천 위키는 **폴더 이름만** 남긴다.
      전체 경로를 적으면 사용자 홈 아래 경로가 그대로 들어가는데,
      이 카탈로그는 공개 저장소에 커밋된다 — 사용자 이름과 폴더 구조가 노출된다.
      추적에 필요한 것은 *"어느 위키에서 뽑았나"*이지 *"그 위키가 어느 드라이브에
      있었나"*가 아니다.
    """
    doc = {"_meta": {"생성일시": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                     "원천_위키": wiki.name, "항목수": len(obj)}, **obj}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=_jsonable),
                    encoding="utf-8")
    print(f"  저장: {path.relative_to(config.BASE_DIR)}")


def main() -> int:
    warn = config.check_wiki()
    if warn:
        print(f"❌ {warn}")
        return 1
    mdir, ddir = config.metrics_dir(), config.data_dir()
    print(f"위키: {config.WIKI_PATH}\n  지표 {mdir.name} · 스키마 {ddir.name}\n")

    config.CATALOG_DIR.mkdir(exist_ok=True)
    metrics = export_metrics(mdir)
    save(metrics, config.CATALOG_DIR / "metrics_catalog.json", config.WIKI_PATH)
    print()
    tables = export_schema(ddir)
    save(tables, config.CATALOG_DIR / "schema_catalog.json", config.WIKI_PATH)
    print()
    insights = export_insights(config.insights_dir())
    save(insights, config.CATALOG_DIR / "insights_catalog.json", config.WIKI_PATH)

    # ★ 지표별 본문 링크 개수를 **0개도 함께** 찍는다.
    #   있는 것만 보여주면 "연결이 없다"는 사실이 화면에서 사라지고,
    #   그 지표는 tags 교집합이라는 느슨한 연결에만 기대게 된다.
    print("\n지표별 본문 인사이트 링크")
    for mid, spec in sorted(metrics.items(),
                            key=lambda kv: (not kv[1].get("관련인사이트_본문링크"), kv[0])):
        links = spec.get("관련인사이트_본문링크") or []
        print(f"  {mid:<28}{', '.join(links) if links else '0개'}")

    print(f"\n{'=' * 56}\nmetrics {len(metrics)}개 / tables {len(tables)}개 / "
          f"insights {len(insights)}개")
    if DIRTY:
        print(f"\n⚠️ 정리가 필요한 노트 {len(DIRTY)}건 — 앱이 아니라 **위키를 고친다**")
        for d in DIRTY:
            print(f"  · {d}")
    else:
        print("정리가 필요한 노트: 0건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
