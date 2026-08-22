# -*- coding: utf-8 -*-
"""숫자를 문장으로 바꾸는 규칙 — 리포트 문장의 단일 지점 (6주차 Day3 실습 B).

왜 문장 생성을 따로 분리하는가
    표만 있는 리포트는 읽기 어렵다. 그런데 문장을 만들다 보면 **금지 표현이 섞여 들어간다.**
    규칙을 한 모듈에 모아두면 한 곳에서 통제할 수 있고, 어긴 문장을 한 곳에서 잡을 수 있다.

★ 근거 강도에 맞는 표현 (Day3 개념 3절)
    같은 숫자라도 **어떤 상태에서 계산됐는지에 따라 문장이 달라야 한다.**
    | 상태            | 표현        | 왜                                          |
    |-----------------|-------------|---------------------------------------------|
    | OK              | 사실 단정   | 정의서 구간 안에서 계산됐고 검증을 통과했다  |
    | 구간확장        | 사실 + 조건 | 승인받았어도 **정의서 밖이라는 사실은 남는다** |
    | 표본부족        | 유보        | 값은 내되 **결론 근거로 쓰지 않는다**        |
    | 임계값_상태 잠정 | 조건 명시   | 근거 없이 올린 임계값은 경고를 끈 것과 같다  |

★ 서식 판정은 여기서 새로 만들지 않는다
    단위 판정(`common.unit_of`)을 화면과 공유한다. 문서가 따로 판정하면 화면에 21.7 GB로
    나온 값이 리포트에 22원으로 찍힌다 — 같은 실행의 같은 값이 두 얼굴을 갖게 된다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import config  # noqa: E402

# ★ 기간 이름은 config 한 곳에서. `_NO_PREV` 는 만드는 쪽(`fmt_change`)과
#   읽는 쪽(`describe_change`)이 **같은 문자열**을 봐야 하므로 상수로 둔다 —
#   각자 적으면 한쪽만 고쳤을 때 분기가 조용히 안 타게 된다.
_PREV = getattr(config, "PREV_LABEL", "전월")
_NO_PREV = f"{_PREV} 자료 없음"


# ── 금지 표현 (Day3 개념 4절) ─────────────────────────────────────────
# 앱은 사실과 변동만 쓴다. 아래는 **앱이 쓸 자격이 없는 말**이다.
FORBIDDEN: dict[str, str] = {
    "인과": r"때문(이다|에|이야)|탓(이다|에)|원인은|(으로|로) 인해|초래|야기|영향을 미(쳤|친)",
    "제안": r"해야( 한다| 할)|필요하다|필요가 있다|권장|제안한다|바람직|하는 것이 좋",
    "가치판단": r"개선(됐|되었|된|이)|악화|호전|우수|부진|양호|나빠(졌|진)|좋아(졌|진)|positive|negative",
    "강도": r"우려|심각|급격|현저|두드러|눈에 띄(게|는)",
    # ★ 한계를 **축소·완화하는 표현**. 한계 절이 있는데 그 옆에 "큰 영향은 없다"를 붙이면
    #   읽는 사람은 한계를 읽고도 안심한다 — 한계를 적은 의미가 사라진다.
    #   한계는 있는 그대로 적고, 그것이 결론에 얼마나 영향을 주는지는 **사람이 판단한다.**
    "완화": (r"큰 (영향|문제)(은|는)? ?없|영향(은|는) 제한적|무시할 (만|수)|"
             r"크게 (문제|영향)( 되지|을 주지)? ?않|감안하더라도|"
             r"그럼에도 (불구하고 )?(유효|충분)|충분히 (신뢰|타당)"),
}


def josa(word: str, pair: tuple[str, str] = ("은", "는")) -> str:
    """앞 단어의 **받침 유무**로 조사를 고른다.

    왜 필요한가
        "계약 기준 활성 고객 수은"처럼 조사가 틀린 문서는 그 순간 자동 생성 티가 나고,
        읽는 사람이 내용보다 형식에 눈이 간다. 지표명은 위키가 정하므로 무엇이 올지
        코드가 미리 알 수 없다 — 규칙으로 처리한다.

    한글 음절은 (코드 - 0xAC00) % 28 이 0이 아니면 받침이 있다.
    한글이 아닌 글자로 끝나면(숫자·영문) 받침 없음으로 본다.
    """
    ch = str(word or "").strip()[-1:]
    if not ch:
        return pair[1]
    if "가" <= ch <= "힣":
        return pair[0] if (ord(ch) - 0xAC00) % 28 else pair[1]
    return pair[1]


def check_forbidden(text: str) -> list[dict]:
    """텍스트에서 금지 표현을 찾아 목록으로 돌려준다.

    왜 이 검사가 필요한가
        문장 규칙을 아무리 정해도, 문장을 손으로 고치다 보면 "개선됐다" 같은 말이
        슬며시 들어온다. **생성 직후 스스로 검사**해야 리포트가 나가기 전에 잡힌다.

    검사에서 빼는 것 — **범위를 정확히 하는 것이지 규칙을 느슨하게 하는 것이 아니다.**
       · 제목(`#`)      : 6장 제목이 "개선 제안"이라 "개선"에 걸린다. 제목은 8장 구조로
                          고정돼 있고 **앱이 생성한 문장이 아니다.**
       · 인용 블록(`>`) : 자리표시자에 "판단은 사람이 한다" 같은 **규칙 설명 자체**가 들어 있다.
       · 표 구분선
       그 밖의 본문은 예외 없이 본다. 오탐을 없애려고 **패턴을 무디게 만들면 안 된다** —
       그 순간 검사기는 진짜 위반도 놓친다.
    """
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("|---"):
            continue
        for kind, pat in FORBIDDEN.items():
            for m in re.finditer(pat, s):
                hits.append({"줄": i, "유형": kind, "표현": m.group(0), "문장": s[:80]})
    return hits


# ── 함수 1 — 값 ───────────────────────────────────────────────────────
def fmt_value(value, 유형: str = "", 지표명: str = "", metric_id: str = "",
              단위: str = "") -> str:
    """값을 단위에 맞춰 적는다. 값이 없으면 **"값 없음"**.

    왜 "값 없음"이라고 쓰는가
        빈칸이나 0으로 두면 읽는 사람이 **0이라는 값**으로 읽는다. "데이터 없음"과
        "값이 0"은 전혀 다른 사실이고, 그 차이가 보고서의 결론을 바꾼다.

    단위 판정은 `common.unit_of`에 맡긴다 — 유형 문자열만 믿으면
    `avg_data_usage`(유형이 금액형인데 실제는 GB 평균)가 "22원"으로 나온다.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "값 없음"
    # ★ `단위`를 넘겨받아 `common.unit_of`에 전달한다. 안 넘기면 이름으로 추측하게 되고,
    #   재고 수량이 "9,612,247명"으로 나온다(리포트·이메일에서 실제로 그랬다).
    unit = common.unit_of({"metric_id": metric_id, "지표명": 지표명,
                           "유형": 유형, "단위": 단위})
    if unit == "%":
        return f"{value * 100:,.1f}%"
    if unit == "명":
        # 선언이 없어 추측으로 "명"이 된 경우 — 지표명에 '건'이 있으면 건으로
        unit = "건" if "건" in str(지표명) else "명"
    # 서식 규칙은 common 한 곳에만 둔다. 여기 사본을 두면 화면과 문서가 갈라진다.
    return common.fmt_unit(value, unit)


