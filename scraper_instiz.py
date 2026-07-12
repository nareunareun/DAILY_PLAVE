import cloudscraper
from bs4 import BeautifulSoup
import re
import time
from scrape_utils import (
    resolve_target_date, classify_date_text,
    TARGET, OLDER, UNKNOWN,
)

BOARD_URL = "https://www.instiz.net/name_enter"
CATEGORY  = 644

HEADERS = {
    "Referer": "https://www.instiz.net/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _make_scraper():
    # 인스티즈는 Cloudflare 뒤에 있어 평범한 requests는 데이터센터 IP에서
    # 간헐적으로 403을 받는다. cloudscraper는 브라우저 TLS 핑거프린트와
    # 챌린지 처리를 흉내 내 차단 빈도를 낮춘다. 한 세션을 페이지 간 재사용해
    # 쿠키 유지 + keep-alive 효과도 얻는다.
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )


def fetch_page(scraper, page=1, retries=3, backoff=2.0):
    params = {"category": CATEGORY}
    if page > 1:
        params["page"] = page
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = scraper.get(BOARD_URL, headers=HEADERS, params=params, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = backoff * attempt
                print(f"  -> [재시도] 페이지 {page} 요청 실패({e}), {wait:.0f}s 후 재시도 ({attempt}/{retries})")
                time.sleep(wait)
    raise last_err

def parse_posts(html, target_date, seen_links):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    older_found = False
    new_links_count = 0
    dated_rows = 0  # 날짜를 인식한 행 수(0이 이어지면 목록 구조 변경 신호)

    rows = soup.select("tr[id^='list'], tr[id='detour']")
    
    for row in rows:
        link_a = row.select_one("td.listsubject a[href]")
        if not link_a: continue
        
        raw_link = link_a.get("href", "")
        pure_link = re.sub(r'[?&]page=\d+', '', raw_link)
        
        is_new_link = pure_link not in seen_links
        if is_new_link:
            seen_links.add(pure_link)
            new_links_count += 1

        date_text = ""
        view_count = 0
        
        subtitle = row.select_one(".list_subtitle")
        if subtitle:
            sub_txt = subtitle.get_text(strip=True)
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{2}|\d{2}\.\d{2}|\d{2}:\d{2})", sub_txt)
            if date_match:
                date_text = date_match.group(1)
            view_match = re.search(r"조회\s*([\d,]+)", sub_txt)
            if view_match:
                view_count = int(view_match.group(1).replace(",", ""))
        else:
            listno_tds = row.select("td.listno")
            for td in listno_tds:
                txt = td.get_text(strip=True).replace(" ", "")
                if ":" in txt or "." in txt:
                    date_text = txt
                    break
            if listno_tds:
                try: view_count = int(listno_tds[-1].get_text(strip=True).replace(",", ""))
                except ValueError: pass
        
        if not date_text: continue

        is_green_post = bool(row.select_one("span.texthead_notice"))

        status = classify_date_text(date_text, target_date)
        if status != UNKNOWN:
            dated_rows += 1
        if status == TARGET:
            pass
        elif status == OLDER:
            # 상단 인기글(우회) 블록은 본문 목록과 중복되며 과거 글이어도
            # 종료 신호로 보면 안 된다. 위치(순번) 대신 구조로 식별한다:
            # detour 행 또는 texthead_notice(=is_green_post)는 건너뛰기만 한다.
            if is_green_post or row.get("id") == "detour":
                continue
            else:
                older_found = True
                continue
        else:  # NEWER(오늘 HH:MM 포함) 또는 UNKNOWN — 계속 탐색
            continue

        if not is_new_link:
            continue

        title = ""
        sbj_div = link_a.select_one(".sbj")
        if sbj_div:
            title = sbj_div.get_text(strip=True)
        else:
            title = link_a.get_text(strip=True)
        
        if subtitle:
            title = title.replace(subtitle.get_text(strip=True), "")
        
        reply_count = 0
        cmt_span = row.select_one(".cmt3, .cmt4")
        if cmt_span:
            cmt_txt = cmt_span.get_text(strip=True)
            try: reply_count = int(cmt_txt.strip("[]"))
            except ValueError: pass
            title = title.replace(cmt_txt, "")
        if reply_count == 0:
            m = re.search(r'(\d+)$', title)
            if m:
                reply_count = int(m.group(1))
                title = title[:m.start()]
            
        title = title.strip()
        if not title: continue

        posts.append({
            "title": title,
            "link": pure_link,
            "view_count": view_count,
            "reply_count": reply_count,
        })

    return posts, older_found, new_links_count, dated_rows

def collect_posts(target_date=None, max_pages=999):
    """target_date(기본: 어제)의 글을 수집. (posts, 'YYYY-MM-DD', complete) 반환.

    소스별 실패 처리(0개면 미완료로 기록, 전 소스 실패 시 빌드 실패)는
    run.py가 담당하므로 여기서는 예외를 올리지 않는다.
    """
    target = resolve_target_date(target_date)
    full_date_str = target.strftime("%Y-%m-%d")
    all_posts = []
    complete = True
    no_date_streak = 0

    print(f"목표 수집 날짜: {full_date_str}")

    seen_links = set()
    scraper = _make_scraper()

    for page in range(1, max_pages + 1):
        print(f"  [인스티즈] 페이지 {page} 탐색 중...")
        try:
            html = fetch_page(scraper, page)
            posts, older_found, new_links_count, dated_rows = parse_posts(html, target, seen_links)

            all_posts.extend(posts)
            print(f"  -> {len(posts)}개 목표일 글 수집" + (" (이전 날짜 글 감지, 종료)" if older_found else ""))

            if older_found: break

            # 링크는 매 페이지 새로워도 날짜 표기를 못 읽으면 무한 탐색이
            # 된다(seen_links 가드가 안 걸림). 구조 변경 신호로 보고 중단.
            no_date_streak = 0 if dated_rows else no_date_streak + 1
            if no_date_streak >= 3:
                print("  -> [경고] 3페이지 연속 날짜 인식 실패 — 목록 구조 변경 의심, 탐색 중단(미완료)")
                complete = False
                break

            if new_links_count == 0 and page > 1:
                print("  -> [알림] 더 이상 새로운 글이 발견되지 않아 탐색을 강제 종료합니다. (끝 페이지 도달)")
                break

        except Exception as e:
            print(f"  -> 오류: {e}")
            complete = False
            break

        if page < max_pages: time.sleep(0.8)

    return all_posts, full_date_str, complete