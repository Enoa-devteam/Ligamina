"""Compatibility matrix v2: discovery, differential, contract and stateful dimensions (P7-10).

    python -m lab.compat_matrix_v2 build   # rewrite outputs/compat/compatibility-matrix-v2.{json,md}
    python -m lab.compat_matrix_v2 check   # fail if the committed v2 matrix is stale or invalid

v2 adds the Phase 7 automated-verification dimensions on top of v1. It does not copy v1: it
binds the committed v1 matrix by path and SHA-256 (``base_matrix``), and v1 is never rewritten.
Every claim other than ``untested`` cites the evidence file, its SHA-256 and the record inside
it, and records coverage counts. The SHA-256 of every source is recorded, so ``check`` fails as
soon as any evidence file changes without v2 being rebuilt. Nothing here runs plugins.

Dimensions (platform ``linux``; values verified / failed / skipped / unknown / untested):

- ``discovery``: runtime command discovery in an isolated Worker. Koishi/NoneBot from the
  accepted P7-04 30+30 pilot; AstrBot from the frozen census dispositions and the P7-09
  inventory-backfill jobs.
- ``differential``: generated Native x2 / Federated comparison per command. ``verified`` means
  every exercised command matched Native; it is not plugin correctness. Any non-equivalent
  command makes the entry ``failed``; unknown and nondeterministic results stay ``unknown``.
- ``contract``: C1-C8 generic checks. ``verified`` only when all eight passed; the pilot did
  not emit stimuli for most checks, and the AstrBot campaign evaluated only C7.
- ``stateful``: P7-07 relations (session isolation, restart persistence) for its own cohort.

Cohorts differ per dimension and are stated in each claim's ``scope``; absence of a dimension
means ``untested``. This matrix is an evidence index, not a support list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from lab import compat_matrix
from lab.compat_matrix import ACCEPTANCE, Sources

ROOT = compat_matrix.ROOT
OUTPUT_JSON = "outputs/compat/compatibility-matrix-v2.json"
OUTPUT_MD = "outputs/compat/compatibility-matrix-v2.md"
SCHEMA = "contracts/lab/compat/v2/compatibility-matrix.schema.json"
BASE_MATRIX = compat_matrix.OUTPUT_JSON
VALUES = compat_matrix.VALUES
DIMENSIONS = ("discovery", "differential", "contract", "stateful")
CONTRACT_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
OUTCOMES = ("equivalent", "non_equivalent", "nondeterministic", "unknown")

PILOT = f"{ACCEPTANCE}/p7-p704-differential-pilot-20261112-feat065-rerun1.json"
STATEFUL = f"{ACCEPTANCE}/p7-p707-stateful-pilot-20261110.json"
AB_PLAN = f"{ACCEPTANCE}/p7-p709-astrbot-campaign-plan-depsfix-20261115.json"
AB_RESULTS = f"{ACCEPTANCE}/p7-p709-astrbot-campaign-results-depsfix-20261120.json"
AB_FINAL = f"{ACCEPTANCE}/p7-p709-astrbot-campaign-checkpoint-20261120T032753Z-final.json"
AB_PATCH_PLAN = f"{ACCEPTANCE}/p7-p709-astrbot-campaign-plan-patch-20261120.json"
AB_PATCH_RESULTS = f"{ACCEPTANCE}/p7-p709-astrbot-campaign-results-patch-20261120.json"

PILOT_SCOPE = "P7-04 hash-ranked 30+30 Koishi/NoneBot pilot cohort, three fresh reruns, network disabled"
AB_SCOPE = "P7-09 AstrBot campaign over the frozen 3,265-entry census, private-chat tool sessions, network disabled"
STATEFUL_SCOPE = "P7-07 stateful adjudication cohort (60 entries from an earlier P7-04 pilot); relations, not commands"


def claim(value: str, evidence: list[dict], reason: str | None = None, **extra: Any) -> dict:
    assert value in VALUES and value != "untested", value
    out = {"value": value, "reason": reason, "evidence": evidence}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def differential_value(outcomes: Counter) -> tuple[str, str | None]:
    if outcomes["non_equivalent"]:
        return "failed", "non_equivalent_command"
    if outcomes["unknown"] or outcomes["nondeterministic"]:
        return "unknown", "unknown_or_nondeterministic_command"
    return "verified", None


def contract_value(statuses: dict[str, Counter]) -> tuple[str, str | None]:
    if any(counts["failed"] for counts in statuses.values()):
        return "failed", "contract_check_failed"
    if all(statuses.get(cid, Counter())["passed"] and not statuses[cid]["unknown"] for cid in CONTRACT_IDS):
        return "verified", None
    return "unknown", "not_every_contract_evaluated"


def _pilot(src: Sources, dims: dict[str, dict]) -> None:
    report = src.json(PILOT)
    for i, entry in enumerate(report["entries"]):
        rid = entry["registry_entry_id"]
        ref = [src.ref(PILOT, f"entries[{i}] registry_entry_id={rid}")]
        out = dims.setdefault(rid, {})
        discovery = entry["native_discovery"]
        commands = entry["commands"]
        if discovery["status"] == "completed":
            out["discovery"] = {"linux": claim("verified", ref, scope=PILOT_SCOPE,
                                               coverage={"commands": commands["discovered"]})}
        else:
            out["discovery"] = {"linux": claim("failed", ref, f"native_discovery_failed:{entry.get('skip_domain')}",
                                               scope=PILOT_SCOPE, coverage={"commands": 0})}
        items = commands.get("items") or []
        if items:
            outcomes = Counter(item["status"] for item in items)
            value, reason = differential_value(outcomes)
            out["differential"] = {"linux": claim(value, ref, reason, scope=PILOT_SCOPE, coverage={
                "exercised": len(items), **{k: outcomes[k] for k in OUTCOMES},
                "nontrivial": commands["nontrivial"],
                "consistent_across_three_fresh_reruns": entry["conclusions_consistent_across_three_fresh_reruns"]})}
        else:
            out["differential"] = {"linux": claim("skipped", ref, entry.get("conclusion_state") or "no_commands_exercised",
                                                  scope=PILOT_SCOPE, coverage={"exercised": 0})}
        statuses = {cid: Counter({entry["contracts"][cid]["status"]: 1}) for cid in CONTRACT_IDS}
        value, reason = contract_value(statuses)
        out["contract"] = {"linux": claim(value, ref, reason, scope=PILOT_SCOPE, coverage={
            cid: entry["contracts"][cid]["status"] for cid in CONTRACT_IDS})}


def _stateful(src: Sources, dims: dict[str, dict]) -> None:
    report = src.json(STATEFUL)
    for i, entry in enumerate(report["entries"]):
        rid = entry["registry_entry_id"]
        relations = {name: relation["status"] for name, relation in sorted(entry["relations"].items())}
        statuses = set(relations.values())
        if "failed" in statuses:
            value, reason = "failed", "relation_failed"
        elif statuses == {"passed"}:
            value, reason = "verified", None
        elif statuses == {"skipped"}:
            value, reason = "skipped", "relations_not_applicable_or_deferred"
        else:
            value, reason = "unknown", sorted({r.get("reason_code") for r in entry["relations"].values()
                                               if r["status"] == "unknown"})[0]
        dims.setdefault(rid, {})["stateful"] = {"linux": claim(
            value, [src.ref(STATEFUL, f"entries[{i}] registry_entry_id={rid}")], reason,
            scope=STATEFUL_SCOPE, coverage=relations)}


def _astrbot_jobs(src: Sources) -> list[dict]:
    """Depsfix-run differential jobs with the six pre-dispatch failures replaced by the patch run."""
    plan, results, final = src.json(AB_PLAN), src.json(AB_RESULTS), src.json(AB_FINAL)
    patch_plan, patch = src.json(AB_PATCH_PLAN), src.json(AB_PATCH_RESULTS)
    if results["run_id"] != plan["run_id"] or results["plan"]["sha256"] != src.hashes[AB_PLAN]:
        raise SystemExit("AstrBot results export is not bound to the depsfix plan")
    queue_counts = {key: value for key, value in final["queue"]["counts"].items() if value and key != "total"}
    exported = Counter(job["status"] for job in results["jobs"])
    if dict(exported) != queue_counts or len(results["jobs"]) != final["queue"]["counts"]["total"]:
        raise SystemExit(f"AstrBot results export {dict(exported)} differs from the final checkpoint {queue_counts}")
    if patch["run_id"] != patch_plan["run_id"] or patch["plan"]["sha256"] != src.hashes[AB_PATCH_PLAN]:
        raise SystemExit("AstrBot patch export is not bound to the patch plan")
    patched = {(job["registry_entry_id"], job["case_id"]): job for job in patch["jobs"]}
    jobs = []
    for job in results["jobs"]:
        if job["stage"] != "differential":
            continue
        key = (job["registry_entry_id"], job["case_id"])
        if job["status"] == "failed" and not job["worker_runs"]:
            if key not in patched:
                raise SystemExit(f"pre-dispatch failure without a patch-run job: {key}")
            jobs.append({**patched.pop(key), "source": AB_PATCH_RESULTS})
        else:
            jobs.append({**job, "source": AB_RESULTS})
    if patched:
        raise SystemExit(f"patch-run jobs without a failed original: {sorted(patched)}")
    return jobs


def _astrbot(src: Sources, dims: dict[str, dict]) -> None:
    plan, results = src.json(AB_PLAN), src.json(AB_RESULTS)
    inventories = {job["registry_entry_id"]: (i, job) for i, job in enumerate(results["jobs"]) if job["stage"] == "inventory"}
    by_entry: dict[str, list[dict]] = {}
    for job in _astrbot_jobs(src):
        by_entry.setdefault(job["registry_entry_id"], []).append(job)
    for rid, disposition in sorted(plan["dispositions"].items()):
        out = dims.setdefault(rid, {})
        plan_ref = src.ref(AB_PLAN, f"dispositions.{rid}")
        inventory_status = disposition.get("inventory_status")
        if disposition["status"] != "passed":
            out["discovery"] = {"linux": claim("skipped", [plan_ref], f"load_{disposition['status']}:{disposition.get('reason_code')}",
                                               scope=AB_SCOPE)}
            continue
        if inventory_status == "observed":
            commands = disposition.get("observed_command_count", 0)
            out["discovery"] = {"linux": claim("verified", [plan_ref], scope=AB_SCOPE, coverage={"commands": commands})}
        elif inventory_status == "backfill_required" and rid in inventories:
            i, job = inventories[rid]
            ref = [plan_ref, src.ref(AB_RESULTS, f"jobs[{i}] unit_id={job['unit_id']}")]
            if job["status"] == "passed" and job["command_ids"] is not None and not job["commands_truncated"]:
                commands = len(job["command_ids"])
                out["discovery"] = {"linux": claim("verified", ref, "inventory_backfilled", scope=AB_SCOPE,
                                                   coverage={"commands": commands})}
            else:
                out["discovery"] = {"linux": claim("unknown", ref, job.get("reason_code") or "inventory_incomplete", scope=AB_SCOPE)}
                continue
        else:
            out["discovery"] = {"linux": claim("unknown", [plan_ref], f"inventory_{inventory_status}", scope=AB_SCOPE)}
            continue
        jobs = by_entry.get(rid, [])
        if not jobs:
            out["differential"] = {"linux": claim("skipped", [plan_ref], "no_runtime_commands_discovered",
                                                  scope=AB_SCOPE, coverage={"exercised": 0})}
            continue
        refs = sorted({job["source"] for job in jobs})
        evidence = [src.ref(path, f"jobs where registry_entry_id={rid} and stage=differential") for path in refs]
        outcomes = Counter(job.get("comparison") or "unknown" for job in jobs)
        value, reason = differential_value(outcomes)
        out["differential"] = {"linux": claim(value, evidence, reason, scope=AB_SCOPE, coverage={
            "exercised": len(jobs), **{k: outcomes[k] for k in OUTCOMES},
            "cleanup_confirmed": sum(job["cleanup_confirmed"] is True for job in jobs)})}
        c7 = Counter(job.get("c7") or "unknown" for job in jobs)
        statuses = {"C7": c7, **{cid: Counter({"unknown": len(jobs)}) for cid in CONTRACT_IDS if cid != "C7"}}
        value, reason = contract_value(statuses)
        out["contract"] = {"linux": claim(value, evidence, reason, scope=AB_SCOPE + "; only C7 is evaluated", coverage={
            "C7": {k: c7[k] for k in ("passed", "failed", "unknown")}, "not_evaluated": [c for c in CONTRACT_IDS if c != "C7"]})}


def build(root: Path = ROOT) -> dict:
    src = Sources(root)
    entries = compat_matrix.entries_from_catalogs(src)
    base = root / BASE_MATRIX
    base_sha = hashlib.sha256(base.read_bytes()).hexdigest()
    dims: dict[str, dict] = {}
    _pilot(src, dims)
    _stateful(src, dims)
    _astrbot(src, dims)
    unknown_ids = sorted(set(dims) - set(entries))
    if unknown_ids:
        raise SystemExit(f"v2 evidence names entries outside the frozen catalogs: {unknown_ids[:3]}")

    records = []
    for rid in sorted(dims):
        record = dict(entries[rid])
        record["dimensions"] = {name: dims[rid][name] for name in DIMENSIONS if name in dims[rid]}
        records.append(record)

    summary: dict[str, dict] = {}
    for eco in sorted({e["ecosystem"] for e in entries.values()}):
        summary[eco] = {"catalog_entries": sum(e["ecosystem"] == eco for e in entries.values()),
                        **{name: Counter() for name in DIMENSIONS}, "commands": Counter(), "contracts": Counter()}
    for record in records:
        eco = summary[record["ecosystem"]]
        for name in DIMENSIONS:
            for platform, value in (record["dimensions"].get(name) or {}).items():
                eco[name][f"{platform}:{value['value']}"] += 1
        coverage = ((record["dimensions"].get("differential") or {}).get("linux") or {}).get("coverage") or {}
        for key in ("exercised", *OUTCOMES):
            eco["commands"][key] += coverage.get(key, 0)
        contract = ((record["dimensions"].get("contract") or {}).get("linux") or {}).get("coverage") or {}
        for cid in CONTRACT_IDS:
            status = contract.get(cid)
            if isinstance(status, str):
                eco["contracts"][f"{cid}:{status}"] += 1
            elif isinstance(status, dict):
                for key, count in status.items():
                    eco["contracts"][f"{cid}:{key}"] += count
    for eco, data in summary.items():
        for name in DIMENSIONS:
            data[name]["untested"] = data["catalog_entries"] - sum(data[name].values())
        summary[eco] = {k: (dict(sorted((kk, vv) for kk, vv in v.items() if vv)) if isinstance(v, Counter) else v)
                        for k, v in data.items()}

    return {
        "schema_version": 2,
        "kind": "compatibility_matrix",
        "base_matrix": {"path": BASE_MATRIX, "sha256": base_sha},
        "dimensions": list(DIMENSIONS),
        "values": list(VALUES),
        "notes": [
            "v2 adds dimensions; load, mcp_tool, federated_event and platform_delivery stay in base_matrix (v1), unchanged",
            "untested means no evidence for that dimension; entries with no v2 evidence are omitted and counted as untested",
            "differential verified means every exercised command matched Native; it is not plugin correctness or support",
            "unknown and nondeterministic command outcomes are never promoted; cohorts differ per dimension, see each scope",
        ],
        "sources": dict(sorted(src.hashes.items())),
        "summary": summary,
        "entries": records,
    }


def render_json(matrix: dict) -> str:
    return compat_matrix.render_json(matrix)


def render_markdown(matrix: dict) -> str:
    out = ["# 兼容性矩阵 v2（自动生成，勿手改）", "",
           "由 `python -m lab.compat_matrix_v2 build` 从已提交的证据生成；`check` 在证据变化而矩阵未重建时失败。"
           "v2 只新增第七阶段维度，`load`、`mcp_tool`、`federated_event`、`platform_delivery` 仍在 v1 矩阵中、保持不变"
           f"（`base_matrix` 绑定 `{matrix['base_matrix']['path']}` 的 SHA-256）。", "",
           "| 维度 | 含义 | 证据与范围 |", "| --- | --- | --- |",
           "| `discovery` | 隔离 Worker 中的运行时命令发现 | Koishi/NoneBot：P7-04 30+30 pilot；AstrBot：冻结普查与 P7-09 inventory backfill |",
           "| `differential` | 生成式 Native×2/Federated 逐命令比较；`verified` 只表示所有已执行命令与原生一致 | P7-04 pilot；P7-09 AstrBot campaign（含 patch run） |",
           "| `contract` | C1–C8 通用契约；全部通过才为 `verified` | P7-04 pilot（多数检查无刺激，保持 unknown）；AstrBot 只评估 C7 |",
           "| `stateful` | P7-07 关系：会话隔离、重启持久化 | P7-07 自身的 60 条目队列 |", "",
           "取值只有 `verified`、`failed`、`skipped`、`unknown`、`untested`。任何 non-equivalent 命令使条目为 `failed`；"
           "unknown 与 nondeterministic 保持 `unknown`，不改写为通过。各维度队列不同，见每条结论的 `scope`。"
           "本矩阵是证据索引，不是支持名单，也不表示插件业务正确。", "",
           "## 按生态与维度的计数", "",
           "| 生态 | 目录条目 | 维度 | 计数（平台:取值） |", "| --- | --- | --- | --- |"]
    for eco, data in matrix["summary"].items():
        for name in DIMENSIONS:
            counts = ", ".join(f"{k} {v}" for k, v in data[name].items())
            out.append(f"| {eco} | {data['catalog_entries']} | `{name}` | {counts} |")
    out += ["", "## 覆盖度", "",
            "| 生态 | 已执行命令 | equivalent | non_equivalent | nondeterministic | unknown | 契约检查（检查:状态） |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for eco, data in matrix["summary"].items():
        commands = data["commands"]
        contracts = ", ".join(f"{k} {v}" for k, v in data["contracts"].items()) or "—"
        out.append(f"| {eco} | {commands.get('exercised', 0)} | {commands.get('equivalent', 0)} | "
                   f"{commands.get('non_equivalent', 0)} | {commands.get('nondeterministic', 0)} | "
                   f"{commands.get('unknown', 0)} | {contracts} |")
    out.append("")
    return "\n".join(out)


def validate(matrix: dict, root: Path = ROOT) -> list[str]:
    from jsonschema import Draft202012Validator

    schema = json.loads((root / SCHEMA).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in Draft202012Validator(schema).iter_errors(matrix)]
    base = root / matrix["base_matrix"]["path"]
    if not base.exists() or hashlib.sha256(base.read_bytes()).hexdigest() != matrix["base_matrix"]["sha256"]:
        errors.append("base_matrix hash differs from the committed v1 matrix")
    for entry in matrix["entries"]:
        for name, platforms in entry["dimensions"].items():
            for platform, value in platforms.items():
                where = f"{entry['registry_entry_id']} {name}/{platform}"
                if value["value"] in ("verified", "failed") and not value["evidence"]:
                    errors.append(f"{where}: {value['value']} without evidence")
                for ref in value["evidence"]:
                    if matrix["sources"].get(ref["path"]) != ref["sha256"]:
                        errors.append(f"{where}: evidence hash not in sources")
                coverage = value.get("coverage") or {}
                if name == "differential" and "exercised" in coverage and coverage["exercised"]:
                    if sum(coverage.get(k, 0) for k in OUTCOMES) != coverage["exercised"]:
                        errors.append(f"{where}: command outcomes do not sum to exercised")
                    expected, _ = differential_value(Counter({k: coverage.get(k, 0) for k in OUTCOMES}))
                    if expected != value["value"]:
                        errors.append(f"{where}: value {value['value']} disagrees with its outcomes ({expected})")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("build", "check"))
    args = parser.parse_args(argv)
    matrix = build()
    errors = validate(matrix)
    if errors:
        print("\n".join(errors[:50]), file=sys.stderr)
        return 1
    rendered = {OUTPUT_JSON: render_json(matrix), OUTPUT_MD: render_markdown(matrix)}
    if args.action == "build":
        for rel, text in rendered.items():
            path = ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        print(json.dumps({"entries": len(matrix["entries"]), "sources": len(matrix["sources"])}))
        return 0
    stale = [rel for rel, text in rendered.items()
             if not (ROOT / rel).exists() or (ROOT / rel).read_text(encoding="utf-8") != text]
    if stale:
        print(f"compatibility matrix v2 is stale: {', '.join(stale)} (run python -m lab.compat_matrix_v2 build)",
              file=sys.stderr)
        return 1
    print(json.dumps({"check": "ok", "entries": len(matrix["entries"]), "sources": len(matrix["sources"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
