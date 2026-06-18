import cloudscraper
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime, timedelta, timezone

BOARD_URL = "https://newduck.net/board_gLxy54"

KST = timezone(timedelta(hours=9))
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

def _parse_view(text):
    text = text.strip().replace(",", "")
    if "만" in text:
        try:
            return int(float(text.replace("만", "")) * 10000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0

def _make_scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

def fetch_page(scraper, page=1):
    if page > 1:
        url = f"{BOARD_URL}/page/{page}"
        resp = scraper.get(url, headers={"Referer": BOARD_URL}, timeout=15)
    else:
        resp = scraper.get(BOARD_URL, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_posts(html, target_date_dot, target_date_dash):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    older_found = False

    for row in soup.select("tr.ldtu"):
        if "lnu" in row.get("class", []):
            continue

        num_td = row.select_one("td.ldtu-number")
        if not num_td or not num_td.get_text(strip=True).isdigit():
            continue

        date_span = row.select_one("td.ldtu-date span.date-msover-date")
        if not date_span:
            continue
        date_text = date_span.get_text(strip=True)

        if _TIME_RE.match(date_text):
            continue
        elif target_date_dot in date_text or target_date_dash in date_text:
            pass
        else:
            older_found = True
            continue

        title_td = row.select_one("td.ldtu-title-wrap")
        if not title_td:
            continue

        title_a = title_td.select_one("a.lu-title")
        if not title_a:
            continue

        title = title_a.get_text(strip=True)
        if not title:
            continue

        href = title_a.get("href", "")
        link = ("https://newduck.net" + href) if href.startswith("/") else href

        reply_count = 0
        reply_a = title_td.select_one("a.lu-comment")
        if reply_a:
            try:
                reply_count = int(reply_a.get_text(strip=True))
            except ValueError:
                pass

        view_count = 0
        view_td = row.select_one("td.lu-read")
        if view_td:
            view_count = _parse_view(view_td.get_text(strip=True))

        posts.append({
            "title": title,
            "link": link,
            "view_count": view_count,
            "reply_count": reply_count,
        })

    return posts, older_found

def collect_posts(max_pages=999):
    scraper = _make_scraper()
    all_posts = []
    yesterday = datetime.now(KST) - timedelta(days=1)
    target_date_dot = yesterday.strftime("%m.%d")
    target_date_dash = yesterday.strftime("%m-%d")
    full_date_str = yesterday.strftime("%Y-%m-%d")

    print(f"목표 수집 날짜: {full_date_str}")

    for page in range(1, max_pages + 1):
        print(f"  [뉴덕] 페이지 {page} 탐색 중...")
        try:
            html = fetch_page(scraper, page)
            posts, older_found = parse_posts(html, target_date_dot, target_date_dash)
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

