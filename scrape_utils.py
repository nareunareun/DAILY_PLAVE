"""스크레이퍼 공통 유틸 (날짜 판별 · 재시도).

네 스크레이퍼가 각자 하던 '어제 날짜 문자열 비교'를 실제 날짜 비교로
통일한다. 문자열 포함 비교는 목표일이 어제일 때만 동작했는데,
백필(--date)로 며칠 전을 수집할 때는 목표일과 오늘 사이의 글을
'과거 글(종료 신호)'로 오판해 탐색이 조기 종료되는 버그가 생긴다.
그래서 목록의 날짜 표기를 파싱해 target보다 최신/일치/과거를
구분해 돌려준다.
"""
import re
import time
from datetime import datetime, date, timedelta, timezone

KST = timezone(timedelta(hours=9))

# (내부 키, 표시 이름, 요약 표기, 스크레이퍼 모듈) — run.py·summarizer.py 공용.
SOURCES = [
    ("dcinside", "디시인사이드", "디시",     "scraper_dcinside"),
    ("theqoo",   "더쿠",        "더쿠",     "scraper_theqoo"),
    ("newduck",  "뉴덕",        "뉴덕",     "scraper_newduck"),
    ("instiz",   "인스티즈",    "인스티즈", "scraper_instiz"),
]

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
# 커뮤니티 목록에 흔한 표기: 07.05 / 07-05 / 25.07.05 / 2025.07.05
_MD_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})\.?$")
_YMD_RE = re.compile(r"^(\d{2}|\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\.?$")

NEWER, TARGET, OLDER, UNKNOWN = "newer", "target", "older", "unknown"


def resolve_target_date(target_date=None):
    """target_date(str 'YYYY-MM-DD' | date | None)를 date로 변환. None이면 어제(KST)."""
    if target_date is None:
        return (datetime.now(KST) - timedelta(days=1)).date()
    if isinstance(target_date, date):
        return target_date
    return datetime.strptime(target_date, "%Y-%m-%d").date()


def parse_list_date(date_text, today=None):
    """목록의 날짜 표기를 date로 파싱. 'HH:MM'(오늘)은 today, 실패하면 None.

    연도 없는 MM.DD는 올해로 보되, 결과가 미래면 작년으로 본다
    (1월에 '12.31'은 작년 12월 31일).
    """
    if today is None:
        today = datetime.now(KST).date()
    txt = date_text.strip().replace(" ", "")
    if _TIME_RE.match(txt):
        return today
    m = _YMD_RE.match(txt)
    if m:
        y, mo, d = m.groups()
        year = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            return date(year, int(mo), int(d))
        except ValueError:
            return None
    m = _MD_RE.match(txt)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            parsed = date(today.year, mo, d)
        except ValueError:
            return None
        if parsed > today:
            parsed = date(today.year - 1, mo, d)
        return parsed
    return None


def classify_date_text(date_text, target, today=None):
    """목록 날짜 표기를 target 대비 NEWER/TARGET/OLDER/UNKNOWN으로 분류."""
    parsed = parse_list_date(date_text, today=today)
    if parsed is None:
        return UNKNOWN
    if parsed > target:
        return NEWER
    if parsed == target:
        return TARGET
    return OLDER


def get_with_retries(getter, desc="", retries=3, backoff=2.0):
    """getter()를 최대 retries회 시도. 일시 오류(서버 순단·타임아웃)를 흡수한다."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return getter()
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = backoff * attempt
                print(f"  -> [재시도] {desc} 요청 실패({e}), {wait:.0f}s 후 재시도 ({attempt}/{retries})")
                time.sleep(wait)
    raise last_err
