# -*- coding: utf-8 -*-
"""Noto Sans KR 서브셋 만들기 — **저장소에 담아 어디서든 PDF가 되게.**

왜 필요한가
    배포본(Streamlit Cloud)에는 폰트가 없어 PDF를 만들지 못했다.
    화면에 "한글 폰트 없음"만 뜨고, 받는 사람은 왜 안 되는지 알 수 없다.

    Noto Sans KR은 **SIL Open Font License**라 재배포가 허용된다.
    (Malgun Gothic은 불가 — 그래서 처음부터 Noto를 골랐다.)
    그러니 저장소에 넣으면 되는데, 원본이 두 벌 합쳐 12MB다.
    대부분이 **한자(Hanja)**이고 이 리포트는 한자를 쓰지 않는다.

무엇을 남기나
    ★ **한글 음절 전체(11,172자)를 통째로 남긴다.**
      상용 2,350자만 남기는 흔한 방식은 '똠·쀼' 같은 글자에서 조용히 빈칸이 된다.
      리포트 문구는 앞으로 바뀌므로 **미래에 쓸 글자를 지금 알 수 없다.**
      음절 전체를 남기면 한글에 관한 한 커버리지 위험이 0이 된다.

    라틴·숫자·문장부호·화살표·도형 기호도 함께 남긴다(표 테두리·▲▼·★··).

무엇을 버리나
    한자·가나·그 밖의 CJK 확장. 쓰면 빈칸이 되므로 **검사로 막는다**
    (`verify` 단계가 리포트 본문 전 글자를 폰트와 대조한다).

실행
    py -X utf8 dev_tools/subset_fonts.py            # 서브셋 생성 + 검사
    py -X utf8 dev_tools/subset_fonts.py --verify   # 검사만

원본이 필요하다 — 없으면 `py -X utf8 dev_tools/get_fonts.py`를 먼저 돌린다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent          # 경로를 박지 않는다
FONT_DIR = BASE / "fonts"
PAIRS = [("NotoSansKR-Regular.ttf", "NotoSansKR-Regular-subset.ttf"),
         ("NotoSansKR-Bold.ttf", "NotoSansKR-Bold-subset.ttf")]

# 남길 유니코드 구간 — 이름을 붙여 둔다. 나중에 왜 넣었는지 알 수 있어야 한다.
KEEP = [
    ("기본 라틴·숫자·문장부호", 0x0020, 0x007E),
    ("라틴 보충(°·×÷ 등)", 0x00A0, 0x00FF),
    ("일반 문장부호(— ‘ ’ “ ” … ·)", 0x2000, 0x206F),
    ("첨자·통화(₩)", 0x2070, 0x20CF),
    ("문자꼴 기호(№ ™ Ω)", 0x2100, 0x214F),
    ("원문자(① ② ③)", 0x2460, 0x24FF),      # 사람이 쓰는 5장 소절 번호
    ("화살표(← → ↑ ↓)", 0x2190, 0x21FF),
    ("수학 기호(± ≤ ≥ ≠ ∑)", 0x2200, 0x22FF),
    ("괘선(표 테두리)", 0x2500, 0x257F),
    ("블록 원소", 0x2580, 0x259F),
    ("도형 기호(■ ▲ ▼ ● ◆)", 0x25A0, 0x25FF),
    ("기타 기호(★ ☆ ⚠ ✔)", 0x2600, 0x26FF),
    ("장식 기호(✓ ✗)", 0x2700, 0x27BF),
    ("한중일 문장부호(、。「」)", 0x3000, 0x303F),
    ("한글 자모", 0x1100, 0x11FF),
    ("한글 호환 자모(ㄱ ㅏ)", 0x3130, 0x318F),
    ("한글 음절 전체", 0xAC00, 0xD7A3),      # ★ 11,172자 — 통째로
    ("반각·전각(％ ！)", 0xFF00, 0xFFEF),
]


def _codepoints() -> set[int]:
    out: set[int] = set()
    for _, lo, hi in KEEP:
        out |= set(range(lo, hi + 1))
    return out


def build() -> None:
    from fontTools import subset

    cps = _codepoints()
    print(f"■ 남길 글자 {len(cps):,}자 · 구간 {len(KEEP)}개")
    for src_name, dst_name in PAIRS:
        src, dst = FONT_DIR / src_name, FONT_DIR / dst_name
        if not src.exists():
            raise SystemExit(f"★ 원본 없음: {src}\n  먼저: py -X utf8 dev_tools/get_fonts.py")
        opts = subset.Options()
        opts.layout_features = ["*"]        # 자소 결합·커닝 유지
        opts.name_IDs = ["*"]
        opts.notdef_outline = True          # 없는 글자를 **네모로 보이게** — 조용한 빈칸 금지
        opts.drop_tables = []
        font = subset.load_font(str(src), opts)
        s = subset.Subsetter(options=opts)
        s.populate(unicodes=cps)
        s.subset(font)
        subset.save_font(font, str(dst), opts)
        font.close()
        print(f"  {src_name}  {src.stat().st_size / 1024 / 1024:.1f}MB"
              f"  →  {dst_name}  {dst.stat().st_size / 1024 / 1024:.1f}MB")


def verify() -> int:
    """리포트가 실제로 쓰는 글자가 서브셋에 전부 있는가.

    ★ **서브셋을 만들었으면 반드시 대조한다.** 없는 글자는 빈칸이나 네모로 나가는데,
      화면에서는 멀쩡해 보이므로 PDF를 열어 보기 전까지 아무도 모른다.
    """
    from fontTools.ttLib import TTFont

    bad = 0
    for _, dst_name in PAIRS:
        dst = FONT_DIR / dst_name
        if not dst.exists():
            print(f"  ★ 없음: {dst_name}")
            bad += 1
            continue
        cmap = set(TTFont(str(dst)).getBestCmap())
        # 리포트·이메일·사람 작성분 — 실제로 PDF에 실리는 글자 전부
        texts = []
        for p in [*(BASE / "outputs").rglob("report.md"), BASE / "manual" / "sections.md"]:
            if p.exists():
                texts.append(p.read_text(encoding="utf-8"))
        # ★ 변형 선택자(U+FE0x)는 **원본 폰트에도 없다.** ⚠️ = ⚠ + U+FE0F 처럼
        #   이모지로 보이게 하는 보이지 않는 표시라 PDF 에서는 의미가 없다.
        #   렌더러(`pdf_render._clean`)가 지우므로 여기서도 셈에서 뺀다 —
        #   지우는 쪽과 세는 쪽이 어긋나면 영영 고쳐지지 않는 '누락'이 남는다.
        used = {ord(c) for t in texts for c in t
                if c not in "\r\n\t" and not (0xFE00 <= ord(c) <= 0xFE0F)}
        missing = sorted(used - cmap)
        print(f"  {dst_name}: 글자 {len(cmap):,}자 · 리포트 사용 {len(used):,}자 · "
              f"누락 {len(missing)}")
        if missing:
            bad += 1
            print("    누락:", " ".join(f"{chr(c)}(U+{c:04X})" for c in missing[:30]))
    return bad


def main() -> int:
    if "--verify" not in sys.argv:
        build()
    print("\n■ 대조 — 리포트가 쓰는 글자가 서브셋에 전부 있는가")
    bad = verify()
    print(f"\n{'통과 — 빈칸으로 나갈 글자 없음' if not bad else '★ 실패 — 위 글자를 KEEP 에 추가'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
