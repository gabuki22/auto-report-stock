# -*- coding: utf-8 -*-
"""앱 설정 — 경로·BigQuery·기준값.

★ 위키 경로는 **소스에 박지 않는다.** 개인 PC 경로에는 사용자 이름과 폴더 구조가
  그대로 담기는데 이 저장소는 공개된다. 아래 순서로 찾는다.

    1) 환경변수 `AUTO_REPORT_WIKI`
    2) 같은 폴더의 `wiki_path.txt` 한 줄   ← 가장 간편. `.gitignore`로 제외된다
    3) 형제 폴더 자동 탐색(`_find_wiki`)

  2번을 쓰려면 `wiki_path.txt`를 만들고 경로만 한 줄 적는다. 파일에서 읽으므로
  백슬래시·한글·공백을 이스케이프 없이 그대로 쓴다.

  설정층·실행층 분리의 요점이 여기다 — 위키를 바꾸려면 **그 한 줄만** 바꾸고
  export를 다시 돌린다. 앱 코드는 건드리지 않는다.
  ※ 배포본에는 이 경로가 없어도 된다. 앱은 `catalog/*.json` 스냅샷만 읽는다.
"""
import os
from pathlib import Path

# ── 경로 ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CATALOG_DIR = BASE_DIR / "catalog"
PIPELINE_DIR = BASE_DIR / "pipeline"
OUTPUTS_DIR = BASE_DIR / "outputs"
FONTS_DIR = BASE_DIR / "fonts"

def _manual_wiki() -> str | None:
    """개인 위키 경로 — 환경변수 → 로컬 파일 순. 없으면 None(자동 탐색으로 넘어간다).

    ★ 여기에 경로를 **적어 두지 않는다.** 공개 저장소에 개인 PC 경로가 남는다.
      자동 탐색만으로는 부족하다 — 형제 폴더에 교안 위키와 우리 위키가 함께 있으면
      엉뚱한 쪽을 고른다(실측: `my-wiki-02`가 잡혔다). 그래서 사람이 한 줄 적는
      자리를 **저장소 밖에** 둔다.
    """
    if env := os.environ.get("AUTO_REPORT_WIKI"):
        return env.strip()
    f = BASE_DIR / "wiki_path.txt"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return None


_MANUAL_WIKI_PATH = _manual_wiki()

# 지표 정의서 폴더 이름 후보 — 교안은 06_metrics, 우리 위키는 07_metrics
_METRICS_DIR_NAMES = ("06_metrics", "07_metrics")
_INSIGHTS_DIR_NAMES = ("04_insights", "06_insights")


def _find_wiki() -> Path | None:
    """형제 폴더 중 지표 정의서 폴더를 가진 것을 찾는다.

    여러 개면 06_metrics를 가진 쪽을 먼저 고른다(교안 표준 구조).
    우리 위키(07_metrics)로 바꾸려면 _MANUAL_WIKI_PATH 한 줄을 지정한다.
    """
    found = []
    for d in sorted(BASE_DIR.parent.iterdir()):
        if not d.is_dir() or d == BASE_DIR:
            continue
        for i, name in enumerate(_METRICS_DIR_NAMES):
            if (d / name).is_dir():
                found.append((i, d))
                break
    found.sort(key=lambda x: (x[0], x[1].name))   # 06_metrics 쪽을 먼저
    return found[0][1] if found else None


WIKI_PATH = Path(_MANUAL_WIKI_PATH).resolve() if _MANUAL_WIKI_PATH else _find_wiki()


def metrics_dir() -> Path | None:
    """WIKI_PATH 안의 지표 정의서 폴더."""
    if WIKI_PATH is None:
        return None
    return next((WIKI_PATH / n for n in _METRICS_DIR_NAMES if (WIKI_PATH / n).is_dir()), None)


def insights_dir() -> Path | None:
    """WIKI_PATH 안의 인사이트 폴더.

    지표 폴더와 마찬가지로 **위키마다 번호가 다르다**(강의 위키 04_insights /
    제조 위키 06_insights). 이름을 하나로 박으면 다른 위키에서 인사이트가 0건이 되고,
    그 사실이 조용히 지나간다.
    """
    if WIKI_PATH is None:
        return None
    return next((WIKI_PATH / n for n in _INSIGHTS_DIR_NAMES
                 if (WIKI_PATH / n).is_dir()), None)


def data_dir() -> Path | None:
    """WIKI_PATH 안의 스키마 노트 폴더."""
    if WIKI_PATH is None:
        return None
    d = WIKI_PATH / "02_data"
    return d if d.is_dir() else None


