"""Damaged configurations must not block startup or be overwritten by recovery."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stockstui.config_manager import ConfigManager, ConfigSaveError
from stockstui.config_validation import validate_config
from stockstui.main import StocksTUI
from stockstui.data_providers import market_provider, fred_provider

PACKAGE = Path(__file__).resolve().parents[1] / "stockstui"


class TestConfigRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch(
            "stockstui.config_manager.dirs",
            SimpleNamespace(
                user_config_dir=str(self.root / "config"),
                user_cache_dir=str(self.root / "cache"),
            ),
        )
        p.start()
        self.addCleanup(p.stop)
        self.config = ConfigManager(PACKAGE)

    def path(self, name):
        return self.root / "config" / name

    def write(self, name, value):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.path(name).write_bytes(raw)
        return raw

    def test_wrong_top_level_preserves_each_original_and_protects_saves(self):
        for name in ["settings.json", "lists.json", "portfolios.json", "themes.json"]:
            with self.subTest(name=name):
                raw = self.write(name, [])
                recovered = ConfigManager(PACKAGE)
                self.assertIn(name, recovered._protected_files)
                self.assertEqual(self.path(name).read_bytes(), raw)
                self.assertEqual(self.path(name + ".bak").read_bytes(), raw)
                with self.assertRaises(ConfigSaveError):
                    recovered._atomic_save(name, {"new": "data"})
                self.assertEqual(self.path(name).read_bytes(), raw)

    def test_invalid_hidden_tabs_use_safe_values_and_preserve_other_settings(self):
        data = deepcopy(self.config.settings)
        data.update(hidden_tabs=None, theme="solarized_dark", custom={"keep": [1, 2]})
        raw = self.write("settings.json", data)
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(recovered.settings["hidden_tabs"], ["fred"])
        self.assertEqual(recovered.settings["theme"], "solarized_dark")
        self.assertEqual(recovered.settings["custom"], {"keep": [1, 2]})
        self.assertEqual(self.path("settings.json").read_bytes(), raw)

    def test_invalid_list_entries_keep_valid_personal_rows_in_memory(self):
        raw = self.write(
            "lists.json",
            {
                "personal": [
                    {
                        "ticker": "AAPL",
                        "alias": "My Apple",
                        "note": "keep",
                        "tags": "energy/oil",
                    },
                    None,
                    {"ticker": 123},
                ],
                "broken": None,
            },
        )
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(
            recovered.lists,
            {
                "personal": [
                    {
                        "ticker": "AAPL",
                        "alias": "My Apple",
                        "note": "keep",
                        "tags": "energy/oil",
                    }
                ]
            },
        )
        self.assertEqual(self.path("lists.json").read_bytes(), raw)
        recovered.lists["personal"].append({"ticker": "MSFT"})
        with self.assertRaises(ConfigSaveError):
            recovered.save_lists()
        self.assertEqual(len(recovered.lists["personal"]), 1)
        self.assertEqual(self.path("lists.json").read_bytes(), raw)

    def test_invalid_portfolio_keeps_valid_personal_portfolio(self):
        raw = self.write(
            "portfolios.json",
            {
                "portfolios": {
                    "personal": {"name": "Mine", "tickers": ["AAPL"]},
                    "broken": [],
                },
                "settings": None,
            },
        )
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(
            recovered.portfolios["portfolios"]["personal"]["tickers"], ["AAPL"]
        )
        self.assertIn("default", recovered.portfolios["portfolios"])
        self.assertEqual(self.path("portfolios.json").read_bytes(), raw)

    def test_bad_list_does_not_trigger_migration_or_block_other_saves(self):
        self.write("lists.json", [])
        portfolio_before = self.path("portfolios.json").read_bytes()
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(self.path("portfolios.json").read_bytes(), portfolio_before)
        recovered.settings["refresh_interval"] = 42.0
        recovered.save_settings()
        self.assertEqual(
            json.loads(self.path("settings.json").read_text())["refresh_interval"], 42.0
        )

    def test_bad_portfolio_does_not_trigger_migration(self):
        raw = self.write("portfolios.json", [])
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(self.path("portfolios.json").read_bytes(), raw)
        self.assertIn("portfolios.json", recovered._protected_files)

    def test_syntax_error_keeps_original_bytes(self):
        raw = b'{"personal": [broken'
        self.path("lists.json").write_bytes(raw)
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(recovered.lists, {})
        self.assertEqual(self.path("lists.json").read_bytes(), raw)
        self.assertEqual(self.path("lists.json.bak").read_bytes(), raw)

    def test_invalid_utf8_is_preserved(self):
        raw = b"\xff\xfe\x80"
        self.path("lists.json").write_bytes(raw)
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(recovered.lists, {})
        self.assertEqual(self.path("lists.json").read_bytes(), raw)
        self.assertEqual(self.path("lists.json.bak").read_bytes(), raw)

    def test_deeply_nested_json_does_not_block_recovery(self):
        raw = b'{"custom":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
        self.path("settings.json").write_bytes(raw)
        recovered = ConfigManager(PACKAGE)
        self.assertIn("settings.json", recovered._protected_files)
        self.assertEqual(self.path("settings.json").read_bytes(), raw)
        self.assertEqual(self.path("settings.json.bak").read_bytes(), raw)

    def test_existing_backup_is_never_overwritten(self):
        self.path("lists.json.bak").write_bytes(b"previous personal data")
        raw = self.write("lists.json", [])
        ConfigManager(PACKAGE)
        ConfigManager(PACKAGE)
        self.assertEqual(
            self.path("lists.json.bak").read_bytes(), b"previous personal data"
        )
        self.assertEqual(self.path("lists.json.bak.1").read_bytes(), raw)
        self.assertFalse(self.path("lists.json.bak.2").exists())

    def test_backup_failure_leaves_original_and_read_only_recovery(self):
        raw = self.write("lists.json", [])
        with patch.object(
            ConfigManager, "_backup_original", side_effect=PermissionError("blocked")
        ):
            recovered = ConfigManager(PACKAGE)
        self.assertEqual(self.path("lists.json").read_bytes(), raw)
        self.assertIn("lists.json", recovered._protected_files)
        self.assertTrue(
            any("Backup could not be created" in s for s in recovered.recovery_messages)
        )

    def test_valid_configuration_stays_writable_and_unchanged_on_load(self):
        self.config.settings["custom"] = {"enabled": True}
        self.config.save_settings()
        before = {p.name: p.read_bytes() for p in (self.root / "config").glob("*.json")}
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(recovered.recovery_messages, [])
        self.assertEqual(
            before,
            {p.name: p.read_bytes() for p in (self.root / "config").glob("*.json")},
        )
        recovered.lists["new"] = [{"ticker": "TEST"}]
        recovered.save_lists()
        self.assertEqual(
            json.loads(self.path("lists.json").read_text())["new"], [{"ticker": "TEST"}]
        )

    def test_messages_do_not_expose_api_key_or_personal_values(self):
        data = deepcopy(self.config.settings)
        data["hidden_tabs"] = None
        data["fred_settings"]["api_key"] = "PRIVATE_TEST_VALUE"
        self.write("settings.json", data)
        recovered = ConfigManager(PACKAGE)
        self.assertEqual(
            recovered.settings["fred_settings"]["api_key"], "PRIVATE_TEST_VALUE"
        )
        self.assertNotIn("PRIVATE_TEST_VALUE", " ".join(recovered.recovery_messages))

    def test_nested_field_validation(self):
        defaults = json.loads((PACKAGE / "default_configs/settings.json").read_text())
        cases = [
            {"hidden_tabs": [{}]},
            {"column_settings": [{}, None, {"key": "Price", "visible": "yes"}]},
            {"refresh_interval": 0},
            {"refresh_interval": float("inf")},
            {"refresh_interval": 10**400},
            {"market_calendar": "invalid"},
            {"fred_settings": None},
            {
                "fred_settings": {
                    "series_list": [None, "GDP", "GDP"],
                    "series_aliases": [],
                    "api_key": 123,
                }
            },
        ]
        for data in cases:
            with self.subTest(data=data):
                clean, issues = validate_config("settings.json", data, defaults)
                self.assertTrue(issues)
                self.assertIsInstance(clean, dict)

    def test_duplicate_tickers_and_columns_are_safe(self):
        lists, issues = validate_config(
            "lists.json", {"mine": [{"ticker": "aapl"}, {"ticker": "AAPL"}]}, {}
        )
        self.assertTrue(issues)
        self.assertEqual(lists["mine"], [{"ticker": "AAPL"}])
        settings, issues = validate_config(
            "settings.json",
            {"column_settings": [{"key": "Price"}, {"key": "Price"}]},
            {},
        )
        self.assertTrue(issues)
        self.assertEqual(
            settings["column_settings"], [{"key": "Price", "visible": True}]
        )

    def test_valid_custom_themes_are_retained_alongside_fallback(self):
        defaults = json.loads((PACKAGE / "default_configs/themes.json").read_text())
        theme = deepcopy(defaults["gruvbox_soft_dark"])
        theme["palette"]["unused_metadata"] = "custom text"
        clean, issues = validate_config(
            "themes.json", {"mine": theme, "broken": {"palette": None}}, defaults
        )
        self.assertTrue(issues)
        self.assertEqual(clean["mine"], theme)
        self.assertIn("gruvbox_soft_dark", clean)


class TestRecoveryStartup(unittest.IsolatedAsyncioTestCase):
    async def check_startup(self, filename, payload):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            original = json.dumps(payload).encode()
            path = config / filename
            path.write_bytes(original)
            with (
                patch(
                    "stockstui.config_manager.dirs",
                    SimpleNamespace(
                        user_config_dir=str(config), user_cache_dir=str(root / "cache")
                    ),
                ),
                patch.object(market_provider, "get_market_status", return_value={}),
                patch.object(market_provider, "get_market_price_data", return_value=[]),
                patch.object(fred_provider, "get_series_info", return_value={}),
            ):
                app = StocksTUI()
                try:
                    with patch.object(app, "notify", wraps=app.notify) as notify:
                        async with app.run_test(size=(145, 42)) as pilot:
                            await pilot.pause()
                            self.assertIn(filename, app.config._protected_files)
                            self.assertTrue(
                                any(
                                    c.kwargs.get("title")
                                    == "Read-only configuration recovery"
                                    for c in notify.call_args_list
                                )
                            )
                            self.assertFalse(
                                any(
                                    c.kwargs.get("title") == "Change not saved"
                                    for c in notify.call_args_list
                                )
                            )
                            self.assertEqual(path.read_bytes(), original)
                            await app.workers.wait_for_complete()
                    self.assertEqual(path.read_bytes(), original)
                finally:
                    app.db_manager.close()

    async def test_settings_wrong_top_level_starts(self):
        await self.check_startup("settings.json", [])

    async def test_lists_wrong_top_level_starts(self):
        await self.check_startup("lists.json", [])

    async def test_portfolios_wrong_top_level_starts(self):
        await self.check_startup("portfolios.json", [])

    async def test_hidden_tabs_null_starts(self):
        await self.check_startup("settings.json", {"hidden_tabs": None})

    async def test_nested_list_damage_starts(self):
        await self.check_startup(
            "lists.json",
            {"personal": [None, {"ticker": "AAPL", "tags": {}}, {"ticker": "AAPL"}]},
        )

    async def test_nested_portfolio_damage_starts(self):
        await self.check_startup(
            "portfolios.json", {"portfolios": None, "settings": None}
        )

    async def test_nested_settings_damage_starts(self):
        await self.check_startup(
            "settings.json",
            {
                "market_calendar": [],
                "column_settings": [{}],
                "fred_settings": None,
                "hidden_tabs": [{}],
            },
        )

    async def test_themes_wrong_top_level_starts(self):
        await self.check_startup("themes.json", [])

    async def test_bad_theme_palette_starts(self):
        await self.check_startup(
            "themes.json", {"gruvbox_soft_dark": {"palette": {"blue": "NOT A COLOR"}}}
        )
