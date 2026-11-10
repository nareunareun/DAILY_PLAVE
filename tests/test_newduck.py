import unittest
from unittest.mock import patch
import scraper_newduck as s

class NewduckTests(unittest.TestCase):
    def test_browser_session(self):
        with patch.object(s.requests, 'Session') as session:
            s._make_scraper()
            session.assert_called_once_with(impersonate='chrome')

    def test_page_limit_is_incomplete(self):
        with patch.object(s, '_make_scraper'), patch.object(s, 'fetch_page', return_value=''), patch.object(s, 'parse_posts', return_value=([{'link':'sample'}], False, 20)):
            posts, _, complete = s.collect_posts('2026-11-09', max_pages=1)
            self.assertEqual(len(posts), 1)
            self.assertFalse(complete)

    def test_older_boundary_completes(self):
        with patch.object(s, '_make_scraper'), patch.object(s, 'fetch_page', return_value=''), patch.object(s, 'parse_posts', return_value=([{'link':'sample'}], True, 20)):
            self.assertTrue(s.collect_posts('2026-11-09', max_pages=1)[2])

    def test_http_failure_is_incomplete(self):
        with patch.object(s, '_make_scraper'), patch.object(s, 'get_with_retries', side_effect=RuntimeError('403')):
            self.assertEqual(s.collect_posts('2026-11-09'), ([], '2026-11-09', False))