def check_wiki() -> str:
    """실행 시 경고 문구. 문제 없으면 빈 문자열."""
    if WIKI_PATH is None:
        return ("위키 경로를 직접 지정하세요 — config.py의 _MANUAL_WIKI_PATH에 "
                f"{' 또는 '.join(_METRICS_DIR_NAMES)} 폴더를 가진 위키 경로를 넣습니다.")
    if metrics_dir() is None:
        return f"{WIKI_PATH} 안에 {' / '.join(_METRICS_DIR_NAMES)} 폴더가 없습니다."
    return ""


# ── BigQuery ──────────────────────────────────────────────────────────
BQ_PROJECT = "gen-lang-client-0109601387"   # None이면 ADC 기본 프로젝트
BQ_DATASET = "wiki_manufacturing"                        # 교안은 project1_day1 — 우리 적재본은 study
BQ_LOCATION = "asia-northeast3"
STAGING_PREFIX = "staging_"

# 우리 적재본은 테이블 이름에 접두어가 붙어 있다.
#   강사 project1_day1 : usage_history      (접두어 없음)
#   우리   study        : data_usage_history (raw CSV 파일명을 그대로 적재)
# 테이블별 매핑을 코드에 박지 않고 접두어 하나만 설정으로 둔다.
# 접두어가 없는 환경이면 "" 로 비운다.
BQ_TABLE_PREFIX = ""

# 지표 정의서는 월 컬럼을 'YYYY-MM' **문자열**로 전제하고 쓰여 있다(강사 환경).
# 우리 적재본은 같은 컬럼이 **DATE**다 — 원본을 조회하면 타입이 어긋나 쿼리가 깨진다.
#   Invalid date: '2024-12'  /  PARSE_DATE(STRING, DATE) 시그니처 없음
# 테이블 이름을 나열하지 않고 **컬럼 이름 규칙**으로 둔다. 여기 적힌 컬럼이 DATE면
# 원본 조회 시에만 문자열로 맞춘다(업로드 스테이징은 CSV라 이미 문자열이므로 건드리지 않는다).
BQ_STRING_MONTH_COLUMNS = ["year_month", "month"]

# ── 이메일 (8주차까지 발송 안 함 — 초안만) ────────────────────────────
# ⚠️ **실제 주소를 코드에 쓰지 않는다.** 여기 값은 전부 예시이고, 8주차에 배포하는
#    사람이 자기 환경에서 바꾼다. 실제 주소가 저장소에 들어가면 되돌리기 어렵다.
EMAIL_TO = ["example@company.com"]
EMAIL_FROM = "report-bot@company.com"
# 화면·리포트 제목 — ★ 코드에 박지 않는다. 이식할 때 고칠 곳이 코드에 남으면
# "config 한 파일만 고치면 된다"는 전제가 깨진다.
APP_TITLE = "주간 재고 리포트 자동화"
REPORT_SUBJECT = "재고 지표 리포트"      # 이메일 제목에 들어가는 본문
# 리포트 표지·본문 제목. ★ "주간 지표 리포트"만으로는 **무엇에 대한 것인지** 없다.
#   받는 사람은 여러 보고서를 함께 받는다 — 제목이 주제를 담아야 골라 읽는다.
REPORT_TITLE = "주간 재고 리포트"

EMAIL_SUBJECT_PREFIX = "[주간]"

# ★ 기간을 부르는 이름. **코드에 '월간'·'전월'을 박지 않는다.**
#   주간 보고인데 리포트 표지에 "월간 지표 리포트"가 찍히고 표 머리가 "전월"이었다.
#   숫자는 맞는데 이름이 틀리면 읽는 사람이 먼저 그 어긋남을 본다.
PERIOD_LABEL = "주간"        # 리포트 표지·이메일 제목 (월간 프로젝트면 "월간")
PREV_LABEL = "전주"          # 비교 대상 (월간 프로젝트면 "전월")
CURR_LABEL = "이번 주"       # 비교표의 당기 열 (월간 프로젝트면 "당월")

# 기간 대비 검증의 이름 — **화면에 보이는 이름이자 조회 키**다.
#   `validate`가 이 이름으로 결과를 쓰고 `report`·`app`이 이 이름으로 골라낸다.
# ★ 정의를 `validate`에 두었더니 배포본이 `AttributeError: MOM_CHECK`로 죽었다.
#   Streamlit Cloud가 `app.py`는 다시 읽으면서 이미 import된 하위 모듈은
#   옛 버전을 붙들고 있었기 때문이다(로컬에서는 재시작되므로 안 보인다).
#   **모두가 이미 읽는 config에 두면** 그런 어긋남이 생길 자리가 없다.
MOM_CHECK = f"{PREV_LABEL} 대비"

