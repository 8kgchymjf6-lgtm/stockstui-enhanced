import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch
import numpy as np
import pandas as pd
from textual.app import App, ComposeResult

from stockstui.ui.widgets.history_chart import HistoryChart


class HistoryChartApp(App):
    """A minimal app for testing the HistoryChart widget."""

    def __init__(self, chart_widget):
        super().__init__()
        self.chart = chart_widget

    def compose(self) -> ComposeResult:
        yield self.chart


class TestHistoryChart(unittest.IsolatedAsyncioTestCase):
    """Tests for the HistoryChart widget."""

    async def test_history_chart_with_valid_data(self):
        """Test chart rendering with a typical valid DataFrame."""
        dates = pd.to_datetime(["2025-01-01", "2025-01-02"])
        df = pd.DataFrame({"Close": [100.0, 102.5]}, index=dates)
        chart = HistoryChart(df, "1mo", id="test-chart")
        app = HistoryChartApp(chart)

        async with app.run_test() as pilot:
            await pilot.pause()
            # The chart should render without errors
            self.assertIsNotNone(chart)

    async def test_history_chart_with_empty_data(self):
        """Test chart rendering with an empty DataFrame."""
        chart = HistoryChart(pd.DataFrame(), "1mo", id="test-chart")
        app = HistoryChartApp(chart)

        async with app.run_test() as pilot:
            await pilot.pause()
            # Should render without errors
            self.assertIsNotNone(chart)

    async def test_history_chart_with_missing_close_column(self):
        """Test chart behavior with a missing 'Close' column, which should now fall back gracefully."""
        dates = pd.to_datetime(["2025-01-01"])
        df = pd.DataFrame({"Open": [100.0]}, index=dates)
        chart = HistoryChart(df, "1d", id="test-chart")
        app = HistoryChartApp(chart)

        # The widget should NOT raise a KeyError anymore, it should fall back to 'Open'
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsNotNone(chart)

    async def test_history_chart_with_nan_values(self):
        """Test chart rendering with NaN values in data."""
        dates = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"])
        df = pd.DataFrame({"Close": [100.0, float("nan"), 102.0]}, index=dates)
        chart = HistoryChart(df, "1mo", id="test-chart")
        app = HistoryChartApp(chart)

        async with app.run_test() as pilot:
            await pilot.pause()
            # Should render without errors
            self.assertIsNotNone(chart)


    async def test_history_chart_uses_first_available_column(self):
        """The first available column should be used when Close and Open are absent."""
        dates = pd.to_datetime(["2025-01-01", "2025-01-02"])
        df = pd.DataFrame({"Adjusted": [99.0, 101.0]}, index=dates)
        chart = HistoryChart(df, "5d", id="test-chart")
        app = HistoryChartApp(chart)

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsNotNone(chart)

    async def test_history_chart_date_period_branches(self):
        """The remaining date-period formats should render without errors."""
        cases = [
            (
                "5y",
                pd.date_range("2020-01-01", "2025-01-01", freq="180D"),
            ),
            (
                "1y",
                pd.date_range("2025-01-01", "2025-12-01", freq="30D"),
            ),
            (
                "5d",
                pd.date_range("2025-01-01", periods=5, freq="D"),
            ),
            (
                "1d",
                pd.date_range(
                    "2025-01-01 09:30",
                    "2025-01-01 23:30",
                    freq="30min",
                ),
            ),
        ]

        for period, dates in cases:
            with self.subTest(period=period):
                df = pd.DataFrame(
                    {"Close": range(100, 100 + len(dates))},
                    index=dates,
                )
                chart = HistoryChart(df, period, id=f"chart-{period}")
                app = HistoryChartApp(chart)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    self.assertIsNotNone(chart)

    def test_history_chart_handles_tiny_y_range(self):
        """A subnormal range should safely produce a single tick."""
        chart = HistoryChart(pd.DataFrame(), "1mo")
        tiny_value = np.nextafter(0.0, 1.0)

        ticks = chart._get_nice_y_ticks(0.0, tiny_value)

        self.assertEqual(ticks, [0.0])

    def test_history_chart_price_tick_edge_cases(self):
        """Price ticks should handle absent, empty, single, and fallback values."""
        chart = HistoryChart(pd.DataFrame(), "1mo")
        plt = MagicMock()

        with (
            patch.object(
                type(chart),
                "plt",
                new_callable=PropertyMock,
                return_value=plt,
            ),
            patch.object(
                type(chart),
                "size",
                new_callable=PropertyMock,
                return_value=SimpleNamespace(height=10),
            ),
        ):
            # No available columns.
            chart._data = SimpleNamespace(columns=[])
            chart._set_price_ticks()
            plt.yticks.assert_not_called()

            # Valid data, but no calculated ticks.
            series = MagicMock()
            series.min.return_value = 10.0
            series.max.return_value = 20.0

            data = MagicMock()
            data.columns = ["Close"]
            data.__getitem__.return_value = series
            chart._data = data

            with patch.object(chart, "_get_nice_y_ticks", return_value=[]):
                chart._set_price_ticks()

            plt.yticks.assert_called_once_with([], [])
            plt.reset_mock()

            # A single calculated tick requires expanded y-axis limits.
            with patch.object(chart, "_get_nice_y_ticks", return_value=[10.0]):
                chart._set_price_ticks()

            plt.ylim.assert_called_once_with(9.5, 10.5)
            plt.yticks.assert_called_once_with([10.0], ["10.00"])
            plt.reset_mock()

            # Fallback where only the minimum value is usable.
            series.min.return_value = 15.0
            series.max.return_value = None
            chart._set_price_ticks()

            plt.yticks.assert_called_once_with([15.0], ["15.00"])


    async def test_history_chart_with_no_columns(self):
        """A DataFrame with an index but no columns should not be plotted."""
        dates = pd.to_datetime(["2025-01-01", "2025-01-02"])
        df = pd.DataFrame(index=dates)
        chart = HistoryChart(df, "1mo", id="no-columns-chart")
        app = HistoryChartApp(chart)

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsNotNone(chart)

    def test_history_chart_remaining_branches(self):
        """Unknown periods and missing price values should be harmless."""
        chart = HistoryChart(pd.DataFrame(), "unknown")
        plt = MagicMock()

        dates = pd.to_datetime(["2025-01-01", "2025-01-02"])
        chart._data = pd.DataFrame({"Close": [100.0, 101.0]}, index=dates)

        with patch.object(
            type(chart),
            "plt",
            new_callable=PropertyMock,
            return_value=plt,
        ):
            chart._set_date_ticks()

        plt.xticks.assert_not_called()

        series = MagicMock()
        series.min.return_value = None
        series.max.return_value = None

        data = MagicMock()
        data.columns = ["Close"]
        data.__getitem__.return_value = series
        chart._data = data

        with (
            patch.object(
                type(chart),
                "plt",
                new_callable=PropertyMock,
                return_value=plt,
            ),
            patch.object(
                type(chart),
                "size",
                new_callable=PropertyMock,
                return_value=SimpleNamespace(height=20),
            ),
        ):
            plt.reset_mock()
            chart._set_price_ticks()

        plt.yticks.assert_not_called()

    def test_history_chart_downsamples_long_intraday_ticks(self):
        """Long intraday data should downsample the generated hourly ticks."""
        dates = pd.date_range(
            "2025-01-01 00:30",
            "2025-01-01 23:30",
            freq="30min",
        )
        chart = HistoryChart(
            pd.DataFrame({"Close": range(len(dates))}, index=dates),
            "1d",
        )
        plt = MagicMock()

        with patch.object(
            type(chart),
            "plt",
            new_callable=PropertyMock,
            return_value=plt,
        ):
            chart._set_date_ticks()

        plt.xticks.assert_called_once()
        tick_positions, labels = plt.xticks.call_args.args
        self.assertLessEqual(len(tick_positions), 8)
        self.assertEqual(len(tick_positions), len(labels))

    def test_history_chart_handles_no_matching_nice_multiplier(self):
        """The original rough step should remain when no multiplier matches."""
        chart = HistoryChart(pd.DataFrame(), "1mo")

        with patch(
            "stockstui.ui.widgets.history_chart.np.log10",
            return_value=0.0,
        ):
            ticks = chart._get_nice_y_ticks(0.0, 80.0, num_ticks=5)

        self.assertEqual(ticks, [0.0, 20.0, 40.0, 60.0, 80.0])


    def test_history_chart_nonempty_data_without_columns(self):
        """Non-empty indexed data without columns should stop before plotting."""
        chart = HistoryChart(pd.DataFrame(), "1mo")
        plt = MagicMock()

        chart._data = SimpleNamespace(
            empty=False,
            index=pd.to_datetime(["2025-01-01", "2025-01-02"]),
            columns=[],
        )

        with patch.object(
            type(chart),
            "plt",
            new_callable=PropertyMock,
            return_value=plt,
        ):
            chart.on_mount()

        plt.clear_data.assert_called_once()
        plt.plot.assert_not_called()
