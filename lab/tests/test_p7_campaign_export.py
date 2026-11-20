from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

EXPORT_PATH = Path(__file__).resolve().parents[2] / "scripts/p7-p709-campaign-export.py"
_spec = importlib.util.spec_from_file_location("p7_p709_campaign_export", EXPORT_PATH)
export_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_module)


def _queue(path: Path, rows: list[tuple]) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE runs (run_id TEXT, state TEXT)")
    con.execute("CREATE TABLE jobs (run_id TEXT, unit_id TEXT, registry_entry_id TEXT, case_id TEXT, stage TEXT, "
                "status TEXT, attempts_used INTEGER, result_json TEXT)")
    con.execute("INSERT INTO runs VALUES ('r1', 'completed')")
    con.executemany("INSERT INTO jobs VALUES ('r1', ?, ?, ?, ?, ?, ?, ?)", rows)
    con.commit()
    con.close()


DIFF = json.dumps({"reason_code": None, "comparison": {"category": "equivalent", "call_signals": {"native_first": {}}},
                   "contracts": {"C7": {"status": "passed", "evidence": {"x": 1}}},
                   "worker_runs": [{"cleanup_confirmed": True, "stdout_sha256": "a"}] * 3})
INV = json.dumps({"inventory": {"load": {"command_descriptors": [{"command_id": "b", "description": "secret"},
                                                                  {"command_id": "a"}], "commands_truncated": False}},
                  "worker_runs": [{"cleanup_confirmed": True}]})


class CampaignExportTests(unittest.TestCase):
    def test_projection_keeps_identities_and_labels_but_no_plugin_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "q.sqlite3"
            _queue(queue, [("u1", "ab-1", "cmd", "differential", "passed", 1, DIFF),
                           ("u2", "ab-2", "inv", "inventory", "passed", 1, INV),
                           ("u3", "ab-2", "later", "differential", "failed", 1,
                            json.dumps({"status": "failed", "reason_code": "worker_spec_invalid"}))])
            report = export_module.export(str(queue), {"run_id": "r1", "jobs": [{"unit_id": "u1"}, {"unit_id": "u2"}]})
        jobs = {job["unit_id"]: job for job in report["jobs"]}
        self.assertEqual(jobs["u1"]["comparison"], "equivalent")
        self.assertEqual(jobs["u1"]["c7"], "passed")
        self.assertTrue(jobs["u1"]["cleanup_confirmed"])
        self.assertEqual(jobs["u2"]["command_ids"], ["a", "b"])
        self.assertIsNone(jobs["u3"]["cleanup_confirmed"])
        self.assertEqual(jobs["u3"]["reason_code"], "worker_spec_invalid")
        self.assertEqual((jobs["u1"]["planned"], jobs["u3"]["planned"]), (True, False))
        self.assertEqual(report["follow_up_jobs"], 1)
        text = json.dumps(report)
        self.assertNotIn("secret", text)
        self.assertNotIn("stdout_sha256", text)

    def test_undrained_queue_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "q.sqlite3"
            _queue(queue, [("u1", "ab-1", "cmd", "differential", "queued", 0, None)])
            with self.assertRaises(SystemExit):
                export_module.export(str(queue), {"run_id": "r1", "jobs": [{"unit_id": "u1"}]})


if __name__ == "__main__":
    unittest.main()
