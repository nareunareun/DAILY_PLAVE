import json
from datetime import datetime, timezone, timedelta
from html import escape

KST = timezone(timedelta(hours=9))

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def source_chips(sources):
    cls_map = {
        "디시":    "chip-dc",
        "더쿠":    "chip-theqoo",
        "뉴덕":    "chip-newduck",
        "인스티즈": "chip-instiz",
    }
    label_map = {
        "인스티즈": "인티",
    }
    chips = []
    for s in sources:
        cls   = cls_map.get(s, "chip-dc")
        label = escape(label_map.get(s, s))
        chips.append(f'<span class="source-chip {cls}">{label}</span>')
    return "".join(chips)

def render_post_table(posts, top=15):
    rows = ""
    for i, p in enumerate(posts[:top], 1):
        # 제목에 <, &, " 등이 흔해(커뮤니티 글) 이스케이프 없이는 마크업이 깨진다.
        link  = escape(p.get("link", "#"), quote=True)
        title = escape(p["title"])
        view  = f"{p['view_count']:,}"
        reply = str(p["reply_count"])
        rows += f"""
        <tr>
          <td class="rank">{i}</td>
          <td class="post-title"><a class="post-link" href="{link}" target="_blank" rel="noopener">{title}</a></td>
          <td class="stat">{view}</td>
          <td class="stat">{reply}</td>
        </tr>"""
    return rows

def generate_html(posts_data, summary, archive_dates=None, is_archive_page=False):
    now_kst = datetime.now(KST)
    # UPDATE 표기는 '수집 시각'을 쓴다. 백필·재생성 때 생성 시각이 찍혀
    # 실제 데이터 시점과 어긋나는 것을 막는다. (없으면 현재 시각)
    try:
        collected_dt = datetime.fromisoformat(posts_data["collected_at"])
    except (KeyError, ValueError):
        collected_dt = now_kst
    collected_at_raw = collected_dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    collected_at = collected_dt.strftime("%Y년 %m월 %d일 %H:%M")
    date_raw = posts_data.get("date", now_kst.strftime("%Y-%m-%d"))
    try:
        date = datetime.strptime(date_raw, "%Y-%m-%d").strftime("%Y년 %m월 %d일")
    except ValueError:
        date = date_raw

    dc_info      = posts_data.get("dcinside", {})
    theqoo_info  = posts_data.get("theqoo",   {})
    newduck_info = posts_data.get("newduck",  {})
    instiz_info  = posts_data.get("instiz",   {})

    dc_total      = dc_info.get("total", 0)
    theqoo_total  = theqoo_info.get("total", 0)
    newduck_total = newduck_info.get("total", 0)
    instiz_total  = instiz_info.get("total", 0)

    dc_posts      = dc_info.get("posts", [])
    theqoo_posts  = theqoo_info.get("posts", [])
    newduck_posts = newduck_info.get("posts", [])
    instiz_posts  = instiz_info.get("posts", [])

    # 요약은 LLM 출력이라 키 누락·특수문자 가능성이 있어 방어적으로 다룬다.
    issues      = summary.get("issues") or []
    overall_mood = escape(summary.get("overall_mood", ""))

    issue_cards = ""
    for issue in issues:
        keywords_data = escape(",".join(issue.get("keywords", [])), quote=True)
        chips = source_chips(issue.get("sources", []))
        issue_cards += f"""
        <div class="issue-card" data-keywords="{keywords_data}">
          <div class="source-chips">{chips}</div>
          <h3 class="issue-title">{escape(issue.get('title', ''))}</h3>
          <p class="issue-summary">{escape(issue.get('summary', ''))}</p>
        </div>"""

    # 요약이 비었을 때(예: API 크레딧 소진으로 요약 생략) 빈 그리드 대신 안내를 보여준다.
    if not issue_cards:
        issue_cards = """
        <div class="issue-card">
          <p class="issue-summary">오늘은 AI 이슈 요약을 생성하지 못했습니다. 아래 커뮤니티별 인기글을 확인해 주세요.</p>
        </div>"""

    dc_rows      = render_post_table(dc_posts)
    theqoo_rows  = render_post_table(theqoo_posts)
    newduck_rows = render_post_table(newduck_posts)
    instiz_rows  = render_post_table(instiz_posts)

    archive_nav = ""
    if is_archive_page or archive_dates:
        if is_archive_page:
            today_val = "../index.html"
            date_prefix = ""
            today_selected = ""
        else:
            today_val = ""
            date_prefix = "archive/"
            today_selected = " selected"

        today_opt = f'      <option value="{today_val}"{today_selected}>LATEST</option>'
        date_opts = ""
        for d in (archive_dates or []):
            sel = " selected" if (is_archive_page and d == date_raw) else ""
            date_opts += f'\n      <option value="{date_prefix}{d}.html"{sel}>{d}</option>'

        archive_nav = f'''
  <div class="archive-nav">
    <select id="archive-sel">
{today_opt}{date_opts}
    </select>
  </div>'''

    # index는 루트, 아카이브는 하위폴더라 CSS 경로 접두사가 다르다.
    css_href = "../style.css" if is_archive_page else "style.css"
    dates_src = "dates.js" if is_archive_page else "archive/dates.js"
    dates_prefix = "" if is_archive_page else "archive/"
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DAILY PLAVE</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
  <link rel="stylesheet" href="{css_href}">
