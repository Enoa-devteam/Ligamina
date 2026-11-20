#!/usr/bin/env python3
"""Export a hash-bound projection of a finished P7-09 AstrBot campaign queue (stdlib only).

    python3 scripts/p7-p709-campaign-export.py --queue-db <sqlite> --plan <plan.json> --output <json>

The queue is opened read-only. Each job keeps only identities, terminal status, the
comparison label, the C7 status, Worker cleanup and (for inventory jobs) the observed command
IDs. No plugin output, scenario text or reply is exported. The file is the committed evidence
from which compatibility matrix v2 reads AstrBot campaign results, including follow-up jobs
that the plan does not list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

TERMINAL = {"passed", "failed", "unknown", "skipped"}


def project(row: tuple) -> dict:
    unit_id, entry_id, case_id, stage, status, attempts, result_json = row
    result = json.loads(result_json) if result_json else {}
    runs = result.get("worker_runs") or []
    job = {
        "unit_id": unit_id, "registry_entry_id": entry_id, "case_id": case_id, "stage": stage,
        "status": status, "attempts": attempts, "reason_code": result.get("reason_code"),
        "worker_runs": len(runs), "cleanup_confirmed": all(run.get("cleanup_confirmed") is True for run in runs) if runs else None,
    }
    if stage == "differential":
        comparison = result.get("comparison") or {}
        job["comparison"] = comparison.get("category")
        job["c7"] = ((result.get("contracts") or {}).get("C7") or {}).get("status")
    else:
        load = ((result.get("inventory") or {}).get("load") or {})
        descriptors = load.get("command_descriptors")
        job["command_ids"] = sorted(d.get("command_id") for d in descriptors) if isinstance(descriptors, list) else None
        job["commands_truncated"] = load.get("commands_truncated")
    return job


def export(queue_db: str, plan: dict) -> dict:
    con = sqlite3.connect(f"file:{queue_db}?mode=ro", uri=True)
    try:
        con.execute("BEGIN")
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        state = con.execute("SELECT state FROM runs WHERE run_id = ?", (plan["run_id"],)).fetchone()
        rows = con.execute(
            "SELECT unit_id, registry_entry_id, case_id, stage, status, attempts_used, result_json "
            "FROM jobs WHERE run_id = ? ORDER BY unit_id", (plan["run_id"],)).fetchall()
    finally:
        con.close()
    if state is None:
        raise SystemExit(f"run {plan['run_id']} is not in the queue")
    jobs = [project(row) for row in rows]
    open_jobs = [job["unit_id"] for job in jobs if job["status"] not in TERMINAL]
    if open_jobs:
        raise SystemExit(f"queue is not drained: {len(open_jobs)} non-terminal jobs")
    planned = {job["unit_id"] for job in plan["jobs"]}
    missing = planned - {job["unit_id"] for job in jobs}
    if missing:
        raise SystemExit(f"{len(missing)} planned jobs are missing from the queue")
    for job in jobs:
        job["planned"] = job["unit_id"] in planned
    return {
        "schema_version": 1,
        "kind": "p7_p709_astrbot_campaign_results",
        "run_id": plan["run_id"],
        "run_state": state[0],
        "quick_check": quick,
        "counts": dict(sorted(Counter(f"{job['stage']}:{job['status']}" for job in jobs).items())),
        "planned_jobs": len(planned),
        "follow_up_jobs": sum(not job["planned"] for job in jobs),
        "acceptance_boundary": "Execution and comparison projection only; equivalent is Native consistency, not plugin correctness or support. Unknown stays unknown.",
        "jobs": jobs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queue-db", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    plan_bytes = args.plan.read_bytes()
    report = export(args.queue_db, json.loads(plan_bytes))
    report = {**report, "plan": {"path": args.plan.as_posix(), "sha256": hashlib.sha256(plan_bytes).hexdigest()}}
    head = json.dumps({k: v for k, v in report.items() if k != "jobs"}, ensure_ascii=False, sort_keys=True, indent=1)[:-2]
    body = ",\n".join(json.dumps(job, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for job in report["jobs"])
    data = (head + ',\n "jobs": [\n' + body + "\n]}\n").encode("utf-8")
    json.loads(data)
    args.output.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    args.output.with_name(args.output.name + ".sha256").write_text(f"{digest}  {args.output.name}\n", encoding="ascii")
    print(json.dumps({"output": args.output.as_posix(), "sha256": digest, "jobs": len(report["jobs"]), "counts": report["counts"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
