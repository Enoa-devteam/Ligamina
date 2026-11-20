"""P7-10: compatibility matrix v2 is built from committed evidence, binds v1 and never promotes unknown."""

from __future__ import annotations

import copy
import hashlib
import unittest
from collections import Counter

from lab import compat_matrix, compat_matrix_v2


class CompatibilityMatrixV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = compat_matrix_v2.build()
        cls.by_id = {entry["registry_entry_id"]: entry for entry in cls.matrix["entries"]}

    def _linux(self, entry: dict, dimension: str) -> dict | None:
        return (entry["dimensions"].get(dimension) or {}).get("linux")

    def test_build_is_deterministic_and_valid(self) -> None:
        again = compat_matrix_v2.build()
        self.assertEqual(compat_matrix_v2.render_json(again), compat_matrix_v2.render_json(self.matrix))
        self.assertEqual(compat_matrix_v2.validate(self.matrix), [])

    def test_v1_is_bound_by_hash_and_left_unchanged(self) -> None:
        base = compat_matrix.ROOT / compat_matrix.OUTPUT_JSON
        self.assertEqual(self.matrix["base_matrix"]["sha256"], hashlib.sha256(base.read_bytes()).hexdigest())
        self.assertEqual(compat_matrix.main(["check"]), 0)
        for entry in self.matrix["entries"]:
            self.assertFalse(set(entry["dimensions"]) & set(compat_matrix.CAPABILITIES))

    def test_astrbot_denominator_covers_every_frozen_entry_and_every_job(self) -> None:
        astrbot = [e for e in self.matrix["entries"] if e["ecosystem"] == "astrbot"]
        self.assertEqual(len(astrbot), 3265)
        discovery = Counter(self._linux(e, "discovery")["value"] for e in astrbot)
        self.assertEqual(discovery, {"verified": 3012, "skipped": 253})
        exercised = sum((self._linux(e, "differential") or {}).get("coverage", {}).get("exercised", 0) for e in astrbot)
        self.assertEqual(exercised, 14655 + 282)
        patched = [e for e in astrbot if any(ref["path"] == compat_matrix_v2.AB_PATCH_RESULTS
                                             for ref in (self._linux(e, "differential") or {}).get("evidence", []))]
        self.assertEqual(len(patched), 6)

    def test_pilot_cohort_matches_the_accepted_p7_04_summary(self) -> None:
        pilot = [e for e in self.matrix["entries"] if e["ecosystem"] in ("koishi", "nonebot")
                 and self._linux(e, "discovery") is not None]
        self.assertEqual(len(pilot), 60)
        totals = Counter()
        for entry in pilot:
            coverage = self._linux(entry, "differential").get("coverage", {})
            for key in ("exercised", *compat_matrix_v2.OUTCOMES):
                totals[key] += coverage.get(key, 0)
        self.assertEqual(dict(totals), {"exercised": 177, "equivalent": 121, "non_equivalent": 34,
                                        "nondeterministic": 2, "unknown": 20})

    def test_unknown_and_nondeterministic_are_never_promoted(self) -> None:
        for entry in self.matrix["entries"]:
            claim = self._linux(entry, "differential")
            if claim is None or claim["value"] != "verified":
                continue
            coverage = claim["coverage"]
            self.assertEqual((coverage["unknown"], coverage["nondeterministic"], coverage["non_equivalent"]), (0, 0, 0))
            self.assertGreater(coverage["equivalent"], 0)
        for entry in self.matrix["entries"]:
            contract = self._linux(entry, "contract")
            if contract is not None:
                self.assertNotEqual(contract["value"], "verified", entry["registry_entry_id"])

    def test_every_claim_cites_hashed_evidence_and_a_scope(self) -> None:
        for entry in self.matrix["entries"]:
            for platforms in entry["dimensions"].values():
                for claim in platforms.values():
                    self.assertTrue(claim["evidence"])
                    self.assertTrue(claim["scope"])
                    for ref in claim["evidence"]:
                        self.assertEqual(self.matrix["sources"][ref["path"]], ref["sha256"])

    def test_changed_evidence_or_outcomes_fail_validation(self) -> None:
        tampered = copy.deepcopy(self.matrix)
        claim = next(self._linux(e, "differential") for e in tampered["entries"]
                     if (self._linux(e, "differential") or {}).get("value") == "verified")
        claim["evidence"][0]["sha256"] = "0" * 64
        self.assertTrue(any("evidence hash" in error for error in compat_matrix_v2.validate(tampered)))

        promoted = copy.deepcopy(self.matrix)
        claim = next(self._linux(e, "differential") for e in promoted["entries"]
                     if (self._linux(e, "differential") or {}).get("value") == "unknown")
        claim["value"] = "verified"
        self.assertTrue(any("disagrees with its outcomes" in error for error in compat_matrix_v2.validate(promoted)))

        rebased = copy.deepcopy(self.matrix)
        rebased["base_matrix"]["sha256"] = "0" * 64
        self.assertTrue(any("base_matrix" in error for error in compat_matrix_v2.validate(rebased)))

    def test_markdown_is_an_evidence_index_not_a_support_list(self) -> None:
        text = compat_matrix_v2.render_markdown(self.matrix)
        self.assertIn("不是支持名单", text)
        self.assertNotIn("| 支持 |", text)

    def test_committed_matrix_is_current(self) -> None:
        self.assertEqual(compat_matrix_v2.main(["check"]), 0)

    def test_check_fails_when_any_evidence_file_changes(self) -> None:
        from unittest.mock import patch

        original = compat_matrix.Sources._read

        def changed(sources, rel):
            data = original(sources, rel)
            if rel != compat_matrix_v2.STATEFUL:
                return data
            data += b" "  # still the same JSON, different bytes
            sources.hashes[rel] = hashlib.sha256(data).hexdigest()
            return data

        with patch.object(compat_matrix.Sources, "_read", changed):
            self.assertEqual(compat_matrix_v2.main(["check"]), 1)


if __name__ == "__main__":
    unittest.main()
