"""Validate and publish a subscription-authored summary without model API calls."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from scrape_utils import KST, SOURCES
from generate_html import generate_html


def validate_summary(summary):
    issues = summary.get('issues')
    if not isinstance(issues, list) or not 3 <= len(issues) <= 6:
        raise ValueError('Expected 3 to 6 issues')
    if not isinstance(summary.get('overall_mood'), str) or not summary['overall_mood'].strip():
        raise ValueError('Missing overall_mood')
    labels = {s[2] for s in SOURCES}
    for rank, issue in enumerate(issues, 1):
        if issue.get('rank') != rank:
            raise ValueError('Issue ranks must be sequential')
        for key in ('title', 'summary'):
            if not isinstance(issue.get(key), str) or not issue[key].strip():
                raise ValueError('Missing ' + key)
        if issue.get('hot_level') not in ('hot', 'warm', 'normal'):
            raise ValueError('Invalid hot_level')
        if not isinstance(issue.get('keywords'), list) or not issue['keywords'] or not all(isinstance(x,str) and x for x in issue['keywords']):
            raise ValueError('Invalid keywords')
        if not isinstance(issue.get('sources'), list) or not issue['sources'] or not set(issue['sources']) <= labels:
            raise ValueError('Invalid sources')


def status(root=Path('.'), now=None):
    now = now or datetime.now(KST)
    today = now.date().isoformat()
    candidates = []
    for path in sorted((root / 'archive/data').glob('????-??-??.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        meta = data.get('summary_meta', {})
        if meta.get('completed_on_kst') == today and data.get('summary', {}).get('issues'):
            return {'action': 'skip', 'reason': 'already_completed_today', 'date': data['date']}
        if data['date'] < today:
            candidates.append(data)
    if candidates:
        latest = candidates[-1]
        if not latest.get('summary_meta') and all(latest.get(k, {}).get('complete') and latest.get(k, {}).get('posts') for k, *_ in SOURCES):
            return {'action': 'summarize', 'date': latest['date']}
    return {'action': 'skip', 'reason': 'no_complete_unprocessed_archive'}


def apply_summary(day, summary, root=Path('.'), now=None):
    validate_summary(summary)
    now = now or datetime.now(KST)
    path = root / 'archive/data' / (day + '.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['date'] != day:
        raise ValueError('Archive date mismatch')
    data['summary'] = summary
    data['summary_sources'] = sorted(k for k, *_ in SOURCES if data.get(k, {}).get('posts'))
    data['summary_meta'] = {'provider': 'codex_subscription', 'completed_on_kst': now.date().isoformat(),
                            'generated_at': now.isoformat(), 'basis': 'post_titles_and_engagement'}
    dates = sorted((p.stem for p in (root / 'archive').glob('????-??-??.html')), reverse=True)
    archive_html = generate_html(data, summary, archive_dates=dates, is_archive_page=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8', newline='')
    (root / 'archive' / (day + '.html')).write_text(archive_html, encoding='utf-8', newline='')
    if day == dates[0]:
        (root / 'index.html').write_text(generate_html(data, summary, archive_dates=dates[1:]), encoding='utf-8', newline='')
    from archive_health import LocalSnapshot, validate_snapshot
    validate_snapshot(LocalSnapshot(root), day)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'apply'))
    parser.add_argument('--date')
    parser.add_argument('--summary-file')
    args = parser.parse_args()
    if args.action == 'status':
        print(json.dumps(status(), ensure_ascii=False))
    else:
        if not args.date or not args.summary_file:
            parser.error('apply requires --date and --summary-file')
        apply_summary(args.date, json.loads(Path(args.summary_file).read_text(encoding='utf-8-sig')))
        print('Summary and pages validated:', args.date)

if __name__ == '__main__':
    main()
