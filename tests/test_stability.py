"""Regression coverage for confirmed price/list persistence and UI failures."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, Button, Label
from textual.worker import WorkerCancelled

from stockstui.config_manager import ConfigManager, ConfigSaveError
from stockstui.database.db_manager import DbManager
from stockstui.data_providers import market_provider as provider
from stockstui.main import StocksTUI
from stockstui.common import PriceDataUpdated
from stockstui.ui.widgets.tag_filter import TagFilterWidget
from stockstui.ui.views.config_views.general_config_view import GeneralConfigView

PACKAGE = Path(__file__).resolve().parents[1] / "stockstui"


class IsolatedConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dirs = patch(
            "stockstui.config_manager.dirs",
            SimpleNamespace(
                user_config_dir=str(self.root / "config"),
                user_cache_dir=str(self.root / "cache"),
            ),
        )
        self.dirs.start()
        self.addCleanup(self.dirs.stop)
        self.config = ConfigManager(PACKAGE)

    def test_failed_replace_restores_memory_and_preserves_file(self):
        before = deepcopy(self.config.lists)
        disk = (self.root / "config/lists.json").read_bytes()
        self.config.lists["test"] = [{"ticker": "TEST"}]
        with patch(
            "stockstui.config_manager.os.replace",
            side_effect=PermissionError("blocked"),
        ):
            with self.assertRaises(ConfigSaveError):
                self.config.save_lists()
        self.assertEqual(self.config.lists, before)
        self.assertEqual((self.root / "config/lists.json").read_bytes(), disk)
        self.assertEqual(list((self.root / "config").glob("*.tmp")), [])

    def test_non_json_value_does_not_replace_committed_file(self):
        before = (self.root / "config/settings.json").read_bytes()
        self.config.settings["refresh_interval"] = float("nan")
        with self.assertRaises(ConfigSaveError):
            self.config.save_settings()
        self.assertEqual((self.root / "config/settings.json").read_bytes(), before)
        self.assertEqual(self.config.settings["refresh_interval"], 300.0)

    def test_two_windows_merge_independent_lists(self):
        other = ConfigManager(PACKAGE)
        self.config.lists["one"] = [{"ticker": "AAPL"}]
        other.lists["two"] = [{"ticker": "MSFT"}]
        self.config.save_lists()
        other.save_lists()
        reloaded = ConfigManager(PACKAGE)
        self.assertEqual(reloaded.lists["one"], [{"ticker": "AAPL"}])
        self.assertEqual(reloaded.lists["two"], [{"ticker": "MSFT"}])
        self.assertIn("one", other.lists)

    def test_two_windows_reject_conflicting_list_edits(self):
        self.config.lists["test"] = [{"ticker": "ORIGINAL"}]
        self.config.save_lists()
        other = ConfigManager(PACKAGE)
        self.config.lists["test"] = [{"ticker": "FIRST"}]
        other.lists["test"] = [{"ticker": "SECOND"}]
        self.config.save_lists()
        with self.assertRaises(ConfigSaveError):
            other.save_lists()
        self.assertEqual(ConfigManager(PACKAGE).lists["test"], [{"ticker": "FIRST"}])
        self.assertEqual(other.lists["test"], [{"ticker": "ORIGINAL"}])

    def test_two_windows_do_not_restore_deleted_key(self):
        self.config.settings["temporary"] = 1
        self.config.save_settings()
        other = ConfigManager(PACKAGE)
        del self.config.settings["temporary"]
        self.config.save_settings()
        other.settings["refresh_interval"] = 43.0
        other.save_settings()
        self.assertNotIn(
            "temporary", json.loads((self.root / "config/settings.json").read_text())
        )

    def test_concurrent_writers_always_leave_parseable_json(self):
        managers = [ConfigManager(PACKAGE) for _ in range(4)]
        barrier = threading.Barrier(4)

        def save(index):
            manager = managers[index]
            manager.lists[f"writer_{index}"] = [{"ticker": f"T{index}"}]
            barrier.wait(5)
            manager.save_lists()

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(4)))
        data = json.loads((self.root / "config/lists.json").read_text())
        for index in range(4):
            self.assertEqual(data[f"writer_{index}"], [{"ticker": f"T{index}"}])

        # A suspended writer must not make a later UI save block indefinitely.
        from stockstui.config_manager import _configuration_lock

        lock_path = self.root / "config/.lists.json.lock"
        with _configuration_lock(lock_path):
            with self.assertRaises(ConfigSaveError):
                with _configuration_lock(lock_path, timeout=0.03):
                    self.fail("The second writer acquired an already-held lock")

    def test_reordered_lists_are_saved_and_survive_independent_edits(self):
        self.config.lists = {"first": [{"ticker": "A"}], "second": [{"ticker": "B"}]}
        self.config.save_lists()
        other = ConfigManager(PACKAGE)
        self.config.lists = dict(reversed(list(self.config.lists.items())))
        self.config.save_lists()
        self.assertEqual(
            list(json.loads((self.root / "config/lists.json").read_text())),
            ["second", "first"],
        )
        other.lists["third"] = [{"ticker": "C"}]
        other.save_lists()
        self.assertEqual(
            list(json.loads((self.root / "config/lists.json").read_text())),
            ["second", "first", "third"],
        )


class TestCacheSafety(unittest.TestCase):
    def setUp(self):
        self.old_price = provider.get_price_cache_state()
        self.old_info = provider.get_info_cache_state()
        provider._price_cache.clear()
        provider._info_cache.clear()
        self.addCleanup(self.restore)

    def restore(self):
        provider._price_cache.clear()
        provider._info_cache.clear()
        provider.populate_price_cache(self.old_price)
        provider.populate_info_cache(self.old_info)

    def entry(self, price=123.0, expired=True):
        return {
            "expiry": datetime.now(timezone.utc) + timedelta(days=-1 if expired else 1),
            "data": {
                "symbol": "AAPL",
                "price": price,
                "description": "Apple",
                "currency": "USD",
                "_fetched_at": "2020-01-01T00:00:00+00:00",
            },
        }

    def test_snapshots_do_not_change_when_live_cache_changes(self):
        provider.populate_price_cache({"AAPL": self.entry()})
        snapshot = provider.get_price_cache_state()
        provider.populate_price_cache({"MSFT": self.entry()})
        snapshot["AAPL"]["data"]["price"] = 999
        self.assertNotIn("MSFT", snapshot)
        self.assertEqual(provider.get_cached_price("AAPL")["price"], 123.0)

    def test_info_snapshot_is_independent(self):
        provider.populate_info_cache({"AAPL": {"currency": "USD"}})
        copy = provider.get_info_cache_state()
        copy["AAPL"]["currency"] = "DKK"
        self.assertEqual(provider.get_info_cache_state()["AAPL"]["currency"], "USD")

    def test_failed_fetch_preserves_quote_and_marks_it_stale(self):
        provider.populate_price_cache({"AAPL": self.entry()})
        provider.populate_info_cache({"AAPL": {"currency": "USD", "exchange": "NYSE"}})
        with (
            patch.object(provider.yf, "Ticker", side_effect=TimeoutError("offline")),
            patch.object(provider, "get_market_status", return_value={"is_open": True}),
            patch.object(provider, "_fetch_fast_data", return_value={}),
        ):
            row = provider.get_market_price_data(["AAPL"], force_refresh=True)[0]
        self.assertEqual(row["price"], 123.0)
        self.assertTrue(row["_stale"])
        self.assertEqual(row["_fetched_at"], "2020-01-01T00:00:00+00:00")

    def test_successful_fast_fetch_updates_age_and_clears_stale(self):
        provider.populate_price_cache({"AAPL": self.entry(expired=False)})
        provider.populate_info_cache({"AAPL": {"currency": "USD", "exchange": "NYSE"}})
        with (
            patch.object(provider, "get_market_status", return_value={"is_open": True}),
            patch.object(
                provider, "_fetch_fast_data", return_value={"AAPL": {"price": 456.0}}
            ),
        ):
            row = provider.get_market_price_data(["AAPL"])[0]
        self.assertEqual(row["price"], 456.0)
        self.assertFalse(row["_stale"])
        self.assertNotEqual(row["_fetched_at"], "2020-01-01T00:00:00+00:00")

    def test_snapshot_can_be_saved_while_cache_grows(self):
        provider.populate_price_cache({"AAPL": self.entry()})
        snapshot = provider.get_price_cache_state()
        with tempfile.TemporaryDirectory() as directory:
            db = DbManager(Path(directory) / "cache.db")
            db.conn.set_trace_callback(
                lambda sql: (
                    provider.populate_price_cache({"MSFT": self.entry()})
                    if sql.startswith("INSERT")
                    else None
                )
            )
            db.save_price_cache_to_db(snapshot)
            self.assertFalse(db.conn.in_transaction)
            self.assertEqual(
                db.conn.execute("SELECT COUNT(*) FROM price_cache").fetchone()[0], 1
            )
            db.close()

    def test_failed_fast_fetch_flag_survives_database_roundtrip(self):
        provider.populate_price_cache({"AAPL": self.entry(expired=False)})
        provider.populate_info_cache({"AAPL": {"currency": "USD", "exchange": "NYSE"}})
        with (
            patch.object(provider, "get_market_status", return_value={"is_open": True}),
            patch.object(provider, "_fetch_fast_data", return_value={}),
        ):
            self.assertTrue(provider.get_market_price_data(["AAPL"])[0]["_stale"])
        self.assertTrue(provider.get_cached_price("AAPL")["_stale"])
        with tempfile.TemporaryDirectory() as directory:
            db = DbManager(Path(directory) / "cache.db")
            db.save_price_cache_to_db(provider.get_price_cache_state())
            reloaded = db.load_price_cache_from_db()
            db.close()
        provider._price_cache.clear()
        provider.populate_price_cache(reloaded)
        self.assertTrue(provider.get_cached_price("AAPL")["_stale"])


async def settle(app):
    for _ in range(40):
        workers = list(app.workers)
        if not workers:
            return
        results = await asyncio.gather(
            *(w.wait() for w in workers), return_exceptions=True
        )
        for value in results:
            if isinstance(value, BaseException) and not isinstance(
                value, WorkerCancelled
            ):
                raise value
        await asyncio.sleep(0.01)
    raise TimeoutError("Workers did not finish")


def prices(a=10.0, b=20.0):
    return [
        dict(
            symbol=s,
            description=s,
            price=p,
            previous_close=p - 1,
            currency="USD",
            _fetched_at="2026-10-18T08:00:00+00:00",
            _stale=False,
        )
        for s, p in [("AAPL", a), ("MSFT", b)]
    ]


class TestPriceUIStability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.dirs = patch(
            "stockstui.config_manager.dirs",
            SimpleNamespace(
                user_config_dir=str(root / "config"), user_cache_dir=str(root / "cache")
            ),
        )
        self.dirs.start()
        self.addCleanup(self.dirs.stop)
        self.patches = [
            patch.object(
                provider, "get_market_price_data", side_effect=lambda *a, **kw: prices()
            ),
            patch.object(provider, "get_market_status", return_value={}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = StocksTUI(
            cli_overrides={
                "session_list": {"review": ["AAPL", "MSFT"]},
                "tab": "review",
            }
        )

    def rows(self, table):
        return [
            [str(getattr(c, "plain", c)) for c in table.get_row(key)]
            for key in table.rows
        ]

    async def test_search_preserves_new_prices_during_refresh_and_clear(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            table = self.app.query_one("#price-table", DataTable)
            await self.app.on_price_data_updated(PriceDataUpdated(prices(), "review"))
            self.app.action_focus_search()
            await pilot.pause()
            search = self.app.query_one("#search-box", Input)
            search.value = "AAPL"
            await pilot.pause()
            self.assertEqual(table.row_count, 1)
            await self.app.on_price_data_updated(
                PriceDataUpdated(prices(999.0, 888.0), "review")
            )
            await pilot.pause()
            self.assertEqual(table.row_count, 1)
            search.value = "AAP"
            await pilot.pause()
            self.assertIn("999", str(self.rows(table)))
            self.assertNotIn("$10.0", str(self.rows(table)))
            self.app._dismiss_search()
            await pilot.pause()
            self.assertEqual(table.row_count, 2)
            self.assertIn("888", str(self.rows(table)))

    async def test_failure_ends_loading_and_next_refresh_recovers(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            table = self.app.query_one("#price-table", DataTable)
            table.clear()
            with patch.object(
                provider, "get_market_price_data", side_effect=TimeoutError("offline")
            ):
                self.app.action_refresh(force=True)
                await settle(self.app)
                await pilot.pause()
            self.assertFalse(table.loading)
            self.assertIn(
                "failed",
                str(self.app.query_one("#last-refresh-time", Label).render()).lower(),
            )
            self.app.action_refresh(force=True)
            await settle(self.app)
            await pilot.pause()
            self.assertFalse(table.loading)
            self.assertEqual(table.row_count, 2)

    async def test_late_price_message_is_ignored(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            self.app._price_request_serial = 7
            await self.app.on_price_data_updated(
                PriceDataUpdated(prices(777.0, 888.0), "review", request_id=7)
            )
            await self.app.on_price_data_updated(
                PriceDataUpdated(prices(1.0, 2.0), "review", request_id=6)
            )
            self.assertIn(
                "777", str(self.rows(self.app.query_one("#price-table", DataTable)))
            )

    async def test_market_status_does_not_cancel_price_worker(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            entered = threading.Event()
            release = threading.Event()

            def held(*args, **kwargs):
                entered.set()
                release.wait(5)
                return prices()

            try:
                with patch.object(provider, "get_market_price_data", side_effect=held):
                    worker = self.app.fetch_prices(["AAPL"], True, "review")
                    self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                    status = self.app.fetch_market_status("NYSE")
                    await pilot.pause()
                    self.assertNotEqual(worker.group, status.group)
                    self.assertFalse(worker.is_cancelled)
                    release.set()
                    await settle(self.app)
            finally:
                release.set()

    async def test_zero_and_negative_intervals_are_rejected(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            general = self.app.query_one(GeneralConfigView)
            field = general.query_one("#refresh-interval-input", Input)
            original = self.app.config.settings["refresh_interval"]
            for bad in ["0", "-1", "nan", "inf"]:
                field.value = bad
                await pilot.pause()
                self.assertFalse(field.validate(bad).is_valid)
                general.on_update_refresh_button_pressed()
                self.assertEqual(self.app.config.settings["refresh_interval"], original)

    async def test_failed_save_does_not_show_success(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            general = self.app.query_one(GeneralConfigView)
            general.query_one("#refresh-interval-input", Input).value = "42"
            original = self.app.config.settings["refresh_interval"]
            with (
                patch(
                    "stockstui.config_manager.os.replace",
                    side_effect=PermissionError("blocked"),
                ),
                patch.object(self.app, "notify") as notify,
            ):
                general.on_update_refresh_button_pressed()
                messages = [str(c.args[0]) for c in notify.call_args_list]
                self.assertTrue(any("blocked" in s for s in messages))
                self.assertFalse(any("updated" in s for s in messages))
                self.assertEqual(self.app.config.settings["refresh_interval"], original)
            await pilot.pause()

    async def test_failed_list_add_keeps_committed_list_and_reports_error(self):
        from stockstui.ui.views.config_views.lists_config_view import ListsConfigView

        async with self.app.run_test(size=(140, 40)) as pilot:
            await settle(self.app)
            await pilot.pause()
            self.app.active_list_category = "stocks"
            before = deepcopy(self.app.config.lists["stocks"])
            view = self.app.query_one(ListsConfigView)
            with patch.object(self.app, "push_screen") as push:
                await view.on_add_ticker_pressed()
                callback = push.call_args.args[1]
            with (
                patch(
                    "stockstui.config_manager.os.replace",
                    side_effect=PermissionError("blocked"),
                ),
                patch.object(self.app, "notify") as notify,
            ):
                callback(("TEST_NEW", "", "", ""))
                messages = [str(c.args[0]) for c in notify.call_args_list]
                self.assertTrue(any("blocked" in value for value in messages))
                self.assertFalse(any("added" in value for value in messages))
                self.assertEqual(self.app.config.lists["stocks"], before)
            await pilot.pause()

    def test_shutdown_always_closes_even_after_cache_save_failure(self):
        self.app.db_manager.close()
        db = MagicMock()
        self.app.db_manager = db
        db.save_price_cache_to_db.side_effect = RuntimeError("synthetic")
        self.app.on_unmount()
        db.save_info_cache_to_db.assert_called_once()
        db.close.assert_called_once()

    def test_runtime_interval_validation_covers_file_values(self):
        self.app.config.settings["auto_refresh"] = True
        with patch.object(self.app, "set_interval") as timer:
            for bad in [0, -1, float("nan"), float("inf"), "bad"]:
                self.app.config.settings["refresh_interval"] = bad
                self.app._manage_price_refresh_timer()
            timer.assert_not_called()
        self.app.db_manager.close()

    def test_failed_position_save_does_not_change_memory(self):
        self.app.db_manager.close()
        self.app.db_manager = MagicMock()
        self.app.db_manager.save_option_position.return_value = False
        with patch.object(self.app, "notify") as notify:
            self.app.add_option_position("TEST", "AAPL", 1, 1)
            self.assertNotIn("TEST", self.app.option_positions)
            self.assertIn("not saved", notify.call_args.args[0])


class TagApp(App):
    def compose(self) -> ComposeResult:
        yield TagFilterWidget(
            ["energy/oil", "tech.growth", "dansk-æ", "tag-button-test", "growth"]
        )


class TestArbitraryTags(unittest.IsolatedAsyncioTestCase):
    async def test_tags_mount_and_preserve_original_identity(self):
        async with TagApp().run_test() as pilot:
            widget = pilot.app.query_one(TagFilterWidget)
            for button in widget.query(".tag-button"):
                button.press()
                await pilot.pause()
            self.assertEqual(
                widget.selected_tags,
                {"energy/oil", "tech.growth", "dansk-æ", "tag-button-test", "growth"},
            )


class TestQuoteStatus(unittest.TestCase):
    def test_missing_timestamp_is_not_presented_as_current(self):
        text = StocksTUI._quote_status(
            [{"symbol": "AAPL", "price": 123.0, "_stale": True}]
        )
        self.assertIn("unknown", text)
        self.assertIn("AAPL", text)
        self.assertNotIn("Last Refresh:", text)

    def test_known_old_timestamp_is_kept(self):
        text = StocksTUI._quote_status(
            [
                {
                    "symbol": "AAPL",
                    "_fetched_at": "2020-01-01T00:00:00+00:00",
                    "_stale": True,
                }
            ]
        )
        self.assertIn("2020-01-01", text)
        self.assertIn("cached", text)
