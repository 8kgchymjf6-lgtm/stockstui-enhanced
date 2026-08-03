import unittest
from unittest.mock import patch, MagicMock
import datetime
from datetime import timezone, timedelta
import pandas as pd
from stockstui.data_providers import market_provider


class TestMarketProviderCoverage(unittest.TestCase):
    """Comprehensive tests for market_provider.py."""

    def setUp(self):
        """Reset caches before each test."""
        market_provider._price_cache.clear()
        market_provider._info_cache.clear()
        market_provider._news_cache.clear()
        market_provider._market_calendars.clear()

    def test_cache_population_and_retrieval(self):
        """Test populating and retrieving cache states."""
        price_data = {"AAPL": {"data": "foo"}}
        info_data = {"AAPL": {"exchange": "NYSE"}}

        market_provider.populate_price_cache(price_data)
        market_provider.populate_info_cache(info_data)

        self.assertEqual(market_provider.get_price_cache_state(), price_data)
        self.assertEqual(market_provider.get_info_cache_state(), info_data)

        self.assertTrue(market_provider.is_cached("AAPL"))
        self.assertEqual(market_provider.get_cached_price("AAPL"), "foo")
        self.assertIsNone(market_provider.get_cached_price("GOOG"))

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_market_price_data_uncached(self, mock_ticker, mock_download):
        """Test fetching data for uncached tickers."""
        # Setup mocks
        mock_ticker_obj = MagicMock()
        mock_ticker.return_value = mock_ticker_obj

        # Mock slow info
        mock_ticker_obj.info = {
            "currency": "USD",
            "exchange": "NYSE",
            "shortName": "Apple",
            "longName": "Apple Inc.",
            "currentPrice": 150.0,
        }
        # Mock fast info (though not used by download directly, it's used in slow fetch)
        mock_ticker_obj.fast_info = {"lastPrice": 150.0}

        # Mock download for fast data
        mock_df = pd.DataFrame(
            {
                ("Close", "AAPL"): [150.0],
                ("High", "AAPL"): [155.0],
                ("Low", "AAPL"): [145.0],
                ("Open", "AAPL"): [148.0],
                ("Volume", "AAPL"): [1000],
            },
            index=[pd.Timestamp.now(tz="UTC")]
        )
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_download.return_value = mock_df

        # Mock market status to be open so it fetches fast data
        with patch(
            "stockstui.data_providers.market_provider.get_market_status"
        ) as mock_status:
            mock_status.return_value = {"is_open": True}

            data = market_provider.get_market_price_data(["AAPL"])

            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["symbol"], "AAPL")
            self.assertEqual(data[0]["price"], 150.0)

            # Verify cache was updated
            self.assertTrue(market_provider.is_cached("AAPL"))

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_market_price_data_cached_fresh(self, mock_ticker, mock_download):
        """Test that fresh cached data prevents new fetches."""
        # Populate cache with fresh data
        future = datetime.datetime.now(timezone.utc) + timedelta(hours=1)
        market_provider._price_cache["AAPL"] = {
            "expiry": future,
            "data": {"symbol": "AAPL", "price": 100.0},
        }

        # Mock market status closed so no fast data fetch
        with patch(
            "stockstui.data_providers.market_provider.get_market_status"
        ) as mock_status:
            mock_status.return_value = {"is_open": False}

            data = market_provider.get_market_price_data(["AAPL"])

            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["price"], 100.0)
            mock_ticker.assert_not_called()
            mock_download.assert_not_called()

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_ticker_info(self, mock_ticker):
        """Test fetching ticker info."""
        mock_instance = mock_ticker.return_value
        mock_instance.info = {
            "currency": "USD",
            "exchange": "NYSE",
            "shortName": "Apple",
        }

        info = market_provider.get_ticker_info("AAPL")
        self.assertEqual(info["exchange"], "NYSE")
        self.assertIn("AAPL", market_provider._info_cache)

        # Test cached return
        info_cached = market_provider.get_ticker_info("AAPL")
        self.assertEqual(info_cached, info)

    def test_get_market_status_unknown_calendar(self):
        """Test market status for unknown calendar."""
        status = market_provider.get_market_status("UNKNOWN_CAL")
        self.assertEqual(status["status"], "unknown")
        self.assertTrue(status["is_open"])

    @patch("stockstui.data_providers.market_provider.mcal")
    def test_get_market_status_open(self, mock_mcal):
        """Test market status when market is open."""
        if mock_mcal is None:
            self.skipTest("pandas_market_calendars not installed")

        mock_cal = MagicMock()
        mock_mcal.get_calendar.return_value = mock_cal

        # Mock schedule
        now = pd.Timestamp.now(tz=timezone.utc)
        mock_cal.tz = timezone.utc

        # Create a schedule where now is between open and close
        schedule_df = pd.DataFrame(
            {
                "market_open": [now - timedelta(hours=1)],
                "market_close": [now + timedelta(hours=6)],
                "premarket_open": [now - timedelta(hours=2)],
                "premarket_close": [now - timedelta(hours=1)],
                "postmarket_open": [now + timedelta(hours=6)],
                "postmarket_close": [now + timedelta(hours=10)],
            },
            index=[now.floor("D")],
        )

        mock_cal.schedule.return_value = schedule_df

        status = market_provider.get_market_status("NYSE")
        self.assertEqual(status["status"], "open")
        self.assertTrue(status["is_open"])

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_news_data(self, mock_ticker):
        """Test fetching news data."""
        mock_instance = mock_ticker.return_value
        mock_instance.news = [
            {
                "content": {
                    "title": "News Title",
                    "pubDate": "2025-01-01T12:00:00Z",
                    "provider": {"displayName": "Publisher"},
                }
            }
        ]
        # Need info to proceed
        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info"
        ) as mock_info:
            mock_info.return_value = {"exchange": "NYSE"}

            news = market_provider.get_news_data("AAPL")
            self.assertEqual(len(news), 1)
            self.assertEqual(news[0]["title"], "News Title")
            self.assertEqual(news[0]["publisher"], "Publisher")

            # Verify cache
            self.assertIn("AAPL", market_provider._news_cache)

    def test_run_debug_tests(self):
        """Test debug helper functions."""
        # Cache test
        market_provider._price_cache["AAPL"] = {"data": {"price": 100}}
        results = market_provider.run_cache_test({"List1": ["AAPL"]})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["list_name"], "List1")

        # Ticker debug test
        with patch("stockstui.data_providers.market_provider.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.info = {"currency": "USD", "longName": "Apple"}
            results = market_provider.run_ticker_debug_test(["AAPL"])
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0]["is_valid"])

    @patch("stockstui.data_providers.market_provider._fetch_fast_data")
    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_ticker_info_comparison(self, mock_ticker, mock_fetch_fast):
        """Test comparing fast, slow, batch, and prepost info."""
        mock_instance = mock_ticker.return_value
        mock_instance.fast_info = {"price": 100}
        mock_instance.info = {"currentPrice": 100}

        def fetch_fast_side_effect(tickers, prepost=False):
            if prepost:
                return {"AAPL": {"price": 102}}
            return {"AAPL": {"price": 101}}
        mock_fetch_fast.side_effect = fetch_fast_side_effect

        comp = market_provider.get_ticker_info_comparison("AAPL")
        self.assertEqual(comp["fast"], {"price": 100})
        self.assertEqual(comp["slow"], {"currentPrice": 100})
        self.assertEqual(comp["batch"], {"price": 101})
        self.assertEqual(comp["prepost"], {"price": 102})
        self.assertEqual(mock_fetch_fast.call_count, 2)
        mock_fetch_fast.assert_any_call(["AAPL"])
        mock_fetch_fast.assert_any_call(["AAPL"], prepost=True)


    def test_calendar_cache_missing_dependency_and_failure(self):
        """Calendar lookup should cache successes and tolerate unavailable calendars."""
        calendar = object()
        fake_mcal = MagicMock()
        fake_mcal.get_calendar.return_value = calendar

        with patch.object(market_provider, "mcal", fake_mcal):
            first = market_provider._get_calendar("NMS")
            second = market_provider._get_calendar("NMS")

        self.assertIs(first, calendar)
        self.assertIs(second, calendar)
        fake_mcal.get_calendar.assert_called_once_with("NYSE")

        market_provider._market_calendars.clear()
        with patch.object(market_provider, "mcal", None):
            self.assertIsNone(market_provider._get_calendar("NYSE"))

        failing_mcal = MagicMock()
        failing_mcal.get_calendar.side_effect = RuntimeError("calendar failure")
        with patch.object(market_provider, "mcal", failing_mcal):
            self.assertIsNone(market_provider._get_calendar("BROKEN"))

    def test_calculate_info_expiry_future_open_and_calendar_error(self):
        """Info expiry should use the next opening or fall back to one hour."""
        future_open = pd.Timestamp.now(tz="UTC") + timedelta(hours=4)
        calendar = MagicMock()
        calendar.schedule.return_value = pd.DataFrame(
            {"market_open": [future_open]}
        )

        with patch(
            "stockstui.data_providers.market_provider._get_calendar",
            return_value=calendar,
        ):
            expiry = market_provider._calculate_info_expiry("NYSE")

        self.assertAlmostEqual(
            expiry.timestamp(),
            (future_open.to_pydatetime() + timedelta(minutes=5)).timestamp(),
            delta=2,
        )

        broken_calendar = MagicMock()
        broken_calendar.schedule.side_effect = RuntimeError("schedule failure")

        with patch(
            "stockstui.data_providers.market_provider._get_calendar",
            return_value=broken_calendar,
        ):
            fallback = market_provider._calculate_info_expiry("NYSE")

        self.assertGreater(fallback, datetime.datetime.now(timezone.utc))
        self.assertLess(
            fallback,
            datetime.datetime.now(timezone.utc) + timedelta(hours=1, seconds=5),
        )

    def test_market_price_data_normalizes_duplicates_and_empty_input(self):
        """Ticker input should be normalized, deduplicated, and safely handle emptiness."""
        self.assertEqual(
            market_provider.get_market_price_data(["", None, ""]),
            [],
        )

        future = datetime.datetime.now(timezone.utc) + timedelta(hours=1)
        market_provider._info_cache["AAPL"] = {
            "exchange": "NYSE",
            "quoteType": "EQUITY",
        }
        market_provider._price_cache["AAPL"] = {
            "expiry": future,
            "data": {"symbol": "AAPL", "price": 100.0},
        }

        with patch(
            "stockstui.data_providers.market_provider.get_market_status",
            return_value={"is_open": False},
        ):
            result = market_provider.get_market_price_data(
                ["aapl", "AAPL", "aapl"]
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["symbol"], "AAPL")

    def test_fetch_slow_data_empty_and_invalid_ticker(self):
        """Slow fetching should accept empty input and cache invalid tickers."""
        self.assertIsNone(
            market_provider._fetch_and_cache_slow_data([])
        )

        ticker = MagicMock()
        ticker.info = {}
        ticker.fast_info = {}

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ):
            market_provider._fetch_and_cache_slow_data(["INVALID"])

        cached = market_provider._price_cache["INVALID"]["data"]
        self.assertEqual(cached["description"], "Invalid Ticker")

    def test_fetch_fast_data_empty_download_and_exception(self):
        """Fast-data fetching should safely handle empty and failed downloads."""
        self.assertEqual(market_provider._fetch_fast_data([]), {})

        with patch(
            "stockstui.data_providers.market_provider.yf.download",
            return_value=pd.DataFrame(),
        ):
            self.assertEqual(
                market_provider._fetch_fast_data(["AAPL"]),
                {},
            )

        with patch(
            "stockstui.data_providers.market_provider.yf.download",
            side_effect=RuntimeError("download failed"),
        ):
            self.assertEqual(
                market_provider._fetch_fast_data(["AAPL"]),
                {},
            )

    def test_fetch_fast_data_skips_missing_close_column(self):
        """Malformed batch data should not crash extraction for a ticker."""
        dataframe = pd.DataFrame(
            {
                ("High", "AAPL"): [101.0],
                ("Low", "AAPL"): [99.0],
            },
            index=[pd.Timestamp.now(tz="UTC")],
        )
        dataframe.columns = pd.MultiIndex.from_tuples(dataframe.columns)

        with patch(
            "stockstui.data_providers.market_provider.yf.download",
            return_value=dataframe,
        ):
            result = market_provider._fetch_fast_data(["AAPL"])

        self.assertEqual(result, {})

    def test_historical_data_invalid_ticker_and_provider_exception(self):
        """Historical requests should return attributed error DataFrames."""
        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info",
            return_value=None,
        ):
            invalid = market_provider.get_historical_data(
                "BAD",
                "1mo",
            )

        self.assertTrue(invalid.empty)
        self.assertEqual(invalid.attrs["symbol"], "BAD")
        self.assertEqual(invalid.attrs["error"], "Invalid Ticker")

        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info",
            return_value={"currency": "USD"},
        ), patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            side_effect=RuntimeError("history failed"),
        ):
            failed = market_provider.get_historical_data(
                "AAPL",
                "1mo",
            )

        self.assertTrue(failed.empty)
        self.assertEqual(failed.attrs["error"], "Data Error")

    def test_news_empty_input_cache_empty_response_and_invalid_date(self):
        """News handling should cover empty input, cache hits, and malformed dates."""
        self.assertEqual(market_provider.get_news_data(""), [])

        cached_news = [{"title": "Cached"}]
        market_provider._news_cache["AAPL"] = (
            datetime.datetime.now(timezone.utc),
            cached_news,
        )

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker"
        ) as ticker_mock:
            result = market_provider.get_news_data("aapl")

        self.assertEqual(result, cached_news)
        ticker_mock.assert_not_called()

        ticker = MagicMock()
        ticker.news = []

        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info",
            return_value={"currency": "USD"},
        ), patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ):
            self.assertEqual(market_provider.get_news_data("EMPTY"), [])

        ticker.news = [
            {},
            {"content": {}},
            {
                "content": {
                    "title": "Malformed date",
                    "pubDate": "not-a-date",
                }
            },
        ]

        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info",
            return_value={"currency": "USD"},
        ), patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ):
            news = market_provider.get_news_data("BROKEN_DATE")

        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["publish_time"], "not-a-date")
        self.assertIsNone(news[0]["publish_datetime_utc"])

    def test_news_for_tickers_deduplicates_and_handles_no_results(self):
        """Combined news should remove duplicate links and distinguish empty input."""
        item_new = {
            "link": "https://example.test/one",
            "publish_datetime_utc": datetime.datetime(2026, 1, 2, tzinfo=timezone.utc),
        }
        item_old = {
            "link": "https://example.test/two",
            "publish_datetime_utc": datetime.datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

        with patch(
            "stockstui.data_providers.market_provider.get_news_data",
            side_effect=[[item_old, item_new], [item_new]],
        ):
            combined = market_provider.get_news_for_tickers(
                ["AAPL", "MSFT"]
            )

        self.assertEqual(combined, [item_new, item_old])

        self.assertEqual(
            market_provider.get_news_for_tickers([]),
            [],
        )

        with patch(
            "stockstui.data_providers.market_provider.get_news_data",
            return_value=[],
        ):
            self.assertIsNone(
                market_provider.get_news_for_tickers(["AAPL"])
            )

    def test_ticker_info_comparison_handles_each_failure(self):
        """Comparison helper should isolate batch, pre/post, and outer failures."""
        ticker = MagicMock()
        ticker.fast_info = {"lastPrice": 100}
        ticker.info = {"currency": "USD"}

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ), patch(
            "stockstui.data_providers.market_provider._fetch_fast_data",
            side_effect=[RuntimeError("batch"), RuntimeError("prepost")],
        ):
            result = market_provider.get_ticker_info_comparison("AAPL")

        self.assertEqual(result["batch"], {})
        self.assertEqual(result["prepost"], {})

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            side_effect=RuntimeError("ticker failure"),
        ):
            failed = market_provider.get_ticker_info_comparison("AAPL")

        self.assertEqual(
            failed,
            {"fast": {}, "slow": {}, "batch": {}, "prepost": {}},
        )

    def test_debug_helpers_cover_failures_and_empty_lists(self):
        """Debug helpers should report failed tickers and empty lists safely."""
        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            side_effect=RuntimeError("ticker failure"),
        ):
            ticker_results = market_provider.run_ticker_debug_test(
                ["BAD"]
            )

        self.assertFalse(ticker_results[0]["is_valid"])
        self.assertEqual(
            ticker_results[0]["description"],
            "Could not retrieve data.",
        )

        with patch(
            "stockstui.data_providers.market_provider.get_market_price_data"
        ) as fetch_mock, patch(
            "stockstui.data_providers.market_provider.time.perf_counter",
            side_effect=[10.0, 10.25],
        ):
            list_results = market_provider.run_list_debug_test(
                {
                    "Empty": [],
                    "Active": ["AAPL", "MSFT"],
                }
            )

        fetch_mock.assert_called_once_with(
            ["AAPL", "MSFT"],
            force_refresh=True,
        )

        by_name = {
            row["list_name"]: row
            for row in list_results
        }
        self.assertEqual(by_name["Empty"]["ticker_count"], 0)
        self.assertEqual(by_name["Empty"]["latency"], 0.0)
        self.assertEqual(by_name["Active"]["ticker_count"], 2)
        self.assertEqual(by_name["Active"]["latency"], 0.25)


    def test_slow_fetch_handles_unreadable_fast_info(self):
        """Slow data should fall back to info fields when fast_info cannot be read."""

        class BrokenFastInfo:
            def get(self, key, default=None):
                raise RuntimeError("fast_info unavailable")

        ticker = MagicMock()
        ticker.info = {
            "currency": "USD",
            "exchange": "NYSE",
            "longName": "Fallback Company",
            "currentPrice": 125.0,
            "sharesOutstanding": 10,
        }
        ticker.fast_info = BrokenFastInfo()

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ), patch(
            "stockstui.data_providers.market_provider._calculate_info_expiry",
            return_value=datetime.datetime.now(timezone.utc) + timedelta(hours=1),
        ):
            market_provider._fetch_and_cache_slow_data(["FALLBACK"])

        cached = market_provider._price_cache["FALLBACK"]["data"]
        self.assertEqual(cached["symbol"], "FALLBACK")
        self.assertEqual(cached["description"], "Data Unavailable")

    def test_failed_slow_fetch_preserves_existing_description(self):
        """A transient fetch failure should not overwrite useful cached data."""
        existing = {
            "symbol": "AAPL",
            "description": "Apple Inc.",
            "price": 150.0,
        }
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.datetime.now(timezone.utc),
            "data": existing.copy(),
        }

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            side_effect=RuntimeError("temporary failure"),
        ):
            market_provider._fetch_and_cache_slow_data(["AAPL"])

        cached = market_provider._price_cache["AAPL"]["data"]
        self.assertEqual(cached["description"], "Apple Inc.")
        self.assertEqual(cached["price"], 150.0)

    def test_fetch_fast_data_skips_empty_close_series(self):
        """A ticker with no usable close prices should be skipped."""
        import numpy as np

        dataframe = pd.DataFrame(
            {
                ("Close", "AAPL"): [np.nan],
                ("High", "AAPL"): [101.0],
                ("Low", "AAPL"): [99.0],
                ("Open", "AAPL"): [100.0],
                ("Volume", "AAPL"): [1000],
            },
            index=[pd.Timestamp.now(tz="UTC")],
        )
        dataframe.columns = pd.MultiIndex.from_tuples(dataframe.columns)

        with patch(
            "stockstui.data_providers.market_provider.yf.download",
            return_value=dataframe,
        ):
            result = market_provider._fetch_fast_data(["AAPL"])

        self.assertEqual(result, {})

    def test_fetch_fast_data_skips_stale_prepost_data(self):
        """Yesterday's pre/post bars must not overwrite today's cached quote."""
        old_timestamp = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)

        dataframe = pd.DataFrame(
            {
                ("Close", "AAPL"): [140.0],
                ("High", "AAPL"): [142.0],
                ("Low", "AAPL"): [139.0],
                ("Open", "AAPL"): [141.0],
                ("Volume", "AAPL"): [500],
            },
            index=[old_timestamp],
        )
        dataframe.columns = pd.MultiIndex.from_tuples(dataframe.columns)

        calendar = MagicMock()
        calendar.tz = "UTC"
        market_provider._info_cache["AAPL"] = {"exchange": "NYSE"}

        with patch(
            "stockstui.data_providers.market_provider.yf.download",
            return_value=dataframe,
        ), patch(
            "stockstui.data_providers.market_provider._get_calendar",
            return_value=calendar,
        ):
            result = market_provider._fetch_fast_data(
                ["AAPL"],
                prepost=True,
            )

        self.assertEqual(result, {})

    def test_market_status_maps_gdax_to_crypto_calendar(self):
        """GDAX should be translated before calendar lookup."""
        with patch(
            "stockstui.data_providers.market_provider._get_calendar",
            return_value=None,
        ) as calendar_mock:
            status = market_provider.get_market_status("GDAX")

        calendar_mock.assert_called_once_with("CME_Crypto")
        self.assertEqual(status["calendar"], "CME_Crypto")
        self.assertTrue(status["is_open"])

    def test_market_status_pre_and_post_sessions(self):
        """Market status should distinguish pre-market and post-market."""
        calendar = MagicMock()
        calendar.tz = "UTC"

        market_open = pd.Timestamp("2026-08-03 14:00:00", tz="UTC")
        market_close = pd.Timestamp("2026-08-03 20:00:00", tz="UTC")
        schedule = pd.DataFrame(
            {
                "market_open": [market_open],
                "market_close": [market_close],
            },
            index=pd.DatetimeIndex(
                [pd.Timestamp("2026-08-03")]
            ),
        )
        calendar.schedule.return_value = schedule

        cases = {
            pd.Timestamp("2026-08-03 10:00:00", tz="UTC"): "pre",
            pd.Timestamp("2026-08-03 21:00:00", tz="UTC"): "post",
        }

        for now, expected in cases.items():
            with self.subTest(expected=expected):
                with patch(
                    "stockstui.data_providers.market_provider._get_calendar",
                    return_value=calendar,
                ), patch(
                    "stockstui.data_providers.market_provider.pd.Timestamp.now",
                    return_value=now,
                ):
                    status = market_provider.get_market_status("NYSE")

                self.assertEqual(status["status"], expected)
                self.assertFalse(status["is_open"])

    def test_market_status_handles_schedule_exception(self):
        """Calendar failures should return the safe unknown/open fallback."""
        calendar = MagicMock()
        calendar.tz = "UTC"
        calendar.schedule.side_effect = RuntimeError("calendar failed")

        with patch(
            "stockstui.data_providers.market_provider._get_calendar",
            return_value=calendar,
        ):
            status = market_provider.get_market_status("NYSE")

        self.assertEqual(status["status"], "unknown")
        self.assertTrue(status["is_open"])

    def test_historical_data_success_sets_metadata(self):
        """Successful historical data should include symbol and currency metadata."""
        history = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.date_range("2026-01-01", periods=2),
        )
        ticker = MagicMock()
        ticker.history.return_value = history

        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info",
            return_value={"currency": "USD"},
        ), patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ):
            result = market_provider.get_historical_data(
                "aapl",
                "1mo",
            )

        self.assertIs(result, history)
        self.assertEqual(result.attrs["symbol"], "AAPL")
        self.assertEqual(result.attrs["currency"], "USD")

    def test_expired_news_cache_fetches_fresh_data(self):
        """Expired news cache entries should not be returned."""
        market_provider._news_cache["AAPL"] = (
            datetime.datetime.now(timezone.utc)
            - timedelta(seconds=market_provider.NEWS_CACHE_DURATION_SECONDS + 1),
            [{"title": "Old cached news"}],
        )

        ticker = MagicMock()
        ticker.news = [
            {
                "content": {
                    "title": "Fresh news",
                    "pubDate": "2026-08-03T12:00:00Z",
                }
            }
        ]

        with patch(
            "stockstui.data_providers.market_provider.get_ticker_info",
            return_value={"currency": "USD"},
        ), patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ):
            result = market_provider.get_news_data("aapl")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Fresh news")

    def test_ticker_info_comparison_without_slow_info(self):
        """Missing slow metadata should return four empty comparison sources."""
        ticker = MagicMock()
        ticker.fast_info = {"lastPrice": 100.0}
        ticker.info = {}

        with patch(
            "stockstui.data_providers.market_provider.yf.Ticker",
            return_value=ticker,
        ), patch(
            "stockstui.data_providers.market_provider._fetch_fast_data"
        ) as fast_mock:
            result = market_provider.get_ticker_info_comparison("BAD")

        self.assertEqual(
            result,
            {"fast": {}, "slow": {}, "batch": {}, "prepost": {}},
        )
        fast_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
