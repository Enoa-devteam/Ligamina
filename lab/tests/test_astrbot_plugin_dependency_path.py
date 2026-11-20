"""Plugin dependency visibility on both AstrBot campaign sides (P7-09, 2026-11-15).

Native installed plugin requirements into /work/site but never put it on sys.path, so plugins
with extra dependencies failed to import natively. Federated prepended the same directory to
PYTHONPATH, ahead of the standard library, so the obsolete ``typing`` backport shadowed the
stdlib module and crashed the Host. A real AstrBot install places plugin packages in
site-packages, after the standard library; both sides must do the same.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _fake_site(root: Path) -> Path:
    site = root / "site"
    (site / "p7_plugin_dep").mkdir(parents=True)
    (site / "p7_plugin_dep" / "__init__.py").write_text("VALUE = 'installed'\n", encoding="utf-8")
    (site / "typing.py").write_text("raise RuntimeError('obsolete typing backport shadowed stdlib')\n", encoding="utf-8")
    return site


class PluginDependencyPathTests(unittest.TestCase):
    def test_native_side_appends_installed_plugin_dependencies_after_the_standard_library(self) -> None:
        from lab.astrbot_native_tool_side import _add_plugin_site

        saved = list(sys.path)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                site = _fake_site(Path(tmp))
                _add_plugin_site(site)
                self.assertIn(str(site), sys.path)
                stdlib = os.path.dirname(os.__file__)
                self.assertGreater(sys.path.index(str(site)), sys.path.index(stdlib))
                import importlib

                self.assertEqual(importlib.import_module("p7_plugin_dep").VALUE, "installed")
                sys.modules.pop("p7_plugin_dep", None)
        finally:
            sys.path[:] = saved
        _add_plugin_site(Path("/nonexistent/p7-site"))  # absent directory is a no-op
        self.assertEqual(sys.path, saved)

    def test_federated_host_sees_dependencies_without_shadowing_the_standard_library(self) -> None:
        from lab.astrbot_tool_side import _plugin_site_bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = _fake_site(root)
            bootstrap = _plugin_site_bootstrap(root, site)
            self.assertNotEqual(bootstrap, site)
            probe = subprocess.run(
                [sys.executable, "-c", "import typing, p7_plugin_dep; print(typing.__file__); print(p7_plugin_dep.VALUE)"],
                env={**os.environ, "PYTHONPATH": str(bootstrap)}, capture_output=True, text=True, check=False)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            typing_file, value = probe.stdout.split()
            self.assertNotIn(str(site), typing_file)
            self.assertEqual(value, "installed")


if __name__ == "__main__":
    unittest.main()