</head>
<body>

<div class="hero">
  <h1>DAILY PLAVE</h1>
  <div class="hero-badge">{date} · 디시인사이드 {dc_total}개 · 더쿠 {theqoo_total}개 · 뉴덕 {newduck_total}개 · 인스티즈 {instiz_total}개</div>
  <div class="mood-bar">
    <strong>DAILY RECAP · </strong>{overall_mood}
  </div>
{archive_nav}
</div>

<div class="container">

  <div class="section-title">이슈 요약</div>
  <div class="issues-grid">
    {issue_cards}
  </div>

  <div class="section-title">커뮤니티별 인기글 TOP 15</div>
  <div class="tables-grid">

    <div class="table-block">
      <div class="table-header dc">💙 디시인사이드</div>
      <table class="posts-table">
        <thead><tr>
          <th class="rank">#</th><th>제목</th><th class="stat">조회</th><th class="stat">댓글</th>
        </tr></thead>
        <tbody>{dc_rows}</tbody>
      </table>
    </div>

    <div class="table-block">
      <div class="table-header theqoo">💜 더쿠</div>
      <table class="posts-table">
        <thead><tr>
          <th class="rank">#</th><th>제목</th><th class="stat">조회</th><th class="stat">댓글</th>
        </tr></thead>
        <tbody>{theqoo_rows}</tbody>
      </table>
    </div>

    <div class="table-block">
      <div class="table-header newduck">🩷 뉴덕</div>
      <table class="posts-table">
        <thead><tr>
          <th class="rank">#</th><th>제목</th><th class="stat">조회</th><th class="stat">댓글</th>
        </tr></thead>
        <tbody>{newduck_rows}</tbody>
      </table>
    </div>

    <div class="table-block">
      <div class="table-header instiz">❤️ 인스티즈</div>
      <table class="posts-table">
        <thead><tr>
          <th class="rank">#</th><th>제목</th><th class="stat">조회</th><th class="stat">댓글</th>
        </tr></thead>
        <tbody>{instiz_rows}</tbody>
      </table>
    </div>

  </div>
</div>

<footer>
  <span class="hero-badge" style="margin-bottom:0">UPDATE <time id="update-time" datetime="{collected_at_raw}">{collected_at}</time><span id="time-ago"></span></span>
</footer>

<button id="top-btn" aria-label="맨 위로">🖤</button>

