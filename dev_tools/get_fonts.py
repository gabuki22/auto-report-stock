# -*- coding: utf-8 -*-
"""PDF용 한글 폰트를 받는다 — Noto Sans KR 정적 TTF (6주차 Day3 실습 E).

왜 Malgun Gothic을 쓸 수 없는가
    Windows 기본 폰트지만 **재배포가 불가**하다. 앱에 포함해서 배포할 수 없다.
    Noto Sans KR은 OFL 라이선스라 재배포할 수 있다. 라이선스 문제라 우회할 방법이 없다.

왜 **정적(static)** 폰트여야 하는가
    zip 최상단의 `NotoSansKR[wght].ttf`는 **가변 폰트**다. fpdf2에서 굵기가 적용되지
    않거나 오류가 난다. `static/` 폴더 안의 Regular·Bold를 써야 한다.

    py -X utf8 dev_tools/get_fonts.py           # 없으면 받는다
    py -X utf8 dev_tools/get_fonts.py --force   # 있어도 다시 받는다
"""
from __future__ import annotations


import sys

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FONT_DIR = BASE / "fonts"

# 받을 대상 — 이름·굵기를 코드 위쪽 한 곳에 모은다.
# 다른 폰트로 바꾸려면 여기만 고치면 되고, 아래 로직에는 폰트 이름이 등장하지 않는다.
FAMILY = "Noto Sans KR"
WEIGHTS = {400: "NotoSansKR-Regular.ttf", 700: "NotoSansKR-Bold.ttf"}
WANT = list(WEIGHTS.values())

# ★ 어디서 받는가 — **CSS API**를 쓴다.
#   · zip 다운로드(`fonts.google.com/download?family=…`)는 이제 zip 대신 HTML을 준다(실측).
#   · GitHub `google/fonts` 저장소에는 **가변 폰트 `NotoSansKR[wght].ttf`(10.4MB)뿐**이다.
#     교안이 경고한 그 파일이라 fpdf2에서 굵기가 안 먹는다.
#   · CSS API는 **UA에 따라 다른 포맷**을 준다. 실측 결과(2026-08-21):
#         "Mozilla/4.0"                      → ttf 2건  ✅
#         "Mozilla/4.0 (compatible; MSIE 6.0…)" → 빈 응답 (EOT 대상으로 보고 아무것도 안 줌)
#         최신 Chrome UA                     → 187KB, CJK를 unicode-range로 쪼갠 woff2 수십 개
#     ⚠️ **UA를 더 그럴듯하게 바꾸지 말 것.** 구체적으로 쓸수록 TTF를 안 준다.
CSS_URL = ("https://fonts.googleapis.com/css2?family="
           + FAMILY.replace(" ", "+") + ":wght@" + ";".join(str(w) for w in WEIGHTS))
LEGACY_UA = "Mozilla/4.0"
MANUAL = f"""수동 다운로드 방법
  1. fonts.google.com/noto/specimen/Noto+Sans+KR 접속
  2. 우측 상단 [Get font] → [Download all]
  3. 받은 zip 압축 해제
  4. **static/ 폴더 안의** {' , '.join(WANT)} 를
     {FONT_DIR} 로 복사

  ⚠️ zip 최상단의 NotoSansKR[wght].ttf 는 **가변 폰트**입니다.
     fpdf2에서 굵기가 적용되지 않거나 오류가 나므로 static/ 쪽을 쓰세요."""


def have_all() -> bool:
    return all((FONT_DIR / n).exists() and (FONT_DIR / n).stat().st_size > 100_000
               for n in WANT)


def report() -> None:
    for n in WANT:
        p = FONT_DIR / n
        if p.exists():
            print(f"  ✅ {n:<28}{p.stat().st_size / 1024 / 1024:,.1f} MB")
        else:
            print(f"  ❌ {n:<28}없음")


