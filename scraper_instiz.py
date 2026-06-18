import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime, timezone, timedelta

BOARD_URL = "https://www.instiz.net/name_enter"
CATEGORY  = 644

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.instiz.net/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

KST = timezone(timedelta(hours=9))
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

def fetch_page(page=1):
    params = {"category": CATEGORY}
    if page > 1:
        params["page"] = page
    resp = requests.get(BOARD_URL, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.text

def parse_posts(html, target_date_str, seen_links):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    older_found = False
    new_links_count = 0

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
        
        if target_date_str in date_text:
            pass 
        elif _TIME_RE.match(date_text):
            continue 
        elif re.search(r"\d+\.\d+", date_text):
            # 상단 인기글(우회) 블록은 본문 목록과 중복되며 과거 글이어도
            # 종료 신호로 보면 안 된다. 위치(순번) 대신 구조로 식별한다:
            # detour 행 또는 texthead_notice(=is_green_post)는 건너뛰기만 한다.
            if is_green_post or row.get("id") == "detour":
                continue
            else:
                older_found = True
                continue
        else:
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

    return posts, older_found, new_links_count

def collect_posts(max_pages=999):
    all_posts = []
    yesterday = datetime.now(KST) - timedelta(days=1)
    target_date_str = yesterday.strftime("%m.%d") 
    full_date_str = yesterday.strftime("%Y-%m-%d")

    print(f"목표 수집 날짜: {full_date_str} (인스티즈 판별용: {target_date_str})")
    
    seen_links = set()

    for page in range(1, max_pages + 1):
        print(f"  [인스티즈] 페이지 {page} 탐색 중...")
        try:
            html = fetch_page(page)
            posts, older_found, new_links_count = parse_posts(html, target_date_str, seen_links)
            
            all_posts.extend(posts)
            print(f"  -> {len(posts)}개 어제 글 수집" + (" (그저께 이전 글 감지, 종료)" if older_found else ""))
            
            if older_found: break

            if new_links_count == 0 and page > 1:
                print("  -> [알림] 더 이상 새로운 글이 발견되지 않아 탐색을 강제 종료합니다. (끝 페이지 도달)")
                break

        except Exception as e:
            print(f"  -> 오류: {e}")
            break
            
        if page < max_pages: time.sleep(0.8)

    return all_posts, full_date_str