<script src="{dates_src}"></script>
<script>
  const STORAGE_KEY = 'plave_read_posts';

  function getReadSet() {{
    try {{ return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')); }}
    catch {{ return new Set(); }}
  }}

  function saveReadSet(set) {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  }}

  document.addEventListener('DOMContentLoaded', function () {{

    /* ── 읽은 글 표시 ── */
    const readSet = getReadSet();
    document.querySelectorAll('.post-link').forEach(function (a) {{
      const url = a.href;
      const row = a.closest('tr');
      if (readSet.has(url)) row.classList.add('read');
      a.addEventListener('click', function () {{
        readSet.add(url);
        saveReadSet(readSet);
        row.classList.add('read');
      }});
    }});

    /* ── 상대 시간 ── */
    const timeEl  = document.getElementById('update-time');
    const agoEl   = document.getElementById('time-ago');
    if (timeEl && agoEl) {{
      const diff = Math.round((Date.now() - new Date(timeEl.getAttribute('datetime')).getTime()) / 60000);
      let label;
      if      (diff < 1)    label = '방금 전';
      else if (diff < 60)   label = diff + '분 전';
      else if (diff < 1440) label = Math.round(diff / 60) + '시간 전';
      else                  label = Math.round(diff / 1440) + '일 전';
      agoEl.textContent = ' (' + label + ')';
    }}

    /* ── 맨 위로 버튼 ── */
    const topBtn = document.getElementById('top-btn');
    window.addEventListener('scroll', function () {{
      topBtn.classList.toggle('visible', window.scrollY > 300);
    }});
    topBtn.addEventListener('click', function () {{
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }});

    /* ── 이슈 카드 필터링 ── */
    const allRows = Array.from(document.querySelectorAll('.posts-table tbody tr'));
    let activeCard = null;

    function applyFilter(keywords) {{
      allRows.forEach(function (row) {{
        const titleEl = row.querySelector('.post-title a');
        if (!titleEl) return;
        const text  = titleEl.textContent;
        const match = keywords.some(function (kw) {{ return text.includes(kw.trim()); }});
        row.classList.toggle('dimmed', !match);
        row.classList.toggle('match',  match);
      }});
    }}

    function resetFilter() {{
      allRows.forEach(function (row) {{
        row.classList.remove('dimmed', 'match');
      }});
    }}

    document.querySelectorAll('.issue-card').forEach(function (card) {{
      card.addEventListener('click', function () {{
        if (activeCard === card) {{
          card.classList.remove('selected');
          activeCard = null;
          resetFilter();
        }} else {{
          if (activeCard) activeCard.classList.remove('selected');
          activeCard = card;
          card.classList.add('selected');
          const keywords = (card.dataset.keywords || '').split(',').filter(Boolean);
          applyFilter(keywords);
        }}
      }});
    }});

    /* ── 아카이브 내비 ── */
    const archiveSel = document.getElementById('archive-sel');
    if (archiveSel) {{
      /* dates.js의 전체 날짜 목록으로 옵션을 보강한다 — 과거에 생성된
         페이지에서도 이후에 추가된 날짜로 이동할 수 있게. */
      if (window.ARCHIVE_DATES) {{
        const have = new Set(Array.from(archiveSel.options, function (o) {{ return o.textContent.trim(); }}));
        window.ARCHIVE_DATES.forEach(function (d) {{
          if (have.has(d)) return;
          let idx = 1;  /* 0번은 LATEST — 이후는 날짜 내림차순 유지 */
          while (idx < archiveSel.options.length && archiveSel.options[idx].textContent.trim() > d) idx++;
          archiveSel.add(new Option(d, '{dates_prefix}' + d + '.html'), idx);
        }});
      }}
      archiveSel.addEventListener('change', function () {{
        if (this.value) {{
          location.href = this.value;
        }} else {{
          location.href = 'index.html';
        }}
      }});
    }}

  }});
</script>

</body>
</html>"""

    return html

def save_html(html, path="index.html"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 페이지를 {path}에 저장했습니다.")

def save_dates_js(dates, path="archive/dates.js"):
    """전체 아카이브 날짜 목록. 모든 페이지의 드롭다운이 이 파일로 최신화된다."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.ARCHIVE_DATES = " + json.dumps(sorted(dates, reverse=True)) + ";\n")
    print(f"아카이브 날짜 목록을 {path}에 저장했습니다.")

if __name__ == "__main__":
    import glob, os
    posts_data = load_json("posts.json")
    summary    = load_json("summary.json")
    archive_files = sorted(glob.glob("archive/????-??-??.html"), reverse=True)
    archive_dates = [os.path.basename(f)[:-5] for f in archive_files]
    html = generate_html(posts_data, summary, archive_dates=archive_dates)
    save_html(html)
    print("완료! index.html을 브라우저로 열어보세요.")
