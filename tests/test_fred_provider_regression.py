import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import requests

from stockstui.data_providers import fred_provider
from stockstui.data_providers.fred_provider import (
    get_series_observations,
    get_series_summary,
)


class TestFredNaSentinelRegression(unittest.TestCase):
    """
    Regression tests for Bug #7:
    When a FRED historical observation value is "." (the FRED API's N/A sentinel),
    it must NOT be treated as 0 when computing change fields.
    Previously, change_1p/change_1y/change_5y would be set to `current - 0 = current`,
    making the field show the full absolute value instead of "N/A".
    """

    def setUp(self):
        # Clear module-level caches before each test to prevent cross-test contamination
        fred_provider._series_cache.clear()
        fred_provider._info_cache.clear()

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_change_1p_is_na_when_prev_value_is_dot(self, mock_get):
        """Regression: change_1p must remain 'N/A' when the previous period is a '.' sentinel."""
        mock_obs = MagicMock()
        mock_obs.json.return_value = {
            "observations": [
                {"date": "2023-06-01", "value": "100.0"},  # Current — valid
                {"date": "2023-05-01", "value": "."},       # Prev period — FRED N/A
            ]
        }
        mock_info = MagicMock()
        mock_info.json.return_value = {"seriess": [{"title": "Test", "units": "Index"}]}

        mock_get.side_effect = lambda url, params, timeout: (
            mock_obs if "observations" in url else mock_info
        )

        summary = get_series_summary("REG_1P_DOT", "fake_key")

        # Before the fix: change_1p == 100.0 (current - 0)
        # After the fix:  change_1p == "N/A"
        self.assertEqual(
            summary["change_1p"],
            "N/A",
            "change_1p should remain 'N/A' when the reference period value is '.'",
        )

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_change_1y_is_na_when_year_ago_value_is_dot(self, mock_get):
        """Regression: change_1y must remain 'N/A' when the 1-year-ago observation is '.'."""
        mock_obs = MagicMock()
        mock_obs.json.return_value = {
            "observations": [
                # Descending order (newest first), as returned by FRED API
                {"date": "2023-06-01", "value": "200.0"},   # Current
                {"date": "2023-05-01", "value": "195.0"},   # Prev period — valid
                {"date": "2022-06-01", "value": "."},        # 1Y ago — FRED N/A
                {"date": "2018-06-01", "value": "150.0"},   # 5Y ago — valid
            ]
        }
        mock_info = MagicMock()
        mock_info.json.return_value = {"seriess": [{"title": "Test", "units": "Index"}]}

        mock_get.side_effect = lambda url, params, timeout: (
            mock_obs if "observations" in url else mock_info
        )

        summary = get_series_summary("REG_1Y_DOT", "fake_key")

        # change_1p should still work (195 is valid)
        self.assertEqual(summary["change_1p"], 5.0, "change_1p should be 200 - 195 = 5.0")

        # Before the fix: change_1y == 200.0 (200 - 0)
        # After the fix:  change_1y == "N/A"
        self.assertEqual(
            summary["change_1y"],
            "N/A",
            "change_1y should remain 'N/A' when the 1-year-ago observation value is '.'",
        )

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_change_5y_is_na_when_five_year_ago_value_is_dot(self, mock_get):
        """Regression: change_5y must remain 'N/A' when the 5-year-ago observation is '.'."""
        mock_obs = MagicMock()
        mock_obs.json.return_value = {
            "observations": [
                {"date": "2023-06-01", "value": "300.0"},  # Current
                {"date": "2023-05-01", "value": "295.0"},  # Prev
                {"date": "2022-06-01", "value": "280.0"},  # 1Y ago
                {"date": "2018-06-01", "value": "."},       # 5Y ago — FRED N/A
            ]
        }
        mock_info = MagicMock()
        mock_info.json.return_value = {"seriess": [{"title": "Test", "units": "Index"}]}

        mock_get.side_effect = lambda url, params, timeout: (
            mock_obs if "observations" in url else mock_info
        )

        summary = get_series_summary("REG_5Y_DOT", "fake_key")

        self.assertEqual(summary["change_1p"], 5.0, "change_1p should be 300 - 295 = 5.0")
        self.assertEqual(summary["change_1y"], 20.0, "change_1y should be 300 - 280 = 20.0")

        # Before the fix: change_5y == 300.0 (300 - 0)
        # After the fix:  change_5y == "N/A"
        self.assertEqual(
            summary["change_5y"],
            "N/A",
            "change_5y should remain 'N/A' when the 5-year-ago observation value is '.'",
        )

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_all_change_fields_na_when_all_reference_periods_are_dot(self, mock_get):
        """All three change fields must all be 'N/A' when every reference period is '.'."""
        mock_obs = MagicMock()
        mock_obs.json.return_value = {
            "observations": [
                {"date": "2023-06-01", "value": "500.0"},  # Current — valid
                {"date": "2023-05-01", "value": "."},       # Prev period
                {"date": "2022-06-01", "value": "."},       # 1Y ago
                {"date": "2018-06-01", "value": "."},       # 5Y ago
            ]
        }
        mock_info = MagicMock()
        mock_info.json.return_value = {"seriess": [{"title": "Test", "units": "Index"}]}

        mock_get.side_effect = lambda url, params, timeout: (
            mock_obs if "observations" in url else mock_info
        )

        summary = get_series_summary("REG_ALL_DOT", "fake_key")

        self.assertEqual(summary["current"], 500.0)
        # Before the fix: all three fields would equal 500.0 (current - 0)
        self.assertEqual(summary["change_1p"], "N/A")
        self.assertEqual(summary["change_1y"], "N/A")
        self.assertEqual(summary["change_5y"], "N/A")

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_valid_change_fields_are_unaffected(self, mock_get):
        """Ensure that valid (non-'.' sentinel) change computations still work correctly."""
        mock_obs = MagicMock()
        mock_obs.json.return_value = {
            "observations": [
                {"date": "2023-06-01", "value": "110.0"},  # Current
                {"date": "2023-05-01", "value": "105.0"},  # Prev period
                {"date": "2022-06-01", "value": "100.0"},  # ~1Y ago
                {"date": "2018-06-01", "value": "80.0"},   # ~5Y ago
            ]
        }
        mock_info = MagicMock()
        mock_info.json.return_value = {"seriess": [{"title": "Test", "units": "Index"}]}

        mock_get.side_effect = lambda url, params, timeout: (
            mock_obs if "observations" in url else mock_info
        )

        summary = get_series_summary("REG_VALID_CHANGES", "fake_key")

        self.assertEqual(summary["current"], 110.0)
        self.assertAlmostEqual(summary["change_1p"], 5.0)   # 110 - 105
        self.assertAlmostEqual(summary["change_1y"], 10.0)  # 110 - 100
        self.assertAlmostEqual(summary["change_5y"], 30.0)  # 110 - 80


