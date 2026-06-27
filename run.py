#!/usr/bin/env python3
import sys
import os
import re
import json
import glob
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def already_done(target_date):
    """이미 target_date(어제) 인스티즈 데이터가 들어간 index.html이 커밋돼 있으면 True.

    자동 재시도(여러 cron) 시 한 번 성공한 날은 이후 실행을 건너뛰어
    중복 커밋·메일을 막는다. 인스티즈가 403으로 0개 커밋된 경우는
    False라서 재시도가 진행된다.
    """
    if not os.path.exists("index.html"):
        return False
    try:
        with open("index.html", encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return False
    m = re.search(
        r'hero-badge">(\d{4})년 (\d{2})월 (\d{2})일 ·.*?인스티즈 (\d+)개', html
    )
    if not m:
        return False
    badge_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return badge_date == target_date and int(m.group(4)) > 0


def main():
    target_date_guess = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
    if already_done(target_date_guess):
        print(f"이미 {target_date_guess} 업데이트 완료(인스티즈 포함). 재시도를 건너뜁니다.")
        return

    print("=" * 60)
    print(" DAILY PLAVE - 커뮤니티 이슈 요약기")
    print("=" * 60)

    print("\n[1/6] 디시인사이드 마이너 갤러리 수집 중...")
    from scraper_dcinside import collect_posts as dc_collect
    dc_posts, target_date = dc_collect()

    print("\n[2/6] 더쿠 수집 중...")
    from scraper_theqoo import collect_posts as theqoo_collect
    theqoo_posts, _ = theqoo_collect()

    print("\n[3/6] 뉴덕 수집 중...")
    from scraper_newduck import collect_posts as newduck_collect
    newduck_posts, _ = newduck_collect()

    print("\n[4/6] 인스티즈 수집 중...")
    from scraper_instiz import collect_posts as instiz_collect
    instiz_posts, _ = instiz_collect()

    from scoring import rank_posts
    dc_posts      = rank_posts(dc_posts,      "dcinside")
    theqoo_posts  = rank_posts(theqoo_posts,  "theqoo")
    newduck_posts = rank_posts(newduck_posts, "newduck")
    instiz_posts  = rank_posts(instiz_posts,  "instiz")

    now_kst = datetime.now(KST)
    posts_data = {
        "collected_at": now_kst.isoformat(),
        "date": target_date,
        "dcinside": {"total": len(dc_posts),      "posts": dc_posts},
        "theqoo":   {"total": len(theqoo_posts),  "posts": theqoo_posts},
        "newduck":  {"total": len(newduck_posts),  "posts": newduck_posts},
        "instiz":   {"total": len(instiz_posts),   "posts": instiz_posts},
    }
    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=2)
    print(f"\n  -> 디시 {len(dc_posts)}개, 더쿠 {len(theqoo_posts)}개, 뉴덕 {len(newduck_posts)}개, 인스티즈 {len(instiz_posts)}개 → posts.json 저장")

    print("\n[5/6] AI 이슈 요약 생성 중...")
    from summarizer import summarize, save_summary
    # 유일한 유료(API) 단계. 크레딧 소진·인증 오류 등으로 실패해도 빌드 전체를
    # 멈추지 않고, 빈 요약으로 대체해 수집 데이터·HTML은 정상 생성되게 한다.
    try:
        summary = summarize(posts_data)
    except Exception as e:
        print(f"  -> [경고] AI 요약 생략(이번 빌드는 요약 없이 진행): {e}")
        summary = {
            "issues": [],
            "overall_mood": "오늘은 AI 요약을 생성하지 못했습니다. (수집 데이터는 정상입니다.)",
        }
    save_summary(summary)

    for issue in summary["issues"]:
        sources = "/".join(issue.get("sources", []))
        print(f"  · {issue['title']} ({sources})")

    print("\n[6/6] HTML 페이지 생성 중...")
    from generate_html import generate_html, save_html

    os.makedirs("archive", exist_ok=True)
    current_date = posts_data['date']

    archive_files = sorted(glob.glob("archive/????-??-??.html"), reverse=True)
    existing_dates = [os.path.basename(f)[:-5] for f in archive_files]
    index_dates = sorted([d for d in existing_dates if d != current_date], reverse=True)
    archive_dates = sorted(set([current_date] + existing_dates), reverse=True)

    html = generate_html(posts_data, summary, archive_dates=index_dates)
    save_html(html)

    archive_path = f"archive/{current_date}.html"
    archive_html = generate_html(posts_data, summary, archive_dates=archive_dates, is_archive_page=True)
    save_html(archive_html, path=archive_path)
    print(f"  -> 아카이브 저장: {archive_path}")

    print("\n" + "=" * 60)
    print("완료!")
    print(f"파일 경로: {os.path.abspath('index.html')}")
    print("브라우저로 index.html을 열어 확인하세요.")
    print("=" * 60)

if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            from dotenv import load_dotenv
            load_dotenv(env_path)
        else:
            print("오류: ANTHROPIC_API_KEY가 설정되지 않았습니다.")
            print("  .env 파일에 ANTHROPIC_API_KEY=sk-ant-... 를 추가하세요.")
            sys.exit(1)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()