"""Offline regression tests: no live scraping, AI requests, or project output writes."""
import contextlib
from datetime import date
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import requests

import run
import scrape_utils
import scraper_instiz as instiz
import summarizer
from generate_html import generate_html

TODAY = date(2026, 10, 13)
TARGET = date(2026, 10, 12)


def row(number, when, desktop=False, notice=False):
    body = f'<a href="https://www.instiz.net/name_enter/{number}"><span class="sbj">sample &lt;post&gt;</span></a>'
    if not desktop:
        body += f'<div class="list_subtitle"><div class="listno regdate">{when} <span>l</span> 조회 123</div></div>'
    cells = f'<td class="listno">{when}</td><td class="listno">123</td>' if desktop else ''
    flag = '<span class="texthead_notice">notice</span>' if notice else ''
    return f'<tr id="list{number}"><td class="listsubject">{flag}{body}</td>{cells}</tr>'


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.net = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden in offline tests'))
        self.net.start()
        self.addCleanup(self.net.stop)
        self.clock = patch.object(instiz, 'classify_date_text', side_effect=lambda text, target: scrape_utils.classify_date_text(text, target, today=TODAY))
        self.clock.start()
        self.addCleanup(self.clock.stop)


class DateParsingTests(OfflineTest):
    def test_date_extraction_formats(self):
        for raw, expected in [('1:04 l 조회 423', '1:04'), ('0:45 l 조회 311', '0:45'), ('10:26 l 조회 135', '10:26'), ('10.12 19:48', '10.12'), ('26.10.12 19:48', '26.10.12'), ('2026.10.12 19:48', '2026.10.12'), ('1.2 9:00', '1.2'), ('조회 123', '')]:
            with self.subTest(raw=raw):
                self.assertEqual(instiz.extract_date_text(raw), expected)

    def test_single_digit_hour_is_recognized_as_today(self):
        for hour in ('0:45', '1:04', '9:59'):
            with self.subTest(hour=hour):
                posts, older, links, dated = instiz.parse_posts(row(1, hour), TARGET, set())
                self.assertEqual((posts, older, links, dated), ([], False, 1, 1))

    def test_target_date_combined_with_time(self):
        for desktop in (False, True):
            with self.subTest(desktop=desktop):
                posts, older, _, dated = instiz.parse_posts(row(1, '10.12 19:48', desktop), TARGET, set())
                self.assertEqual(len(posts), 1)
                self.assertFalse(older)
                self.assertEqual(dated, 1)
                self.assertEqual(posts[0]['title'], 'sample <post>')

    def test_explicit_year_and_old_date_stop(self):
        for raw in ('26.10.11 9:00', '2026.10.11 9:00'):
            with self.subTest(raw=raw):
                posts, older, _, dated = instiz.parse_posts(row(1, raw, True), TARGET, set())
                self.assertEqual((posts, older, dated), ([], True, 1))

    def test_old_notice_does_not_end_collection(self):
        posts, older, _, dated = instiz.parse_posts(row(1, '10.11 19:48', True, True), TARGET, set())
        self.assertEqual((posts, older, dated), ([], False, 1))

    def test_duplicate_links_are_not_collected_twice(self):
        seen = set()
        first = instiz.parse_posts(row(1, '10.12'), TARGET, seen)
        second = instiz.parse_posts(row(1, '10.12'), TARGET, seen)
        self.assertEqual(len(first[0]), 1)
        self.assertEqual(second[0], [])

    def test_pagination_passes_three_single_digit_hour_pages(self):
        pages = [row(1, '9:30'), row(2, '8:30'), row(3, '0:45'), row(4, '10.12 23:59'), row(5, '10.11 23:59')]
        with patch.object(instiz, '_make_scraper'), patch.object(instiz, 'fetch_page', side_effect=pages) as fetch, patch.object(instiz.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            posts, target, complete = instiz.collect_posts('2026-10-12')
        self.assertEqual((len(posts), target, complete, fetch.call_count), (1, '2026-10-12', True, 5))

    def test_unknown_date_guard_remains(self):
        pages = [row(n, 'unknown') for n in range(1, 4)]
        with patch.object(instiz, '_make_scraper'), patch.object(instiz, 'fetch_page', side_effect=pages) as fetch, patch.object(instiz.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            posts, _, complete = instiz.collect_posts('2026-10-12')
        self.assertEqual((posts, complete, fetch.call_count), ([], False, 3))


class AccessRestrictionTests(OfflineTest):
    def test_403_is_not_retried_or_bypassed(self):
        response = requests.Response()
        response.status_code = 403
        response.url = instiz.BOARD_URL
        client = Mock()
        client.get.return_value = response
        with patch.object(instiz.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(requests.HTTPError):
                instiz.fetch_page(client)
        self.assertEqual(client.get.call_count, 1)
        sleep.assert_not_called()
        self.assertIn('HTTP 403', output.getvalue())

    def test_transient_server_error_can_retry(self):
        bad = requests.Response()
        bad.status_code = 500
        good = requests.Response()
        good.status_code = 200
        good._content = b'listing'
        client = Mock()
        client.get.side_effect = [bad, good]
        with patch.object(instiz.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(instiz.fetch_page(client), 'listing')
        self.assertEqual(client.get.call_count, 2)

    def test_403_collection_stays_incomplete(self):
        response = requests.Response()
        response.status_code = 403
        error = requests.HTTPError('Forbidden', response=response)
        with patch.object(instiz, '_make_scraper'), patch.object(instiz, 'fetch_page', side_effect=error), contextlib.redirect_stdout(io.StringIO()):
            posts, _, complete = instiz.collect_posts('2026-10-12')
        self.assertEqual((posts, complete), ([], False))


class PipelineTests(OfflineTest):
    def sample_post(self):
        return {'title': 'offline sample <post>', 'link': 'https://example.invalid/post', 'view_count': 123, 'reply_count': 5, 'recommend_count': 2}

    def exercise(self, directory, missing=False, existing=None, ai_fails=False):
        modules = {}
        for key, _, _, module_name in scrape_utils.SOURCES:
            posts = [] if missing and key == 'instiz' else [self.sample_post()]
            modules[module_name] = types.SimpleNamespace(collect_posts=Mock(return_value=(posts, '2026-10-12', bool(posts))))
        old = Path.cwd()
        try:
            os.chdir(directory)
            if existing is not None:
                Path('archive/data').mkdir(parents=True, exist_ok=True)
                Path('archive/data/2026-10-12.json').write_text(json.dumps(existing), encoding='utf-8')
            summary = {'issues': [{'title': 'offline issue', 'summary': 'offline summary', 'sources': ['인스티즈']}], 'overall_mood': 'offline mood'}
            with patch.dict('sys.modules', modules), patch('sys.argv', ['run', '--date', '2026-10-12']), patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'unused-test-placeholder'}), patch.object(summarizer, 'summarize', side_effect=RuntimeError('credit balance too low') if ai_fails else None, return_value=summary), contextlib.redirect_stdout(io.StringIO()):
                run.main()
            return modules
        finally:
            os.chdir(old)

    def test_original_ai_client_can_generate_summary(self):
        with patch.object(summarizer, 'Anthropic') as client:
            client.return_value.messages.create.return_value.content = [types.SimpleNamespace(text='{"issues": [{"title": "ok"}], "overall_mood": "ok"}')]
            result = summarizer.summarize({'collected_at': '2026-10-13T09:00:00+09:00', 'date': '2026-10-12'})
            self.assertEqual(result['issues'][0]['title'], 'ok')
            client.return_value.messages.create.assert_called_once()

    def test_full_pipeline_survives_credit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, ai_fails=True)
            root = Path(directory)
            data = json.loads((root / 'archive/data/2026-10-12.json').read_text(encoding='utf-8'))
            html = (root / 'index.html').read_text(encoding='utf-8')
            self.assertEqual(data['summary'], run.empty_summary())
            self.assertEqual(len(data['summary_sources']), 4)
            self.assertEqual(html.count('class="posts-table"'), 4)
            self.assertIn('offline sample &lt;post&gt;', html)
            self.assertIn('class="issues-grid"', html)
            self.assertIn('AI 이슈 요약을 생성하지 못했습니다', html)

    def test_partial_page_is_saved_with_missing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, missing=True)
            root = Path(directory)
            status = json.loads((root / '.last_run_status.json').read_text(encoding='utf-8'))
            self.assertEqual(status['missing'], ['인스티즈'])
            self.assertTrue((root / 'index.html').exists())

    def test_failed_retry_does_not_overwrite_previous_page(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, missing=True)
            root = Path(directory)
            before = (root / 'index.html').read_bytes()
            with self.assertRaisesRegex(RuntimeError, '인스티즈'):
                self.exercise(directory, missing=True)
            self.assertEqual(before, (root / 'index.html').read_bytes())

    def test_already_complete_skips_collectors(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory)
            modules = self.exercise(directory)
            for module in modules.values():
                module.collect_posts.assert_not_called()

    def test_repaired_retry_only_fills_missing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, missing=True)
            modules = self.exercise(directory)
            for key, _, _, name in scrape_utils.SOURCES:
                self.assertEqual(modules[name].collect_posts.call_count, int(key == 'instiz'))
            status = json.loads((Path(directory) / '.last_run_status.json').read_text(encoding='utf-8'))
            self.assertEqual(status['missing'], [])

    def test_recharged_summary_recovers_without_rescraping(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, ai_fails=True)
            root = Path(directory)
            before = json.loads((root / 'archive/data/2026-10-12.json').read_text(encoding='utf-8'))
            modules = self.exercise(directory)
            after = json.loads((root / 'archive/data/2026-10-12.json').read_text(encoding='utf-8'))
            for module in modules.values():
                module.collect_posts.assert_not_called()
            self.assertEqual(after['collected_at'], before['collected_at'])
            self.assertTrue(after['summary']['issues'])
            self.assertIn('offline issue', (root / 'index.html').read_text(encoding='utf-8'))

    def test_repeated_credit_failure_does_not_republish(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, ai_fails=True)
            root = Path(directory)
            before_html = (root / 'index.html').read_bytes()
            before_data = (root / 'archive/data/2026-10-12.json').read_bytes()
            modules = self.exercise(directory, ai_fails=True)
            for module in modules.values():
                module.collect_posts.assert_not_called()
            self.assertEqual(before_html, (root / 'index.html').read_bytes())
            self.assertEqual(before_data, (root / 'archive/data/2026-10-12.json').read_bytes())

    def test_credit_failure_does_not_hide_missing_source_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, missing=True, ai_fails=True)
            before = (Path(directory) / 'index.html').read_bytes()
            with self.assertRaisesRegex(RuntimeError, '인스티즈'):
                self.exercise(directory, missing=True, ai_fails=True)
            self.assertEqual(before, (Path(directory) / 'index.html').read_bytes())

    def test_summary_recovery_preserves_existing_partial_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            self.exercise(directory, ai_fails=True)
            path = Path(directory) / 'archive/data/2026-10-12.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['instiz']['complete'] = False
            path.write_text(json.dumps(data), encoding='utf-8')
            self.exercise(directory, missing=True)
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(saved['instiz']['posts'], data['instiz']['posts'])
            self.assertFalse(saved['instiz']['complete'])
            self.assertTrue(saved['summary']['issues'])


if __name__ == '__main__':
    unittest.main()
