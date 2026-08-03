import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import importlib
import stockstui.config_manager
from platformdirs import PlatformDirs
from stockstui.config_manager import ConfigManager


class TestConfigManager(unittest.TestCase):
    """
    Unit tests for ConfigManager. All original tests are preserved,
    now with better failure messages and flexible expectations.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)

        self.app_root = self.tmp_path / "app"
        self.user_config_dir = self.tmp_path / "user_config"
        self.user_cache_dir = self.tmp_path / "user_cache"
        self.default_dir = self.app_root / "default_configs"

        self.app_root.mkdir()
        self.user_config_dir.mkdir()
        self.user_cache_dir.mkdir()
        self.default_dir.mkdir()

        # Use the actual default settings that the ConfigManager uses
        self.default_settings = {
            "theme": "gruvbox_soft_dark",
            "auto_refresh": False,
            "refresh_interval": 30.0,
            "default_tab_category": "stocks",
            "market_calendar": "NYSE",
            "hidden_tabs": [],
        }
        self.default_lists = {"stocks": [{"ticker": "DEFAULT"}]}
        self.default_themes = {
            "gruvbox_soft_dark": {"dark": True, "palette": {"blue": "#0000ff"}}
        }
        self.default_portfolios = {"portfolios": {"default": {"tickers": []}}}

        for fname, data in [
            ("settings.json", self.default_settings),
            ("lists.json", self.default_lists),
            ("themes.json", self.default_themes),
            ("portfolios.json", self.default_portfolios),
        ]:
            (self.default_dir / fname).write_text(json.dumps(data))

        self.mock_dirs = MagicMock(spec=PlatformDirs)
        self.mock_dirs.user_config_dir = str(self.user_config_dir)
        self.mock_dirs.user_cache_dir = str(self.user_cache_dir)
        self.patcher = patch("platformdirs.PlatformDirs", return_value=self.mock_dirs)
        self.patcher.start()

        # Reload the module to use the mocked PlatformDirs
        importlib.reload(stockstui.config_manager)

    def tearDown(self):
        self.patcher.stop()
        self.tmpdir.cleanup()

    def test_initialization_creates_user_files_from_defaults(self):
        cm = ConfigManager(app_root=self.app_root)
        # Test that settings are loaded with expected defaults
        self.assertEqual(cm.settings["theme"], self.default_settings["theme"])
        self.assertEqual(cm.lists, self.default_lists)

    def test_loads_existing_user_files(self):
        user_settings = {"theme": "user_theme", "auto_refresh": False}
        settings_path = self.user_config_dir / "settings.json"
        settings_path.write_text(json.dumps(user_settings))

        cm = ConfigManager(app_root=self.app_root)
        # ConfigManager should prioritize user files over defaults
        self.assertEqual(
            cm.settings.get("theme"),
            user_settings["theme"],
            "User theme wasn't loaded correctly",
        )

    def test_handles_corrupted_json_file(self):
        settings_path = self.user_config_dir / "settings.json"
        settings_path.write_text("{not valid json")

        cm = ConfigManager(app_root=self.app_root)
        # Should fall back to default settings
        self.assertEqual(cm.settings["theme"], self.default_settings["theme"])

    def test_save_settings_creates_file(self):
        cm = ConfigManager(app_root=self.app_root)
        cm.settings["theme"] = "new_theme"
        cm.save_settings()

        settings_path = self.user_config_dir / "settings.json"
        self.assertTrue(
            settings_path.exists(), "settings.json must exist after save_settings()"
        )

        with open(settings_path, "r") as f:
            saved = json.load(f)
        self.assertEqual(
            saved.get("theme"),
            "new_theme",
            "settings.json didn't include updated theme",
        )

    def test_portfolio_migration_logic(self):
        """Test the portfolio migration logic specifically"""
        # Create test lists that should be migrated
        test_lists = {
            "stocks": [{"ticker": "AAPL"}, {"ticker": "MSFT"}],
            "crypto": [{"ticker": "BTC-USD"}],
        }

        # Write test lists to default config
        lists_path = self.default_dir / "lists.json"
        lists_path.write_text(json.dumps(test_lists))

        cm = ConfigManager(app_root=self.app_root)

        # Check if migration occurred by looking for the expected behavior
        if "portfolios" in cm.portfolios and "default" in cm.portfolios["portfolios"]:
            default_tickers = cm.portfolios["portfolios"]["default"]["tickers"]
            # Check if any of our test tickers are in the default portfolio
            test_tickers = ["AAPL", "MSFT"]
            for ticker in test_tickers:
                self.assertIn(ticker, default_tickers)
            self.assertTrue(
                cm.portfolios.get("settings", {}).get("migration_completed", False)
            )

    def test_get_setting(self):
        cm = ConfigManager(app_root=self.app_root)
        self.assertEqual(cm.get_setting("theme"), self.default_settings["theme"])
        self.assertEqual(cm.get_setting("non_existent", "default_val"), "default_val")

    def test_save_lists_and_portfolios(self):
        cm = ConfigManager(app_root=self.app_root)
        cm.lists["new_list"] = []
        cm.save_lists()
        self.assertTrue((self.user_config_dir / "lists.json").exists())

        cm.portfolios["new_p"] = {}
        cm.save_portfolios()
        self.assertTrue((self.user_config_dir / "portfolios.json").exists())

    def test_merge_default_settings(self):
        # User has some settings
        user_settings = {"theme": "user_theme"}
        (self.user_config_dir / "settings.json").write_text(json.dumps(user_settings))

        # Default has more settings
        default_settings = {
            "theme": "default_theme",
            "new_key": "new_val",
            "column_settings": [{"key": "Col1", "visible": True}],
        }
        (self.default_dir / "settings.json").write_text(json.dumps(default_settings))

        cm = ConfigManager(app_root=self.app_root)

        self.assertEqual(cm.settings["theme"], "user_theme")
        self.assertEqual(cm.settings["new_key"], "new_val")
        self.assertEqual(cm.settings["column_settings"], default_settings["column_settings"])

    def test_merge_column_settings(self):
        # User has some column settings
        user_settings = {
            "column_settings": [{"key": "Col1", "visible": False}]
        }
        (self.user_config_dir / "settings.json").write_text(json.dumps(user_settings))

        # Default has more column settings
        default_settings = {
            "column_settings": [
                {"key": "Col1", "visible": True},
                {"key": "Col2", "visible": True}
            ]
        }
        (self.default_dir / "settings.json").write_text(json.dumps(default_settings))

        cm = ConfigManager(app_root=self.app_root)

        # Col1 should be preserved from user (visible: False), Col2 should be added
        col_keys = [c["key"] for c in cm.settings["column_settings"]]
        self.assertIn("Col1", col_keys)
        self.assertIn("Col2", col_keys)

        col1 = next(c for c in cm.settings["column_settings"] if c["key"] == "Col1")
        self.assertFalse(col1["visible"])

    def test_handles_empty_user_file(self):
        settings_path = self.user_config_dir / "settings.json"
        settings_path.write_text("") # Empty file

        cm = ConfigManager(app_root=self.app_root)
        # Should fall back to default settings
        self.assertEqual(cm.settings["theme"], self.default_settings["theme"])
        # Should have created a backup
        self.assertTrue((self.user_config_dir / "settings.json.bak").exists())

    def test_atomic_save_failure(self):
        cm = ConfigManager(app_root=self.app_root)
        # Mock os.replace to fail
        with patch("os.replace", side_effect=OSError("Replace failed")):
            with self.assertLogs(level="ERROR") as log:
                cm._atomic_save("test.json", {"a": 1})
                self.assertIn("Replace failed", log.output[0])


    def test_merge_defaults_handles_invalid_default_json(self):
        """Invalid default settings during merging should be logged, not raised."""
        (self.user_config_dir / "settings.json").write_text(
            json.dumps({"theme": "user_theme"})
        )
        (self.default_dir / "settings.json").write_text("{invalid json")

        with self.assertLogs(level="ERROR") as logs:
            cm = stockstui.config_manager.ConfigManager(
                app_root=self.app_root
            )

        self.assertEqual(cm.settings["theme"], "user_theme")
        self.assertTrue(
            any(
                "Failed to merge default settings" in message
                for message in logs.output
            )
        )

    def test_corrupted_file_backup_failure_still_restores_default(self):
        """A failed backup must not prevent restoration from defaults."""
        settings_path = self.user_config_dir / "settings.json"
        settings_path.write_text("{broken json")

        original_replace = stockstui.config_manager.os.replace

        def replace_side_effect(source, destination):
            if str(destination).endswith(".bak"):
                raise OSError("backup failed")
            return original_replace(source, destination)

        with patch(
            "stockstui.config_manager.os.replace",
            side_effect=replace_side_effect,
        ), self.assertLogs(level="ERROR") as logs:
            cm = stockstui.config_manager.ConfigManager(
                app_root=self.app_root
            )

        self.assertEqual(
            cm.settings["theme"],
            self.default_settings["theme"],
        )
        self.assertTrue(
            any(
                "Could not back up corrupted file" in message
                for message in logs.output
            )
        )

    def test_invalid_default_file_returns_empty_dict(self):
        """A malformed default file should produce an empty config safely."""
        filename = "broken.json"
        (self.default_dir / filename).write_text("{invalid json")

        cm = stockstui.config_manager.ConfigManager.__new__(
            stockstui.config_manager.ConfigManager
        )
        cm.user_config_dir = self.user_config_dir
        cm.default_dir = self.default_dir

        with self.assertLogs(level="ERROR") as logs:
            result = cm._load_or_create(filename)

        self.assertEqual(result, {})
        self.assertTrue(
            any(
                "Failed to create user config" in message
                for message in logs.output
            )
        )

    def test_missing_default_file_returns_empty_dict(self):
        """A missing default file should return an empty config."""
        cm = stockstui.config_manager.ConfigManager.__new__(
            stockstui.config_manager.ConfigManager
        )
        cm.user_config_dir = self.user_config_dir
        cm.default_dir = self.default_dir

        with self.assertLogs(level="CRITICAL"):
            result = cm._load_or_create("missing.json")

        self.assertEqual(result, {})

    def test_migration_returns_when_portfolios_structure_is_missing(self):
        """Migration should do nothing when the portfolios root is absent."""
        cm = stockstui.config_manager.ConfigManager.__new__(
            stockstui.config_manager.ConfigManager
        )
        cm.portfolios = {}
        cm.lists = {"stocks": [{"ticker": "AAPL"}]}

        with patch.object(cm, "save_portfolios") as save_mock:
            cm._migrate_stocks_to_default_portfolio()

        save_mock.assert_not_called()

    def test_migration_returns_when_already_completed(self):
        """Completed migrations should not run or save again."""
        cm = stockstui.config_manager.ConfigManager.__new__(
            stockstui.config_manager.ConfigManager
        )
        cm.portfolios = {
            "portfolios": {"default": {"tickers": []}},
            "settings": {"migration_completed": True},
        }
        cm.lists = {"stocks": [{"ticker": "AAPL"}]}

        with patch.object(cm, "save_portfolios") as save_mock:
            cm._migrate_stocks_to_default_portfolio()

        save_mock.assert_not_called()

    def test_migration_marks_complete_without_stock_tickers(self):
        """Migration should complete safely when no usable stock tickers exist."""
        cm = stockstui.config_manager.ConfigManager.__new__(
            stockstui.config_manager.ConfigManager
        )
        cm.portfolios = {
            "portfolios": {"default": {"tickers": []}}
        }
        cm.lists = {
            "stocks": [
                {"name": "Missing ticker"},
                {},
            ]
        }

        with patch.object(cm, "save_portfolios") as save_mock:
            cm._migrate_stocks_to_default_portfolio()

        self.assertTrue(
            cm.portfolios["settings"]["migration_completed"]
        )
        self.assertEqual(
            cm.portfolios["portfolios"]["default"]["tickers"],
            [],
        )
        save_mock.assert_called_once()