def _unit_of_row(row) -> str:
    return common.unit_of(row if isinstance(row, dict) else row.to_dict())


# ── 함수 2 — 변화 ─────────────────────────────────────────────────────
def fmt_change(row) -> str:
    """절대 변화와 변화율을 **함께** 적는다 — "+314,819원 (+1.15%)".

    왜 둘 다 적는가
        변화율만 적으면 규모를 모르고(1%가 3천만 원일 수도 3천 원일 수도 있다),
        절대값만 적으면 크기를 판단할 기준이 없다.

    비율 지표는 **%p와 %를 둘 다** 적는다. 36.6% → 39.0%는 +2.4%p이자 +6.6%다.
    하나만 쓰면 읽는 사람이 다른 쪽으로 이해하고, 그 차이가 결론을 바꾼다.
    """
    d = row.get("절대변화")
    rate = row.get("상대변화율")
    if d is None or pd.isna(d):
        why = common.blank_safe(row.get("이유"))
        return f"{_NO_PREV} — 비교 불가" + (f" ({why})" if why else "")

    rate_txt = "" if rate is None or pd.isna(rate) else f" ({rate:+.2f}%)"
    if d == 0:
        # 0에 +를 붙이지 않는다. "+0.00%"는 아주 작은 증가처럼 읽힌다.
        return "변화 없음 (0.00%)"

    pp = row.get("퍼센트포인트변화")
    if pp is not None and not pd.isna(pp):
        return f"{pp:+.1f}%p{rate_txt}"

    unit = _unit_of_row(row)
    if unit == "GB":
        head = f"{d:+,.1f} GB"
    elif unit == "원":
        head = f"{d:+,.0f}원"
    elif unit in common.COUNT_UNITS:
        u = unit
        if u == "명" and "건" in str(row.get("지표명", "")):
            u = "건"
        head = f"{d:+,.0f}{u}"
    else:
        head = f"{d:+,.4g}"
    return head + rate_txt


