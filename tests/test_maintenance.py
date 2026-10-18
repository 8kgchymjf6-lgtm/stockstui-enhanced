"""External script failures must propagate and installers must preserve launchers."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from textual.app import App, ComposeResult
from textual.widgets import Markdown
from stockstui.ui.views.news_view import NewsView
from stockstui.ui.views.config_views.lists_config_view import ListsConfigView
from rich.text import Text

ROOT = Path(__file__).resolve().parents[1]
FAKE_PYTHON = """import json,os,pathlib,sys
p=pathlib.Path(os.environ['CALL_LOG'])
rows=json.loads(p.read_text()) if p.exists() else []
rows.append(dict(args=sys.argv[1:],cwd=os.getcwd(),config=os.environ.get('XDG_CONFIG_HOME')))
p.write_text(json.dumps(rows))
a=sys.argv[1:]
if a[:2]==['-m','coverage']:
 if a[2]=='--version': sys.exit(int(os.environ.get('MISSING_COVERAGE','0')))
 if a[2]=='run': sys.exit(int(os.environ.get('TEST_EXIT','0')))
 if a[2]=='report': sys.exit(int(os.environ.get('REPORT_EXIT','0')))
if a[:2]==['-m','unittest']: sys.exit(int(os.environ.get('TEST_EXIT','0')))
if a[:2]==['-m','pip'] and 'install' in a:
 if os.environ.get('CREATE_LAUNCHER'): pathlib.Path(os.environ['CREATE_LAUNCHER']).write_text('created while pip ran')
 sys.exit(int(os.environ.get('INSTALL_EXIT','0')))
sys.exit(0)
"""


class TestMaintenanceScripts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        for f in ("run_tests.sh", "install.sh"):
            shutil.copy2(ROOT / f, self.project / f)
        self.venv = self.project / ".venv"
        (self.venv / "bin").mkdir(parents=True)
        self.python = self.venv / "bin/python"
        self.python.write_text(f"#!{sys.executable}\n" + FAKE_PYTHON)
        self.python.chmod(0o755)
        self.executable = self.venv / "bin/stockstui"
        self.executable.write_text("#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o755)
        self.bin = self.root / "commands"
        self.bin.mkdir()
        self.launcher = self.bin / "stockstui"
        self.log = self.root / "calls.json"
        self.env = os.environ.copy()
        self.env.update(CALL_LOG=str(self.log), STOCKSTUI_PYTHON=str(self.python))

    def run_script(self, script, *args, **env):
        return subprocess.run(
            ["bash", str(self.project / script), *args],
            cwd=self.root,
            env={**self.env, **env},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )

    def calls(self):
        return json.loads(self.log.read_text()) if self.log.exists() else []

    def install(self, *args, **env):
        return self.run_script(
            "install.sh",
            "--venv",
            str(self.venv),
            "--bin-dir",
            str(self.bin),
            *args,
            **env,
        )

    def test_coverage_threshold_failure_is_a_failure(self):
        result = self.run_script("run_tests.sh", REPORT_EXIT="2")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertNotIn("All requested test checks passed", result.stdout)
        self.assertEqual(self.calls()[-1]["args"], ["-m", "coverage", "report"])
        self.assertTrue(all(c["cwd"] == str(self.project) for c in self.calls()))
        self.assertTrue(all(not Path(c["config"]).exists() for c in self.calls()))

    def test_test_failure_is_preserved_and_skips_report(self):
        result = self.run_script("run_tests.sh", TEST_EXIT="3")
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertFalse(any("report" in c["args"] for c in self.calls()))

    def test_missing_coverage_does_not_silently_disable_gate(self):
        result = self.run_script("run_tests.sh", MISSING_COVERAGE="1")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(len(self.calls()), 1)

    def test_no_coverage_is_explicit_and_does_not_check_or_install_tools(self):
        result = self.run_script("run_tests.sh", "--no-coverage")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0]["args"][:2], ["-m", "unittest"])

    def test_all_gates_pass_before_success_is_printed(self):
        result = self.run_script("run_tests.sh")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("All requested test checks passed", result.stdout)
        self.assertFalse(any("pip" in c["args"] for c in self.calls()))

    def test_bad_test_script_arguments_fail_before_running_tests(self):
        for args in [("--bad",), ("--no-coverage", "extra")]:
            result = self.run_script("run_tests.sh", *args)
            self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(self.calls(), [])

    def test_installer_uses_absolute_project_from_another_directory(self):
        result = self.install("--offline", "--no-deps")
        self.assertEqual(result.returncode, 0, result.stdout)
        call = next(c for c in self.calls() if "install" in c["args"])
        self.assertIn(str(self.project), call["args"])
        self.assertIn("--no-index", call["args"])
        self.assertIn("--no-deps", call["args"])
        self.assertNotIn("--upgrade", call["args"])
        self.assertFalse(self.launcher.exists())

    def test_default_install_preserves_existing_command(self):
        self.launcher.symlink_to("/old/pipx/stockstui")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(os.readlink(self.launcher), "/old/pipx/stockstui")

    def test_existing_or_dangling_link_requires_explicit_replacement(self):
        self.launcher.symlink_to("/old/pipx/stockstui")
        result = self.install("--link")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(os.readlink(self.launcher), "/old/pipx/stockstui")
        self.assertEqual(self.calls(), [])
        result = self.install("--replace-launcher")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(os.readlink(self.launcher), str(self.executable))

    def test_regular_files_are_preserved_even_with_replacement_flag(self):
        self.launcher.write_text("my own command")
        for flag in ("--link", "--replace-launcher"):
            result = self.install(flag)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.launcher.read_text(), "my own command")
        self.assertEqual(self.calls(), [])

    def test_failed_install_does_not_change_existing_launcher(self):
        self.launcher.symlink_to("/old/pipx/stockstui")
        result = self.install("--replace-launcher", INSTALL_EXIT="5")
        self.assertEqual(result.returncode, 5, result.stdout)
        self.assertEqual(os.readlink(self.launcher), "/old/pipx/stockstui")

    def test_command_created_during_install_is_not_overwritten(self):
        result = self.install("--link", CREATE_LAUNCHER=str(self.launcher))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.launcher.read_text(), "created while pip ran")

    def test_link_creation_and_repeated_install_are_safe(self):
        for _ in range(2):
            result = self.install("--link")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(os.readlink(self.launcher), str(self.executable))
        self.assertEqual(list(self.bin.glob(".stockstui-link.*")), [])


class TestUITypeFindings(unittest.IsolatedAsyncioTestCase):
    async def test_enter_on_list_ticker_awaits_edit_handler(self):
        view = ListsConfigView()
        with patch.object(
            view, "on_edit_ticker_pressed", new_callable=AsyncMock
        ) as edit:
            await view.on_row_selected(MagicMock())
            edit.assert_awaited_once()

    async def test_rich_news_text_is_converted_to_markdown_string(self):
        class NewsApp(App):
            def __init__(self):
                super().__init__()
                self.config = MagicMock()
                self.config.lists = {}
                self.news_ticker = None

            def compose(self) -> ComposeResult:
                yield NewsView()

        async with NewsApp().run_test() as pilot:
            view = pilot.app.query_one(NewsView)
            with patch.object(view.query_one(Markdown), "update") as update:
                view.update_content(Text("No news available."), [])
                update.assert_called_once_with("No news available.")
                update.reset_mock()
                view._highlight_current_link()
                update.assert_called_once_with("No news available.")
