#!/usr/bin/env python3
"""DAILY PLAVE 일일 수집 오케스트레이터 (자가 치유 구조).

날짜별 수집 결과를 archive/data/<날짜>.json으로 저장소에 함께 커밋해 두고,
재실행 때 이미 완결 수집된 소스는 재사용하며 실패했거나 미완료인 소스만
다시 수집해 병합한다. 하루 여러 번 도는 cron이 그대로 자동 복구 장치가
된다: 새벽에 한 사이트가 다운이어도 낮 cron이 그 소스만 채워 넣는다.

사용법:
  python run.py                     # 어제(KST) 수집 (cron 기본)
  python run.py --date 2026-07-03   # 놓친 날짜 백필
  python run.py --force             # 완료된 소스도 전부 다시 수집
"""
import sys
import os
import json
import glob
import argparse
from datetime import datetime, timezone, timedelta

from scrape_utils import SOURCES

KST = timezone(timedelta(hours=9))

DATA_DIR = os.path.join("archive", "data")
# 워크플로 메일 단계가 읽는 실행 결과 요약(커밋되지 않음).
STATUS_PATH = ".last_run_status.json"

def empty_summary():
    # 매번 새 dict/list를 만들어 반환한다(공유 객체 변형 방지).
    return {
        "issues": [],
        "overall_mood": "오늘은 AI 요약을 생성하지 못했습니다. (수집 데이터는 정상입니다.)",
    }


def data_path(date_str):
    return os.path.join(DATA_DIR, f"{date_str}.json")


