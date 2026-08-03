import unittest
from unittest.mock import patch
import pandas as pd
from datetime import datetime, timedelta, timezone
from rich.text import Text
from textual.app import App

from stockstui.presentation import formatter


class TestFormatter(unittest.IsolatedAsyncioTestCase):
    """Unit tests for data formatting functions."""

    async def test_format_historical_data_as_table(self):
        """Test formatting historical data into a DataTable."""
        # Daily data
        dates_daily = pd.to_datetime(["2025-01-01", "2025-01-02"])
        df_daily = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [105.0, 106.0],
                "Low": [99.0, 100.0],
                "Close": [102.0, 103.0],
                "Volume": [1000, 2000],
            },
            index=dates_daily,
        )

        # We need an active app context for DataTable to measure columns
        app = App()
        async with app.run_test():
            table_daily = formatter.format_historical_data_as_table(df_daily)
            self.assertEqual(str(table_daily.columns["Date"].label), "Date")

            # Intraday data
            dates_intraday = pd.to_datetime(["2025-01-01 10:00", "2025-01-01 11:00"])
            df_intraday = pd.DataFrame(
                {
                    "Open": [100.0, 101.0],
                    "High": [105.0, 106.0],
                    "Low": [99.0, 100.0],
                    "Close": [102.0, 103.0],
                    "Volume": [1000, 2000],
                },
                index=dates_intraday,
            )

            table_intraday = formatter.format_historical_data_as_table(df_intraday)
            self.assertEqual(str(table_intraday.columns["Date"].label), "Timestamp")

    def test_format_price_data_for_table(self):
        """Test the formatting of price data, including change calculation and aliasing."""
        sample_data = [
            {
                "symbol": "AAPL",
                "description": "Apple Inc.",
                "price": 155.25,
                "previous_close": 150.00,
                "day_low": 154.0,
                "day_high": 156.0,
                "fifty_two_week_low": 120.0,
                "fifty_two_week_high": 180.0,
            }
        ]
        old_prices = {"AAPL": 155.00}  # Price went up
        alias_map = {"AAPL": "My Apple Stock"}

        result = formatter.format_price_data_for_table(
            sample_data, old_prices, alias_map
        )

        self.assertEqual(len(result), 1)
        row = result[0]

        # Assert on dictionary keys
        self.assertEqual(row["Description"], "My Apple Stock")  # Alias should be used
        self.assertEqual(row["Price"], 155.25)
        self.assertAlmostEqual(row["Change"], 5.25)
        self.assertAlmostEqual(row["% Change"], 5.25 / 150.0)
        self.assertEqual(row["Day's Range"], "$154.0–156.0")
        self.assertEqual(row["52-Wk Range"], "$120.0–180.0")
        self.assertEqual(row["Ticker"], "AAPL")
        self.assertEqual(
            row["_change_direction"], "up"
        )  # Price increased vs old_prices

    def test_format_price_data_direction_down(self):
        """Test that change direction is 'down' when price decreases."""
        sample_data = [{"symbol": "TSLA", "price": 800.0}]
        old_prices = {"TSLA": 801.0}

        row = formatter.format_price_data_for_table(sample_data, old_prices, {})[0]
        self.assertEqual(row["_change_direction"], "down")

    def test_format_price_data_direction_none(self):
        """Test that change direction is None when price is unchanged or old price is missing."""
        sample_data = [{"symbol": "GOOG", "price": 2800.0}]

        # No old price
        row_no_old = formatter.format_price_data_for_table(sample_data, {}, {})[0]
        self.assertIsNone(row_no_old["_change_direction"])

        # Same old price
        old_prices_same = {"GOOG": 2800.0}
        row_same = formatter.format_price_data_for_table(
            sample_data, old_prices_same, {}
        )[0]
        self.assertIsNone(row_same["_change_direction"])

    def test_format_news_for_display(self):
        """Test formatting of news data into a markdown string."""
        sample_news = [
            {
                "source_ticker": "NVDA",
                "title": "Big News!",
                "link": "http://example.com",
                "publisher": "A Publisher",
                "publish_time": "2025-08-19 12:00 UTC",
                "summary": "A summary of the news.",
            }
        ]

        markdown, urls = formatter.format_news_for_display(sample_news)

        self.assertIn("Source: **`NVDA`**", markdown)
        self.assertIn("**[Big News!](http://example.com)**", markdown)
        self.assertIn("By A Publisher at 2025-08-19 12:00 UTC", markdown)
        self.assertIn("A summary of the news.", markdown)
        self.assertEqual(urls, ["http://example.com"])

    def test_format_empty_news(self):
        """Test formatting for an empty news list."""
        markdown, urls = formatter.format_news_for_display([])
        self.assertIsInstance(markdown, Text)
        self.assertIn("No news found", markdown.plain)
        self.assertEqual(urls, [])

    def test_format_market_status(self):
        """Test the formatting of market status into a user-friendly string and styling info."""
        status_dict = {
            "calendar": "NYSE",
            "status": "open",
            "holiday": None,
            "next_close": None,
        }
        result = formatter.format_market_status(status_dict)
        text, text_parts = result
        self.assertIsInstance(text, str)
        self.assertIn("NYSE", text)
        self.assertIsInstance(text_parts, list)

        status_dict_holiday_named = {
            "calendar": "NYSE",
            "status": "closed",
            "holiday": "Christmas",
            "next_open": None,
            "reason": "holiday",
        }
        result_holiday_named = formatter.format_market_status(status_dict_holiday_named)
        self.assertIsNotNone(result_holiday_named)
        self.assertIn("(Holiday: Christmas)", result_holiday_named[1][1][0])

        status_dict_holiday_generic = {
            "calendar": "NYSE",
            "status": "closed",
            "holiday": "Holiday",
            "next_open": None,
            "reason": "holiday",
        }
        result_holiday_generic = formatter.format_market_status(
            status_dict_holiday_generic
        )
        self.assertIsNotNone(result_holiday_generic)
        self.assertIn("(Holiday)", result_holiday_generic[1][1][0])

        status_dict_holiday_none = {
            "calendar": "NYSE",
            "status": "closed",
            "holiday": None,
            "next_open": None,
            "reason": "holiday",
        }
        result_holiday_none = formatter.format_market_status(status_dict_holiday_none)
        self.assertIsNotNone(result_holiday_none)
        self.assertIn("(Holiday)", result_holiday_none[1][1][0])

        # Test invalid input
        self.assertIsNone(formatter.format_market_status(None))
        self.assertIsNone(formatter.format_market_status("not a dict"))

    def test_format_debug_tables(self):
        """Test formatting for various debug data tables."""
        # Ticker debug
        ticker_data = [
            {"symbol": "A", "is_valid": True, "description": "Desc", "latency": 0.1}
        ]
        rows_ticker = formatter.format_ticker_debug_data_for_table(ticker_data)
        self.assertEqual(rows_ticker[0], ("A", True, "Desc", 0.1))

        # List debug
        list_data = [{"list_name": "L1", "ticker_count": 10, "latency": 0.5}]
        rows_list = formatter.format_list_debug_data_for_table(list_data)
        self.assertEqual(rows_list[0], ("L1", 10, 0.5))

        # Cache test
        cache_data = [{"list_name": "C1", "ticker_count": 5, "latency": 0.2}]
        rows_cache = formatter.format_cache_test_data_for_table(cache_data)
        self.assertEqual(rows_cache[0], ("C1", 5, 0.2))

    def test_format_info_comparison(self):
        """Test comparing fast, slow, batch, and prepost info dictionaries."""
        fast = {"a": 1, "b": 2}
        slow = {"a": 1, "b": 3, "c": 4}
        batch = {"a": 1, "b": 2, "d": 5}
        prepost = {"a": 1, "b": 2, "e": 6}

        rows = formatter.format_info_comparison(fast, slow, batch, prepost)

        # Expect 5 rows: a, b, c, d, e
        self.assertEqual(len(rows), 5)

        # Check 'a' - match across all four
        row_a = next(r for r in rows if r[0] == "a")
        self.assertEqual(row_a, ("a", "1", "1", "1", "1", False))

        # Check 'b' - mismatch (fast/batch/prepost have 2, slow has 3)
        row_b = next(r for r in rows if r[0] == "b")
        self.assertEqual(row_b, ("b", "2", "2", "2", "3", True))

        # Check 'c' - missing in fast/batch/prepost
        row_c = next(r for r in rows if r[0] == "c")
        self.assertEqual(row_c, ("c", "N/A", "N/A", "N/A", "4", False))

        # Check 'd' - present only in batch
        row_d = next(r for r in rows if r[0] == "d")
        self.assertEqual(row_d, ("d", "N/A", "5", "N/A", "N/A", False))

        # Check 'e' - present only in prepost
        row_e = next(r for r in rows if r[0] == "e")
        self.assertEqual(row_e, ("e", "N/A", "N/A", "6", "N/A", False))

        # Test error case
        rows_err = formatter.format_info_comparison({}, {})
        self.assertEqual(rows_err[0][0], "Error")

        # Test handling of objects that raise exceptions during key lookup (like yfinance's FastInfo)
        class ExceptionThrowingDict(dict):
            def keys(self):
                return ["currency", "lastPrice"]
            def get(self, key, default=None):
                if key == "currency":
                    raise KeyError("currency")
                return super().get(key, default)

        fast_raising = ExceptionThrowingDict({"lastPrice": 100})
        slow = {"currency": "USD", "lastPrice": 100}
        rows_raising = formatter.format_info_comparison(fast_raising, slow)

        # Check that 'currency' was safely handled and set to "N/A" for fast_info
        row_currency = next(r for r in rows_raising if r[0] == "currency")
        self.assertEqual(row_currency, ("currency", "N/A", "N/A", "N/A", "USD", False))

        # Test handling of unhashable values (e.g. lists/dicts under keys like companyOfficers)
        unhashable_fast = {"companyOfficers": [{"name": "A"}]}
        unhashable_slow = {"companyOfficers": [{"name": "A"}]}
        unhashable_batch = {"companyOfficers": [{"name": "B"}]}

        # No mismatch
        rows_no_mismatch = formatter.format_info_comparison(unhashable_fast, unhashable_slow)
        row_co_no = next(r for r in rows_no_mismatch if r[0] == "companyOfficers")
        self.assertFalse(row_co_no[5])

        # Mismatch (different list content)
        rows_mismatch = formatter.format_info_comparison(unhashable_fast, unhashable_slow, unhashable_batch)
        row_co_yes = next(r for r in rows_mismatch if r[0] == "companyOfficers")
        self.assertTrue(row_co_yes[5])

    def test_escape(self):
        """Test escaping special characters for Rich markdown."""
        text = "Hello [World] *"
        escaped = formatter.escape(text)
        self.assertEqual(escaped, r"Hello \[World\] \*")


    def test_format_market_cap_all_ranges(self):
        """Market caps should use the appropriate magnitude suffix."""
        self.assertEqual(formatter.format_market_cap("invalid"), "N/A")
        self.assertEqual(formatter.format_market_cap(2_000_000_000_000), "2.00T")
        self.assertEqual(formatter.format_market_cap(3_000_000_000), "3.00B")
        self.assertEqual(formatter.format_market_cap(4_000_000), "4.00M")
        self.assertEqual(formatter.format_market_cap(5_000), "5.00K")
        self.assertEqual(formatter.format_market_cap(999), "999")
        self.assertEqual(formatter.format_market_cap(-2_000_000), "-2.00M")

    def test_get_currency_symbol_fallbacks(self):
        """Currency symbols should be case-insensitive and safely default."""
        self.assertEqual(formatter.get_currency_symbol("eur"), "€")
        self.assertEqual(formatter.get_currency_symbol(None), "$")
        self.assertEqual(formatter.get_currency_symbol("UNKNOWN"), "$")

    def test_format_price_data_volume_ranges_and_missing_values(self):
        """Volumes should be formatted across all supported magnitude ranges."""
        data = [
            {"symbol": "BILLION", "volume": 2_500_000_000},
            {"symbol": "MILLION", "volume": 2_500_000},
            {"symbol": "THOUSAND", "volume": 2_500},
            {"symbol": "SMALL", "volume": 25},
            {"symbol": "MISSING", "volume": None},
        ]

        rows = formatter.format_price_data_for_table(data, {}, {})
        by_ticker = {row["Ticker"]: row for row in rows}

        self.assertEqual(by_ticker["BILLION"]["Volume"], "2.5B")
        self.assertEqual(by_ticker["MILLION"]["Volume"], "2.5M")
        self.assertEqual(by_ticker["THOUSAND"]["Volume"], "2K")
        self.assertEqual(by_ticker["SMALL"]["Volume"], "25")
        self.assertEqual(by_ticker["MISSING"]["Volume"], "N/A")

    def test_format_price_data_trailing_currency_and_fallbacks(self):
        """Trailing currencies and absent numerical values should format safely."""
        data = [
            {
                "symbol": "NOVO-B.CO",
                "currency": "DKK",
                "day_low": 500.0,
                "day_high": 510.0,
                "fifty_two_week_low": 400.0,
                "fifty_two_week_high": 700.0,
                "open": 505.0,
                "previous_close": 504.0,
            },
            {
                "symbol": "EMPTY",
                "currency": "USD",
            },
        ]

        rows = formatter.format_price_data_for_table(data, {}, {})
        novo, empty = rows

        self.assertEqual(novo["Day's Range"], "500.0–510.0 DKK")
        self.assertEqual(novo["52-Wk Range"], "400.0–700.0 DKK")
        self.assertEqual(novo["Open"], "505.0 DKK")
        self.assertEqual(novo["Prev Close"], "504.0 DKK")

        self.assertEqual(empty["Day's Range"], "N/A")
        self.assertEqual(empty["52-Wk Range"], "N/A")
        self.assertEqual(empty["Open"], "N/A")
        self.assertEqual(empty["Prev Close"], "N/A")

    def test_format_info_comparison_handles_all_get_errors(self):
        """Every comparison source should tolerate failing get operations."""
        class RaisingMapping:
            def keys(self):
                return {"price"}

            def get(self, key, default=None):
                raise RuntimeError("lookup failed")

        rows = formatter.format_info_comparison(
            RaisingMapping(),
            RaisingMapping(),
            RaisingMapping(),
            RaisingMapping(),
        )

        self.assertEqual(
            rows,
            [("price", "N/A", "N/A", "N/A", "N/A", False)],
        )

    def test_format_news_with_missing_fields(self):
        """Missing news fields should be displayed as dimmed N/A values."""
        markdown, urls = formatter.format_news_for_display([{}])

        self.assertIn("[dim]N/A[/dim]", markdown)
        self.assertIn("By [dim]N/A[/dim] at [dim]N/A[/dim]", markdown)
        self.assertIn("**Summary:**\n[dim]N/A[/dim]", markdown)
        self.assertEqual(urls, [])

    def test_format_market_status_pre_post_and_weekend(self):
        """Pre-market, post-market, and weekend states should be labelled."""
        pre = formatter.format_market_status(
            {"calendar": "NYSE", "status": "pre"}
        )
        post = formatter.format_market_status(
            {"calendar": "NYSE", "status": "post"}
        )
        weekend = formatter.format_market_status(
            {
                "calendar": "NYSE",
                "status": "closed",
                "reason": "weekend",
            }
        )

        self.assertEqual(pre[1][0], ("PRE ", "status-pre"))
        self.assertEqual(post[1][0], ("AFTER ", "status-post"))
        self.assertIn("(Weekend)", weekend[1][1][0])

    def test_format_market_status_next_close_and_open(self):
        """Market status should include the relevant next trading event."""
        now = datetime.now(timezone.utc)

        open_status = formatter.format_market_status(
            {
                "calendar": "NYSE",
                "status": "open",
                "is_open": True,
                "next_close": now + timedelta(hours=2),
            }
        )
        self.assertTrue(
            any("Closes" in part[0] for part in open_status[1])
        )

        closed_today = formatter.format_market_status(
            {
                "calendar": "NYSE",
                "status": "closed",
                "is_open": False,
                "next_open": now + timedelta(hours=1),
            }
        )
        self.assertTrue(
            any("Opens" in part[0] for part in closed_today[1])
        )

        closed_future = formatter.format_market_status(
            {
                "calendar": "NYSE",
                "status": "closed",
                "is_open": False,
                "next_open": now + timedelta(days=2),
            }
        )
        next_event = next(
            part[0] for part in closed_future[1] if "Opens" in part[0]
        )
        self.assertRegex(next_event, r"\(Opens [A-Z][a-z]{2} \d{2}:\d{2}\)")


if __name__ == "__main__":
    unittest.main()
