"""커뮤니티 인기글 점수 산정 (공통 모듈).

각 커뮤니티 내에서 조회/댓글/추천 수를 min-max 정규화한 뒤 가중 합산한다.
원시 수치는 자릿수(scale)가 크게 다르기 때문에(조회 수천 vs 댓글 수십)
그대로 가중하면 조회수가 점수를 지배한다. 정규화로 0~1 스케일을 맞춰야
댓글 등 '반응' 지표가 의도한 가중치만큼 실제로 반영되고, 그 결과
조회수만 높고 반응이 적은 단순 클릭 유도글을 상위에서 걸러낼 수 있다.
"""

# 커뮤니티별 지표 가중치 (정규화 후 적용). 각 합은 1.0.
# 반응 지표(댓글/추천)에 무게를 실어 클릭 유도글을 억제한다.
WEIGHTS = {
    "dcinside": {"reply_count": 0.45, "recommend_count": 0.35, "view_count": 0.20},
    "theqoo":   {"reply_count": 0.65, "view_count": 0.35},
    "newduck":  {"reply_count": 0.65, "view_count": 0.35},
    "instiz":   {"reply_count": 0.65, "view_count": 0.35},
}
_DEFAULT_WEIGHTS = {"reply_count": 0.65, "view_count": 0.35}


def _normalize(values):
    """리스트를 min-max 정규화. 전부 같은 값이면 0으로 처리(순위 영향 없음)."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0] * len(values)
    span = hi - lo
    return [(v - lo) / span for v in values]


def rank_posts(posts, source):
    """source 커뮤니티의 게시글에 score를 부여하고 내림차순 정렬해 반환."""
    if not posts:
        return posts

    weights = WEIGHTS.get(source, _DEFAULT_WEIGHTS)

    normalized = {
        metric: _normalize([p.get(metric, 0) for p in posts])
        for metric in weights
    }

    for i, p in enumerate(posts):
        p["score"] = round(sum(weights[m] * normalized[m][i] for m in weights), 4)

    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts
