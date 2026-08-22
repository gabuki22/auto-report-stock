# -*- coding: utf-8 -*-
"""화면의 모양을 정하는 **한 파일** — 메탈 테마.

왜 한 파일인가
    색과 크기가 여러 파일에 흩어져 있었다. 인라인 스타일마다 `#475569` 같은 값이
    박혀 있었고, 그 값들은 **밝은 배경을 가정하고 고른 것**이라 어두운 화면에서
    글자가 배경에 묻혔다. 한 곳에서 토큰으로 내려보내면 그런 일이 생기지 않는다.

무엇이 "메탈"인가
    ★ **금속은 색이 아니라 빛의 방향이다.**
      같은 회색이라도 위가 밝고 아래가 어두우면 볼록해 보이고, 반대면 오목해 보인다.
      그래서 면마다 `위쪽 1px 밝은 선(하이라이트) + 아래쪽 어두운 선(그림자)`을 준다.
      여기에 아주 옅은 세로 결(brushed) 을 얹으면 판금처럼 읽힌다.

    색은 채도를 거의 빼고 **푸른기 도는 무채색(gunmetal)** 으로 간다.
    선명한 색은 상태(통과·경고·차단)에만 남겨 둔다 — 화면에서 색이 뜻을 갖게 하려면
    그 색이 흔하면 안 된다. (CLAUDE.md 7절 상태 색 대응은 그대로 지킨다.)

글자 위계
    제목·소제목·본문·캡션이 크기만이 아니라 **무게·자간·색**까지 달라야 구분된다.
    크기만 줄이면 "작은 제목"이 되고, 색까지 낮춰야 "덜 중요한 것"이 된다.
"""
from __future__ import annotations

# ── 토큰 ──────────────────────────────────────────────────────────────
# 값을 여기 밖에 적지 않는다. 인라인 스타일은 var(--tk-*) 로 참조한다.
TOKENS = {
    # 바탕 — 아래로 갈수록 어두운 무채색. 푸른기를 조금 남겨 차가운 금속으로.
    "bg":          "#0c0f13",
    "surface":     "#161b22",     # 카드·표 바탕
    "surface-2":   "#1d232b",     # 표 머리·강조 면
    "surface-3":   "#242b34",     # 눌린 면·입력
    # 선 — 세 단계. 다 같은 굵기·색이면 무엇이 큰 구분인지 알 수 없다.
    "line":        "#2a323c",     # 표 안 행 구분
    "line-strong": "#3a4552",     # 카드 테두리
    "line-key":    "#556373",     # 단계 구분처럼 큰 경계
    # 금속 느낌 — 위 하이라이트 / 아래 그림자
    "bevel-hi":    "rgba(255,255,255,0.075)",
    "bevel-lo":    "rgba(0,0,0,0.45)",
    # 글자 — 네 단계
    "text":        "#e8eef6",     # 본문
    "text-head":   "#f5f9ff",     # 제목(가장 밝게)
    "text-dim":    "#9fadbf",     # 보조 설명
    "text-faint":  "#8593a5",     # 캡션·비활성
    # 강조 — 크롬빛. 채도를 낮게 두어 상태 색과 다투지 않게 한다.
    "accent":      "#9fb6cd",
    "accent-dim":  "#5b6b7d",
}

# 글자 크기 — rem. 단계 사이를 넉넉히 벌린다(1.25배 안팎).
SCALE = {
    "h1": "2.05rem", "h2": "1.42rem", "h3": "1.08rem",
    "body": "0.95rem", "small": "0.86rem", "caption": "0.79rem",
}


def _vars() -> str:
    a = "".join(f"--tk-{k}:{v};" for k, v in TOKENS.items())
    b = "".join(f"--fs-{k}:{v};" for k, v in SCALE.items())
    return f":root{{{a}{b}}}"


