import json
import time
from anthropic import Anthropic, APIConnectionError, APITimeoutError

# 요약에 보낼 글 선별 기준(반응 기준).
# 출처마다 글 양이 크게 달라(디시·뉴덕 ~30 vs 더쿠·인스티즈 수십~1400+)
# 고정 개수 컷은 작은 출처엔 과하고 큰 출처엔 반응 있는 글을 버린다.
# 그래서 '댓글 수'로 거른다: 댓글이 임계값 이상인 글을 반응 강도순으로
# 포함하되, 작은 출처가 굶지 않게 최소치를 보장하고, 폭주일의 토큰을
# 막기 위해 상한을 둔다. (글은 score 내림차순 정렬 상태)
REPLY_THRESHOLD = 3   # 이 댓글 수 이상이면 '유의미 반응'으로 보고 포함
MIN_POSTS = 15        # 출처별 최소 보장(반응 글이 적어도 top score 15개)
MAX_POSTS = 80        # 출처별 상한(토큰 방어)


def select_posts(posts):
    """한 출처에서 요약에 보낼 글을 반응 기준으로 선별."""
    reacted = [p for p in posts if p.get("reply_count", 0) >= REPLY_THRESHOLD]
    chosen = reacted if len(reacted) >= MIN_POSTS else posts[:MIN_POSTS]
    return chosen[:MAX_POSTS]


def build_prompt(posts_data):
    sources = [
        ("dcinside", "디시"),
        ("theqoo",   "더쿠"),
        ("newduck",  "뉴덕"),
        ("instiz",   "인스티즈"),
    ]
    lines = []
    for key, label in sources:
        posts = posts_data.get(key, {}).get("posts", [])
        for p in select_posts(posts):
            lines.append(f"[{label}] {p['title']} (댓글 {p.get('reply_count', 0)})")
    return "\n".join(lines)

def summarize(posts_data, max_retries=5):
    client = Anthropic(
        max_retries=3,
        timeout=60.0,
    )

    collected_at = posts_data["collected_at"]
    date = posts_data.get("date", collected_at[:10])
    post_list = build_prompt(posts_data)

    prompt = f"""아래는 오늘({date}) 플레이브 팬 커뮤니티(디시인사이드, 더쿠, 뉴덕, 인스티즈) 게시글 제목 목록입니다.
수집 시각: {collected_at}

글 목록 (각 출처 표시, 반응순, 끝에 댓글 수 표기 — 각 출처 반응 상위권):
{post_list}

위 글 목록을 분석해서 네 커뮤니티를 통틀어 현재 화제가 되고 있는 이슈를 3~6개로 요약해주세요.
출처가 한 곳에만 있더라도 중요하면 포함하고, 여러 커뮤니티에서 공통으로 언급되면 더 중요한 이슈로 다뤄주세요.
각 글 끝의 (댓글 N)은 반응 강도를 나타냅니다. 댓글이 많은 글일수록 화제성이 크므로, 댓글 수가 많은 주제와 여러 커뮤니티에 공통으로 등장하는 주제를 우선적으로 중요 이슈로 다뤄주세요.

[어투 규칙] 모든 'summary'와 'overall_mood' 문장은 반드시 존댓말로 작성하세요.
문장은 '~합니다', '~입니다', '~네요', '~보입니다'처럼 정중한 종결어미로 끝내고,
'~다', '~함', '~음', '~네', '~인 듯' 같은 반말·음슬체·개조식 종결은 절대 사용하지 마세요.

응답 형식 (JSON):
{{
  "issues": [
    {{
      "rank": 1,
      "title": "이슈 제목 (15자 이내)",
      "summary": "해당 이슈에 대한 설명 (2-3문장, 존댓말)",
      "keywords": ["키워드1", "키워드2"],
      "hot_level": "hot/warm/normal",
      "sources": ["디시", "더쿠", "뉴덕", "인스티즈"]
    }}
  ],
  "overall_mood": "오늘 팬 커뮤니티 전체 분위기 한 줄 요약 (존댓말)"
}}

JSON만 응답하고 다른 텍스트는 포함하지 마세요."""

    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except (APIConnectionError, APITimeoutError) as e:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            print(f"[재시도 {attempt}/{max_retries}] 연결 오류: {e} — {wait}초 후 재시도...")
            time.sleep(wait)

    raw = message.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    return json.loads(raw)

def save_summary(summary, path="summary.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"요약 결과를 {path}에 저장했습니다.")

