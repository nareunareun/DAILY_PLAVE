"""Validate a target day's data/page pair, then verify the published remote snapshot.

Uses only the standard library so the final health check can run even when an
optional scraper or AI dependency failed to install. It never sends email.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from generate_html import generate_html
from scrape_utils import SOURCES


class ArchiveError(RuntimeError):
    pass


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ArchiveError("잘못된 대상 날짜")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ArchiveError("유효하지 않은 대상 날짜") from exc
    return value


def normalized(text):
    return text.replace("\r\n", "\n")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError("데이터에 중복된 키가 있음")
        result[key] = value
    return result


def invalid_constant(value):
    raise ArchiveError("데이터에 유효하지 않은 숫자가 있음")


def load_day(text, target):
    try:
        data = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, TypeError) as exc:
        raise ArchiveError("날짜별 데이터를 읽을 수 없음") from exc
    if not isinstance(data, dict) or data.get("date") != valid_date(target):
        raise ArchiveError("데이터의 날짜가 대상 날짜와 다름")
    try:
        collected = datetime.fromisoformat(data["collected_at"])
        if collected.tzinfo is None:
            raise ValueError("timezone missing")
    except (KeyError, ValueError, TypeError) as exc:
        raise ArchiveError("수집 시각이 없거나 잘못됨") from exc
    total = 0
    for key, label, *_ in SOURCES:
        info = data.get(key)
        if not isinstance(info, dict) or not isinstance(info.get("posts"), list):
            raise ArchiveError(f"{label} 데이터 구조가 잘못됨")
        posts = info["posts"]
        if type(info.get("total")) is not int or info["total"] != len(posts):
            raise ArchiveError(f"{label} 글 개수와 실제 데이터가 다름")
        if type(info.get("complete")) is not bool:
            raise ArchiveError(f"{label} 수집 상태가 잘못됨")
        for post in posts:
            if not isinstance(post, dict):
                raise ArchiveError(f"{label} 글 형식이 잘못됨")
            for field in ("title", "link"):
                if not isinstance(post.get(field), str) or not post[field].strip():
                    raise ArchiveError(f"{label} 글의 필수 내용이 없음")
            link = urlsplit(post["link"])
            if link.scheme not in ("https", "http") or not link.hostname or link.username or link.password:
                raise ArchiveError(f"{label} 글 링크가 잘못됨")
            for field in ("view_count", "reply_count"):
                if type(post.get(field)) is not int or post[field] < 0:
                    raise ArchiveError(f"{label} 글 통계가 잘못됨")
        total += len(posts)
    if total == 0:
        raise ArchiveError("대상 날짜의 유효한 글이 전혀 없음")
    summary = data.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("issues"), list):
        raise ArchiveError("요약 저장 형식이 잘못됨")
    if not isinstance(summary.get("overall_mood"), str):
        raise ArchiveError("요약 저장 형식이 잘못됨")
    return data


class Navigation(HTMLParser):
    def __init__(self, archive):
        super().__init__()
        self.archive = archive
        self.in_select = False
        self.dates = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_select = attrs.get("id") == "archive-sel"
        if tag == "option" and self.in_select:
            value = attrs.get("value", "")
            if value in ("", "../index.html"):
                return
            pattern = r"(\d{4}-\d{2}-\d{2})\.html" if self.archive else r"archive/(\d{4}-\d{2}-\d{2})\.html"
            match = re.fullmatch(pattern, value)
            if not match:
                raise ArchiveError("페이지의 날짜 이동 정보가 잘못됨")
            self.dates.append(valid_date(match[1]))

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_select = False


def validate_page(data, text, archive, known_dates):
    nav = Navigation(archive)
    nav.feed(text)
    if nav.dates != sorted(set(nav.dates), reverse=True):
        raise ArchiveError("페이지의 날짜 목록이 중복되거나 잘못 정렬됨")
    if not set(nav.dates).issubset(known_dates):
        raise ArchiveError("페이지가 존재하지 않는 날짜를 참조함")
    if archive and data["date"] not in nav.dates:
        raise ArchiveError("날짜별 페이지에서 대상 날짜를 확인할 수 없음")
    if not archive and data["date"] in nav.dates:
        raise ArchiveError("메인 페이지의 날짜 이동 정보가 잘못됨")
    try:
        expected = generate_html(data, data["summary"], archive_dates=nav.dates, is_archive_page=archive)
    except Exception as exc:
        raise ArchiveError("저장 데이터로 페이지를 재구성할 수 없음") from exc
    if normalized(text) != normalized(expected):
        raise ArchiveError("데이터와 페이지 내용이 일치하지 않거나 페이지가 손상됨")


class LocalSnapshot:
    def __init__(self, root):
        self.root = Path(root)

    def read(self, relative):
        try:
            return (self.root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ArchiveError("필수 아카이브 자료가 없거나 읽을 수 없음") from exc

    def paths(self):
        return [p.relative_to(self.root).as_posix() for p in (self.root / "archive").glob("*.html")]


def git(root, *args):
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30, check=True)
        return result.stdout.decode("utf-8")
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        # Do not echo credential-bearing Git configuration or command output.
        raise ArchiveError("원격 Git 아카이브 상태를 확인할 수 없음") from exc


class RemoteSnapshot:
    def __init__(self, root):
        self.root = root
        git(root, "fetch", "--no-tags", "origin", "main:refs/remotes/origin/main")
        self.commit = git(root, "rev-parse", "origin/main").strip()

    def read(self, relative):
        return git(self.root, "show", f"{self.commit}:{relative}")

    def paths(self):
        return git(self.root, "ls-tree", "-r", "--name-only", self.commit, "archive").splitlines()


@dataclass
class Health:
    target: str
    counts: dict
    missing: list
    summary_missing: bool
    pages: dict


def validate_snapshot(snapshot, target):
    valid_date(target)
    dates = {match[1] for path in snapshot.paths() if (match := re.fullmatch(r"archive/(\d{4}-\d{2}-\d{2})\.html", path))}
    if target not in dates:
        raise ArchiveError("대상 날짜의 아카이브 페이지가 없음")
    for day in dates:
        valid_date(day)
    latest = max(dates)
    data = load_day(snapshot.read(f"archive/data/{target}.json"), target)
    archive = snapshot.read(f"archive/{target}.html")
    validate_page(data, archive, True, dates)
    latest_data = data if latest == target else load_day(snapshot.read(f"archive/data/{latest}.json"), latest)
    home = snapshot.read("index.html")
    validate_page(latest_data, home, False, dates)
    return Health(target, {label: data[key]["total"] for key, label, *_ in SOURCES},
                  [label for key, label, *_ in SOURCES if not data[key]["posts"] or not data[key]["complete"]],
                  not bool(data["summary"]["issues"]), {f"archive/{target}.html": archive, "": home})


def get_published(url):
    request = Request(url, headers={"User-Agent": "DAILY-PLAVE-archive-health", "Cache-Control": "no-cache"})
    try:
        with urlopen(request, timeout=8) as response:
            content = response.read(8 * 1024 * 1024 + 1)
            if response.status != 200 or len(content) > 8 * 1024 * 1024:
                raise ArchiveError("게시 페이지 응답이 잘못됨")
            return content.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ArchiveError("게시 페이지를 확인할 수 없음") from exc


def verify_remote(root, target, site_url, attempts=10, delay=10, snapshot_factory=RemoteSnapshot, fetch=get_published, wait=time.sleep):
    if site_url != "https://nareunareun.github.io/DAILY_PLAVE/":
        raise ArchiveError("승인되지 않은 게시 주소")
    snapshot = snapshot_factory(root)
    health = validate_snapshot(snapshot, target)
    for attempt in range(attempts):
        try:
            for relative, expected in health.pages.items():
                if normalized(fetch(urljoin(site_url, relative))) != normalized(expected):
                    raise ArchiveError("원격 자료와 실제 게시 페이지가 아직 일치하지 않음")
            return health
        except ArchiveError:
            if attempt + 1 == attempts:
                raise
            print(f"게시 반영 확인 대기 ({attempt + 1}/{attempts})")
            wait(delay)
    raise ArchiveError("게시 검증을 수행하지 못함")


def finish(health, outcomes):
    warnings = []
    if any(value != "success" for value in outcomes):
        warnings.append("수집·생성·원격 반영 중 오류가 있었지만 기존 정상 원격 아카이브와 게시를 확인했습니다.")
    if health.missing:
        warnings.append("일부 소스 미완료: " + ", ".join(health.missing))
    if health.summary_missing:
        warnings.append("AI 요약 없음 — 날짜별 수집·게시 자료는 정상입니다.")
    for warning in warnings:
        print("::warning::" + warning)
    message = f"{health.target} 원격 아카이브·게시 검증 통과 / " + ", ".join(f"{key} {value}개" for key, value in health.counts.items())
    print(message)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        try:
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
                stream.write("## 아카이브 상태\n\n" + message + "\n\n" + "\n".join("- " + item for item in warnings) + "\n")
        except OSError:
            print("::warning::아카이브 검증은 통과했지만 실행 요약을 기록하지 못했습니다.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("candidate", "remote"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--site-url", default="https://nareunareun.github.io/DAILY_PLAVE/")
    parser.add_argument("--outcome", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.mode == "candidate":
            validate_snapshot(LocalSnapshot(args.root), args.date)
            print("게시 후보 데이터·페이지 검증 통과")
        else:
            finish(verify_remote(args.root, args.date, args.site_url), args.outcome)
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, ArchiveError) else "아카이브 검증 중 예기치 않은 오류"
        prefix = "warning" if args.mode == "candidate" else "error"
        print(f"::{prefix}::{message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
