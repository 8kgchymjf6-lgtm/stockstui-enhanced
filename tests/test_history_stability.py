"""History results must belong to the current selection and request generation."""
import asyncio
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock

import pandas as pd
from textual.widgets import DataTable, Switch
from textual.worker import WorkerState

from stockstui.main import StocksTUI
from stockstui.common import HistoricalDataUpdated
from stockstui.ui.views.history_view import HistoryView


def history(value=100):
    return pd.DataFrame({"Open": [value], "High": [value + 1], "Low": [value - 1],
                         "Close": [value], "Volume": [1234]},
                        index=pd.to_datetime(["2026-10-16"]))


class TestHistoryStability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for p in (
            patch("stockstui.config_manager.dirs", SimpleNamespace(
                user_config_dir=str(root / "config"), user_cache_dir=str(root / "cache"))),
            patch("stockstui.main.market_provider.get_market_price_data", return_value=[]),
            patch("stockstui.main.market_provider.get_market_status", return_value={}),
            patch("stockstui.main.market_provider.get_historical_data", return_value=history()),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.app = StocksTUI(cli_overrides={"tab": "history"})
        self.addCleanup(self.app.db_manager.close)

    def select(self, ticker="AAPL", period="1mo", interval="1d"):
        self.app.history_ticker = ticker
        self.app.query_one("#history-display-container").loading = True
        return self.app.fetch_historical_data(ticker, period, interval)

    def message(self, data=None, **changes):
        args = dict(data=history() if data is None else data,
                    ticker=self.app.history_ticker, period=self.app._history_period,
                    interval=self.app._history_interval,
                    request_id=self.app._history_request_serial)
        args.update(changes)
        return HistoricalDataUpdated(**args)

    async def test_queued_old_ticker_period_interval_and_generation_cannot_render(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            # Keep completed messages queued while changing the selected request.
            with patch.object(self.app, "post_message", wraps=self.app.post_message) as post:
                self.select("MSFT", "1d", "5m")
                await self.app.workers.wait_for_complete()
            await pilot.pause()
            self.assertTrue(any(isinstance(c.args[0], HistoricalDataUpdated) for c in post.call_args_list))
            current = self.app._last_historical_data
            container = self.app.query_one("#history-display-container")
            view = self.app.query_one(HistoryView)
            with patch.object(view, "_render_historical_data", new_callable=AsyncMock) as render:
                for changes in (dict(ticker="AAPL"), dict(period="1y"),
                                dict(interval="1d"), dict(request_id=0)):
                    container.loading = True
                    await self.app.on_historical_data_updated(self.message(history(1), **changes))
                    self.assertIs(self.app._last_historical_data, current)
                    self.assertTrue(container.loading)
                render.assert_not_awaited()

    async def test_switch_away_and_back_rejects_first_same_ticker_response(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            for ticker, period in (("AAPL", "1mo"), ("MSFT", "1y"), ("AAPL", "1mo")):
                self.select(ticker, period)
                await self.app.workers.wait_for_complete()
                await pilot.pause()
                if self.app._history_request_serial == 1:
                    obsolete = self.message(history(1))
            latest = history(999)
            await self.app.on_historical_data_updated(self.message(latest))
            await self.app.on_historical_data_updated(obsolete)
            self.assertIs(self.app._last_historical_data, latest)
            self.assertIn("999", str(self.app.query_one("#history-table", DataTable).get_row_at(0)))

    async def test_same_selection_refresh_also_rejects_previous_generation(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            old = self.message(history(1))
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            latest = history(456)
            await self.app.on_historical_data_updated(self.message(latest))
            await self.app.on_historical_data_updated(old)
            self.assertIs(self.app._last_historical_data, latest)

    async def test_slow_cancelled_thread_cannot_overwrite_new_period(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            entered, release, finished = threading.Event(), threading.Event(), threading.Event()
            def provider(ticker, period, interval):
                if period == "1mo":
                    entered.set()
                    try:
                        if not release.wait(10):
                            raise TimeoutError("Test did not release history worker")
                        return history(1)
                    finally:
                        finished.set()
                return history(789)
            try:
                with patch("stockstui.main.market_provider.get_historical_data", side_effect=provider):
                    old_worker = self.select()
                    self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                    new_worker = self.select("AAPL", "1d", "5m")
                    await new_worker.wait()
                    await pilot.pause()
                    self.assertTrue(old_worker.is_cancelled)
                    release.set()
                    self.assertTrue(await asyncio.to_thread(finished.wait, 5))
                    await pilot.pause()
                self.assertEqual(self.app._last_historical_data.iloc[0]["Close"], 789)
                self.assertFalse(self.app.query_one("#history-display-container").loading)
            finally:
                release.set()

    async def test_exception_and_missing_result_end_loading_and_next_request_recovers(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            for failure in (TimeoutError("offline"), None):
                with patch("stockstui.main.market_provider.get_historical_data", side_effect=failure if isinstance(failure, Exception) else None, return_value=None):
                    self.select()
                    await self.app.workers.wait_for_complete()
                    await pilot.pause()
                self.assertFalse(self.app.query_one("#history-display-container").loading)
                self.assertEqual(self.app._last_historical_data.attrs["error"], "Data Error")
                text = self.app.query_one("#history-display-container > Static")
                self.assertIn("Could not process data", str(text.render()))
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(self.app.query_one("#history-table", DataTable).row_count, 1)

    async def test_obsolete_failure_does_not_replace_new_data(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            latest = self.app._last_historical_data
            failed = pd.DataFrame()
            failed.attrs.update(error="Data Error", symbol="AAPL")
            await self.app.on_historical_data_updated(self.message(failed, request_id=0))
            self.assertIs(self.app._last_historical_data, latest)

    async def test_selected_ticker_changed_before_next_request_rejects_old_data(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            old = self.message(history(1))
            latest = self.app._last_historical_data
            self.app.history_ticker = "MSFT"
            await self.app.on_historical_data_updated(old)
            self.assertIs(self.app._last_historical_data, latest)

    async def test_view_toggle_during_new_selection_does_not_render_previous_ticker(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            with patch.object(self.app, "_fetch_historical_data"):
                self.select("MSFT")
                self.assertIsNone(self.app._last_historical_data)
                self.app.query_one("#history-view-toggle", Switch).value = True
                await pilot.pause()
                self.assertEqual(len(self.app.query("#history-table")), 0)

    async def test_only_current_worker_cancellation_ends_loading(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            container = self.app.query_one("#history-display-container")
            container.loading = True
            current = object()
            self.app._current_history_worker = current
            self.app.on_history_worker_state_changed(SimpleNamespace(worker=object(), state=WorkerState.CANCELLED))
            self.assertTrue(container.loading)
            self.app.on_history_worker_state_changed(SimpleNamespace(worker=current, state=WorkerState.CANCELLED))
            self.assertFalse(container.loading)

    async def test_closing_app_rejects_results_and_new_requests(self):
        async with self.app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            self.select()
            await self.app.workers.wait_for_complete()
            await pilot.pause()
            latest = self.app._last_historical_data
            # Restore Textual's lifecycle flag before run_test performs teardown.
            with patch.object(self.app, "_closing", True):
                await self.app.on_historical_data_updated(self.message(history(1)))
                with patch.object(self.app, "_fetch_historical_data") as fetch:
                    self.assertIsNone(self.app.fetch_historical_data("MSFT", "1y"))
                    fetch.assert_not_called()
                self.assertIs(self.app._last_historical_data, latest)
