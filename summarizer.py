import json
import time
from anthropic import Anthropic, APIConnectionError, APITimeoutError

def load_posts(path="posts.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_prompt(posts_data):
    sources = [
        ("dcinside", "디시"),
        ("theqoo",   "더쿠"),
        ("newduck",  "뉴덕"),
        ("instiz",   "인스티즈"),
    ]
    lines = []
    for key, label in sources:
        for p in posts_data.get(key, {}).get("posts", [])[:50]:
            lines.append(f"[{label}] {p['title']}")
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

글 제목 목록 (각 출처 표시, 인기순):
{post_list}

위 글 목록을 분석해서 네 커뮤니티를 통틀어 현재 화제가 되고 있는 이슈를 3~6개로 요약해주세요.
출처가 한 곳에만 있더라도 중요하면 포함하고, 여러 커뮤니티에서 공통으로 언급되면 더 중요한 이슈로 다뤄주세요.

응답 형식 (JSON):
{{
  "issues": [
    {{
      "rank": 1,
      "title": "이슈 제목 (15자 이내)",
      "summary": "해당 이슈에 대한 설명 (2-3문장)",
      "keywords": ["키워드1", "키워드2"],
      "hot_level": "hot/warm/normal",
      "sources": ["디시", "더쿠", "뉴덕", "인스티즈"]
    }}
  ],
  "overall_mood": "오늘 팬 커뮤니티 전체 분위기 한 줄 요약"
}}

JSON만 응답하고 다른 텍스트는 포함하지 마세요."""

    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
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

