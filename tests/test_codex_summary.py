import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from codex_summary import status, validate_summary
from scrape_utils import KST, SOURCES

class SummaryScheduleTests(unittest.TestCase):
    def check(self, data, now):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'archive/data').mkdir(parents=True)
            for d in data:
                (root/'archive/data'/ (d['date']+'.json')).write_text(json.dumps(d),encoding='utf-8')
            return status(root,now)

    def day(self, day, completed=None):
        d={'date':day, 'summary':{'issues':[{'title':'sample'}]}}
        d.update({k:{'complete':True,'posts':[{}]} for k,*_ in SOURCES})
        if completed: d['summary_meta']={'completed_on_kst':completed}
        return d

    def test_manual_completion_skips_scheduled_run_same_kst_day(self):
        result=self.check([self.day('2026-11-09','2026-11-10')],datetime(2026,11,10,21,tzinfo=KST))
        self.assertEqual(result['reason'],'already_completed_today')

    def test_next_day_selects_new_archive(self):
        result=self.check([self.day('2026-11-09','2026-11-10'),self.day('2026-11-10')],datetime(2026,11,11,21,tzinfo=KST))
        self.assertEqual(result,{'action':'summarize','date':'2026-11-10'})

    def test_no_new_archive_does_not_backfill_old_days(self):
        result=self.check([self.day('2026-11-08'),self.day('2026-11-09','2026-11-10')],datetime(2026,11,11,21,tzinfo=KST))
        self.assertEqual(result['action'],'skip')

    def test_incomplete_latest_archive_waits(self):
        d=self.day('2026-11-10'); d['newduck']['complete']=False
        self.assertEqual(self.check([d],datetime(2026,11,11,21,tzinfo=KST))['action'],'skip')

    def test_invalid_summary_rejected(self):
        with self.assertRaises(ValueError): validate_summary({'issues':[], 'overall_mood':'sample'})