def _fetch(url: str, ua: str, timeout: int = 120) -> bytes:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download() -> bool:
    """CSS API에서 weight별 정적 TTF URL을 읽어 내려받는다."""
    import re

    print(f"  CSS 조회 — {CSS_URL}")
    try:
        css = _fetch(CSS_URL, LEGACY_UA, 60).decode("utf-8", "replace")
    except Exception as e:                          # noqa: BLE001 — 원인을 그대로 보여준다
        print(f"    실패: {type(e).__name__} — {e}")
        return False

    # @font-face 블록마다 font-weight와 src url을 짝지어 뽑는다
    found: dict[int, str] = {}
    for block in css.split("@font-face"):
        w = re.search(r"font-weight:\s*(\d+)", block)
        u = re.search(r"src:\s*url\((https://[^)]+\.ttf)\)", block)
        if w and u:
            found[int(w.group(1))] = u.group(1)

    missing = [w for w in WEIGHTS if w not in found]
    if missing:
        # ttf가 안 나왔다면 woff2를 받은 것이다 — UA 문제이므로 조용히 넘기지 않는다
        print(f"    CSS에서 굵기 {missing}의 TTF를 찾지 못했습니다 "
              f"(응답에 ttf {css.count('.ttf')}건 / woff2 {css.count('.woff2')}건)")
        return False

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for w, name in WEIGHTS.items():
        try:
            blob = _fetch(found[w], LEGACY_UA)
        except Exception as e:                      # noqa: BLE001
            print(f"    {name} 실패: {type(e).__name__} — {e}")
            return False
        # 파일 앞 4바이트로 TTF인지 본다. HTML 오류 페이지를 폰트로 저장하면
        # 등록 단계에서야 터지고 원인을 찾기 어렵다.
        if blob[:4] not in (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO"):
            print(f"    {name} 실패: 폰트 파일이 아님 ({len(blob):,} bytes)")
            return False
        (FONT_DIR / name).write_bytes(blob)
        print(f"    받음: {name}  ({len(blob) / 1024 / 1024:,.1f} MB)")
    return True


def render_test() -> bool:
    """받은 폰트를 fpdf2에 **실제로 등록해** 한글이 렌더링되는지 확인한다.

    파일이 존재한다는 것만으로는 부족하다 — 가변 폰트를 받아도 파일은 있고,
    등록은 되는데 **글자가 네모(□)로 나온다.** 그래서 1페이지를 실제로 만들어 본다.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        print("  fpdf2 미설치 — py -m pip install fpdf2")
        return False

    pdf = FPDF()
    pdf.add_page()
    try:
        pdf.add_font("Noto", "", str(FONT_DIR / WANT[0]))
        pdf.add_font("Noto", "B", str(FONT_DIR / WANT[1]))
    except Exception as e:                          # noqa: BLE001
        print(f"  폰트 등록 실패: {type(e).__name__} — {e}")
        return False

    pdf.set_font("Noto", "B", 18)
    pdf.cell(0, 12, "한글 테스트 — 굵게", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 12)
    for line in ["월간 지표 리포트 — 2025-01",
                 "청구 매출은 27,804,305원이다.",
                 "저사용 고객 비율은 39.0%이다(판정 임계값 잠정).",
                 "가나다라마바사 아자차카타파하 0123456789 ABCabc"]:
        pdf.cell(0, 9, line, new_x="LMARGIN", new_y="NEXT")

    out = FONT_DIR / "_font_test.pdf"
    pdf.output(str(out))
    print(f"  테스트 PDF: {out}  ({out.stat().st_size / 1024:,.0f} KB)")
    return True


def main() -> int:
    print(f"폰트 폴더: {FONT_DIR}")
    force = "--force" in sys.argv

    if have_all() and not force:
        print(f"\n이미 있습니다 ({FAMILY})")
        report()
    else:
        print(f"\n{FAMILY} 정적 TTF를 받습니다")
        if not download():
            print("\n❌ 자동 다운로드 실패\n")
            print(MANUAL)
            report()
            return 1
        report()

    print("\n한글 렌더링 확인")
    if not render_test():
        return 1
    print("\n_font_test.pdf 를 열어 한글이 네모(□□□)로 나오지 않는지 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