# ★ **쓸 때는 하나, 읽을 때는 너그럽게.**
#   이름을 바꾸기 전에 확정된 실행의 `validation.json`에는 옛 이름이 그대로 있다.
#   새 이름만 찾으면 옛 실행을 불러왔을 때 경고가 **조용히 0건**이 된다 —
#   화면은 멀쩡한데 강조가 사라지므로 알아채기 어렵다.
#   배포본이 옛 모듈을 붙들고 있을 때도 이쪽이 덜 부서진다.
MOM_CHECK_ALIASES = (MOM_CHECK, "전주 대비", "전월 대비")

# 첨부 목록. **파일명만 적고 실제 첨부는 하지 않는다**(8주차 범위).
# 없는 파일은 목록에서 빠지고, 빠졌다는 사실이 화면에 보인다.
EMAIL_ATTACHMENTS = ["report.pdf", "report.md", "metrics.csv", "comparison.csv"]

# ── 기준값 ────────────────────────────────────────────────────────────
MIN_SCHEMA_MATCH = 0.8      # 스키마 일치율 최소 기준

# 전월 대비 이상 변동 임계값(%). 상대변화율의 절대값이 이 값 이상이면 경고.
# ⚠️ 지표마다 정상 변동 폭이 다르다 — 매출 5%는 크고, 데이터 사용량 5%는 계절성으로도 난다.
#
# 그래서 **지표별 임계값은 정의서 프론트매터**(아래 필드)에 둔다. 여기 값은 그것이 없을 때만
# 쓰는 **기본값**이다. 임계값은 "이 지표가 얼마나 변하면 이상한가"이므로 지표의 성질이고,
# 지표의 성질은 정의서에 있어야 한다 — config에 지표별로 적으면 정의가 두 곳에 생긴다.
MOM_THRESHOLD = 5.0

# 정의서에서 지표별 임계값을 읽어올 프론트매터 필드 이름.
# 코드가 아는 것은 **이 필드 이름 하나**뿐이고, 값도 어느 지표에 있는지도 전부 위키가 정한다.
# 지표명을 코드에 쓰면(`if mid == "avg_data_usage"`) 임계값이 위키와 코드 두 곳에 살게 된다.
MOM_THRESHOLD_FIELD = "변동임계값"

# 추이 차트에 그릴 개월 수. 6개월로는 계절성을 판별할 수 없으므로 **추세선을 넣지 않는다.**
TREND_MONTHS = 12          # 주간 스냅샷이라 12기간 = 약 3개월

# ── 이전 기간 판정 ─────────────────────────────────────────────────────
# 전월/전주를 **달력으로 계산할지, 데이터에서 찾을지.**
#
# ★ 월 단위 지표는 달력으로 충분하다(2025-02의 전월은 2025-01).
#   그러나 **주간 스냅샷은 간격이 불규칙하다** — 실측에서 5일·8일·14일(주차 건너뜀)이
#   섞여 있었다. "7일 전"으로 계산하면 스냅샷이 없는 날짜가 나와 전주 값이 0행이 된다.
#   그래서 **직전 스냅샷을 데이터에서 찾는다.**
#
# None 이면 달력 기준(전월)으로 계산한다. 문자열이면 그 SQL로 조회한다.
#   · @start 파라미터가 바인딩된다(이번 기간의 시작일)
#   · 결과는 한 행 한 컬럼, 문자열 날짜여야 한다
PREV_PERIOD_SQL = (
    "SELECT CAST(MAX(`날짜`) AS STRING) AS p "
    "FROM `{project}.{dataset}.stock_snapshot` WHERE `날짜` < @start"
)

# ── 기간 컬럼 판정 ─────────────────────────────────────────────────────
# 업로드 파일에서 "기간"을 담은 컬럼을 찾는 정규식.
# ★ 코드에 박으면 컬럼명이 한글인 프로젝트에서 통째로 막힌다 — 실제로 `날짜` 컬럼이
#   `^(year_month|.*_date|.*_month)$` 에 걸리지 않아 화면 업로드가 2단계에서 멈췄다.
PERIOD_COLUMN_PATTERN = r"^(year_month|날짜|기준일|일자|.*_date|.*_month)$"