# ── 함수 3 — 값 서술 ──────────────────────────────────────────────────
def describe_metric(row, status: str = "", spec: dict | None = None) -> str:
    """지표 하나를 **근거 강도에 맞는 한 문장**으로 적는다.

    왜 상태마다 문장이 다른가
        "27,804,305원이다"와 "27,804,305원으로 나타나나 근거로 쓰지 않는다"는
        같은 숫자에 대한 전혀 다른 진술이다. 상태를 문장에 반영하지 않으면
        **표본 3건짜리 값이 확정된 사실처럼 읽힌다.**
    """
    spec = spec or {}
    name = row.get("지표명", row.get("metric_id", "지표"))
    status = status or common.blank_safe(row.get("status")) or "OK"
    val = fmt_value(row.get("value"), row.get("유형", ""), name, row.get("metric_id", ""),
                    row.get("단위", ""))

    j = josa(name)
    # ★ 값이 없으면 **그 사실이 상태보다 먼저다.** 순서를 바꾸면 "이탈 손실 금액은
    #   값 없음이다(정의서 유효구간 밖, 확장 승인)" 같은 문장이 나온다 — 계산되지
    #   않은 지표를 마치 "값 없음"이라는 값을 가진 것처럼 서술하게 된다.
    if val == "값 없음":
        why = status if status and status != "OK" else "사유 미상"
        base = f"{name}{j} 계산되지 않았다({why})."
    elif status == "표본부족":
        n = row.get("sample_size")
        n_txt = f"{n:,.0f}건" if isinstance(n, (int, float)) and not pd.isna(n) else "기준 미달"
        base = (f"{name}{j} {val}으로 나타나나 표본 {n_txt}으로 기준에 미달해 "
                f"근거로 쓰지 않는다.")
    elif status == "구간확장":
        base = f"{name}{j} {val}이다(정의서 유효구간 밖, 확장 승인)."
    else:
        base = f"{name}{j} {val}이다."

    # 지표 **내부 판정 임계값**(저사용 기준 10GB 같은)이 잠정이면 문장에 남긴다.
    # 실습 E의 `변동임계값`(전월 대비 경고 기준)과는 다른 값이므로 "판정 임계값"이라 쓴다.
    # 이 문장이 그대로 리포트 한계 절의 재료가 된다.
    if str(spec.get("임계값_상태", "")).strip() == "잠정":
        body = base.rstrip(".")
        # 이미 괄호로 끝나면 그 안에 합친다 — "…(A) (B)."는 읽기 나쁘다
        base = (body[:-1] + "; 판정 임계값 잠정)." if body.endswith(")")
                else body + "(판정 임계값 잠정).")
    return base


# ── 함수 4 — 변화 서술 ────────────────────────────────────────────────
def describe_change(row, threshold: float | None = None, basis: str = "") -> str:
    """전월 대비 변화를 한 문장으로 적는다. **방향에 가치판단을 붙이지 않는다.**

    왜 "증가했다"까지만 쓰는가
        매출 증가가 늘 좋은 것도, 사용량 감소가 늘 나쁜 것도 아니다. 무엇이 좋은
        변화인지는 조직의 목표에 달렸고 그것은 데이터에 없다. 앱이 방향에 값을
        매기기 시작하면 읽는 사람이 그 판단을 그대로 옮겨 적는다.
    """
    name = row.get("지표명", row.get("metric_id", "지표"))
    j = josa(name)
    change = fmt_change(row)
    if change.startswith(_NO_PREV):
        return f"{name}{j} {change}."

    rate = row.get("상대변화율")
    # "변화 없음"은 "…없음로"가 되어 조사가 붙지 않는다. 문장을 나눈다.
    head = (f"{name}{j} {_PREV} 대비 변화가 없다(0.00%)"
            if change.startswith("변화 없음") else f"{name}{j} {_PREV} 대비 {change}")
    if threshold is None or rate is None or pd.isna(rate):
        return head + "."

    th = f"{threshold:g}%" + (f" ({basis})" if basis else "")
    tail = (f"임계값 {th}를 초과했다" if abs(rate) >= threshold
            else f"임계값 {th} 이내다")
    return (f"{head}. {tail[0].upper() + tail[1:]}."
            if change.startswith("변화 없음") else f"{head}로 {tail}.")
