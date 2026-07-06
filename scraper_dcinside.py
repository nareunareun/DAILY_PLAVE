import requests
from bs4 import BeautifulSoup
import time
from scrape_utils import (
    resolve_target_date, classify_date_text, get_with_retries,
    NEWER, TARGET, OLDER,
)

GALLERY_URL = "https://gall.dcinside.com/mgallery/board/lists/"
GALLERY_ID = "plave"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://gall.dcinside.com/",
}

# 페이지 간 TCP 연결(keep-alive)·쿠키를 재사용한다.
_session = requests.Session()
_session.headers.update(HEADERS)

def fetch_page(page=1):
    params = {"id": GALLERY_ID, "page": page}
    resp = _session.get(GALLERY_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_posts(html, target_date):
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

        status = classify_date_text(date_text, target_date)
        if status == TARGET: pass
        elif status == OLDER:
            older_found = True
            continue
        else:  # NEWER(목표일 이후 글) 또는 UNKNOWN — 더 깊은 페이지로 계속
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

def collect_posts(target_date=None, max_pages=999):
    """target_date(기본: 어제)의 글을 수집. (posts, 'YYYY-MM-DD', complete) 반환.

    complete=False는 페이지 탐색이 오류로 중단돼 그날 글 일부만 모였을 수
    있다는 뜻이다. 호출부(run.py)는 이런 소스를 미완료로 기록해 다음
    실행에서 다시 수집하게 한다.
    """
    target = resolve_target_date(target_date)
    full_date_str = target.strftime("%Y-%m-%d")
    all_posts = []
    complete = True

    print(f"목표 수집 날짜: {full_date_str}")

    for page in range(1, max_pages + 1):
        print(f"  [디시인사이드] 페이지 {page} 탐색 중...")
        try:
            html = get_with_retries(lambda p=page: fetch_page(p), desc=f"페이지 {page}")
            posts, older_found = parse_posts(html, target)
            all_posts.extend(posts)
            print(f"  -> {len(posts)}개 목표일 글 수집" + (" (이전 날짜 글 감지, 종료)" if older_found else ""))

            if older_found: break
        except Exception as e:
            print(f"  -> 오류: {e}")
            complete = False
            break
        if page < max_pages: time.sleep(0.8)

    return all_posts, full_date_str, complete