import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import time
import pandas as pd
import datetime
from stockstui.data_providers import options_provider


class TestOptionsProvider(unittest.TestCase):
    """Tests for the options_provider module."""

    def setUp(self):
        """Reset caches before each test."""
        options_provider.clear_options_cache()

    def test_is_cache_valid(self):
        """Test cache validity logic."""
        # Fresh entry
        valid_entry = {"timestamp": time.time()}
        self.assertTrue(options_provider._is_cache_valid(valid_entry))

        # Stale entry (older than TTL)
        stale_entry = {
            "timestamp": time.time() - options_provider.OPTIONS_CACHE_TTL - 1
        }
        self.assertFalse(options_provider._is_cache_valid(stale_entry))

        # Empty/None
        self.assertFalse(options_provider._is_cache_valid({}))
        self.assertFalse(options_provider._is_cache_valid(None))

    def test_clear_options_cache(self):
        """Test clearing the cache."""
        # Populate caches
        options_provider._options_cache["AAPL_nearest"] = {
            "data": "foo",
            "timestamp": time.time(),
        }
        options_provider._expirations_cache["AAPL"] = {
            "data": "bar",
            "timestamp": time.time(),
        }

        # Clear specific ticker
        options_provider.clear_options_cache("AAPL")
        self.assertNotIn("AAPL_nearest", options_provider._options_cache)
        self.assertNotIn("AAPL", options_provider._expirations_cache)

        # Populate again
        options_provider._options_cache["TSLA_nearest"] = {
            "data": "foo",
            "timestamp": time.time(),
        }

        # Clear all
        options_provider.clear_options_cache()
        self.assertEqual(len(options_provider._options_cache), 0)
        self.assertEqual(len(options_provider._expirations_cache), 0)

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_available_expirations_fetch(self, mock_ticker):
        """Test fetching expirations from API."""
        mock_instance = mock_ticker.return_value
        mock_instance.options = ("2025-01-01", "2025-02-01")

        expirations = options_provider.get_available_expirations("AAPL")

        self.assertEqual(expirations, ("2025-01-01", "2025-02-01"))
        # Verify it was cached
        self.assertIn("AAPL", options_provider._expirations_cache)
        self.assertEqual(
            options_provider._expirations_cache["AAPL"]["data"], expirations
        )

    def test_get_available_expirations_cached(self):
        """Test fetching expirations from cache."""
        cached_data = ("2025-03-01",)
        options_provider._expirations_cache["GOOG"] = {
            "data": cached_data,
            "timestamp": time.time(),
        }

        # Should not call yf.Ticker (not mocked here, so if it does it might fail or hit net)
        # But we can verify it returns cached data
        expirations = options_provider.get_available_expirations("GOOG")
        self.assertEqual(expirations, cached_data)

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_available_expirations_error(self, mock_ticker):
        """Test error handling when fetching expirations."""
        mock_instance = mock_ticker.return_value
        # Simulate property access raising an exception
        type(mock_instance).options = PropertyMock(side_effect=Exception("API Error"))

        # Suppress expected error logging during this test
        import logging

        logging.disable(logging.ERROR)
        try:
            expirations = options_provider.get_available_expirations("FAIL")
            self.assertIsNone(expirations)
        finally:
            logging.disable(logging.NOTSET)

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_options_chain_fetch(self, mock_ticker):
        """Test fetching options chain from API."""
        mock_instance = mock_ticker.return_value

        # Mock option_chain return
        mock_chain = MagicMock()
        mock_chain.calls = pd.DataFrame(
            {"strike": [100], "lastPrice": [5.0], "impliedVolatility": [0.2]}
        )
        mock_chain.puts = pd.DataFrame(
            {"strike": [100], "lastPrice": [4.0], "impliedVolatility": [0.2]}
        )
        mock_chain.underlying = {"regularMarketPrice": 105.0}

        mock_instance.option_chain.return_value = mock_chain

        result = options_provider.get_options_chain("AAPL", "2025-01-01")

        self.assertIsNotNone(result)
        self.assertIn("calls", result)
        self.assertIn("puts", result)
        self.assertEqual(result["underlying"]["regularMarketPrice"], 105.0)
        self.assertEqual(result["expiration"], "2025-01-01")

        # Verify caching
        cache_key = "AAPL_2025-01-01"
        self.assertIn(cache_key, options_provider._options_cache)

    def test_calculate_greeks_for_chain(self):
        """Test Greek calculation helper."""
        df = pd.DataFrame(
            {"strike": [100.0], "impliedVolatility": [0.2], "lastPrice": [5.0]}
        )
        underlying_price = 100.0
        # Future date
        future_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime(
            "%Y-%m-%d"
        )

        result_df = options_provider._calculate_greeks_for_chain(
            df, underlying_price, future_date, "c"
        )

        # Check if Greek columns were added
        self.assertIn("delta", result_df.columns)
        self.assertIn("gamma", result_df.columns)
        self.assertIn("theta", result_df.columns)
        self.assertIn("vega", result_df.columns)

        # Check values are calculated (not None)
        self.assertIsNotNone(result_df.iloc[0]["delta"])

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_options_chain_error(self, mock_ticker):
        """Test error handling in get_options_chain."""
        mock_instance = mock_ticker.return_value
        mock_instance.option_chain.side_effect = Exception("API Error")

        # Suppress expected error logging during this test
        import logging

        logging.disable(logging.ERROR)
        try:
            result = options_provider.get_options_chain("FAIL")
            self.assertIsNone(result)
        finally:
            logging.disable(logging.NOTSET)


    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_available_expirations_empty_result(self, mock_ticker):
        """An empty expirations response should return None."""
        mock_ticker.return_value.options = ()

        result = options_provider.get_available_expirations("AAPL")

        self.assertIsNone(result)
        self.assertNotIn("AAPL", options_provider._expirations_cache)

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_stale_expirations_cache_is_ignored(self, mock_ticker):
        """Expired cached expirations should be replaced with fresh data."""
        options_provider._expirations_cache["AAPL"] = {
            "data": ("OLD",),
            "timestamp": (
                time.time()
                - options_provider.OPTIONS_CACHE_TTL
                - 1
            ),
        }
        mock_ticker.return_value.options = ("2026-09-18",)

        result = options_provider.get_available_expirations("aapl")

        self.assertEqual(result, ("2026-09-18",))
        mock_ticker.assert_called_once_with("aapl")

    def test_calculate_greeks_returns_early_for_invalid_inputs(self):
        """Empty data or missing underlying price should be returned unchanged."""
        empty_df = pd.DataFrame()

        self.assertIsNone(
            options_provider._calculate_greeks_for_chain(
                None, 100.0, "2026-09-18", "c"
            )
        )
        self.assertIs(
            options_provider._calculate_greeks_for_chain(
                empty_df, 100.0, "2026-09-18", "c"
            ),
            empty_df,
        )

        populated_df = pd.DataFrame(
            {"strike": [100.0], "impliedVolatility": [0.2]}
        )
        self.assertIs(
            options_provider._calculate_greeks_for_chain(
                populated_df, None, "2026-09-18", "c"
            ),
            populated_df,
        )

    @patch(
        "stockstui.data_providers.options_provider."
        "black_scholes.calculate_greeks"
    )
    def test_invalid_expiration_date_uses_zero_time(
        self, mock_calculate_greeks
    ):
        """An invalid date should still calculate Greeks with T equal to zero."""
        mock_calculate_greeks.return_value = {
            "delta": 0.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
        }

        frame = pd.DataFrame(
            {"strike": [100.0], "impliedVolatility": [0.2]}
        )

        result = options_provider._calculate_greeks_for_chain(
            frame,
            105.0,
            "not-a-date",
            "c",
        )

        self.assertIn("delta", result.columns)
        self.assertEqual(
            mock_calculate_greeks.call_args.kwargs["T"],
            0,
        )

    def test_get_options_chain_uses_fresh_cache(self):
        """A fresh cached options chain should be returned directly."""
        cached_result = {
            "calls": "cached calls",
            "puts": "cached puts",
            "underlying": {},
            "expiration": "2026-09-18",
        }
        options_provider._options_cache["AAPL_2026-09-18"] = {
            "data": cached_result,
            "timestamp": time.time(),
        }

        with patch(
            "stockstui.data_providers.options_provider.yf.Ticker"
        ) as mock_ticker:
            result = options_provider.get_options_chain(
                "aapl",
                "2026-09-18",
            )

        self.assertIs(result, cached_result)
        mock_ticker.assert_not_called()

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_options_chain_without_date_skips_greeks(
        self, mock_ticker
    ):
        """A nearest-expiration request should return without Greek calculation."""
        mock_chain = MagicMock()
        mock_chain.calls = pd.DataFrame(
            {"strike": [100.0], "impliedVolatility": [0.2]}
        )
        mock_chain.puts = pd.DataFrame(
            {"strike": [100.0], "impliedVolatility": [0.2]}
        )
        mock_chain.underlying = {"regularMarketPrice": 105.0}
        mock_ticker.return_value.option_chain.return_value = mock_chain

        with patch(
            "stockstui.data_providers.options_provider."
            "_calculate_greeks_for_chain"
        ) as mock_greeks:
            result = options_provider.get_options_chain("AAPL")

        self.assertIsNotNone(result)
        self.assertIsNone(result["expiration"])
        mock_greeks.assert_not_called()

    @patch("stockstui.data_providers.options_provider.yf.Ticker")
    def test_get_options_chain_value_error(self, mock_ticker):
        """Invalid expiration errors should return None."""
        mock_ticker.return_value.option_chain.side_effect = ValueError(
            "invalid expiration"
        )

        with patch(
            "stockstui.data_providers.options_provider.logging.error"
        ) as log_error:
            result = options_provider.get_options_chain(
                "AAPL",
                "1900-01-01",
            )

        self.assertIsNone(result)
        log_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