def load_data(date_str):
    try:
        with open(data_path(date_str), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def source_ok(data, key):
    """저장된 데이터에서 해당 소스가 '완결 수집' 상태인지.

    0개는 사이트 다운·구조 변경일 가능성이 높아 미완료로 취급하고,
    페이지 탐색이 오류로 끊긴 경우(complete=False)도 다음 실행에서
    다시 수집하게 한다.
    """
    if not data:
        return False
    info = data.get(key) or {}
    return bool(info.get("posts")) and info.get("complete", True)


def write_status(target, posts_data, changed):
    counts = {}
    missing = []
    for key, label, *_ in SOURCES:
        info = (posts_data or {}).get(key) or {}
        counts[label] = info.get("total", 0)
        if not source_ok(posts_data, key):
            missing.append(label)
    status = {"date": target, "counts": counts, "missing": missing, "changed": changed}
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    return status


def main():
    ap = argparse.ArgumentParser(description="DAILY PLAVE 커뮤니티 수집·페이지 생성")
    ap.add_argument("--date", help="수집 날짜 YYYY-MM-DD (기본: 어제 KST)")
    ap.add_argument("--force", action="store_true", help="완료된 소스도 전부 다시 수집")
    args = ap.parse_args()

    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            sys.exit(f"오류: --date 형식이 잘못됐습니다: {args.date} (예: 2026-07-03)")
        target = args.date
    else:
        target = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")

    existing = None if args.force else load_data(target)
    pending = [(k, l, m) for k, l, _, m in SOURCES if not source_ok(existing, k)]

    if not pending:
        print(f"이미 {target} 네 소스 모두 수집 완료. 재시도를 건너뜁니다.")
        write_status(target, existing, changed=False)
        return

    print("=" * 60)
    print(" DAILY PLAVE - 커뮤니티 이슈 요약기")
    print(f" 수집 날짜: {target} / 대상 소스: {', '.join(l for _, l, _ in pending)}")
    print("=" * 60)

    from scoring import rank_posts

    posts_data = {
        "collected_at": datetime.now(KST).isoformat(),
        "date": target,
    }
    changed = False

    for key, label, _, module_name in SOURCES:
        if existing and source_ok(existing, key):
            posts_data[key] = existing[key]
            print(f"\n[{label}] 기존 수집분 재사용 ({existing[key].get('total', 0)}개)")
            continue

        print(f"\n[{label}] 수집 중...")
        try:
            module = __import__(module_name)
            posts, _, complete = module.collect_posts(target_date=target)
        except Exception as e:
            print(f"  -> [경고] {label} 수집 실패(다음 실행에서 재시도): {e}")
            posts, complete = [], False

        posts = rank_posts(posts, key)
        posts_data[key] = {
            "total": len(posts),
            "posts": posts,
            "complete": bool(posts) and complete,
        }
        if posts:
            changed = True

    nonempty = [k for k, *_ in SOURCES if posts_data[k].get("total", 0) > 0]
    if not nonempty:
        write_status(target, posts_data, changed=False)
        raise RuntimeError(
            f"{target} 전 소스 수집 실패 — 게시할 데이터가 없어 빌드를 중단합니다."
        )

    if not changed:
        # 부족한 소스를 재시도했지만 아무것도 새로 얻지 못했다.
        # 기존 페이지를 타임스탬프만 바꿔 다시 커밋하는 낭비를 막고,
        # 워크플로를 실패시켜 GitHub 실패 메일로 상황을 알린다.
        status = write_status(target, posts_data, changed=False)
        raise RuntimeError(
            f"{target} 미수집 소스 재시도 실패(여전히 누락: {', '.join(status['missing'])}) — 변경 없음."
        )

    status = write_status(target, posts_data, changed=True)
    print(f"\n  -> 수집 현황: " + ", ".join(f"{l} {status['counts'][l]}개" for _, l, *_ in SOURCES))
    if status["missing"]:
        print(f"  -> [경고] 미완료 소스(다음 실행에서 재시도): {', '.join(status['missing'])}")

    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=2)

    print("\n[요약] AI 이슈 요약 생성 중...")
    from summarizer import summarize, save_summary
    # 유일한 유료(API) 단계. 크레딧 소진·인증 오류 등으로 실패해도 빌드 전체를
    # 멈추지 않는다. 소스 구성이 같으면 기존 요약을 재사용해 호출을 아낀다.
    prev_summary = (existing or {}).get("summary")
    prev_sources = set((existing or {}).get("summary_sources") or [])
    # 소스 '집합'만 비교하면 끊겼던(complete=False) 소스를 온전히 다시 채운
    # 날에도 부분 데이터로 만든 옛 요약을 재사용해 버린다. 소스별 개수까지
    # 같을 때만 같은 데이터로 보고 재사용한다.
    same_counts = all(
        ((existing or {}).get(k) or {}).get("total") == posts_data[k].get("total")
        for k in nonempty
    )
    if prev_summary and prev_summary.get("issues") and prev_sources == set(nonempty) and same_counts:
        print("  -> 소스 구성·개수가 같아 기존 요약을 재사용합니다.")
        summary = prev_summary
    else:
        try:
            summary = summarize(posts_data)
        except Exception as e:
            print(f"  -> [경고] AI 요약 생략(이번 빌드는 요약 없이 진행): {e}")
            summary = prev_summary if (prev_summary and prev_summary.get("issues")) else empty_summary()
    save_summary(summary)

    for issue in summary.get("issues", []):
        sources = "/".join(issue.get("sources", []))
        print(f"  · {issue['title']} ({sources})")

    # 날짜별 데이터 파일(요약 포함)을 저장소에 커밋해 영구 보존한다.
    # 이 파일이 있으면 언제든 HTML을 다시 만들 수 있고, 재실행 병합의
    # 기준이 된다.
    posts_data["summary"] = summary
    posts_data["summary_sources"] = sorted(nonempty)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(data_path(target), "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=2)
    print(f"  -> 데이터 저장: {data_path(target)}")

    print("\n[생성] HTML 페이지 생성 중...")
    from generate_html import generate_html, save_html, save_dates_js

    os.makedirs("archive", exist_ok=True)
    archive_files = sorted(glob.glob("archive/????-??-??.html"), reverse=True)
    existing_dates = [os.path.basename(f)[:-5] for f in archive_files]
    all_dates = sorted(set([target] + existing_dates), reverse=True)
    # 전 페이지 드롭다운이 참조하는 날짜 목록 — 과거 페이지도 최신 날짜로 이동 가능.
    save_dates_js(all_dates)

    archive_path = f"archive/{target}.html"
    archive_html = generate_html(posts_data, summary, archive_dates=all_dates, is_archive_page=True)
    save_html(archive_html, path=archive_path)
    print(f"  -> 아카이브 저장: {archive_path}")

    # index.html은 항상 '가장 최신 날짜'의 데이터로 생성한다.
    # 과거 날짜를 백필할 때 index가 과거 데이터로 덮이는 것을 막고,
    # 백필한 날짜가 index의 아카이브 목록에도 바로 나타나게 한다.
    latest = all_dates[0]
    if latest == target:
        idx_data, idx_summary = posts_data, summary
    else:
        idx_data = load_data(latest)
        idx_summary = (idx_data or {}).get("summary") or empty_summary()
    if idx_data:
        index_dates = [d for d in all_dates if d != latest]
        index_html = generate_html(idx_data, idx_summary, archive_dates=index_dates)
        save_html(index_html)
    else:
        # 데이터 파일 도입 전의 과거 날짜가 최신인 경우: 기존 index를 보존한다.
        print(f"  -> index.html 재생성 생략({latest} 데이터 파일 없음) — 아카이브만 갱신")

    print("\n" + "=" * 60)
    print("완료!" + (" (일부 소스 미완료 — 다음 실행에서 자동 재시도)" if status["missing"] else ""))
    print(f"파일 경로: {os.path.abspath('index.html')}")
    print("=" * 60)


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            from dotenv import load_dotenv
            load_dotenv(env_path)
        else:
            # API 키가 없어도 수집·페이지 생성은 진행한다(요약만 생략됨).
            print("[알림] ANTHROPIC_API_KEY 없음 — AI 요약 없이 진행합니다.")

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