class TestGetSeriesObservationsCacheFallbackRegression(unittest.TestCase):
    """
    Regression tests for Bug #8:
    When get_series_observations has fresh-but-partial cached data (fewer entries than
    the requested limit) and a subsequent network request fails, it must return the
    cached data as a fallback instead of returning None.
    Previously, valid cached data was silently discarded when the network call failed.
    """

    def setUp(self):
        # Clear the module-level series cache before each test for isolation
        fred_provider._series_cache.clear()

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_returns_cached_fallback_when_network_fails(self, mock_get):
        """Regression: Fresh-but-partial cache data must be returned when the network fails."""
        # Pre-populate cache with a small but valid dataset (fewer entries than requested limit)
        now = datetime.now(timezone.utc)
        cached_data = [
            {"date": "2023-06-01", "value": "100.0"},
            {"date": "2023-05-01", "value": "99.5"},
        ]
        fred_provider._series_cache["FALLBACK_NET_FAIL"] = (now, cached_data)

        # Simulate a network failure
        mock_get.side_effect = requests.exceptions.RequestException("Connection refused")

        # Request more data than the cache has (limit=100, cache only has 2 entries)
        result = get_series_observations("FALLBACK_NET_FAIL", "fake_key", limit=100)

        # Before the fix: result == None (cache discarded, network failed, nothing returned)
        # After the fix:  result == cached_data (fallback is served)
        self.assertIsNotNone(result, "Should return cached data instead of None on network failure")
        self.assertEqual(result, cached_data)

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_returns_none_when_no_cache_and_network_fails(self, mock_get):
        """When there is no cached data at all and the network fails, None is the correct return."""
        # Ensure cache is empty for this series
        fred_provider._series_cache.pop("NO_CACHE_SERIES", None)

        mock_get.side_effect = requests.exceptions.RequestException("Timeout")

        result = get_series_observations("NO_CACHE_SERIES", "fake_key", limit=100)

        # Without any cache, None is the expected fallback
        self.assertIsNone(result, "Should return None when there is no cache and the network fails")

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_returns_full_cache_immediately_without_network_call(self, mock_get):
        """When the cache has >= limit entries, it must be returned without any network call."""
        now = datetime.now(timezone.utc)
        # Create cache data with 5 entries, which satisfies a limit=5 request
        cached_data = [{"date": f"2023-0{i}-01", "value": str(i * 10.0)} for i in range(1, 6)]
        fred_provider._series_cache["FULL_CACHE_SERIES"] = (now, cached_data)

        result = get_series_observations("FULL_CACHE_SERIES", "fake_key", limit=5)

        # Should return directly from cache without any network call
        mock_get.assert_not_called()
        self.assertEqual(result, cached_data)

    @patch("stockstui.data_providers.fred_provider.requests.get")
    def test_network_success_updates_cache_and_returns_fresh_data(self, mock_get):
        """When a network request succeeds, it should update the cache and return fresh data."""
        # Pre-populate cache with partial data to trigger the fallback path setup
        now = datetime.now(timezone.utc)
        partial_cache = [{"date": "2023-01-01", "value": "50.0"}]
        fred_provider._series_cache["CACHE_UPDATE_SERIES"] = (now, partial_cache)

        # Network succeeds with more data
        fresh_data = [
            {"date": "2023-06-01", "value": "100.0"},
            {"date": "2023-05-01", "value": "99.0"},
            {"date": "2023-04-01", "value": "98.0"},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"observations": fresh_data}
        mock_get.return_value = mock_response

        result = get_series_observations("CACHE_UPDATE_SERIES", "fake_key", limit=3)

        # Fresh data should be returned
        self.assertEqual(result, fresh_data)
        # Cache should now hold the fresh data
        _, cached = fred_provider._series_cache["CACHE_UPDATE_SERIES"]
        self.assertEqual(cached, fresh_data)
