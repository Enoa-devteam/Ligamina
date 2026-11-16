from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

GATE_PATH = Path(__file__).resolve().parents[2] / "scripts/p7-p709-campaign-gate.py"
_spec = importlib.util.spec_from_file_location("p7_p709_campaign_gate", GATE_PATH)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _signals(errors: int = 0, silent: int = 0, calls: int = 2) -> dict:
    return {"calls": calls, "errors": errors, "silent": silent}


def _result(federated: dict | None = None, c7_reason: str | None = None, category: str = "equivalent") -> dict:
    return {
        "comparison": {"category": category, "call_signals": {
            "native_first": _signals(), "native_second": _signals(), "federated": federated or _signals()}},
        "contracts": {"C7": {"reason_code": c7_reason}},
        "worker_runs": [{"status": "passed", "reason_code": None, "cleanup_confirmed": True}] * 3,
    }


def _report(count: int) -> dict:
    return {"status": "running", "calls": [{"status": "finished", "unit_id": f"u{i}"} for i in range(count)]}


class CampaignGateTests(unittest.TestCase):
    def test_job_requeued_for_a_pending_retry_is_not_a_stuck_row(self) -> None:
        # 2026-11-15 b0005: the batch's last job finished a retryable attempt 1 at 19:31:55 and was
        # queued again; the gate ran in the same second. Attempt 2 ran in slot 2's next batch.
        rows = {f"u{i}": {"status": "passed", "result": _result()} for i in range(10)}
        rows["u9"] = {"status": "queued", "attempts_used": 1, "max_attempts": 2, "result": None}
        verdict = gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)
        self.assertEqual(verdict["status"], "passed", verdict["reasons"])
        self.assertEqual(verdict["counts"]["retry_pending"], 1)

        rows["u9"] = {"status": "leased", "attempts_used": 1, "max_attempts": 2, "result": None}
        self.assertIn("non_terminal_queue_rows:1", gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)["reasons"])
        rows["u9"] = {"status": "queued", "attempts_used": 2, "max_attempts": 2, "result": None}
        self.assertIn("non_terminal_queue_rows:1", gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)["reasons"])
    def test_clean_batch_passes(self) -> None:
        rows = {f"u{i}": {"status": "passed", "result": _result()} for i in range(10)}
        verdict = gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)
        self.assertEqual(verdict["status"], "passed")
        self.assertEqual(verdict["reasons"], [])

    def test_stale_core_signature_halts_the_campaign(self) -> None:
        stale = _result(federated=_signals(errors=2), c7_reason="mcp_command_not_listed", category="non_equivalent")
        rows = {f"u{i}": {"status": "passed", "result": stale if i < 6 else _result()} for i in range(10)}
        verdict = gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)
        self.assertEqual(verdict["status"], "anomaly")
        self.assertIn("federated_all_calls_error:6/10>0.2", verdict["reasons"])
        self.assertIn("c7_command_not_listed:6/10>0.05", verdict["reasons"])

    def test_silent_native_side_and_missing_signals_are_anomalies(self) -> None:
        silent = _result(category="unknown")
        silent["comparison"]["call_signals"]["native_first"] = _signals(silent=2)
        rows = {f"u{i}": {"status": "unknown", "result": silent} for i in range(4)}
        rows["u4"] = {"status": "passed", "result": {"comparison": {"category": "equivalent"}, "worker_runs": []}}
        rows["u5"] = {"status": "leased", "result": None}
        verdict = gate.evaluate(_report(6), rows, gate.DEFAULT_LIMITS)
        self.assertIn("native_all_calls_silent:4/5>0.2", verdict["reasons"])
        self.assertIn("call_signals_missing:1", verdict["reasons"])
        self.assertIn("non_terminal_queue_rows:1", verdict["reasons"])

    def test_timed_out_worker_without_signals_is_a_rate_not_a_harness_anomaly(self) -> None:
        # 2026-11-13 b0006: both Native Workers of one hanging command hit the 420 s Worker
        # timeout, so those sides had no readable output and no call signals.
        timed_out = _result(federated=_signals(errors=1), category="unknown")
        timed_out["comparison"]["call_signals"]["native_first"] = None
        timed_out["comparison"]["call_signals"]["native_second"] = None
        timed_out["worker_runs"] = [
            {"status": "unknown", "reason_code": "worker_timeout", "cleanup_confirmed": True},
            {"status": "unknown", "reason_code": "worker_timeout", "cleanup_confirmed": True},
            {"status": "passed", "reason_code": None, "cleanup_confirmed": True},
        ]
        rows = {f"u{i}": {"status": "passed", "result": _result()} for i in range(10)}
        rows["u0"] = {"status": "unknown", "result": timed_out}
        verdict = gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)
        self.assertEqual(verdict["status"], "passed", verdict["reasons"])
        self.assertEqual(verdict["counts"]["worker_not_passed"], 1)

        for i in range(1, 3):
            rows[f"u{i}"] = {"status": "unknown", "result": timed_out}
        verdict = gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)
        self.assertIn("worker_not_passed:3/10>0.1", verdict["reasons"])

    def test_passed_worker_without_signals_is_still_a_harness_anomaly(self) -> None:
        broken = _result()
        broken["comparison"]["call_signals"]["federated"] = None
        rows = {f"u{i}": {"status": "passed", "result": _result()} for i in range(10)}
        rows["u0"] = {"status": "passed", "result": broken}
        verdict = gate.evaluate(_report(10), rows, gate.DEFAULT_LIMITS)
        self.assertIn("call_signals_missing:1", verdict["reasons"])

    def test_native_observation_failure_is_a_hard_anomaly_once_the_harness_is_fixed(self) -> None:
        # 2026-11-14 b0028: surrogate-escaped plugin text made the Native protocol line raise, so both
        # passed Native Workers reported a failed observation. The depsfix harness keeps such text,
        # so any recurrence is a new harness defect; affected jobs are still listed.
        failed_native = _result(federated=_signals(silent=2), category="unknown")
        failed_native["comparison"]["call_signals"]["native_first"] = None
        failed_native["comparison"]["call_signals"]["native_second"] = None
        failed_native["comparison"]["incomplete_sides"] = {
            "native_first": "worker_observation_incomplete", "native_second": "worker_observation_incomplete",
            "federated": "worker_observation_incomplete"}
        rows = {f"u{i}": {"status": "passed", "result": _result()} for i in range(100)}
        rows["u7"] = {"status": "unknown", "result": failed_native}
        verdict = gate.evaluate(_report(100), rows, gate.DEFAULT_LIMITS)
        self.assertIn("native_observation_failed:1/100>0.0", verdict["reasons"])
        self.assertEqual(verdict["patch_candidates"], ["u7"])

    def test_native_errors_on_every_call_halt_above_five_percent(self) -> None:
        # 2026-11-15 b0009 diagnosis: Native never put installed plugin requirements on sys.path, so
        # plugins with dependencies were not loaded and every Native call failed with
        # "native command not discovered" (956 of 1,921 such jobs). No gate signal watched it.
        native_errors = _result(category="non_equivalent")
        native_errors["comparison"]["call_signals"]["native_first"] = _signals(errors=2)
        native_errors["comparison"]["call_signals"]["native_second"] = _signals(errors=2)
        rows = {f"u{i}": {"status": "passed", "result": _result()} for i in range(100)}
        rows["u0"] = {"status": "passed", "result": native_errors}
        verdict = gate.evaluate(_report(100), rows, gate.DEFAULT_LIMITS)
        self.assertEqual(verdict["status"], "passed", verdict["reasons"])
        self.assertEqual(verdict["counts"]["native_all_calls_error"], 1)
        for i in range(1, 6):
            rows[f"u{i}"] = {"status": "passed", "result": native_errors}
        verdict = gate.evaluate(_report(100), rows, gate.DEFAULT_LIMITS)
        self.assertIn("native_all_calls_error:6/100>0.05", verdict["reasons"])


if __name__ == "__main__":
    unittest.main()
