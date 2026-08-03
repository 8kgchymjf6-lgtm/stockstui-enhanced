import unittest
from unittest.mock import MagicMock, patch

import requests

from stockstui.data_providers import fred_provider


class TestFredProviderCoverage(unittest.TestCase):
    """Focused edge-case tests for the FRED data provider."""

    def setUp(self):
        fred_provider._series_cache.clear()
        fred_provider._info_cache.clear()

    def test_detect_frequency_all_supported_ranges(self):
        """Observation spacing should map to daily, weekly, monthly, quarterly, or annual."""
        cases = {
            "D": [
                {"date": "2026-01-02"},
                {"date": "2026-01-01"},
            ],
            "W": [
                {"date": "2026-01-08"},
                {"date": "2026-01-01"},
            ],
            "M": [
                {"date": "2026-02-01"},
                {"date": "2026-01-01"},
            ],
            "Q": [
                {"date": "2026-04-01"},
                {"date": "2026-01-01"},
            ],
            "A": [
                {"date": "2026-01-01"},
                {"date": "2025-01-01"},
            ],
        }

        for expected, observations in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(
                    fred_provider.detect_frequency(observations),
                    expected,
                )

    def test_detect_frequency_defaults_for_too_little_or_invalid_data(self):
        """Ambiguous and malformed dates should safely default to monthly."""
        self.assertEqual(fred_provider.detect_frequency([]), "M")
        self.assertEqual(
            fred_provider.detect_frequency([{"date": "2026-01-01"}]),
            "M",
        )
        self.assertEqual(
            fred_provider.detect_frequency(
                [
                    {"date": "not-a-date"},
                    {"date": "also-invalid"},
                ]
            ),
            "M",
        )

    def test_compute_enhanced_metrics_empty_and_invalid_values(self):
        """Missing or non-numeric observations should return empty metrics."""
        empty = fred_provider.compute_enhanced_metrics([], "M")
        invalid = fred_provider.compute_enhanced_metrics(
            [
                {"value": "."},
                {"value": "invalid"},
                {"value": None},
            ],
            "M",
        )

        for result in (empty, invalid):
            self.assertIsNone(result["yoy_pct"])
            self.assertIsNone(result["roll_12"])
            self.assertIsNone(result["z_10y"])
            self.assertIsNone(result["pct_of_range"])

    def test_compute_enhanced_metrics_frequency_periods(self):
        """Quarterly, annual, weekly, and daily inputs should use their own periods."""
        frequency_lengths = {
            "Q": 9,
            "A": 4,
            "W": 105,
            "D": 521,
        }

        for frequency, count in frequency_lengths.items():
            observations = [
                {"value": str(float(count - index))}
                for index in range(count)
            ]

            with self.subTest(frequency=frequency):
                metrics = fred_provider.compute_enhanced_metrics(
                    observations,
                    frequency,
                )
                self.assertIsNotNone(metrics["roll_12"])
                self.assertIsNotNone(metrics["roll_24"])
                self.assertIsNotNone(metrics["yoy_pct"])
                self.assertIsNotNone(metrics["hist_min_10y"])
                self.assertIsNotNone(metrics["hist_max_10y"])

    def test_compute_enhanced_metrics_constant_values_avoid_division_by_zero(self):
        """Constant data should not produce invalid z-scores or range percentages."""
        observations = [{"value": "10"} for _ in range(24)]

        metrics = fred_provider.compute_enhanced_metrics(
            observations,
            "M",
        )

        self.assertIsNone(metrics["z_10y"])
        self.assertIsNone(metrics["pct_of_range"])
        self.assertEqual(metrics["hist_min_10y"], 10.0)
        self.assertEqual(metrics["hist_max_10y"], 10.0)

    def test_search_series_missing_key_and_success(self):
        """Search should reject a missing key and return API results on success."""
        self.assertEqual(fred_provider.search_series("inflation", ""), [])

        response = MagicMock()
        response.json.return_value = {
            "seriess": [{"id": "CPIAUCSL", "title": "Consumer Price Index"}]
        }

        with patch(
            "stockstui.data_providers.fred_provider.requests.get",
            return_value=response,
        ) as mock_get:
            result = fred_provider.search_series("inflation", "fake-key")

        self.assertEqual(result[0]["id"], "CPIAUCSL")
        response.raise_for_status.assert_called_once()
        mock_get.assert_called_once()

    def test_search_series_handles_network_error(self):
        """A failed FRED search should return an empty list."""
        with patch(
            "stockstui.data_providers.fred_provider.requests.get",
            side_effect=requests.exceptions.RequestException("offline"),
        ):
            result = fred_provider.search_series("rates", "fake-key")

        self.assertEqual(result, [])

    def test_get_series_info_empty_response_and_network_error(self):
        """Missing metadata and network failures should both return None."""
        empty_response = MagicMock()
        empty_response.json.return_value = {"seriess": []}

        with patch(
            "stockstui.data_providers.fred_provider.requests.get",
            return_value=empty_response,
        ):
            self.assertIsNone(
                fred_provider.get_series_info("EMPTY", "fake-key")
            )

        with patch(
            "stockstui.data_providers.fred_provider.requests.get",
            side_effect=requests.exceptions.RequestException("offline"),
        ):
            self.assertIsNone(
                fred_provider.get_series_info("FAIL", "fake-key")
            )

    def test_summary_uses_frequency_specific_fetch_limits(self):
        """Metadata frequency should determine how many observations are requested."""
        cases = {
            "Quarterly": ("Q", 44),
            "Annual": ("A", 15),
            "Daily": ("D", 2860),
            "Weekly": ("W", 572),
            "Monthly": ("M", 132),
        }

        for metadata_frequency, expected in cases.items():
            expected_code, expected_limit = expected
            info = {
                "title": "Test",
                "units": "Index",
                "frequency": metadata_frequency,
            }

            with self.subTest(frequency=metadata_frequency):
                with patch(
                    "stockstui.data_providers.fred_provider.get_series_info",
                    return_value=info,
                ), patch(
                    "stockstui.data_providers.fred_provider.get_series_observations",
                    return_value=None,
                ) as mock_observations:
                    summary = fred_provider.get_series_summary(
                        "TEST",
                        "fake-key",
                    )

                self.assertEqual(summary["frequency"], expected_code)
                mock_observations.assert_called_once_with(
                    "TEST",
                    "fake-key",
                    limit=expected_limit,
                )

    def test_summary_detects_seasonal_adjustment(self):
        """Seasonally adjusted metadata should be represented as SA."""
        info = {
            "title": "Test",
            "units": "Percent",
            "frequency": "Monthly",
            "seasonal_adjustment": "Seasonally Adjusted",
        }

        with patch(
            "stockstui.data_providers.fred_provider.get_series_info",
            return_value=info,
        ), patch(
            "stockstui.data_providers.fred_provider.get_series_observations",
            return_value=None,
        ):
            summary = fred_provider.get_series_summary(
                "TEST",
                "fake-key",
            )

        self.assertEqual(summary["seasonal_adj"], "SA")


    def test_summary_handles_invalid_previous_value(self):
        """An invalid previous-period value should leave change_1p as N/A."""
        observations = [
            {"date": "2026-06-01", "value": "100.0"},
            {"date": "2026-05-01", "value": "not-a-number"},
        ]

        with patch(
            "stockstui.data_providers.fred_provider.get_series_info",
            return_value=None,
        ), patch(
            "stockstui.data_providers.fred_provider.get_series_observations",
            return_value=observations,
        ):
            summary = fred_provider.get_series_summary(
                "INVALID_PREVIOUS",
                "fake-key",
            )

        self.assertEqual(summary["current"], 100.0)
        self.assertEqual(summary["change_1p"], "N/A")

    def test_summary_skips_observations_with_invalid_dates(self):
        """Malformed historical dates should be ignored without losing valid data."""
        observations = [
            {"date": "2026-06-01", "value": "100.0"},
            {"date": "invalid-date", "value": "95.0"},
            {"date": "2025-06-01", "value": "90.0"},
        ]

        with patch(
            "stockstui.data_providers.fred_provider.get_series_info",
            return_value=None,
        ), patch(
            "stockstui.data_providers.fred_provider.get_series_observations",
            return_value=observations,
        ):
            summary = fred_provider.get_series_summary(
                "INVALID_DATE",
                "fake-key",
            )

        self.assertEqual(summary["current"], 100.0)
        self.assertEqual(summary["change_1y"], 10.0)

    def test_summary_handles_invalid_one_and_five_year_values(self):
        """Invalid comparison values should leave 1Y and 5Y changes as N/A."""
        observations = [
            {"date": "2026-06-01", "value": "100.0"},
            {"date": "2026-05-01", "value": "99.0"},
            {"date": "2025-06-01", "value": "invalid-one-year"},
            {"date": "2021-06-01", "value": "invalid-five-year"},
        ]

        with patch(
            "stockstui.data_providers.fred_provider.get_series_info",
            return_value=None,
        ), patch(
            "stockstui.data_providers.fred_provider.get_series_observations",
            return_value=observations,
        ):
            summary = fred_provider.get_series_summary(
                "INVALID_LONG_TERM",
                "fake-key",
            )

        self.assertEqual(summary["change_1p"], 1.0)
        self.assertEqual(summary["change_1y"], "N/A")
        self.assertEqual(summary["change_5y"], "N/A")

    def test_summary_handles_corrupt_observation_structure(self):
        """Unexpected observation structures should return the default summary."""
        with patch(
            "stockstui.data_providers.fred_provider.get_series_info",
            return_value=None,
        ), patch(
            "stockstui.data_providers.fred_provider.get_series_observations",
            return_value=[{}],
        ):
            summary = fred_provider.get_series_summary(
                "CORRUPT",
                "fake-key",
            )

        self.assertEqual(summary["id"], "CORRUPT")
        self.assertEqual(summary["current"], "N/A")
        self.assertEqual(summary["change_1p"], "N/A")


if __name__ == "__main__":
    unittest.main()
