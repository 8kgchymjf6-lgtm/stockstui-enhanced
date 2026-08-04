import unittest
import pandas as pd
import tempfile
from pathlib import Path
from types import SimpleNamespace

from textual.widgets import DataTable, RadioButton
from textual.dom import NoMatches
from stockstui.ui.views.history_view import HistoryView
from stockstui.ui.widgets.history_chart import HistoryChart
from stockstui.main import StocksTUI
from tests.test_utils import TEST_APP_ROOT
from stockstui.config_manager import ConfigManager


class TestHistoryView(unittest.IsolatedAsyncioTestCase):
    """Isolated unit tests for the HistoryView widget."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.user_config_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _setup_app_with_data(self, data):
        """Creates a real app instance with a temporary config and pre-loaded data."""
        app = StocksTUI()
        with unittest.mock.patch("stockstui.config_manager.PlatformDirs") as mock_dirs:
            mock_dirs.return_value.user_config_dir = str(self.user_config_dir)
            app.config = ConfigManager(app_root=TEST_APP_ROOT.parent)
        app._load_and_register_themes()
        app._last_historical_data = data
        app._history_period = "1mo"
        return app

    async def test_renders_table_view_correctly(self):
        # FIX: Use a realistic DataFrame with all required OHLCV columns.
        dates = pd.to_datetime(["2025-08-18", "2025-08-19"])
        data = pd.DataFrame(
            {
                "Open": [100.0, 101.5],
                "High": [102.0, 103.0],
                "Low": [99.5, 100.8],
                "Close": [101.0, 102.2],
                "Volume": [1000000, 1200000],
            },
            index=dates,
        )
        app = self._setup_app_with_data(data)

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await history_view._render_historical_data()
            await pilot.pause()

            table = history_view.query_one(DataTable)
            self.assertEqual(table.row_count, 2)
            self.assertEqual(len(history_view.query(HistoryChart)), 0)

    async def test_renders_chart_view_when_toggled(self):
        dates = pd.to_datetime(["2025-08-18", "2025-08-19"])
        data = pd.DataFrame({"Close": [102, 103]}, index=dates)
        app = self._setup_app_with_data(data)

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            history_view.query_one("#history-view-toggle").value = True
            await history_view._render_historical_data()
            await pilot.pause()

            self.assertIsInstance(history_view.query_one(HistoryChart), HistoryChart)
            self.assertEqual(len(history_view.query(DataTable)), 0)

    async def test_renders_error_message_for_empty_data(self):
        empty_df = pd.DataFrame()
        empty_df.attrs = {"error": "Invalid Ticker", "symbol": "BAD"}
        app = self._setup_app_with_data(empty_df)

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await history_view._render_historical_data()
            await pilot.pause()

            message = history_view.query_one("#history-display-container > Static")
            self.assertIn("Invalid ticker", str(message.render()))


    async def test_mount_applies_history_cli_overrides(self):
        """CLI chart and period options should be applied on mount."""
        app = self._setup_app_with_data(pd.DataFrame())
        app.cli_overrides = {"chart": True, "period": "1d"}
        app.history_ticker = "AAPL"
        app.fetch_historical_data = unittest.mock.MagicMock()

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()

            toggle = history_view.query_one("#history-view-toggle")
            self.assertTrue(toggle.value)

            radio_set = history_view.query_one("#history-range-select")
            self.assertIsNotNone(radio_set.pressed_button)
            self.assertEqual(
                str(radio_set.pressed_button.label),
                "1D",
            )

            app.fetch_historical_data.assert_called_with("AAPL", "1d", "5m")
            self.assertEqual(app._history_period, "1d")

    async def test_mount_without_ticker_renders_information_message(self):
        """An empty initial state should explain that a ticker is required."""
        app = self._setup_app_with_data(None)
        app.cli_overrides = {}
        app.history_ticker = ""

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()

            message = history_view.query_one(
                "#history-display-container > #info-message"
            )
            self.assertIn("Enter a ticker symbol", str(message.render()))

    async def test_renders_remaining_empty_data_messages(self):
        """Network, processing, and generic empty-data messages should render."""
        cases = [
            ("Network Error", "MSFT", "Could not retrieve data"),
            ("Data Error", "TSLA", "Could not process data"),
            (None, "NVDA", "No historical data found"),
        ]

        for error_type, symbol, expected in cases:
            with self.subTest(error_type=error_type):
                empty_df = pd.DataFrame()
                empty_df.attrs = {"symbol": symbol}
                if error_type is not None:
                    empty_df.attrs["error"] = error_type

                app = self._setup_app_with_data(empty_df)
                app.history_ticker = ""

                async with app.run_test() as pilot:
                    history_view = HistoryView()
                    await pilot.app.mount(history_view)
                    await history_view._render_historical_data()
                    await pilot.pause()

                    message = history_view.query_one(
                        "#history-display-container > Static"
                    )
                    self.assertIn(expected, str(message.render()))

    async def test_requests_daily_history_and_handles_missing_ticker(self):
        """Normal periods should use daily data; an empty ticker should do nothing."""
        app = self._setup_app_with_data(pd.DataFrame())
        app.cli_overrides = {}
        app.history_ticker = ""
        app.fetch_historical_data = unittest.mock.MagicMock()

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()

            history_view._request_historical_data()
            app.fetch_historical_data.assert_not_called()

            app.history_ticker = "MSFT"
            history_view._request_historical_data()

            app.fetch_historical_data.assert_called_once_with(
                "MSFT", "1mo", "1d"
            )
            self.assertEqual(app._history_period, "1mo")
            self.assertTrue(
                history_view.query_one(
                    "#history-display-container"
                ).loading
            )

    async def test_history_input_events_and_sorting(self):
        """Ticker parsing, submission, range changes, toggling, and sorting."""
        app = self._setup_app_with_data(None)
        app.cli_overrides = {}
        app.history_ticker = ""
        app._set_and_apply_history_sort = unittest.mock.MagicMock()

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()

            self.assertEqual(
                history_view._parse_ticker_from_input(
                    " msft - Microsoft Corporation "
                ),
                "MSFT",
            )
            self.assertEqual(
                history_view._parse_ticker_from_input(" nvda "),
                "NVDA",
            )

            history_view._request_historical_data = unittest.mock.MagicMock()

            history_view.on_history_ticker_submitted(
                SimpleNamespace(value="")
            )
            history_view._request_historical_data.assert_not_called()

            history_view.on_history_ticker_submitted(
                SimpleNamespace(value=" aapl - Apple ")
            )
            self.assertEqual(app.history_ticker, "AAPL")
            history_view._request_historical_data.assert_called_once()

            history_view._request_historical_data.reset_mock()
            history_view.on_history_range_changed(SimpleNamespace())
            history_view._request_historical_data.assert_called_once()

            history_view._render_historical_data = unittest.mock.AsyncMock()
            await history_view.on_history_view_toggled(SimpleNamespace())
            history_view._render_historical_data.assert_awaited_once()

            history_view.on_history_table_header_selected(
                SimpleNamespace(
                    column_key=SimpleNamespace(value="Close")
                )
            )
            app._set_and_apply_history_sort.assert_called_once_with(
                "Close", "click"
            )

    async def test_history_view_ignores_missing_widgets(self):
        """Widget removal during asynchronous work should be harmless."""
        app = self._setup_app_with_data(None)
        app.cli_overrides = {}
        app.history_ticker = "AAPL"

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()

            with unittest.mock.patch.object(
                history_view,
                "query_one",
                side_effect=NoMatches,
            ):
                await history_view._render_historical_data()
                history_view._request_historical_data()


    async def test_mount_handles_incomplete_cli_overrides(self):
        """False, missing, and unknown CLI overrides should be harmless."""
        cases = [
            {"chart": False},
            {"period": "unknown"},
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides):
                app = self._setup_app_with_data(None)
                app.cli_overrides = overrides
                app.history_ticker = ""

                async with app.run_test() as pilot:
                    history_view = HistoryView()
                    await pilot.app.mount(history_view)
                    await pilot.pause()

                    toggle = history_view.query_one("#history-view-toggle")
                    self.assertFalse(toggle.value)

    async def test_request_history_without_pressed_button(self):
        """No selected range should result in no data request."""
        app = self._setup_app_with_data(pd.DataFrame())
        app.history_ticker = "AAPL"
        app.fetch_historical_data = unittest.mock.MagicMock()

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()
            app.fetch_historical_data.reset_mock()

            with unittest.mock.patch.object(
                history_view,
                "query_one",
                return_value=SimpleNamespace(pressed_button=None),
            ):
                history_view._request_historical_data()

            app.fetch_historical_data.assert_not_called()

    async def test_request_history_with_unknown_period_label(self):
        """An unknown selected range should result in no data request."""
        app = self._setup_app_with_data(pd.DataFrame())
        app.history_ticker = "AAPL"
        app.fetch_historical_data = unittest.mock.MagicMock()

        async with app.run_test() as pilot:
            history_view = HistoryView()
            await pilot.app.mount(history_view)
            await pilot.pause()
            app.fetch_historical_data.reset_mock()

            unknown_button = SimpleNamespace(label="Unknown")
            radio_set = SimpleNamespace(pressed_button=unknown_button)

            with unittest.mock.patch.object(
                history_view,
                "query_one",
                return_value=radio_set,
            ):
                history_view._request_historical_data()

            app.fetch_historical_data.assert_not_called()
