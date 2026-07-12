# DAILY PLAVE

## 목적

하루종일 커뮤니티 4곳(디시인사이드·더쿠·뉴덕·인스티즈)의 모든 글을 살펴보지
않고도 그날의 이슈와 반응을 놓치지 않기 위한 완전 자동화 시스템.
핵심 가치는 **커뮤니티별 인기글 TOP 15의 선별 품질**이며, AI 요약은 보조
기능이다(요약이 실패해도 수집·페이지 생성은 반드시 진행되어야 한다).
추가 요금이 드는 해결책(프록시, 유료 서비스)은 쓰지 않는다. API(Anthropic)는
요약에만 사용한다.

## 구조

- `run.py` — 오케스트레이터. 매 실행: 날짜별 데이터 파일 확인 → 부족한
  소스만 수집 → 병합 → 요약 → HTML 생성. `--date YYYY-MM-DD`(백필),
  `--force`(전체 재수집) 옵션.
- `scraper_*.py` — 소스별 수집기. `collect_posts(target_date=None)` →
  `(posts, "YYYY-MM-DD", complete)`. `complete=False`면 탐색이 오류로
  중단돼 일부만 모인 것.
- `scrape_utils.py` — 날짜 판별(백필 대응)·요청 재시도·소스 목록(`SOURCES`)
  공통 모듈. 소스를 추가/제거할 때는 여기 `SOURCES`만 고치면 된다.
- `scoring.py` — min-max 정규화 후 댓글 가중 점수로 TOP 15 선별.
- `summarizer.py` — Claude API 요약(유일한 유료 단계, 실패 시 생략).
- `generate_html.py` — index.html + archive/날짜.html 생성.
- `archive/data/날짜.json` — **날짜별 원본 데이터(요약 포함, 커밋됨).**
  이 파일이 있으면 언제든 HTML 재생성 가능. 재실행 병합의 기준.
- `archive/dates.js` — 전체 아카이브 날짜 목록(커밋됨, 매 실행 갱신).
  각 페이지의 날짜 드롭다운을 열람 시점 기준으로 보강해, 과거에 생성된
  페이지에서도 이후 추가된 날짜로 이동할 수 있다.
- `.github/workflows/daily_update.yml` — 하루 7회 cron(00:32~11:01 KST)
  + 수동 실행. 성공 메일에 소스별 수집 개수 표기.

## 자가 치유 동작 (설계 의도)

- 소스별 독립: 한 소스가 실패해도 나머지로 부분 페이지를 만들어 커밋한다.
- 부분 커밋된 날은 "완료"가 아니다 — 다음 cron이 **부족한 소스만** 다시
  수집해 병합한다(성공한 소스는 재수집하지 않아 조회수 왜곡·부하 없음).
- 소스가 0개이거나 탐색이 중간에 끊긴(complete=False) 경우 미완료로 취급.
- 목록에서 날짜를 인식한 행이 3페이지 연속 없으면 사이트 구조·날짜 표기
  변경으로 보고 탐색을 중단, 미완료로 기록한다(무한 탐색·타임아웃 방지).
- 네 소스 모두 완결 수집된 날만 이후 실행이 건너뛴다.
- 전 소스 실패 또는 재시도에서 아무것도 새로 얻지 못하면 exit 1로 빌드를
  실패시켜 GitHub 실패 메일이 가게 한다(무음 실패 방지).

## 장애 대응 런북

| 증상 | 원인 | 대처 |
|---|---|---|
| 인스티즈 403 (Cloudflare Forbidden) | GitHub 러너(Azure) IP 차단. 코드 문제 아님 | 그날 다른 cron이 자동 재시도. 밤 11:01까지 전부 실패하면 아래 '로컬 복구' |
| ⚠ 부분 업데이트 메일 | 한 소스 다운/차단 | 기본적으로 방치해도 됨 — 다음 cron이 자동으로 메꿈. 하루 종일 미완료면 로컬 복구 |
| 어떤 소스가 며칠째 0개 | 사이트 HTML 구조 변경 | 해당 `scraper_*.py`의 CSS 선택자를 실제 페이지와 대조해 수정 |
| 하루를 통째로 놓침 | 전 소스 실패 후 복구 안 함 | **백필**: `python run.py --date YYYY-MM-DD` (며칠 내라면 가능, 조회수는 수집 시점 기준) |
| AI 요약 없음 | API 크레딧 소진/키 오류 | 페이지는 정상. console.anthropic.com에서 크레딧/키 확인 |
| cron이 아예 안 돎 | 저장소 60일 무활동 시 GitHub이 예약 실행 중지 | Actions 탭에서 워크플로 재활성화 (일일 커밋이 있는 한 발생 안 함) |

### 로컬 복구 (Claude가 실행할 때)

이 저장소는 Windows의 `C:\Users\Admin\Desktop\CC\DAILY PLAVE`에 있고,
Claude는 WSL(`/mnt/c/...`)에서 작업한다. 집 IP는 Cloudflare 차단이 없어
로컬 실행이 가장 확실한 복구 수단이다.

```bash
cd "/mnt/c/Users/Admin/Desktop/CC/DAILY PLAVE"
git pull --ff-only
python3 run.py                      # 어제 데이터. 놓친 날짜는 --date YYYY-MM-DD
git add index.html archive/
git commit -m "Daily update: $(date +%Y-%m-%d)"
git push
```

- API 키는 `.env`에 있음(자동 로드). 의존성은 `pip3 install --user --break-system-packages -r requirements.txt`.
- 사용자에게 직접 실행 명령을 알려줄 때는 Windows(cmd) 기준으로 안내할 것.
- 자정(KST)이 지나도 데이터 파일 도입 이후로는 `--date`로 백필 가능하므로
  서두를 필요는 없지만, 목록 페이지가 며칠 지나면 깊어지므로 빠를수록 좋다.

## 주의사항

- `already_done` 판정은 `archive/data/<날짜>.json`의 소스별 완결 여부로
  한다. index.html 배지 파싱(과거 방식)은 더 이상 쓰지 않는다.
- index.html은 항상 **가장 최신 날짜**의 데이터로 생성된다. 과거 날짜를
  백필해도 index가 과거로 덮이지 않는다.
- `requirements.txt`의 `cloudscraper`는 버전을 고정하지 않는다 —
  Cloudflare가 바뀌면 새 버전이 대응하므로 최신을 받는 게 유리하다.
- 커밋 대상은 `index.html`, `archive/`(데이터 포함), `style.css`뿐.
  `posts.json`·`summary.json`·`.last_run_status.json`은 로컬 산출물.
