import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime, timezone, timedelta

GALLERY_URL = "https://gall.dcinside.com/mgallery/board/lists/"
GALLERY_ID = "plave"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://gall.dcinside.com/",
}

KST = timezone(timedelta(hours=9))
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

def fetch_page(page=1):
    params = {"id": GALLERY_ID, "page": page}
    resp = requests.get(GALLERY_URL, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_posts(html, target_date_str):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    older_found = False

    for row in soup.select("tr.ub-content"):
        subject_tag = row.select_one("td.gall_subject")
        if subject_tag:
            subject_text = subject_tag.get_text(strip=True)
            if "공지" in subject_text or "설문" in subject_text:
                continue

        num_tag = row.select_one("td.gall_num")
        if not num_tag or not num_tag.get_text(strip=True).isdigit():
            continue

        date_tag = row.select_one("td.gall_date")
        if not date_tag: continue
        date_text = date_tag.get_text(strip=True)

        if _TIME_RE.match(date_text): continue
        elif date_text == target_date_str: pass
        else:
            older_found = True
            continue

        # 사진/영상 배지가 a 태그를 중복 생성하므로 클래스로 필터링
        title = ""
        link = ""
        for a_tag in row.select("td.gall_tit a"):
            cls = a_tag.get("class", [])
            if "reply_num" in cls or "badge_type" in cls:
                continue
            
            txt = a_tag.get_text(strip=True)
            if txt:
                title = txt
                link = a_tag.get("href", "")
                break
                
        if not title: continue

        if link and not link.startswith("http"):
            link = "https://gall.dcinside.com" + link

        reply_count = 0
        reply_tag = row.select_one("td.gall_tit .reply_num")
        if reply_tag:
            try: reply_count = int(reply_tag.get_text(strip=True).strip("[]"))
            except ValueError: pass

        view_count = 0
        view_tag = row.select_one("td.gall_count")
        if view_tag:
            try: view_count = int(view_tag.get_text(strip=True).replace(",", ""))
            except ValueError: pass

        recommend_count = 0
        rec_tag = row.select_one("td.gall_recommend")
        if rec_tag:
            try: recommend_count = int(rec_tag.get_text(strip=True))
            except ValueError: pass

        posts.append({
            "title": title,
            "link": link,
            "view_count": view_count,
            "reply_count": reply_count,
            "recommend_count": recommend_count,
        })

    return posts, older_found

def collect_posts(max_pages=999):
    all_posts = []
    yesterday = datetime.now(KST) - timedelta(days=1)
    target_date_str = yesterday.strftime("%m.%d")
    full_date_str = yesterday.strftime("%Y-%m-%d")

    print(f"목표 수집 날짜: {full_date_str} (표기: {target_date_str})")

    for page in range(1, max_pages + 1):
        print(f"  [디시인사이드] 페이지 {page} 탐색 중...")
        try:
            html = fetch_page(page)
            posts, older_found = parse_posts(html, target_date_str)
            all_posts.extend(posts)
            print(f"  -> {len(posts)}개 어제 글 수집" + (" (그저께 글 감지, 종료)" if older_found else ""))
            
            if older_found: break
        except Exception as e:
            print(f"  -> 오류: {e}")
            break
        if page < max_pages: time.sleep(0.8)

    return all_posts, full_date_str