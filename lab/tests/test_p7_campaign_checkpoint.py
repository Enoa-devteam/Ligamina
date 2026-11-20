from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

BUILDER_PATH = Path(__file__).resolve().parents[2] / "scripts/p7-p709-campaign-checkpoint.py"
_spec = importlib.util.spec_from_file_location("p7_p709_campaign_checkpoint", BUILDER_PATH)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


class CheckpointBatchEntryTests(unittest.TestCase):
    def test_idle_call_at_the_end_of_a_drained_queue_is_not_a_job(self) -> None:
        # 2026-11-20: the final batches found the queue empty, so the executor recorded a
        # {"status": "idle", "unit_id": null} call; it is a stop marker, not a reported job.
        run = "20261120T020711Z-slot-1-pid-1-b0009"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acc = root / "outputs/acceptance"
            acc.mkdir(parents=True)

            def write(name: str, value: dict) -> str:
                path = acc / name
                data = json.dumps(value).encode("utf-8")
                path.write_bytes(data)
                import hashlib
                (acc / (name + ".sha256")).write_text(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
                return f"outputs/acceptance/{name}"

            for kind in ("linux-worker-probe", "linux-admission"):
                write(f"p7-p709-{kind}-campaign-{run}.json", {"kind": kind})
            report = write(f"p7-p709-astrbot-campaign-execution-batch-{run}.json", {
                "kind": "p7_p709_astrbot_campaign_execution_checkpoint", "run_id": "r1", "queue_counts": {},
                "calls": [
                    {"status": "finished", "unit_id": "u1", "comparison": "equivalent", "c7_status": "passed"},
                    {"status": "idle", "unit_id": None, "comparison": None, "c7_status": None},
                ],
            })
            entry, calls = builder.batch_entry(root, report, "r1")
        self.assertEqual(entry["calls"], 1)
        self.assertEqual([call["unit_id"] for call in calls], ["u1"])
        self.assertEqual(entry["idle_markers"], 1)


if __name__ == "__main__":
    unittest.main()