# 판금 결 — 아주 옅은 세로 줄. 진하면 지저분해지고, 없으면 그냥 회색 상자가 된다.
_BRUSH = ("repeating-linear-gradient(90deg,"
          "rgba(255,255,255,0.014) 0 1px,rgba(0,0,0,0) 1px 3px)")
# 면 — 위가 밝고 아래가 어두운 세로 그라데이션이 볼록함을 만든다.
_PLATE = "linear-gradient(180deg,var(--tk-surface-2) 0%,var(--tk-surface) 100%)"


CSS = f"""
<style>
{_vars()}

/* ── 바탕 ─────────────────────────────────────────────── */
[data-testid="stAppViewContainer"], .stApp {{
  background:
    radial-gradient(1200px 600px at 50% -10%, #1a2029 0%, rgba(0,0,0,0) 60%),
    var(--tk-bg);
  color: var(--tk-text);
}}
.block-container {{ padding-top: 2.2rem; max-width: 1180px; }}
[data-testid="stAppViewContainer"] * {{ font-size: var(--fs-body); }}

/* ── 글자 위계 ────────────────────────────────────────────
   크기·무게·자간·색을 함께 움직인다. 크기만 바꾸면 위계가 안 생긴다. */
h1, [data-testid="stMarkdownContainer"] h1 {{
  font-size: var(--fs-h1) !important; font-weight: 800; letter-spacing: -0.03em;
  color: var(--tk-text-head);
  /* 각인(engraved) — 위 그림자 + 아래 하이라이트 */
  text-shadow: 0 -1px 0 rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.08);
  margin-bottom: .2rem;
}}
h2, [data-testid="stMarkdownContainer"] h2 {{
  font-size: var(--fs-h2) !important; font-weight: 700; letter-spacing: -0.015em;
  color: var(--tk-text-head); margin: 1.9rem 0 .55rem;
  padding-bottom: .5rem; position: relative;
}}
/* 단계 제목 아래 금속 레일 — 가운데가 밝고 끝이 어두워 빛을 받은 것처럼 보인다 */
h2::after {{
  content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
  background: linear-gradient(90deg,
    var(--tk-line-key) 0%, var(--tk-accent) 18%, var(--tk-line-key) 55%,
    rgba(0,0,0,0) 100%);
  border-radius: 1px;
}}
h3, [data-testid="stMarkdownContainer"] h3 {{
  font-size: var(--fs-h3) !important; font-weight: 700; letter-spacing: -0.01em;
  color: var(--tk-text); margin: 1.25rem 0 .45rem;
  padding-left: .62rem; border-left: 3px solid var(--tk-accent-dim);
}}
[data-testid="stMarkdownContainer"] p {{ color: var(--tk-text); line-height: 1.62; }}
[data-testid="stMarkdownContainer"] strong {{ color: var(--tk-text-head); font-weight: 700; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{
  font-size: var(--fs-caption) !important; color: var(--tk-text-faint) !important;
}}

/* ── 큰 경계 — 단계와 단계 사이 ──────────────────────────
   ★ Streamlit 자체 hr 규칙이 더 구체적이라 그냥 `hr {{}}` 로는 진다(실측 1px).
     컨테이너를 앞에 붙여 구체성을 올린다. `!important` 로 이기는 것보다
     **어느 규칙이 이겼는지 읽히는 쪽**이 낫다. */
[data-testid="stMarkdownContainer"] hr, .stApp hr {{
  border: 0 !important; height: 3px !important; margin: 2.1rem 0 1.1rem;
  background: linear-gradient(180deg,
    var(--tk-bevel-lo) 0 1px, var(--tk-line-key) 1px 2px, var(--tk-bevel-hi) 2px 3px);
}}

/* ── 표 — 칸이 분명히 보이게 ───────────────────────────── */
[data-testid="stMarkdownContainer"] table {{
  width: 100%; border-collapse: separate; border-spacing: 0;
  margin: .55rem 0 .9rem;
  border: 1px solid var(--tk-line-strong); border-radius: 8px; overflow: hidden;
  background: var(--tk-surface);
  box-shadow: 0 1px 0 var(--tk-bevel-hi) inset, 0 6px 18px rgba(0,0,0,0.35);
}}
[data-testid="stMarkdownContainer"] th {{
  background: {_PLATE}, {_BRUSH};
  color: var(--tk-text-head); font-weight: 700;
  font-size: var(--fs-small) !important; letter-spacing: .01em;
  padding: .58rem .7rem; text-align: left;
  border-bottom: 1px solid var(--tk-line-key);
  box-shadow: 0 1px 0 var(--tk-bevel-hi) inset;
  white-space: nowrap;
}}
[data-testid="stMarkdownContainer"] td {{
  padding: .5rem .7rem; border-bottom: 1px solid var(--tk-line);
  font-size: var(--fs-small) !important; color: var(--tk-text);
  vertical-align: top;
  /* ★ 한글은 **어절 단위로** 끊는다.
     기본값은 글자 아무 데서나 끊어서, 열이 좁아지면
     "A/S 수 주 잔 량"처럼 한 글자씩 세로로 쌓인다(실측: 부록 8-1 표). */
  word-break: keep-all;
}}
/* 첫 열 = 이름 열. 여기가 밀리면 표 전체가 읽히지 않는다.
   최소 너비를 주되 위에서 정한 어절 끊기로 자연스러운 폭을 잡게 둔다. */
/* ★ 이름 열은 **줄바꿈하지 않는다.**
   이름이 세로로 쌓이면 표를 훑을 수 없다(실측: "취소 수주 관련 재고금액"이 4줄).
   `min-width`로는 부족했다 — 긴 산식이 남는 폭을 다 가져가 최소폭에 붙어 버린다.
   `:has(code)`로 산식 열만 줄이려 했더니 **metric_id 열까지** 잡혔다(둘 다 코드다).
   그래서 폭을 다투는 대신 **이름은 한 줄로 고정**하고, 넘치면 표만 가로로 민다. */
[data-testid="stMarkdownContainer"] td:first-child,
[data-testid="stMarkdownContainer"] th:first-child {{ white-space: nowrap; }}
/* 표가 넘치면 **표만** 스크롤한다 — 페이지 전체가 옆으로 밀리면 안 된다. */
[data-testid="stMarkdownContainer"]:has(table) {{ overflow-x: auto; }}
/* 긴 산식·코드는 **어디서든 끊어** 다른 열을 밀지 않게 한다.
   이름은 어절로, 코드는 아무 데서나 — 두 규칙이 서로 반대인 것이 맞다. */
[data-testid="stMarkdownContainer"] td code {{
  overflow-wrap: anywhere; word-break: break-all; white-space: normal;
}}
/* 세로 칸 구분 — 첫 열 빼고 왼쪽 선. 열이 많을수록 이게 있어야 눈이 안 흐른다 */
[data-testid="stMarkdownContainer"] td + td,
[data-testid="stMarkdownContainer"] th + th {{ border-left: 1px solid var(--tk-line); }}
[data-testid="stMarkdownContainer"] tr:last-child td {{ border-bottom: 0; }}
[data-testid="stMarkdownContainer"] tbody tr:nth-child(even) td {{
  background: rgba(255,255,255,0.016);
}}
[data-testid="stMarkdownContainer"] tbody tr:hover td {{
  background: rgba(159,182,205,0.07);
}}

/* ── 카드 면 — 지표·확장·알림 ──────────────────────────── */
[data-testid="stMetric"] {{
  background: {_PLATE}, {_BRUSH};
  border: 1px solid var(--tk-line-strong); border-radius: 9px;
  padding: .7rem .85rem;
  box-shadow: 0 1px 0 var(--tk-bevel-hi) inset, 0 4px 12px rgba(0,0,0,0.32);
}}
[data-testid="stMetricLabel"] * {{
  font-size: var(--fs-caption) !important; color: var(--tk-text-faint) !important;
  letter-spacing: .02em;
}}
[data-testid="stMetricValue"] {{
  font-size: 1.32rem !important; font-weight: 700; color: var(--tk-text-head);
}}
[data-testid="stExpander"] {{
  border: 1px solid var(--tk-line-strong); border-radius: 9px;
  background: var(--tk-surface); overflow: hidden;
}}
[data-testid="stExpander"] summary {{
  background: {_PLATE}, {_BRUSH};
  font-size: var(--fs-small) !important; color: var(--tk-text);
  box-shadow: 0 1px 0 var(--tk-bevel-hi) inset;
}}
[data-testid="stAlert"] {{
  border-radius: 9px; border-left-width: 4px;
  background: var(--tk-surface-2);
  box-shadow: 0 1px 0 var(--tk-bevel-hi) inset;
}}
[data-testid="stAlert"] * {{ color: var(--tk-text) !important; }}

/* ── 단추 — 눌리는 금속 ────────────────────────────────── */
[data-testid="stButton"] button, button[data-testid^="stBaseButton"] {{
  background: {_PLATE}, {_BRUSH};
  border: 1px solid var(--tk-line-key); border-radius: 8px;
  color: var(--tk-text); font-weight: 600; font-size: var(--fs-small) !important;
  box-shadow: 0 1px 0 var(--tk-bevel-hi) inset, 0 2px 5px rgba(0,0,0,0.4);
  transition: none;
}}
[data-testid="stButton"] button:hover, button[data-testid^="stBaseButton"]:hover {{
  border-color: var(--tk-accent); color: var(--tk-text-head);
}}
[data-testid="stButton"] button:active, button[data-testid^="stBaseButton"]:active {{
  /* 눌리면 하이라이트를 아래로 옮긴다 — 볼록이 오목이 된다 */
  box-shadow: 0 -1px 0 var(--tk-bevel-hi) inset, 0 2px 6px rgba(0,0,0,0.5) inset;
}}
[data-testid="stButton"] button[kind="primary"],
button[data-testid="stBaseButton-primary"] {{
  background: linear-gradient(180deg, #3d4b5c 0%, #2a3542 100%), {_BRUSH};
  border-color: var(--tk-accent-dim); color: var(--tk-text-head);
}}
[data-testid="stButton"] button:disabled, button[data-testid^="stBaseButton"]:disabled {{
  color: var(--tk-text-faint); border-color: var(--tk-line); box-shadow: none;
  background: var(--tk-surface);
}}

/* ── 사이드바 — 본문과 다른 판이라는 것이 보이게 ────────── */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #12171d 0%, #0e1218 100%);
  border-right: 1px solid var(--tk-line-key);
  box-shadow: 1px 0 0 var(--tk-bevel-hi) inset;
}}
[data-testid="stSidebar"] h3 {{ border-left-color: var(--tk-accent); }}

/* ── 입력 ─────────────────────────────────────────────── */
[data-baseweb="select"] > div, [data-testid="stTextInput"] input {{
  background: var(--tk-surface-3) !important;
  border: 1px solid var(--tk-line-strong) !important; border-radius: 7px;
  color: var(--tk-text) !important;
  box-shadow: 0 2px 5px rgba(0,0,0,0.35) inset;
}}
[data-testid="stFileUploaderDropzone"] {{
  background: var(--tk-surface) !important;
  border: 1px dashed var(--tk-line-key) !important; border-radius: 9px;
}}
code {{
  background: var(--tk-surface-3); color: var(--tk-accent);
  border: 1px solid var(--tk-line); border-radius: 5px;
  padding: .06rem .32rem; font-size: var(--fs-caption) !important;
}}
[data-testid="stProgress"] > div > div > div {{ background: var(--tk-accent); }}
</style>
"""


def inject(st) -> None:
    """테마를 화면에 넣는다. `set_page_config` 바로 뒤에서 **한 번만** 부른다."""
    st.markdown(CSS, unsafe_allow_html=True)
