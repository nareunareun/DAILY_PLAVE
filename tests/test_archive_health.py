"""Target-day notification policy tests; all network calls are blocked or mocked."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import archive_health as health
from generate_html import generate_html
from scrape_utils import SOURCES

TARGET = '2026-10-12'
SITE = 'https://nareunareun.github.io/DAILY_PLAVE/'


def day(target=TARGET, partial=False, empty=False):
    data = {'date': target, 'collected_at': '2026-10-13T09:00:00+09:00', 'summary': {'issues': [], 'overall_mood': '요약 생략'}}
    for key, *_ in SOURCES:
        posts = [] if empty or partial and key == 'instiz' else [{'title': 'sample <post>', 'link': 'https://example.invalid/post', 'view_count': 2, 'reply_count': 1}]
        data[key] = {'total': len(posts), 'posts': posts, 'complete': bool(posts)}
    return data


class Snapshot:
    def __init__(self, data=None):
        self.files = {}
        if data:
            self.add(data)

    def add(self, data):
        target = data['date']
        self.files[f'archive/data/{target}.json'] = json.dumps(data, ensure_ascii=False)
        dates = sorted([p.split('/')[1][:-5] for p in self.files if p.startswith('archive/') and p.endswith('.html')] + [target], reverse=True)
        self.files[f'archive/{target}.html'] = generate_html(data, data['summary'], archive_dates=dates, is_archive_page=True)
        self.files['index.html'] = generate_html(data, data['summary'], archive_dates=[d for d in dates if d != target])

    def read(self, path):
        if path not in self.files:
            raise health.ArchiveError('missing remote object')
        return self.files[path]

    def paths(self):
        return list(self.files)


class HealthTests(unittest.TestCase):
    def setUp(self):
        net = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        net.start()
        self.addCleanup(net.stop)

    def assert_invalid(self, snapshot):
        with self.assertRaises(health.ArchiveError):
            health.validate_snapshot(snapshot, TARGET)

    def test_valid_day(self):
        result = health.validate_snapshot(Snapshot(day()), TARGET)
        self.assertEqual(sum(result.counts.values()), 4)
        self.assertEqual(result.missing, [])

    def test_partial_day_is_usable(self):
        result = health.validate_snapshot(Snapshot(day(partial=True)), TARGET)
        self.assertEqual(result.missing, ['인스티즈'])

    def test_no_day_is_critical(self):
        self.assert_invalid(Snapshot())

    def test_empty_day_is_critical_even_with_pages(self):
        self.assert_invalid(Snapshot(day(empty=True)))

    def test_wrong_day_does_not_pass(self):
        self.assert_invalid(Snapshot(day('2026-10-11')))

    def test_data_date_mismatch(self):
        snap = Snapshot(day())
        wrong = day('2026-10-11')
        snap.files[f'archive/data/{TARGET}.json'] = json.dumps(wrong)
        self.assert_invalid(snap)

    def test_corrupt_json(self):
        snap = Snapshot(day())
        snap.files[f'archive/data/{TARGET}.json'] = '{broken'
        self.assert_invalid(snap)

    def test_duplicate_json_key(self):
        snap = Snapshot(day())
        snap.files[f'archive/data/{TARGET}.json'] = '{"date":"2026-10-12","date":"2026-10-11"}'
        self.assert_invalid(snap)

    def test_inconsistent_counts(self):
        data = day(); data['instiz']['total'] = 5
        self.assert_invalid(Snapshot(data))

    def test_invalid_post(self):
        snap = Snapshot(day()); data = day()
        data['instiz']['posts'][0]['title'] = ''
        snap.files[f'archive/data/{TARGET}.json'] = json.dumps(data)
        self.assert_invalid(snap)

    def test_invalid_number(self):
        snap = Snapshot(day()); data = day()
        data['instiz']['posts'][0]['score'] = float('nan')
        snap.files[f'archive/data/{TARGET}.json'] = json.dumps(data)
        self.assert_invalid(snap)

    def test_missing_page(self):
        snap = Snapshot(day()); del snap.files[f'archive/{TARGET}.html']
        self.assert_invalid(snap)

    def test_data_page_mismatch(self):
        snap = Snapshot(day())
        snap.files[f'archive/{TARGET}.html'] = snap.files[f'archive/{TARGET}.html'].replace('sample &lt;post&gt;', 'wrong post', 1)
        self.assert_invalid(snap)

    def test_truncated_page(self):
        snap = Snapshot(day()); snap.files[f'archive/{TARGET}.html'] = snap.files[f'archive/{TARGET}.html'][:-20]
        self.assert_invalid(snap)

    def test_old_home_page_is_not_accepted(self):
        snap = Snapshot(day()); older = day('2026-10-11')
        snap.files['index.html'] = generate_html(older, older['summary'])
        self.assert_invalid(snap)

    def test_target_can_be_older_than_latest_valid_day(self):
        snap = Snapshot(day()); snap.add(day('2026-10-13'))
        self.assertEqual(health.validate_snapshot(snap, TARGET).target, TARGET)

    def test_line_ending_conversion_is_not_corruption(self):
        snap = Snapshot(day())
        for path in list(snap.files):
            if path.endswith('.html'):
                snap.files[path] = snap.files[path].replace('\n', '\r\n')
        health.validate_snapshot(snap, TARGET)

    def verify(self, snap, fetch=None, attempts=1, wait=None):
        fetch = fetch or (lambda url: snap.read(url.removeprefix(SITE) or 'index.html'))
        return health.verify_remote('.', TARGET, SITE, attempts=attempts, delay=0, snapshot_factory=lambda _: snap, fetch=fetch, wait=wait or Mock())

    def test_published_remote_pair_is_required(self):
        self.assertEqual(self.verify(Snapshot(day())).target, TARGET)

    def test_local_success_cannot_hide_failed_first_push(self):
        health.validate_snapshot(Snapshot(day()), TARGET)
        with self.assertRaises(health.ArchiveError):
            self.verify(Snapshot())

    def test_retry_collection_and_push_failures_warn_if_remote_is_valid(self):
        result = self.verify(Snapshot(day(partial=True)))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            health.finish(result, ['failure', 'failure', 'success', 'failure'])
        self.assertIn('::warning::', output.getvalue())
        self.assertNotIn('::error::', output.getvalue())

    def test_ai_missing_is_warning_not_critical(self):
        result = self.verify(Snapshot(day()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            health.finish(result, ['success'] * 4)
        self.assertIn('AI 요약 없음', output.getvalue())
        self.assertNotIn('::error::', output.getvalue())

    def test_broken_candidate_cannot_replace_healthy_remote(self):
        broken = Snapshot(day()); broken.files[f'archive/{TARGET}.html'] = ''
        self.assert_invalid(broken)
        self.assertEqual(self.verify(Snapshot(day())).target, TARGET)

    def test_publication_pending_can_recover(self):
        snap = Snapshot(day()); wait = Mock()
        fetch = Mock(side_effect=[health.ArchiveError('pending'), snap.files[f'archive/{TARGET}.html'], snap.files['index.html']])
        with contextlib.redirect_stdout(io.StringIO()):
            self.verify(snap, fetch=fetch, attempts=2, wait=wait)
        wait.assert_called_once()

    def test_publication_never_arrives_is_critical(self):
        with self.assertRaises(health.ArchiveError):
            self.verify(Snapshot(day()), fetch=lambda _: 'old or empty page', attempts=2)

    def test_remote_verification_unavailable_is_not_success(self):
        with self.assertRaises(health.ArchiveError):
            health.verify_remote('.', TARGET, SITE, snapshot_factory=Mock(side_effect=health.ArchiveError('remote unavailable')))

    def test_critical_cli_returns_nonzero(self):
        with patch('sys.argv', ['health', 'remote', '--date', TARGET]), patch.object(health, 'verify_remote', side_effect=health.ArchiveError('missing archive')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(health.main(), 1)
        self.assertIn('::error::', output.getvalue())

    def test_healthy_remote_cli_succeeds_despite_collection_failure(self):
        result = self.verify(Snapshot(day(partial=True)))
        with patch('sys.argv', ['health', 'remote', '--date', TARGET, '--outcome', 'failure']), patch.object(health, 'verify_remote', return_value=result), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(health.main(), 0)
        self.assertIn('::warning::', output.getvalue())

    def test_optional_summary_write_does_not_change_health(self):
        result = self.verify(Snapshot(day()))
        with patch.dict(health.os.environ, {'GITHUB_STEP_SUMMARY': 'unwritable'}), patch('builtins.open', side_effect=OSError('read only')), contextlib.redirect_stdout(io.StringIO()) as output:
            health.finish(result, ['success'] * 4)
        self.assertIn('::warning::', output.getvalue())
        self.assertNotIn('::error::', output.getvalue())

    def test_workflow_uses_final_gate_and_does_not_send_gmail(self):
        import yaml
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/daily_update.yml').read_text(encoding='utf-8')
        workflow = yaml.safe_load(text)
        steps = workflow['jobs']['update']['steps']
        by_id = {step.get('id'): step for step in steps if 'id' in step}
        self.assertTrue(by_id['collect']['continue-on-error'])
        self.assertTrue(by_id['candidate']['continue-on-error'])
        self.assertTrue(by_id['publish']['continue-on-error'])
        self.assertEqual(by_id['publish']['if'], "steps.candidate.outcome == 'success'")
        self.assertIn('git pull --rebase origin main && python archive_health.py candidate', by_id['publish']['run'])
        self.assertEqual(steps[-1]['if'], 'always()')
        self.assertNotIn('continue-on-error', steps[-1])
        self.assertIn('archive_health.py remote', steps[-1]['run'])
        self.assertIn('ANTHROPIC_API_KEY', by_id['collect']['env'])
        self.assertNotIn('GMAIL_', text)
        self.assertNotIn('smtplib', text)
        self.assertEqual(len(workflow.get('on', workflow.get(True))['schedule']), 7)


if __name__ == '__main__':
    unittest.main()