# ── 카탈로그에 담을 지표의 범위 ────────────────────────────────────────
# 한 위키에 여러 도메인의 정의서가 함께 사는 경우, **이 프로젝트와 무관한 지표까지
# 카탈로그에 들어와 화면을 덮는다.** 실제로 재고 앱에 강의 CS 지표 20종이 떴다.
#
# 정의서 프론트매터의 `데이터셋` 값이 이 값과 다르면 카탈로그에서 제외한다.
# `데이터셋` 필드가 아예 없는 정의서도 제외한다(다른 도메인의 기본값을 쓰는 것이므로).
# None 이면 전부 담는다(도메인이 하나뿐인 프로젝트).
METRIC_DATASET_FILTER = BQ_DATASET

# ── 추이 차트 ─────────────────────────────────────────────────────────
# ★ 어떤 지표를 어떤 축에 그릴지는 **프로젝트마다 다르다.** 코드에 두면 이식할 때
#   화면이 남의 도메인 지표로 덮인다(실제로 재고 앱에 CS 지표 차트가 떴다).
#   색은 DESIGN.md의 Tailwind 500 팔레트를 문자열로 쓴다(common을 import하면 순환 참조).
CHART_SPECS = [
    {"key": "kinds", "title": "재고 4구분 — 첫 주 대비 증감", "normalize": "change",
     "left": [("stock_raw_material", "원재료", "#64748b"),
              ("stock_handling", "핸들링", "#3b82f6"),
              ("stock_as_item", "A/S품목", "#f59e0b"),
              ("stock_as_warehouse", "A/S창고", "#f43f5e")],
     "right": [], "left_title": "% (첫 주 대비)", "right_title": "",
     "caption": "★ **절대액이 아니라 증감**이다. 네 구분은 규모가 달라(핸들링 6억 vs A/S창고 2억) "
                "절대액으로 그리면 큰 값이 작은 변화를 가린다. 0선 위/아래로 방향을 읽는다. "
                "실제 주간보고도 증감(달력 1개월 대비)을 본다."},
    {"key": "flow", "title": "무출하 재고 · 출하",
     "left": [("stagnant_stock_amount", "무출하 재고금액", "#8b5cf6")],
     "right": [("weekly_shipment_qty", "주간 출하 수량", "#10b981")],
     "left_title": "원", "right_title": "개",
     "caption": "좌축 무출하 금액 / 우축 출하 수량 — **축이 다르므로 교차점은 의미가 없다.** "
                "출하가 주는데 무출하가 늘면 재고가 굳고 있다는 뜻이다."},
    {"key": "process", "title": "공정별 계획 달성률", "normalize": None,
     "left": [("plan_rate_injection", "사출", "#64748b"),
              ("plan_rate_paint", "도장", "#f43f5e"),
              ("plan_rate_laser", "레이저", "#3b82f6"),
              ("plan_rate_print", "인쇄", "#10b981"),
              ("plan_rate_inspect", "검사", "#f59e0b")],
     "right": [], "left_title": "%", "right_title": "",
     "caption": "★ **같은 시점의 공정끼리 비교한다.** 한 선만 아래로 벌어지면 그 공정이 병목이고, "
                "그 뒤 공정이 함께 낮아지는 것은 받을 물량이 없기 때문이다. "
                "**공정 흐름에서 가장 앞선 낮은 공정**이 원인일 가능성이 높다."},
    {"key": "order", "title": "수주 지연 · 진행률",
     "left": [("overdue_order_dobun", "납기 초과 도번 수", "#f43f5e")],
     "right": [("order_progress_rate", "수주 진행률", "#3b82f6")],
     "left_title": "개", "right_title": "%",
     "caption": "좌축 도번 수 / 우축 %. **수주 원장이 있어야 나오는 축**이다 — 납기는 재고 스냅샷에 없다. "
                "진행률 평균이 그대로인데 지연이 늘면 **평균이 지연을 가리고 있다는 신호**다."},
]

# 추이 기간을 **데이터에서** 가져온다. 주간 스냅샷은 간격이 불규칙해서
# "N개월 전"으로 계산하면 실제 스냅샷이 없는 날짜가 나온다.
# None 이면 달력 월 단위로 되돌아간다(월간 프로젝트).
TREND_PERIODS_SQL = (
    "SELECT CAST(`날짜` AS STRING) AS p "
    "FROM `{project}.{dataset}.stock_snapshot` "
    "WHERE `날짜` <= @end GROUP BY 1 ORDER BY 1 DESC LIMIT {n}"
)

# 화면 상단·이메일에 띄울 핵심 지표 4종. ★ 프로젝트마다 다르므로 config에 둔다.
#   재고 보고에서 먼저 봐야 할 것: 총액 · 지연 · 안 움직이는 재고 · 약속 대비 진행
CARD_METRICS = ["weekly_stock_amount", "overdue_order_dobun",
                "process_gap", "order_progress_rate"]
