# -*- coding: utf-8 -*-
"""사람이 쓰는 장을 관리한다 — 재생성해도 보존 (6주차 Day4 실습 A).

풀려는 문제
    리포트를 다시 만들면 사람이 쓴 2·5·6장이 **날아간다.** Day3 마지막에 판단만 하고
    미뤄둔 그 문제다.

왜 별도 파일인가 (교안 A-1의 세 방안 중)
    | 방안                          | 판정                                   |
    |-------------------------------|----------------------------------------|
    | **별도 파일에 두고 생성 시 병합** | **채택** — 재생성해도 남고, 사람이 고칠 수 있다 |
    | 화면에서 입력받아 run 폴더에 저장 | 실행마다 다시 써야 한다                 |
    | 이전 실행에서 불러오기          | **기간이 다른데 그대로 쓸 위험**        |

    채택안에도 위험이 하나 있다 — **지난달 내용을 그대로 쓰는 것.**
    그래서 작성일·대상기간을 함께 적어두고 어긋나면 경고한다. 막지는 않는다.
    이번 달에도 유효한 배경이라면 그대로 쓰는 게 맞고, 그 판단은 사람이 한다.

★ 장 번호·제목은 `report.HUMAN_SECTIONS` 한 곳에서 온다
    템플릿이 "## 5. 원인 분석"을 자기 식으로 적으면 리포트의 헤딩과 한 글자만 달라도
    **병합이 조용히 실패한다.** 교안이 "다르게 나오면"에서 지목한 그 함정이다.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import report as rp  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
MANUAL_PATH = BASE / "manual" / "sections.md"

# 작성일이 이만큼 지나면 알린다. 막지 않고 알리기만 한다 —
# 오래된 배경이 여전히 맞을 수도 있고, 그 판단은 사람 몫이다.
STALE_DAYS = 60

FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def template(period: str = "", author: str = "(이름)") -> str:
    """빈 템플릿. **각 장에 무엇을 써야 하는지 힌트를 함께** 넣는다.

    빈 헤딩만 있으면 무엇을 쓸지 몰라 결국 안 쓰게 된다.
    힌트는 주석(`<!-- -->`)이라 지우지 않아도 리포트에 그대로 남지 않는다.
    """
    out = ["---",
           f"작성일: {date.today().isoformat()}",
           f"대상기간: {period}",
           f"작성자: {author}",
           "---", ""]
    for n, spec in rp.HUMAN_SECTIONS.items():
        out += [rp.heading(n), "",
                f"<!-- {spec['작성힌트']} -->", ""]
    return "\n".join(out)


def ensure_file(period: str = "") -> bool:
    """파일이 없으면 템플릿을 만든다. 새로 만들었으면 True."""
    if MANUAL_PATH.exists():
        return False
    MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_PATH.write_text(template(period), encoding="utf-8")
    return True


def _front_matter(text: str) -> dict:
    m = FM.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def load_manual(period: str) -> dict:
    """`manual/sections.md` → 장번호별 내용 + 경고.

    반환: {"장": {번호: 내용}, "경고": [...], "메타": {...}, "생성됨": bool}

    ★ 내용이 비어 있는 장은 **담지 않는다.** 빈 문자열을 담으면 병합 단계에서
      자리표시자를 **빈 칸으로 덮어써** 리포트가 "작성됨"으로 보이면서 아무 내용도 없게 된다.
    """
    created = ensure_file(period)
    text = MANUAL_PATH.read_text(encoding="utf-8")
    meta = _front_matter(text)
    body = FM.sub("", text, count=1)

    # 헤딩 분할은 리포트와 같은 함수를 쓴다 — 규칙이 두 곳이면 어긋난다
    sections = {}
    for s in rp.split_sections(body):
        if not s["번호"]:
            continue
        content = re.sub(r"<!--.*?-->", "", s["본문"], flags=re.S).strip()
        if content:
            sections[s["번호"]] = content

    warns = []
    if created:
        warns.append(f"`{MANUAL_PATH.relative_to(BASE)}` 템플릿을 새로 만들었습니다. "
                     "각 장을 채운 뒤 리포트를 다시 생성하세요.")

    # 기간 불일치 — **지난달 내용을 그대로 쓰는** 것이 이 방식의 유일한 위험이다
    wrote_for = meta.get("대상기간", "")
    if sections and wrote_for and period and wrote_for != period:
        warns.append(f"이전 기간({wrote_for}) 내용입니다. 이번 대상 기간은 {period}입니다 — "
                     "그대로 써도 되는지 확인하세요.")

    # 오래됨
    try:
        written = datetime.fromisoformat(str(meta.get("작성일", ""))).date()
        aged = (date.today() - written).days
        if sections and aged >= STALE_DAYS:
            warns.append(f"작성일 {written.isoformat()} — {aged}일 지났습니다.")
    except ValueError:
        if meta.get("작성일"):
            warns.append(f"작성일을 읽지 못했습니다: {meta.get('작성일')!r}")

    return {"장": sections, "경고": warns, "메타": meta, "생성됨": created}


def merge_into_report(report_md: str, manual: dict) -> tuple[str, dict]:
    """리포트의 자리표시자를 사람이 쓴 내용으로 바꾼다.

    ★ 반환이 문자열 하나가 아닌 이유: **어느 장이 채워졌고 어느 장이 남았는지**를
      화면과 이메일 제목이 알아야 한다(미작성이면 제목에 "(초안)"이 붙는다).
      병합된 문자열만 돌려주면 그 정보를 다시 파싱해야 한다.

    내용이 없는 장은 **자리표시자를 그대로 남긴다.** 지우면 리포트가 "숫자 보고서"가 되고,
    받는 사람은 그것을 완결된 분석으로 오해한다(Day3 개념 1절).
    """
    written = manual.get("장") or {}
    merged, remain = [], []
    out_lines: list[str] = []

    for s in rp.split_sections(report_md):
        if not s["번호"]:
            out_lines.append(s["본문"])
            continue
        head = f"## {s['번호']}. {s['제목']}"
        body = s["본문"]
        if s["미작성"] and s["번호"] in written:
            body = written[s["번호"]]
            merged.append(s["번호"])
        elif s["미작성"]:
            remain.append(s["번호"])
        out_lines.append(f"{head}\n\n{body}")

    return "\n\n".join(out_lines).rstrip() + "\n", {
        "병합": merged, "미작성": remain,
        "경고": manual.get("경고") or [],
    }


def save_manual(text: str, period: str, author: str = "") -> None:
    """화면에서 편집한 내용을 저장한다. **프론트매터를 현재 값으로 갱신한다.**

    갱신하지 않으면 이번 달에 쓴 글이 지난달 작성일을 달고 남아, 다음 달에
    "오래됨"·"기간 불일치" 경고가 뜨지 않는다 — 경고가 있으나 마나 해진다.
    """
    body = FM.sub("", text, count=1).strip()
    old = _front_matter(text)
    head = ["---",
            f"작성일: {date.today().isoformat()}",
            f"대상기간: {period}",
            f"작성자: {author or old.get('작성자', '(이름)')}",
            "---", ""]
    MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_PATH.write_text("\n".join(head) + body + "\n", encoding="utf-8")
