import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytz

from stockstui.data_providers import market_provider


class TestMarketProvider(unittest.TestCase):
    """
    Unit tests for the market_provider module.
    """

    def setUp(self):
        """Reset the internal caches before each test."""
        market_provider._price_cache.clear()
        market_provider._info_cache.clear()
        market_provider._news_cache.clear()
        market_provider._market_calendars.clear()

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_market_price_data_fetches_uncached(self, mock_yf_ticker):
        """Test that data is fetched for tickers not present in the cache."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.info = {
            "currency": "USD",
            "longName": "Apple Inc.",
            "exchange": "NMS",
            "regularMarketPreviousClose": 150.0,
        }
        mock_ticker_obj.fast_info = {"lastPrice": 155.0}
        mock_yf_ticker.return_value = mock_ticker_obj

        data = market_provider.get_market_price_data(["AAPL"])
        self.assertEqual(data[0]["symbol"], "AAPL")

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_get_market_price_data_uses_cache(
        self, mock_market_status, mock_yf_ticker, mock_yf_download
    ):
        """Test that fresh, cached data is used instead of making an API call."""
        now = datetime.now(timezone.utc)
        market_provider._price_cache["GOOG"] = {
            "expiry": now + timedelta(hours=1),
            "data": {"symbol": "GOOG", "price": 2800.0},
        }
        mock_market_status.return_value = {"is_open": False}
        market_provider.get_market_price_data(["GOOG"])
        mock_yf_ticker.assert_not_called()
        mock_yf_download.assert_not_called()

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_fetch_slow_data_handles_exception(self, mock_yf_ticker):
        """Test graceful failure when fetching slow data fails."""
        mock_yf_ticker.side_effect = Exception("API Error")
        market_provider._fetch_and_cache_slow_data(["FAIL"])
        self.assertEqual(
            market_provider._price_cache["FAIL"]["data"]["description"],
            "Data Unavailable",
        )

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_ticker_info_handles_exception(self, mock_yf_ticker):
        """Test graceful failure when get_ticker_info fails."""
        mock_yf_ticker.return_value.info = {}
        self.assertIsNone(market_provider.get_ticker_info("BAD"))
        mock_yf_ticker.side_effect = Exception("API Error")
        self.assertIsNone(market_provider.get_ticker_info("ERROR"))

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_news_for_invalid_ticker(self, mock_yf_ticker):
        """Test that get_news returns None for an invalid ticker."""
        mock_yf_ticker.return_value.info = {}
        self.assertIsNone(market_provider.get_news_data("INVALID"))

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_get_news_data_handles_malformed_items(self, mock_yf_ticker):
        """Test that news parsing is resilient to missing data fields."""
        mock_yf_ticker.return_value.info = {"currency": "USD"}
        # This item is missing 'summary', 'provider', and 'canonicalUrl'
        mock_yf_ticker.return_value.news = [
            {"content": {"title": "Test News", "pubDate": "2025-08-19T12:00:00.000Z"}}
        ]

        # The call should not raise an exception
        news = market_provider.get_news_data("AAPL")

        self.assertEqual(len(news), 1)
        item = news[0]
        self.assertEqual(item["title"], "Test News")
        self.assertEqual(item["summary"], "N/A")
        self.assertEqual(item["publisher"], "N/A")
        self.assertEqual(item["link"], "#")

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    @patch("stockstui.data_providers.market_provider.datetime")
    @patch("stockstui.data_providers.market_provider.pd.Timestamp.now")
    @patch("stockstui.data_providers.market_provider.mcal.get_calendar")
    def test_cache_invalidated_after_market_open(
        self, mock_get_calendar, mock_pd_now, mock_dt, mock_yf_ticker, mock_yf_download
    ):
        """
        Test that the price cache is correctly invalidated after a new market session opens.
        This ensures that stale 'previous_close' values are not used.
        """
        # 1. --- Setup a predictable market calendar ---
        mock_calendar = MagicMock()
        schedule = pd.DataFrame(
            {
                "market_open": [
                    pd.Timestamp("2025-08-18 09:30:00-0400", tz="America/New_York"),
                    pd.Timestamp("2025-08-19 09:30:00-0400", tz="America/New_York"),
                ],
                "market_close": [
                    pd.Timestamp("2025-08-18 16:00:00-0400", tz="America/New_York"),
                    pd.Timestamp("2025-08-19 16:00:00-0400", tz="America/New_York"),
                ],
            },
            index=pd.to_datetime(["2025-08-18", "2025-08-19"]),
        )
        mock_calendar.schedule.return_value = schedule
        mock_calendar.tz = "America/New_York"
        mock_get_calendar.return_value = mock_calendar

        # 2. --- Simulate Day 1: Initial fetch and cache population ---
        day1_noon_utc = datetime(2025, 8, 18, 16, 0, 0, tzinfo=timezone.utc)
        day1_noon_ny = pd.Timestamp(day1_noon_utc).tz_convert("America/New_York")
        mock_dt.now.return_value = day1_noon_utc
        mock_pd_now.return_value = day1_noon_ny

        mock_ticker_obj1 = MagicMock()
        mock_ticker_obj1.info = {
            "regularMarketPreviousClose": 100.0,
            "currency": "USD",
            "exchange": "NYSE",
        }
        mock_ticker_obj1.fast_info = {"lastPrice": 105.0}
        mock_yf_ticker.return_value = mock_ticker_obj1

        # Mock download for fast data
        mock_df1 = pd.DataFrame(
            {( "Close", "AAPL"): [105.0], ("High", "AAPL"): [106.0], ("Low", "AAPL"): [104.0], ("Open", "AAPL"): [100.0], ("Volume", "AAPL"): [1000]},
            index=[day1_noon_ny]
        )
        mock_df1.columns = pd.MultiIndex.from_tuples(mock_df1.columns)
        mock_yf_download.return_value = mock_df1

        market_provider.get_market_price_data(["AAPL"])
        
        self.assertEqual(mock_yf_ticker.call_count, 1)
        self.assertEqual(mock_yf_download.call_count, 1)
        self.assertEqual(
            market_provider._price_cache["AAPL"]["data"]["previous_close"], 100.0
        )

        # 3. --- Simulate Day 2: Time passes, market opens ---
        day2_noon_utc = datetime(2025, 8, 19, 16, 0, 0, tzinfo=timezone.utc)
        day2_noon_ny = pd.Timestamp(day2_noon_utc).tz_convert("America/New_York")
        mock_dt.now.return_value = day2_noon_utc
        mock_pd_now.return_value = day2_noon_ny

        mock_ticker_obj2 = MagicMock()
        mock_ticker_obj2.info = {
            "regularMarketPreviousClose": 105.0,
            "currency": "USD",
            "exchange": "NYSE",
        }
        mock_ticker_obj2.fast_info = {"lastPrice": 110.0}
        mock_yf_ticker.return_value = mock_ticker_obj2

        mock_df2 = pd.DataFrame(
            {( "Close", "AAPL"): [110.0], ("High", "AAPL"): [111.0], ("Low", "AAPL"): [109.0], ("Open", "AAPL"): [105.0], ("Volume", "AAPL"): [1100]},
            index=[day2_noon_ny]
        )
        mock_df2.columns = pd.MultiIndex.from_tuples(mock_df2.columns)
        mock_yf_download.return_value = mock_df2

        # 4. --- Trigger the function again (no force refresh) ---
        market_provider.get_market_price_data(["AAPL"], force_refresh=False)

        # 5. --- Assert the correct behavior ---
        # It should have called Ticker again because of expiry
        self.assertEqual(mock_yf_ticker.call_count, 2)
        self.assertEqual(mock_yf_download.call_count, 2)
        self.assertEqual(
            market_provider._price_cache["AAPL"]["data"]["previous_close"], 105.0
        )

    def test_unknown_exchange_status(self):
        """Test that unknown exchanges default to appropriate fallback status."""
        unknown_exchange = "UNKNOWN_EXCHANGE"
        status = market_provider.get_market_status(unknown_exchange)
        self.assertEqual(status["calendar"], unknown_exchange)
        # Unknown exchanges default to Open/True in fallback
        self.assertTrue(
            status["is_open"],
            "Unknown exchange should default to Open (fallback behavior)",
        )

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    @patch("stockstui.data_providers.market_provider.pd")
    @patch("stockstui.data_providers.market_provider.mcal")
    def test_gspc_exchange_mapping(self, mock_mcal, mock_pd, mock_ticker):
        """Test correct mapping of SNP/GSPC to NYSE and status check."""
        import logging

        logging.basicConfig(level=logging.ERROR)
        import pandas as real_pd

        # Configure mock_pd to use real pandas classes
        mock_pd.Timedelta = real_pd.Timedelta
        mock_pd.DataFrame = real_pd.DataFrame

        # Mock Timestamp.now to return 02:00 AM ET (Closed)
        mock_now = real_pd.Timestamp("2025-12-11 02:00:00-05:00")

        # We need mock_pd.Timestamp to maintain the Mock structure for .now() patching
        # But allow constructor calls to pass through to real Timestamp
        mock_pd.Timestamp.now.side_effect = (
            lambda tz=None: mock_now.astimezone(tz) if tz else mock_now
        )

        mock_instance = mock_ticker.return_value
        mock_instance.info = {"exchange": "SNP", "currency": "USD"}
        mock_pd.Timestamp.side_effect = lambda *args, **kwargs: real_pd.Timestamp(
            *args, **kwargs
        )

        # Setup mock calendar
        mock_cal = MagicMock()
        mock_cal.tz = pytz.timezone("America/New_York")
        mock_mcal.get_calendar.return_value = mock_cal

        # Setup mock schedule with valid data to prevent 'RangeIndex' errors
        # Create a schedule that indicates market is CLOSED at 2 AM
        # But has valid open/close times for the day
        schedule_df = pd.DataFrame(
            {
                "market_open": [pd.Timestamp("2025-12-11 09:30:00-05:00")],
                "market_close": [pd.Timestamp("2025-12-11 16:00:00-05:00")],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2025-12-11")]),
        )
        mock_cal.schedule.return_value = schedule_df

        info = market_provider.get_ticker_info("^GSPC")
        exchange = info.get("exchange")

        status = market_provider.get_market_status(exchange)

        # VERIFY MAPPING: Ensure get_calendar was called with 'NYSE', not 'SNP'
        mock_mcal.get_calendar.assert_called_with("NYSE")

        self.assertFalse(
            status["is_open"], f"Exchange {exchange} resulted in is_open=True"
        )
        self.assertEqual(status["status"], "closed", "Should be closed at 2:00 AM")

    @patch("stockstui.data_providers.market_provider.yf.download")
    def test_fast_data_does_not_overwrite_with_none(self, mock_yf_download):
        """
        Test that if fast data returns None for day_high/day_low,
        it does NOT overwrite existing valid values in the cache.
        """
        # 1. Setup cache with valid "slow" and "info" data
        market_provider._info_cache["AAPL"] = {"exchange": "NYSE", "quoteType": "EQUITY"}
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {
                "symbol": "AAPL",
                "price": 150.0,
                "day_high": 155.0,
                "day_low": 145.0,
                "volume": 1000,
            },
        }

        # 2. Simulate fast data fetch returning NaN for high/low
        # In pandas, missing values are typically NaN.
        import numpy as np
        mock_df = pd.DataFrame(
            {
                ("Close", "AAPL"): [151.0],
                ("High", "AAPL"): [np.nan],
                ("Low", "AAPL"): [np.nan],
                ("Open", "AAPL"): [150.0],
                ("Volume", "AAPL"): [1100],
            },
            index=[pd.Timestamp.now(tz="UTC")]
        )
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_yf_download.return_value = mock_df

        # 3. Trigger update
        with patch(
            "stockstui.data_providers.market_provider.get_market_status",
            return_value={"is_open": True},
        ):
            data = market_provider.get_market_price_data(["AAPL"])

        # 4. Verify results
        result = data[0]
        self.assertEqual(result["price"], 151.0, "Price should update from fast data")
        self.assertEqual(result["volume"], 1100, "Volume should update from fast data")
        self.assertEqual(
            result["day_high"], 155.0, "Day high should NOT be overwritten by None/NaN"
        )
        self.assertEqual(
            result["day_low"], 145.0, "Day low should NOT be overwritten by None/NaN"
        )

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_future_exemption_bypasses_market_hours(
        self, mock_market_status, mock_yf_download
    ):
        """Test that tickers with quoteType 'FUTURE' bypass market status checks."""
        # Setup: Market is CLOSED
        mock_market_status.return_value = {"is_open": False}

        # 1. Test FUTURE (Uppercase)
        market_provider._info_cache["ES=F"] = {"exchange": "CME", "quoteType": "FUTURE"}
        market_provider._price_cache["ES=F"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "ES=F", "price": 4500.0}
        }

        # Use a real DataFrame to avoid complex mocking of MultiIndex access
        mock_df = pd.DataFrame(
            {
                ("Close", "ES=F"): [4505.0],
                ("High", "ES=F"): [4510.0],
                ("Low", "ES=F"): [4495.0],
                ("Open", "ES=F"): [4500.0],
                ("Volume", "ES=F"): [10000]
            },
            index=[pd.Timestamp.now(tz="UTC")]
        )
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_yf_download.return_value = mock_df

        data = market_provider.get_market_price_data(["ES=F"])

        # Verify yf.download was called even though market is closed
        mock_yf_download.assert_called()
        self.assertEqual(data[0]["price"], 4505.0)

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_cryptocurrency_and_currency_exemption(
        self, mock_market_status, mock_yf_download
    ):
        """Test that CRYPTOCURRENCY and CURRENCY also bypass market status checks."""
        mock_market_status.return_value = {"is_open": False}

        # Setup BTC (CRYPTOCURRENCY) and EURUSD (CURRENCY)
        market_provider._info_cache["BTC-USD"] = {"exchange": "CCC", "quoteType": "CRYPTOCURRENCY"}
        market_provider._price_cache["BTC-USD"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "BTC-USD", "price": 60000.0}
        }

        market_provider._info_cache["EURUSD=X"] = {"exchange": "CCY", "quoteType": "CURRENCY"}
        market_provider._price_cache["EURUSD=X"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "EURUSD=X", "price": 1.10}
        }

        mock_yf_download.return_value = None # Just to see if it's called

        market_provider.get_market_price_data(["BTC-USD", "EURUSD=X"])

        # Should be called with both tickers
        called_tickers = mock_yf_download.call_args[0][0]
        self.assertIn("BTC-USD", called_tickers)
        self.assertIn("EURUSD=X", called_tickers)

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_equity_respects_market_hours(self, mock_market_status, mock_yf_download):
        """Test that regular EQUITY tickers still respect market hours."""
        mock_market_status.return_value = {"is_open": False}

        market_provider._info_cache["AAPL"] = {"exchange": "NYSE", "quoteType": "EQUITY"}
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }

        market_provider.get_market_price_data(["AAPL"])

        # yf.download should NOT be called for EQUITY when market is closed
        mock_yf_download.assert_not_called()

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_mixed_tickers_exemption(self, mock_market_status, mock_yf_download):
        """Test mixed EQUITY and FUTURE tickers when market is closed."""
        mock_market_status.return_value = {"is_open": False}

        market_provider._info_cache["AAPL"] = {"exchange": "NYSE", "quoteType": "EQUITY"}
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }

        market_provider._info_cache["ES=F"] = {"exchange": "CME", "quoteType": "FUTURE"}
        market_provider._price_cache["ES=F"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "ES=F", "price": 4500.0}
        }

        market_provider.get_market_price_data(["AAPL", "ES=F"])

        # yf.download should only be called for ES=F
        mock_yf_download.assert_called_once()
        called_tickers = mock_yf_download.call_args[0][0]
        self.assertEqual(called_tickers, ["ES=F"])

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_quote_type_case_insensitivity(self, mock_market_status, mock_yf_download):
        """Test that quoteType matching is case-insensitive."""
        mock_market_status.return_value = {"is_open": False}

        # Lowercase "future"
        market_provider._info_cache["ES=F"] = {"exchange": "CME", "quoteType": "future"}
        market_provider._price_cache["ES=F"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "ES=F", "price": 4500.0}
        }

        market_provider.get_market_price_data(["ES=F"])
        mock_yf_download.assert_called()

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_missing_quote_type_defaults_to_equity_behavior(
        self, mock_market_status, mock_yf_download
    ):
        """Test that tickers with missing quoteType respect market hours."""
        mock_market_status.return_value = {"is_open": False}

        # No quoteType field
        market_provider._info_cache["AAPL"] = {"exchange": "NYSE"}
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }

        market_provider.get_market_price_data(["AAPL"])
        mock_yf_download.assert_not_called()

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_slow_data_fetch_caches_quote_type(self, mock_yf_ticker):
        """Test that _fetch_and_cache_slow_data correctly stores quoteType."""
        mock_ticker_obj = MagicMock()
        mock_ticker_obj.info = {
            "currency": "USD",
            "exchange": "CME",
            "quoteType": "FUTURE",
            "shortName": "E-Mini S&P 500",
        }
        mock_ticker_obj.fast_info = {"lastPrice": 4500.0, "currency": "USD"}
        mock_yf_ticker.return_value = mock_ticker_obj

        market_provider._fetch_and_cache_slow_data(["ES=F"])

        self.assertIn("ES=F", market_provider._info_cache)
        self.assertEqual(market_provider._info_cache["ES=F"]["quoteType"], "FUTURE")

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_pre_post_market_fetching(self, mock_market_status, mock_yf_download):
        """Test that pre/post market data is fetched only when enabled and appropriate."""
        # 1. Setup: Market is in PRE-MARKET session
        mock_market_status.return_value = {"status": "pre", "is_open": False}

        # Security that supports pre/post
        market_provider._info_cache["AAPL"] = {
            "exchange": "NYSE",
            "quoteType": "EQUITY",
            "hasPrePostMarketData": True
        }
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }

        # Scenario A: Feature ENABLED
        market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=True)
        # Should be called with prepost=True
        self.assertTrue(mock_yf_download.call_args.kwargs.get("prepost"))
        mock_yf_download.reset_mock()

        # Scenario B: Feature DISABLED
        market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=False)
        # Should NOT be called because feature is disabled and market is not open
        mock_yf_download.assert_not_called()
        mock_yf_download.reset_mock()

        # Scenario C: Market is OPEN (Regular hours)
        mock_market_status.return_value = {"status": "open", "is_open": True}
        market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=True)
        # Should be called with prepost=False (default for regular hours)
        self.assertFalse(mock_yf_download.call_args.kwargs.get("prepost"))
        mock_yf_download.reset_mock()

        # Scenario D: Security does NOT support pre/post
        mock_market_status.return_value = {"status": "post", "is_open": False}
        market_provider._info_cache["AAPL"]["hasPrePostMarketData"] = False
        market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=True)
        # Should NOT be called because ticker doesn't support it
        mock_yf_download.assert_not_called()

    @patch("stockstui.data_providers.market_provider._fetch_and_cache_slow_data")
    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_prepost_market_fetching_closed(self, mock_market_status, mock_yf_download, mock_slow_fetch):
        """Test that pre/post market data is fetched using history when the market is closed and cache is expired/force/empty."""
        # Setup: Market is CLOSED
        mock_market_status.return_value = {"status": "closed", "is_open": False}

        # Security that supports pre/post
        market_provider._info_cache["AAPL"] = {
            "exchange": "NYSE",
            "quoteType": "EQUITY",
            "hasPrePostMarketData": True
        }

        # Scenario A: Cache is empty
        market_provider._price_cache.pop("AAPL", None)
        market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=True)
        # Should be called with prepost=True because cache is empty
        self.assertTrue(mock_yf_download.call_args.kwargs.get("prepost"))
        mock_yf_download.reset_mock()

        # Scenario B: Cache exists but is expired
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) - timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }
        market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=True)
        # Should be called with prepost=True because cache has expired
        self.assertTrue(mock_yf_download.call_args.kwargs.get("prepost"))
        mock_yf_download.reset_mock()

        # Scenario C: Cache exists, is valid, but force_refresh is True
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }
        market_provider.get_market_price_data(["AAPL"], force_refresh=True, enable_pre_post_market=True)
        # Should be called with prepost=True because force_refresh is True
        self.assertTrue(mock_yf_download.call_args.kwargs.get("prepost"))
        mock_yf_download.reset_mock()

        # Scenario D: Cache exists, is valid, and force_refresh is False
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {"symbol": "AAPL", "price": 150.0}
        }
        market_provider.get_market_price_data(["AAPL"], force_refresh=False, enable_pre_post_market=True)
        # Should NOT be called because cache is valid and not force_refresh
        mock_yf_download.assert_not_called()

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_market_cap_recalculation_with_shares(self, mock_market_status, mock_yf_download):
        """Test that market_cap is recalculated based on shares during fast price update."""
        mock_market_status.return_value = {"is_open": True}

        # Pre-populate cache with shares and a starting price/market_cap
        market_provider._info_cache["AAPL"] = {"exchange": "NYSE", "quoteType": "EQUITY"}
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {
                "symbol": "AAPL",
                "price": 100.0,
                "shares": 5000000,
                "market_cap": 500000000.0,
            },
        }

        # Mock download returning a new price of 120.0
        mock_df = pd.DataFrame(
            {
                ("Close", "AAPL"): [120.0],
                ("High", "AAPL"): [122.0],
                ("Low", "AAPL"): [119.0],
                ("Open", "AAPL"): [120.0],
                ("Volume", "AAPL"): [100000],
            },
            index=[pd.Timestamp.now(tz="UTC")]
        )
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_yf_download.return_value = mock_df

        # Fetch market price data (triggers live update and market cap recalculation)
        data = market_provider.get_market_price_data(["AAPL"])

        self.assertEqual(data[0]["price"], 120.0)
        # Expected market cap: 5000000 shares * 120.0 price = 600000000.0
        self.assertEqual(data[0]["market_cap"], 600000000.0)

    @patch("stockstui.data_providers.market_provider.yf.download")
    @patch("stockstui.data_providers.market_provider.get_market_status")
    def test_stale_pre_post_market_download_is_skipped(self, mock_market_status, mock_yf_download):
        """Test that stale pre/post market data from previous trading days is not used to overwrite fresh cache values."""
        # 1. Setup: Market is in PRE-MARKET session
        mock_market_status.return_value = {"status": "pre", "is_open": False}

        # Ticker supports pre/post
        market_provider._info_cache["AAPL"] = {
            "exchange": "NYSE",
            "quoteType": "EQUITY",
            "hasPrePostMarketData": True
        }
        # Cache has the fresh pre-market price of 155.0 from the slow fetch
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {
                "symbol": "AAPL",
                "price": 155.0,
                "volume": 500,
            }
        }

        # Mock download returning stale data from yesterday (1 day ago)
        stale_date = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)
        mock_df = pd.DataFrame(
            {
                ("Close", "AAPL"): [150.0],
                ("High", "AAPL"): [152.0],
                ("Low", "AAPL"): [149.0],
                ("Open", "AAPL"): [150.0],
                ("Volume", "AAPL"): [1000],
            },
            index=[stale_date]
        )
        mock_df.columns = pd.MultiIndex.from_tuples(mock_df.columns)
        mock_yf_download.return_value = mock_df

        # Fetch market price data (triggers _fetch_fast_data)
        data = market_provider.get_market_price_data(["AAPL"], enable_pre_post_market=True)

        # The price should still be 155.0 (the fresh pre-market price in cache)
        # instead of being overwritten by the stale price of 150.0 from yesterday's download
        self.assertEqual(data[0]["price"], 155.0)

    def test_merge_price_data_basic(self):
        """Test that merge_price_data merges updates correctly and ignores None values."""
        from stockstui.utils import merge_price_data
        existing = {
            "symbol": "AAPL",
            "price": 150.0,
            "volume": 1000,
            "description": "Apple Inc."
        }
        new_data = {
            "price": 155.0,
            "volume": None,
            "pe_ratio": 30.0
        }
        merged = merge_price_data(existing, new_data)
        self.assertEqual(merged["price"], 155.0)
        self.assertEqual(merged["volume"], 1000)
        self.assertEqual(merged["pe_ratio"], 30.0)
        self.assertEqual(merged["description"], "Apple Inc.")

    def test_merge_price_data_ath_retention(self):
        """Test that merge_price_data retains existing all_time_high if new value is None or missing."""
        from stockstui.utils import merge_price_data
        existing = {
            "symbol": "AAPL",
            "price": 150.0,
            "all_time_high": 200.0
        }
        # Case 1: new ATH is None
        new_data_none = {
            "price": 152.0,
            "all_time_high": None
        }
        merged = merge_price_data(existing, new_data_none)
        self.assertEqual(merged["all_time_high"], 200.0)

        # Case 2: new ATH is missing
        new_data_missing = {
            "price": 152.0
        }
        merged_missing = merge_price_data(existing, new_data_missing)
        self.assertEqual(merged_missing["all_time_high"], 200.0)

    def test_merge_price_data_ath_invalidation(self):
        """Test that all_time_high is updated if a new value exceeds it or if a new price/high exceeds it."""
        from stockstui.utils import merge_price_data
        existing = {
            "symbol": "AAPL",
            "price": 150.0,
            "all_time_high": 200.0
        }

        # Case 1: Higher ATH is supplied
        new_data_higher = {
            "all_time_high": 210.0
        }
        merged = merge_price_data(existing, new_data_higher)
        self.assertEqual(merged["all_time_high"], 210.0)

        # Case 2: Current price exceeds existing ATH
        new_data_price_exceeds = {
            "price": 205.0
        }
        merged = merge_price_data(existing, new_data_price_exceeds)
        self.assertEqual(merged["all_time_high"], 205.0)

        # Case 3: Day high exceeds existing ATH
        new_data_high_exceeds = {
            "day_high": 207.0
        }
        merged = merge_price_data(existing, new_data_high_exceeds)
        self.assertEqual(merged["all_time_high"], 207.0)

    @patch("stockstui.data_providers.market_provider.yf.Ticker")
    def test_slow_fetch_handles_failure_without_erasing_cache(self, mock_yf_ticker):
        """Test that if _fetch_and_cache_slow_data fails, it retains existing cached data."""
        # Pre-populate cache
        market_provider._price_cache["AAPL"] = {
            "expiry": datetime.now(timezone.utc) + timedelta(hours=1),
            "data": {
                "symbol": "AAPL",
                "price": 150.0,
                "all_time_high": 200.0,
                "description": "Apple Inc."
            }
        }

        # Mock a failed fetch (e.g. exception raised inside yf.Ticker)
        mock_yf_ticker.side_effect = Exception("Network timeout")

        # Run slow fetch
        market_provider._fetch_and_cache_slow_data(["AAPL"])

        # Cached data should not be overwritten with "Data Unavailable"
        cached = market_provider._price_cache["AAPL"]
        self.assertEqual(cached["data"]["price"], 150.0)
        self.assertEqual(cached["data"]["all_time_high"], 200.0)
        self.assertEqual(cached["data"]["description"], "Apple Inc.")


