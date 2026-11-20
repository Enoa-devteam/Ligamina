from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab import astrbot_census


@unittest.skipUnless(hasattr(os, "getuid"), "dependency download containers are Linux-only")
class DependencyDownloadTimeoutTests(unittest.TestCase):
    def test_timed_out_download_container_is_removed_before_the_error_propagates(self) -> None:
        # 2026-11-17: a hanging proxy hit the 900 s timeout, which killed only the docker client;
        # the unlabelled download container kept running and could not be reconciled.
        calls = []

        def fake_run(command, **kwargs):
            calls.append(list(command))
            if command[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp, patch.object(astrbot_census.subprocess, "run", side_effect=fake_run):
            with self.assertRaises(subprocess.TimeoutExpired):
                astrbot_census.download_wheels(Path(tmp))

        run = calls[0]
        name = run[run.index("--name") + 1]
        self.assertTrue(name.startswith("ligamina-dl-"))
        self.assertEqual(calls[1][:3], ["docker", "rm", "-f"])
        self.assertEqual(calls[1][3], name)

    def test_completed_download_does_not_issue_a_removal(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp, patch.object(astrbot_census.subprocess, "run", side_effect=fake_run):
            result = astrbot_census.download_wheels(Path(tmp))
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
