import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime, timedelta, timezone

BOARD_URL = "https://theqoo.net/plave"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://theqoo.net/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

KST = timezone(timedelta(hours=9))
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

def fetch_page(page=1):
    params = {"page": page} if page > 1 else {}
    resp = requests.get(BOARD_URL, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_posts(html, target_date_str):
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

        if _TIME_RE.match(time_text):
            continue
        elif target_date_str in time_text:
            pass
        else:
            older_found = True
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

def collect_posts(max_pages=999):
    all_posts = []
    yesterday = datetime.now(KST) - timedelta(days=1)
    target_date_str = yesterday.strftime("%m.%d")
    full_date_str = yesterday.strftime("%Y-%m-%d")

    print(f"목표 수집 날짜: {full_date_str} (더쿠 표기: {target_date_str})")

    for page in range(1, max_pages + 1):
        print(f"  [더쿠] 페이지 {page} 탐색 중...")
        try:
            html = fetch_page(page)
            posts, older_found = parse_posts(html, target_date_str)
            all_posts.extend(posts)
            print(f"  -> {len(posts)}개 어제 글 수집" + (" (그저께 글 감지, 종료)" if older_found else ""))
            if older_found:
                break
        except Exception as e:
            print(f"  -> 오류: {e}")
            break
        if page < max_pages:
            time.sleep(0.8)

    return all_posts, full_date_str

