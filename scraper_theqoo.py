import requests
from bs4 import BeautifulSoup
import time
from scrape_utils import (
    resolve_target_date, classify_date_text, get_with_retries,
    NEWER, TARGET, OLDER,
)

BOARD_URL = "https://theqoo.net/plave"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://theqoo.net/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 페이지 간 TCP 연결(keep-alive)·쿠키를 재사용한다.
_session = requests.Session()
_session.headers.update(HEADERS)

def fetch_page(page=1):
    params = {"page": page} if page > 1 else {}
    resp = _session.get(BOARD_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_posts(html, target_date):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    older_found = False

    skip_classes = {"notice", "notice_expand"}
    for row in soup.select("tr"):
        if any(c in row.get("class", []) for c in skip_classes):
            continue

        no_td = row.select_one("td.no")
        if not no_td or not no_td.get_text(strip=True).isdigit():
            continue

        time_td = row.select_one("td.time")
        if not time_td:
            continue
        time_text = time_td.get_text(strip=True)

        status = classify_date_text(time_text, target_date)
        if status == TARGET:
            pass
        elif status == OLDER:
            older_found = True
            continue
        else:  # NEWER 또는 UNKNOWN — 더 깊은 페이지로 계속
            continue

        title_td = row.select_one("td.title")
        if not title_td:
            continue

        title_a = title_td.select_one("a:first-child")
        if not title_a:
            continue

        title = title_a.get_text(strip=True)
        if not title:
            continue

        href = title_a.get("href", "")
        link = ("https://theqoo.net" + href) if href.startswith("/") else href

        reply_count = 0
        reply_a = title_td.select_one("a.replyNum")
        if reply_a:
            try:
                reply_count = int(reply_a.get_text(strip=True))
            except ValueError:
                pass

        view_count = 0
        view_td = row.select_one("td.m_no")
        if view_td:
            try:
                view_count = int(view_td.get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        posts.append({
            "title": title,
            "link": link,
            "view_count": view_count,
            "reply_count": reply_count,
        })

    return posts, older_found

def collect_posts(target_date=None, max_pages=999):
    """target_date(기본: 어제)의 글을 수집. (posts, 'YYYY-MM-DD', complete) 반환."""
    target = resolve_target_date(target_date)
    full_date_str = target.strftime("%Y-%m-%d")
    all_posts = []
    complete = True

    print(f"목표 수집 날짜: {full_date_str}")

    for page in range(1, max_pages + 1):
        print(f"  [더쿠] 페이지 {page} 탐색 중...")
        try:
            html = get_with_retries(lambda p=page: fetch_page(p), desc=f"페이지 {page}")
            posts, older_found = parse_posts(html, target)
            all_posts.extend(posts)
            print(f"  -> {len(posts)}개 목표일 글 수집" + (" (이전 날짜 글 감지, 종료)" if older_found else ""))
            if older_found:
                break
        except Exception as e:
            print(f"  -> 오류: {e}")
            complete = False
            break
        if page < max_pages:
            time.sleep(0.8)

    return all_posts, full_date_str, complete

