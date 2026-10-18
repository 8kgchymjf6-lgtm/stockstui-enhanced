"""Quote timestamps stay paired with their prices through fetches and persistence."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd
from textual.app import App, ComposeResult
from textual.widgets import Input, Label

from stockstui.common import PriceDataUpdated
from stockstui.data_providers import market_provider as provider
from stockstui.database.db_manager import DbManager
from stockstui.main import StocksTUI
from stockstui.quote_time import parse_quote_time, quote_time_fields, format_quote_time
from stockstui.ui.suggesters import TickerSuggester
from stockstui.ui.views.history_view import HistoryView

STAMP = "2026-10-16T20:00:00+00:00"


class TestQuoteTime(unittest.TestCase):
    def setUp(self):
        for name in ("_price_cache", "_info_cache"):
            p = patch.object(provider, name, {})
            p.start()
            self.addCleanup(p.stop)

    def test_timestamp_accepts_epoch_and_explicit_timezones(self):
        expected = datetime.fromisoformat(STAMP)
        for value in (expected.timestamp(), STAMP, "2026-10-16T22:00:00+02:00", expected):
            self.assertEqual(parse_quote_time(value), expected)

    def test_invalid_and_naive_timestamps_are_unknown(self):
        for value in (None, True, False, float("nan"), float("inf"), 10**1000,
                      -1, 0, "bad", "2026-10-16T20:00:00", datetime(2026, 10, 16), pd.NaT):
            self.assertIsNone(parse_quote_time(value), repr(value))

    def slow(self, price=123, timestamp=STAMP):
        ticker = MagicMock()
        ticker.info = dict(currency="USD", regularMarketPrice=price,
                           regularMarketTime=timestamp, longName="Example", exchange="NMS")
        ticker.fast_info = dict(lastPrice=120, shares=1000)
        with patch.object(provider.yf, "Ticker", return_value=ticker), patch.object(
            provider, "_calculate_info_expiry", return_value=datetime.now(timezone.utc)+timedelta(hours=1)
        ):
            provider._fetch_and_cache_slow_data(["AAPL"])
        return provider.get_cached_price("AAPL")

    def test_slow_price_and_time_come_from_same_quote(self):
        row = self.slow()
        self.assertEqual(row["price"], 123)
        self.assertEqual(row["_quote_at"], STAMP)
        self.assertEqual(row["_quote_time_kind"], "quote")
        self.assertGreater(parse_quote_time(row["_fetched_at"]), parse_quote_time(STAMP))

    def test_success_without_timestamp_clears_old_quote_time(self):
        self.slow()
        row = self.slow(price=124, timestamp=None)
        self.assertIsNone(row["_quote_at"])
        self.assertIsNone(row["_quote_time_kind"])

    def test_failed_slow_fetch_preserves_quote_and_time(self):
        before = self.slow()
        with patch.object(provider.yf, "Ticker", side_effect=TimeoutError("offline")):
            provider._fetch_and_cache_slow_data(["AAPL"])
        after = provider.get_cached_price("AAPL")
        for key in ("price", "_quote_at", "_quote_time_kind", "_fetched_at"):
            self.assertEqual(after[key], before[key])
        self.assertTrue(after["_stale"])

    def test_fast_bar_timestamp_matches_last_nonempty_close(self):
        index = pd.to_datetime(["2026-10-16T19:58:00Z", "2026-10-16T19:59:00Z"])
        df = pd.DataFrame({(field, "AAPL"): values for field, values in {
            "Close": [125., float("nan")], "High": [126., 127.], "Low": [124., 125.],
            "Open": [124., 125.], "Volume": [100, 200]}.items()}, index=index)
        with patch.object(provider.yf, "download", return_value=df):
            row = provider._fetch_fast_data(["AAPL"])["AAPL"]
        self.assertEqual(row["price"], 125)
        self.assertEqual(row["_quote_at"], "2026-10-16T19:58:00+00:00")
        self.assertEqual(row["_quote_time_kind"], "bar_start")
        self.assertIn("1m bar starts", format_quote_time(row))

    def test_new_fast_price_cannot_inherit_previous_timestamp(self):
        self.slow()
        with patch.object(provider, "get_market_status", return_value={"is_open": True}), patch.object(
            provider, "_fetch_fast_data", return_value={"AAPL": {"price": 456}}
        ):
            row = provider.get_market_price_data(["AAPL"])[0]
        self.assertEqual(row["price"], 456)
        self.assertIsNone(row["_quote_at"])

    def test_failed_fast_fetch_preserves_old_timestamp(self):
        before = self.slow()
        with patch.object(provider, "get_market_status", return_value={"is_open": True}), patch.object(
            provider, "_fetch_fast_data", return_value={}
        ):
            row = provider.get_market_price_data(["AAPL"])[0]
        self.assertEqual(row["_quote_at"], before["_quote_at"])
        self.assertEqual(row["_fetched_at"], before["_fetched_at"])
        self.assertTrue(row["_stale"])

    def test_quote_time_survives_sqlite_round_trip(self):
        before = self.slow()
        with tempfile.TemporaryDirectory() as folder:
            db = DbManager(Path(folder)/"cache.db")
            try:
                db.save_price_cache_to_db(provider.get_price_cache_state())
                provider._price_cache.clear()
                provider.populate_price_cache(db.load_price_cache_from_db())
                after = provider.get_cached_price("AAPL")
                for key in ("price", "_quote_at", "_quote_time_kind", "_fetched_at"):
                    self.assertEqual(before[key], after[key])
            finally:
                db.close()

    def test_status_distinguishes_quote_bar_and_fetch_times(self):
        rows = [dict(symbol="AAPL", _stale=False, _fetched_at="2026-10-18T10:00:00+00:00",
                     **quote_time_fields(STAMP, "quote")),
                dict(symbol="BTC-USD", _stale=False, **quote_time_fields("2026-10-18T09:59:00+00:00", "bar_start")),
                dict(symbol="OLD", _stale=True)]
        text = StocksTUI._quote_status(rows)
        for expected in ("Oldest quote:", "2026-10-16", "Oldest 1m bar start:", "2026-10-18", "Quote time unknown: 1", "Oldest known fetch:", "OLD"):
            self.assertIn(expected, text)


class SuggestionApp(App):
    def compose(self) -> ComposeResult:
        yield Input(suggester=TickerSuggester([("AAPL", "Apple Inc.")]), id="ticker")
        yield Label(id="last-refresh-time")


class TestQuoteUI(unittest.IsolatedAsyncioTestCase):
    async def test_accepting_suggestion_keeps_whole_ticker_and_history_parses_it(self):
        async with SuggestionApp().run_test() as pilot:
            field = pilot.app.query_one(Input)
            for value in ("AAP", "aap", "Apple"):
                field.value = value
                field.cursor_position = len(value)
                field.focus()
                await pilot.pause()
                self.assertEqual(field._suggestion, "AAPL - Apple Inc. - AAPL")
                await pilot.press("right")
                self.assertEqual(field.value, "AAPL - Apple Inc. - AAPL")
                self.assertEqual(HistoryView()._parse_ticker_from_input(field.value), "AAPL")

    async def test_status_tooltip_includes_each_symbol_and_source(self):
        async with SuggestionApp().run_test() as pilot:
            rows = [dict(symbol="AAPL", _stale=False, _fetched_at=STAMP, **quote_time_fields(STAMP, "quote")),
                    dict(symbol="BTC-USD", _stale=False, **quote_time_fields(STAMP, "bar_start")),
                    dict(symbol="MISSING", _stale=True)]
            StocksTUI._show_quote_status(pilot.app, StocksTUI._quote_status(rows), rows)
            tip = pilot.app.query_one(Label).tooltip.plain
            for text in ("AAPL: quote", "BTC-USD: 1m bar starts", "MISSING: quote time unknown", "fetched", "cached/unverified"):
                self.assertIn(text, tip)
