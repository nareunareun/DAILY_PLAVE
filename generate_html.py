import json
from datetime import datetime, timezone, timedelta

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
        label = label_map.get(s, s)
        chips.append(f'<span class="source-chip {cls}">{label}</span>')
    return "".join(chips)

def render_post_table(posts, top=15):
    rows = ""
    for i, p in enumerate(posts[:top], 1):
        link  = p.get("link", "#")
        title = p["title"]
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
    collected_at_raw = now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    collected_at = now_kst.strftime("%Y년 %m월 %d일 %H:%M")
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

    issues      = summary["issues"]
    overall_mood = summary["overall_mood"]

    issue_cards = ""
    for issue in issues:
        keywords_data = ",".join(issue["keywords"])
        chips = source_chips(issue.get("sources", []))
        issue_cards += f"""
        <div class="issue-card" data-keywords="{keywords_data}">
          <div class="source-chips">{chips}</div>
          <h3 class="issue-title">{issue['title']}</h3>
          <p class="issue-summary">{issue['summary']}</p>
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

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DAILY PLAVE</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
  <style>
    :root {{
      --bg:             #f7f4ff;
      --surface:        #ffffff;
      --surface-2:      #f0ebff;
      --border:         #e2d8f5;
      --border-light:   #ede8fa;
      --text-primary:   #2e2055;
      --text-secondary: #7a6b9e;
      --text-muted:     #b4a9cc;
      --accent:         #9575d0;
      --accent-deep:    #7c5cbf;
      --accent-light:   #c9b6ed;
      --accent-bg:      #ede8ff;
      --read-opacity:   0.38;

      /* 커뮤니티 파스텔 색상 */
      --dc-bg:      #dbeafe; --dc-text:      #1d4ed8;
      --theqoo-bg:  #ede9fe; --theqoo-text:  #6d28d9;
      --newduck-bg: #fce7f3; --newduck-text: #9d174d;
      --instiz-bg:  #fee2e2; --instiz-text:  #b91c1c;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Pretendard', sans-serif;
      background: var(--bg);
      color: var(--text-primary);
      min-height: 100vh;
      line-height: 1.6;
    }}

    /* ── Hero ── */
    .hero {{
      background: linear-gradient(150deg, #ece8ff 0%, #f8f2ff 50%, #fdf0ff 100%);
      padding: 44px 20px 36px;
      text-align: center;
      border-bottom: 1px solid var(--border);
    }}

    .hero-badge {{
      display: inline-block;
      background: var(--accent-bg);
      color: var(--accent-deep);
      font-size: 12px;
      font-weight: 600;
      padding: 5px 14px;
      border-radius: 20px;
      letter-spacing: 0.3px;
      border: 1px solid var(--accent-light);
    }}

    h1 {{
      font-size: clamp(26px, 6vw, 38px);
      font-weight: 800;
      letter-spacing: -1px;
      margin-bottom: 12px;
      background: linear-gradient(90deg, var(--accent-deep), #b07ee8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}

    .mood-bar {{
      margin: 18px auto 0;
      max-width: 580px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 11px 18px;
      font-size: 13.5px;
      color: var(--text-secondary);
      box-shadow: 0 1px 6px rgba(149,117,208,0.08);
    }}

    .mood-bar strong {{ color: var(--accent-deep); font-weight: 700; }}

    /* ── Layout ── */
    .container {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 36px 16px 36px;
    }}

    .section-title {{
      font-size: 13.5px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 18px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .section-title::after {{
      content: '';
      flex: 1;
      height: 1px;
      background: var(--border);
    }}

    /* ── Issue cards ── */
    .issues-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
      margin-bottom: 36px;
    }}

    @media (max-width: 760px) {{ .issues-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    @media (max-width: 480px) {{ .issues-grid {{ grid-template-columns: 1fr; }} }}

    .issue-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s;
      box-shadow: 0 1px 4px rgba(149,117,208,0.07);
    }}

    .issue-card:hover {{
      box-shadow: 0 4px 16px rgba(149,117,208,0.15);
      border-color: var(--accent-light);
      transform: translateY(-2px);
    }}

    .source-chips {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}

    .source-chip {{
      font-size: 10px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 10px;
      letter-spacing: 0.1px;
    }}

    .chip-dc      {{ background: var(--dc-bg);      color: var(--dc-text); }}
    .chip-theqoo  {{ background: var(--theqoo-bg);  color: var(--theqoo-text); }}
    .chip-newduck {{ background: var(--newduck-bg); color: var(--newduck-text); }}
    .chip-instiz  {{ background: var(--instiz-bg);  color: var(--instiz-text); }}

    .issue-title {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 8px;
      margin-top: 2px;
      line-height: 1.45;
    }}

    .issue-summary {{
      font-size: 13px;
      color: var(--text-secondary);
      line-height: 1.7;
    }}

    /* ── Tables ── */
    .tables-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 18px;
      margin-bottom: 0;
    }}

    @media (max-width: 560px) {{ .tables-grid {{ grid-template-columns: 1fr; }} }}

    .table-block {{ min-width: 0; }}

    .table-header {{
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 8px;
      padding: 7px 12px;
      border-radius: 10px;
    }}

    .table-header.dc      {{ background: var(--dc-bg);      color: var(--dc-text); }}
    .table-header.theqoo  {{ background: var(--theqoo-bg);  color: var(--theqoo-text); }}
    .table-header.newduck {{ background: var(--newduck-bg); color: var(--newduck-text); }}
    .table-header.instiz  {{ background: var(--instiz-bg);  color: var(--instiz-text); }}

    .posts-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    .posts-table thead th {{
      padding: 7px 8px;
      text-align: left;
      color: var(--text-muted);
      border-bottom: 2px solid var(--border);
      font-weight: 600;
      white-space: nowrap;
    }}

    .posts-table tbody td {{
      padding: 8px 8px;
      border-bottom: 1px solid var(--border-light);
      vertical-align: middle;
    }}

    .posts-table tbody tr:last-child td {{ border-bottom: none; }}
    .posts-table tbody tr:hover {{ background: var(--surface-2); }}

    .rank {{
      color: var(--text-muted);
      width: 24px;
      text-align: center;
      font-weight: 600;
    }}

    .stat {{
      color: var(--text-muted);
      width: 42px;
      text-align: right;
      white-space: nowrap;
    }}

    .post-title {{ max-width: 0; }}

    .post-title a {{
      color: var(--text-primary);
      text-decoration: none;
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      transition: color 0.15s;
    }}

    .post-title a:hover {{ color: var(--accent-deep); text-decoration: underline; }}

    /* 읽은 글 */
    .posts-table tbody tr.read td {{ opacity: var(--read-opacity); }}
    .posts-table tbody tr.read .post-title a {{ text-decoration: line-through; }}
    .posts-table tbody tr.read:hover td {{ opacity: 0.6; }}

    /* ── Mobile ── */
    @media (max-width: 480px) {{
      .hero {{ padding: 32px 16px 24px; }}
      .issues-grid {{ grid-template-columns: 1fr; }}
      .container {{ padding: 24px 12px 40px; }}
    }}

    /* ── Footer ── */
    footer {{
      background: linear-gradient(150deg, #ece8ff 0%, #f8f2ff 50%, #fdf0ff 100%);
      text-align: center;
      padding: 36px 16px 56px;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--border);
    }}

    /* ── 상대 시간 ── */
    #time-ago {{
      color: var(--text-muted);
      font-size: 12px;
    }}

    /* ── 맨 위로 버튼 ── */
    #top-btn {{
      position: fixed;
      bottom: 28px;
      left: 50%;
      transform: translateX(-50%);
      background: none;
      border: none;
      padding: 0;
      font-size: 15px;
      cursor: pointer;
      transition: opacity 0.25s;
      opacity: 0;
      pointer-events: none;
      z-index: 100;
    }}

    #top-btn.visible {{
      opacity: 1;
      pointer-events: auto;
    }}

    /* ── 이슈 카드 필터링 ── */
    .issue-card {{
      cursor: pointer;
    }}

    .issue-card.selected {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(149,117,208,0.18), 0 4px 16px rgba(149,117,208,0.15);
    }}

    .posts-table tbody tr.dimmed td {{
      opacity: 0.15;
    }}

    .posts-table tbody tr.match .post-title a {{
      color: var(--accent-deep);
      font-weight: 700;
    }}

    /* ── 아카이브 내비 ── */
    .archive-nav {{
      margin: 16px auto 0;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
    }}

    .archive-nav select {{
      background: var(--surface);
      color: var(--text-secondary);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 6px 14px;
      font-size: 12px;
      cursor: pointer;
      outline: none;
      font-family: inherit;
      text-align: center;
    }}

    .archive-nav select option {{
      direction: ltr;
      text-align: left;
    }}

  </style>
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

if __name__ == "__main__":
    import glob, os
    posts_data = load_json("posts.json")
    summary    = load_json("summary.json")
    archive_files = sorted(glob.glob("archive/????-??-??.html"), reverse=True)
    archive_dates = [os.path.basename(f)[:-5] for f in archive_files]
    html = generate_html(posts_data, summary, archive_dates=archive_dates)
    save_html(html)
    print("완료! index.html을 브라우저로 열어보세요.")
