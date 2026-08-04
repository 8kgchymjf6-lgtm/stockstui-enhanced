import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
from stockstui.ui.widgets.oi_chart import OIChart


class TestOIChart(unittest.TestCase):
    """Test suite for Open Interest Chart widget."""

    def setUp(self):
        """Create sample options data for testing."""
        # Sample calls data
        self.calls_df = pd.DataFrame(
            {
                "strike": [580, 590, 600, 610, 620, 630, 640, 650, 660, 670, 680],
                "openInterest": [
                    100,
                    200,
                    500,
                    1000,
                    2000,
                    1500,
                    800,
                    400,
                    200,
                    100,
                    50,
                ],
                "contractSymbol": [f"CALL{s}" for s in range(11)],
            }
        )

        # Sample puts data
        self.puts_df = pd.DataFrame(
            {
                "strike": [580, 590, 600, 610, 620, 630, 640, 650, 660, 670, 680],
                "openInterest": [
                    50,
                    150,
                    300,
                    600,
                    1800,
                    2500,
                    1200,
                    600,
                    300,
                    150,
                    75,
                ],
                "contractSymbol": [f"PUT{s}" for s in range(11)],
            }
        )

        self.underlying_price = 630.0

    def test_chart_initialization(self):
        """Test that the chart can be initialized."""
        chart = OIChart(self.calls_df, self.puts_df, self.underlying_price)
        self.assertIsNotNone(chart)
        self.assertEqual(chart._underlying_price, self.underlying_price)

    def test_replot_logic(self):
        """Test the replot logic with mocks."""
        chart = OIChart(self.calls_df, self.puts_df, self.underlying_price)

        # Mock app and theme variables
        mock_app = MagicMock()
        mock_app.theme_variables = {"green": "green", "red": "red"}

        # Mock plt property AND app property
        with (
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.plt", new_callable=PropertyMock
            ) as mock_plt_prop,
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.app", new_callable=PropertyMock
            ) as mock_app_prop,
        ):
            mock_plt = MagicMock()
            mock_plt_prop.return_value = mock_plt
            mock_app_prop.return_value = mock_app

            chart.replot()

            # Verify clear_data called
            mock_plt.clear_data.assert_called_once()

            # Verify multiple_bar called
            mock_plt.multiple_bar.assert_called_once()

            # Verify grid called
            mock_plt.grid.assert_called_once()

    def test_replot_empty_data(self):
        """Test replot with empty data handles gracefully."""
        empty_df = pd.DataFrame(columns=["strike", "openInterest", "contractSymbol"])
        chart = OIChart(empty_df, empty_df, self.underlying_price)

        mock_app = MagicMock()
        mock_app.theme_variables = {}

        with (
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.plt", new_callable=PropertyMock
            ) as mock_plt_prop,
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.app", new_callable=PropertyMock
            ) as mock_app_prop,
        ):
            mock_plt = MagicMock()
            mock_plt_prop.return_value = mock_plt
            mock_app_prop.return_value = mock_app

            chart.replot()

            mock_plt.clear_data.assert_called_once()
            # multiple_bar should NOT be called for empty data
            mock_plt.multiple_bar.assert_not_called()

    def test_chart_with_empty_calls(self):
        """Test chart with empty calls dataframe."""
        empty_calls = pd.DataFrame(columns=["strike", "openInterest", "contractSymbol"])
        chart = OIChart(empty_calls, self.puts_df, self.underlying_price)
        self.assertIsNotNone(chart)

    def test_chart_with_empty_puts(self):
        """Test chart with empty puts dataframe."""
        empty_puts = pd.DataFrame(columns=["strike", "openInterest", "contractSymbol"])
        chart = OIChart(self.calls_df, empty_puts, self.underlying_price)
        self.assertIsNotNone(chart)

    def test_chart_with_both_empty(self):
        """Test chart with both empty dataframes."""
        empty_df = pd.DataFrame(columns=["strike", "openInterest", "contractSymbol"])
        chart = OIChart(empty_df, empty_df, self.underlying_price)
        self.assertIsNotNone(chart)

    def test_chart_with_single_strike(self):
        """Test chart with only one strike."""
        single_call = pd.DataFrame(
            {"strike": [630], "openInterest": [1000], "contractSymbol": ["CALL"]}
        )
        single_put = pd.DataFrame(
            {"strike": [630], "openInterest": [1500], "contractSymbol": ["PUT"]}
        )
        chart = OIChart(single_call, single_put, self.underlying_price)
        self.assertIsNotNone(chart)

        # Test plotting single strike
        mock_app = MagicMock()
        mock_app.theme_variables = {"green": "green", "red": "red"}

        with (
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.plt", new_callable=PropertyMock
            ) as mock_plt_prop,
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.app", new_callable=PropertyMock
            ) as mock_app_prop,
        ):
            mock_plt = MagicMock()
            mock_plt_prop.return_value = mock_plt
            mock_app_prop.return_value = mock_app

            chart.replot()
            mock_plt.multiple_bar.assert_called_once()

    def test_chart_with_wide_strikes(self):
        """Test chart with strikes far from underlying."""
        wide_calls = pd.DataFrame(
            {
                "strike": [100, 200, 300, 900, 1000, 1100],
                "openInterest": [10, 20, 30, 40, 50, 60],
                "contractSymbol": [f"CALL_WIDE{s}" for s in range(6)],
            }
        )
        chart = OIChart(wide_calls, self.puts_df, self.underlying_price)
        self.assertIsNotNone(chart)

    def test_chart_data_integrity(self):
        """Test that chart preserves data integrity."""
        chart = OIChart(self.calls_df, self.puts_df, self.underlying_price)

        # Verify internal data is stored
        self.assertTrue(chart._calls_df.equals(self.calls_df))
        self.assertTrue(chart._puts_df.equals(self.puts_df))

    def test_chart_with_zero_oi(self):
        """Test chart with zero open interest."""
        zero_oi_calls = pd.DataFrame(
            {"strike": [630], "openInterest": [0], "contractSymbol": ["CALL"]}
        )
        chart = OIChart(zero_oi_calls, self.puts_df, self.underlying_price)
        self.assertIsNotNone(chart)

    def test_chart_with_missing_strikes(self):
        """Test chart with gaps in strike prices."""
        gapped_calls = pd.DataFrame(
            {
                "strike": [600, 620, 660, 680],  # Missing 610, 630, 640, 650, 670
                "openInterest": [100, 500, 300, 100],
                "contractSymbol": ["C1", "C2", "C3", "C4"],
            }
        )
        chart = OIChart(gapped_calls, self.puts_df, self.underlying_price)
        self.assertIsNotNone(chart)


    def _run_replot(self, chart):
        """Run replot with mocked Textual and plotext dependencies."""
        mock_app = MagicMock()
        mock_app.theme_variables = {"green": "green", "red": "red"}

        with (
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.plt",
                new_callable=PropertyMock,
            ) as mock_plt_property,
            patch(
                "stockstui.ui.widgets.oi_chart.OIChart.app",
                new_callable=PropertyMock,
            ) as mock_app_property,
        ):
            mock_plt = MagicMock()
            mock_plt_property.return_value = mock_plt
            mock_app_property.return_value = mock_app

            chart.replot()
            return mock_plt

    def test_replot_only_calls_and_only_puts(self):
        """Each side of the option chain should work independently."""
        empty = pd.DataFrame(columns=["strike", "openInterest"])

        calls_chart = OIChart(
            self.calls_df,
            empty,
            self.underlying_price,
        )
        calls_plot = self._run_replot(calls_chart)
        calls_plot.multiple_bar.assert_called_once()

        puts_chart = OIChart(
            empty,
            self.puts_df,
            self.underlying_price,
        )
        puts_plot = self._run_replot(puts_chart)
        puts_plot.multiple_bar.assert_called_once()

    def test_replot_nonempty_data_without_strikes(self):
        """Non-empty inputs with no extracted strikes should stop safely."""
        calls = MagicMock()
        calls.empty = False
        calls.__getitem__.return_value.tolist.return_value = []

        puts = MagicMock()
        puts.empty = False
        puts.__getitem__.return_value.tolist.return_value = []

        chart = OIChart(calls, puts, self.underlying_price)
        mock_plot = self._run_replot(chart)

        mock_plot.clear_data.assert_called_once()
        mock_plot.multiple_bar.assert_not_called()

    def test_replot_zero_open_interest_uses_fallback_range(self):
        """All-zero open interest should fall back to the complete strike range."""
        calls = pd.DataFrame(
            {
                "strike": [620, 630, 640],
                "openInterest": [0, 0, 0],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [620, 630, 640],
                "openInterest": [0, 0, 0],
            }
        )

        chart = OIChart(calls, puts, self.underlying_price)
        mock_plot = self._run_replot(chart)

        mock_plot.multiple_bar.assert_called_once()
        mock_plot.yticks.assert_not_called()
        mock_plot.grid.assert_called_once_with(True, True)

    def test_replot_filters_large_strike_ranges(self):
        """Wide and medium ranges should prefer round strikes."""
        cases = [
            (
                list(range(400, 851, 5)),
                630.0,
            ),
            (
                list(range(580, 681, 2)),
                630.0,
            ),
        ]

        for strikes, underlying in cases:
            with self.subTest(first=strikes[0], last=strikes[-1]):
                calls = pd.DataFrame(
                    {
                        "strike": strikes,
                        "openInterest": [100] * len(strikes),
                    }
                )
                puts = pd.DataFrame(
                    {
                        "strike": strikes,
                        "openInterest": [50] * len(strikes),
                    }
                )

                chart = OIChart(calls, puts, underlying)
                mock_plot = self._run_replot(chart)

                mock_plot.multiple_bar.assert_called_once()
                labels = mock_plot.multiple_bar.call_args.args[0]
                self.assertLessEqual(len(labels), 41)

    def test_replot_declutters_labels_and_formats_y_ticks(self):
        """Long charts should declutter labels and format large tick values."""
        strikes = [600 + index for index in range(31)]
        calls = pd.DataFrame(
            {
                "strike": strikes,
                "openInterest": [
                    0,
                    1_000,
                    2_000,
                    3_000,
                    4_000,
                    5_000,
                    6_000,
                    7_000,
                    8_000,
                    9_000,
                    10_000,
                    20_000,
                    30_000,
                    40_000,
                    50_000,
                    60_000,
                    70_000,
                    80_000,
                    90_000,
                    100_000,
                    200_000,
                    300_000,
                    400_000,
                    500_000,
                    600_000,
                    700_000,
                    800_000,
                    900_000,
                    1_000_000,
                    1_500_000,
                    2_000_000,
                ],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": strikes,
                "openInterest": [500] * len(strikes),
            }
        )

        chart = OIChart(calls, puts, 615.0)
        mock_plot = self._run_replot(chart)

        labels = mock_plot.multiple_bar.call_args.args[0]
        self.assertIn("", labels)
        self.assertIn("615", labels)

        mock_plot.yticks.assert_called_once()
        tick_labels = mock_plot.yticks.call_args.args[1]
        self.assertIn("0", tick_labels)
        self.assertTrue(any(label.endswith("K") for label in tick_labels))
        self.assertTrue(any(label.endswith("M") for label in tick_labels))

    def test_replot_covers_all_nice_tick_bases(self):
        """Y-axis steps should cover all four rounding intervals."""
        max_values = [
            5,
            10,
            25,
            45,
        ]

        for max_oi in max_values:
            with self.subTest(max_oi=max_oi):
                calls = pd.DataFrame(
                    {
                        "strike": [625, 630],
                        "openInterest": [0, max_oi],
                    }
                )
                puts = pd.DataFrame(
                    {
                        "strike": [625, 630],
                        "openInterest": [0, 0],
                    }
                )

                chart = OIChart(calls, puts, 630.0)
                mock_plot = self._run_replot(chart)

                mock_plot.yticks.assert_called_once()

    def test_on_mount_calls_replot(self):
        """Mounting the chart should trigger a replot."""
        chart = OIChart(
            self.calls_df,
            self.puts_df,
            self.underlying_price,
        )

        with patch.object(chart, "replot") as replot:
            chart.on_mount()

        replot.assert_called_once_with()

    def test_replot_keeps_candidates_in_narrow_range(self):
        """A narrow range with many strikes should retain all candidates."""
        strikes = list(range(81, 120))
        calls = pd.DataFrame(
            {
                "strike": strikes,
                "openInterest": [100] * len(strikes),
            }
        )
        puts = pd.DataFrame(
            {
                "strike": strikes,
                "openInterest": [50] * len(strikes),
            }
        )

        chart = OIChart(calls, puts, underlying_price=100.0)
        mock_plot = self._run_replot(chart)

        labels = mock_plot.multiple_bar.call_args.args[0]

        self.assertEqual(len(labels), len(strikes))
        self.assertIn("100", labels)

if __name__ == "__main__":
    unittest.main()
