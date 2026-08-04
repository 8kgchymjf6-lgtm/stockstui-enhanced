import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from textual.app import App
from textual.dom import NoMatches
import webbrowser
from stockstui.ui.views.fred_view import FredView, FredDataTable


class FredViewTestApp(App):
    """App for testing FredView with mocked config."""

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        self.config.settings = {
            "fred_settings": {
                "api_key": "fake_key",
                "series_list": ["TEST1"],
                "series_aliases": {"TEST1": "Test Alias"},
            }
        }
        self.theme_variables = {
            "success": "green",
            "error": "red",
            "warning": "yellow",
            "text-muted": "dim",
        }
        # Fake notify
        self.notify = MagicMock()

    def compose(self):
        yield FredView()


class TestFredView(unittest.IsolatedAsyncioTestCase):
    @patch("stockstui.data_providers.fred_provider.get_series_summary")
    async def test_populate_table(self, mock_summary):
        """Test that _populate_table correctly renders data."""
        # Prepare sample summary
        sample_summary = {
            "id": "TEST1",
            "title": "Test Series 1",
            "current": 105.0,
            "yoy_pct": 5.0,
            "roll_12": 102.0,
            "roll_24": 100.0,
            "z_10y": 1.5,
            "hist_min_10y": 90.0,
            "hist_max_10y": 110.0,
            "pct_of_range": 75.0,
            "date": "2023-01-01",
            "frequency": "M",
            "units_short": "Index",
        }
        # Mock background worker return value to provide complete data
        mock_summary.return_value = sample_summary

        app = FredViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(FredView)

            # Summaries list for manual call (keeping it for explicit test control)
            summaries = [sample_summary]

            # Manually call _populate_table (bypassing threaded load)
            view._populate_table(summaries)
            await pilot.pause()

            table = app.query_one(FredDataTable)
            self.assertEqual(table.row_count, 1)

            # Check row data - verify alias was used
            row = table.get_row("TEST1")
            self.assertEqual(str(row[0]), "Test Alias")  # Alias from config
            self.assertEqual(str(row[1]), "105.00")
            
            # Verify more row data
            self.assertEqual(str(row[2]), "+5.0%")  # yoy_pct formatted with %
            self.assertEqual(str(row[3]), "102.00")  # roll_12
            self.assertEqual(str(row[4]), "100.00")  # roll_24
            self.assertEqual(str(row[5]), "+1.50")  # z_10y formatted with sign
            self.assertEqual(str(row[6]), "90.00")  # hist_min
            self.assertEqual(str(row[7]), "110.00")  # hist_max
            self.assertEqual(str(row[8]), "75%")  # pct_of_range formatted with %
            self.assertEqual(str(row[9]), "2023-01-01")  # date
            self.assertEqual(str(row[10]), "M")  # frequency
            self.assertEqual(str(row[11]), "Index")  # units

            # Verify table has rows
            self.assertGreater(table.row_count, 0)

    @patch("stockstui.data_providers.fred_provider.get_series_summary")
    @patch("webbrowser.open")
    async def test_action_open_series(self, mock_browser, mock_summary):
        """Test action_open_series opens browser."""
        # Mock background worker
        mock_summary.return_value = {"id": "TEST1", "title": "Test Series 1"}

        app = FredViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(FredView)
            table = app.query_one(FredDataTable)

            # Populate
            view._populate_table([{"id": "TEST1", "current": 100}])
            await pilot.pause()

            # Select the row
            table.focus()
            table.cursor_coordinate = (0, 0)

            # Trigger action
            view.action_open_series()
            await pilot.pause()

            mock_browser.assert_called_with("https://fred.stlouisfed.org/series/TEST1")
            
            # Verify notify was called
            self.assertEqual(app.notify.call_count, 1)

    @patch("stockstui.data_providers.fred_provider.get_series_summary")
    async def test_action_edit_series(self, mock_summary):
        """Test action_edit_series pushes modal."""
        mock_summary.return_value = {"id": "TEST1", "title": "Test Series 1"}

        app = FredViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(FredView)
            table = app.query_one(FredDataTable)

            # Populate
            view._populate_table([{"id": "TEST1", "current": 100}])
            await pilot.pause()

            table.focus()
            table.cursor_coordinate = (0, 0)

            # Mock push_screen
            app.push_screen = MagicMock()

            view.action_edit_series()
            await pilot.pause()

            app.push_screen.assert_called_once()
            args, _ = app.push_screen.call_args
            modal = args[0]
            self.assertEqual(modal.series_id, "TEST1")
            
    @patch("stockstui.data_providers.fred_provider.get_series_summary")
    async def test_fred_view_composes_data_table(self, mock_summary):
        """Test that FredView composes with a FredDataTable."""
        mock_summary.return_value = {"id": "TEST1"}
        
        app = FredViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(FredView)
            await pilot.pause()
            
            # Verify data table exists
            table = app.query_one(FredDataTable)
            self.assertIsNotNone(table)
            
            # Verify view has loading label initially
            labels = list(view.query("Static"))
            self.assertGreater(len(labels), 0)
            
    @patch("stockstui.data_providers.fred_provider.get_series_summary")
    async def test_fred_view_settings_structure(self, mock_summary):
        """Test that FredView settings are properly structured."""
        mock_summary.return_value = {"id": "TEST1"}
        
        app = FredViewTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            
            # Verify config structure
            self.assertIn("fred_settings", app.config.settings)
            self.assertIn("api_key", app.config.settings["fred_settings"])
            self.assertIn("series_list", app.config.settings["fred_settings"])
            self.assertIn("series_aliases", app.config.settings["fred_settings"])
            
            # Verify theme variables
            self.assertIn("success", app.theme_variables)
            self.assertIn("error", app.theme_variables)
            self.assertIn("warning", app.theme_variables)


    def test_fred_data_table_bubbles_actions(self):
        """Table actions should be forwarded to the nearest supporting ancestor."""
        table = FredDataTable()
        parent = MagicMock()
        parent.action_edit_series = MagicMock()
        parent.action_open_series = MagicMock()

        with patch.object(
            type(table),
            "ancestors",
            new_callable=PropertyMock,
            return_value=[object(), parent],
        ):
            table.action_edit_series()
            table.action_open_series()

        parent.action_edit_series.assert_called_once_with()
        parent.action_open_series.assert_called_once_with()

    def test_fred_data_table_actions_without_parent(self):
        """Table actions should be harmless without a supporting ancestor."""
        table = FredDataTable()

        with patch.object(
            type(table),
            "ancestors",
            new_callable=PropertyMock,
            return_value=[object()],
        ):
            table.action_edit_series()
            table.action_open_series()

    def test_fred_view_focus_table_handles_missing_table(self):
        """Focusing should work normally and ignore a missing table."""
        view = FredView()
        table = MagicMock()

        with patch.object(view, "query_one", return_value=table):
            view.action_focus_table()

        table.focus.assert_called_once_with()

        with patch.object(view, "query_one", side_effect=NoMatches):
            view.action_focus_table()

    def test_fred_view_edit_series_guard_clauses(self):
        """Editing should stop when no table cell is selected."""
        view = FredView()
        table = MagicMock()
        table.cursor_type = "none"

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock) as app_property,
        ):
            app = MagicMock()
            app_property.return_value = app
            view.action_edit_series()

        app.push_screen.assert_not_called()

        table.cursor_type = "cell"
        cell_key = MagicMock()
        cell_key.row_key = None
        table.coordinate_to_cell_key.return_value = cell_key

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock) as app_property,
        ):
            app = MagicMock()
            app_property.return_value = app
            view.action_edit_series()

        app.push_screen.assert_not_called()

    def test_fred_view_edit_callback_updates_and_removes_alias(self):
        """The edit callback should support cancel, update, and alias removal."""
        view = FredView()
        table = MagicMock()
        table.cursor_type = "cell"

        row_key = MagicMock()
        row_key.value = "TEST1"
        cell_key = MagicMock()
        cell_key.row_key = row_key
        table.coordinate_to_cell_key.return_value = cell_key

        app = MagicMock()
        app.config.settings = {
            "fred_settings": {
                "series_list": ["TEST1"],
                "series_aliases": {"TEST1": "Old Alias"},
            }
        }

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=app),
            patch.object(view, "load_all_series") as load_all_series,
        ):
            view.action_edit_series()

            callback = app.push_screen.call_args.args[1]

            callback(None)
            app.config.save_settings.assert_not_called()

            callback("New Alias")
            self.assertEqual(
                app.config.settings["fred_settings"]["series_aliases"]["TEST1"],
                "New Alias",
            )

            callback("")
            self.assertNotIn(
                "TEST1",
                app.config.settings["fred_settings"]["series_aliases"],
            )

        self.assertEqual(app.config.save_settings.call_count, 2)
        self.assertEqual(load_all_series.call_count, 2)
        self.assertEqual(app.notify.call_count, 2)

    def test_fred_view_edit_callback_creates_alias_mapping(self):
        """The callback should create series_aliases when it is absent."""
        view = FredView()
        table = MagicMock()
        table.cursor_type = "cell"

        row_key = MagicMock()
        row_key.value = "TEST2"
        cell_key = MagicMock()
        cell_key.row_key = row_key
        table.coordinate_to_cell_key.return_value = cell_key

        app = MagicMock()
        app.config.settings = {
            "fred_settings": {
                "series_list": ["TEST2"],
            }
        }

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=app),
            patch.object(view, "load_all_series"),
        ):
            view.action_edit_series()
            callback = app.push_screen.call_args.args[1]
            callback("Alias 2")

        self.assertEqual(
            app.config.settings["fred_settings"]["series_aliases"],
            {"TEST2": "Alias 2"},
        )

    def test_fred_view_open_series_guard_and_error_paths(self):
        """Opening should handle invalid selections and browser failures."""
        view = FredView()
        table = MagicMock()
        app = MagicMock()

        table.cursor_type = "none"

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=app),
        ):
            view.action_open_series()

        app.notify.assert_not_called()

        table.cursor_type = "cell"
        table.cursor_row = 0
        cell_key = MagicMock()
        cell_key.row_key = None
        table.coordinate_to_cell_key.return_value = cell_key

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=app),
        ):
            view.action_open_series()

        app.notify.assert_not_called()

        row_key = MagicMock()
        row_key.value = "TEST1"
        cell_key.row_key = row_key

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=app),
            patch(
                "stockstui.ui.views.fred_view.webbrowser.open",
                side_effect=webbrowser.Error("no browser"),
            ),
        ):
            view.action_open_series()

        self.assertEqual(app.notify.call_args.kwargs["severity"], "error")
        self.assertEqual(app.notify.call_args.kwargs["timeout"], 8)

        app.notify.reset_mock()

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(type(view), "app", new_callable=PropertyMock, return_value=app),
            patch(
                "stockstui.ui.views.fred_view.webbrowser.open",
                side_effect=RuntimeError("browser failure"),
            ),
        ):
            view.action_open_series()

        app.notify.assert_called_with(
            "Failed to open browser: browser failure",
            severity="error",
        )

        with patch.object(view, "query_one", side_effect=NoMatches):
            view.action_open_series()

    def test_fred_view_helpers_handle_missing_table(self):
        """Display helpers should ignore an unmounted table."""
        view = FredView()

        with patch.object(view, "query_one", side_effect=NoMatches):
            view._set_loading(True)
            view._show_error()
            view._display_empty()
            view._populate_table([])


    def test_edit_series_empty_alias_when_alias_is_absent(self):
        """An empty alias should be harmless when no alias exists."""
        view = FredView()
        table = MagicMock()
        table.cursor_type = "cell"

        row_key = MagicMock()
        row_key.value = "TEST3"
        cell_key = MagicMock()
        cell_key.row_key = row_key
        table.coordinate_to_cell_key.return_value = cell_key

        app = MagicMock()
        app.config.settings = {
            "fred_settings": {
                "series_list": ["TEST3"],
                "series_aliases": {},
            }
        }

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "load_all_series") as load_all_series,
        ):
            view.action_edit_series()
            callback = app.push_screen.call_args.args[1]
            callback("")

        self.assertEqual(
            app.config.settings["fred_settings"]["series_aliases"],
            {},
        )
        app.config.save_settings.assert_called_once_with()
        load_all_series.assert_called_once_with()

    def test_edit_series_handles_missing_table(self):
        """Editing should safely ignore an unmounted table."""
        view = FredView()

        with patch.object(view, "query_one", side_effect=NoMatches):
            view.action_edit_series()

    def test_load_all_series_handles_missing_configuration(self):
        """Missing API keys and empty series lists should show helpful states."""
        view = FredView()
        app = MagicMock()

        load_function = FredView.load_all_series.__wrapped__

        app.config.settings = {"fred_settings": {}}

        with patch.object(
            type(view),
            "app",
            new_callable=PropertyMock,
            return_value=app,
        ):
            load_function(view)

        app.call_from_thread.assert_called_once_with(view._show_error)

        app.call_from_thread.reset_mock()
        app.config.settings = {
            "fred_settings": {
                "api_key": "fake-key",
                "series_list": [],
            }
        }

        with patch.object(
            type(view),
            "app",
            new_callable=PropertyMock,
            return_value=app,
        ):
            load_function(view)

        app.call_from_thread.assert_called_once_with(view._display_empty)

    def test_load_all_series_filters_failed_requests(self):
        """A failed series request should not discard successful summaries."""
        view = FredView()
        app = MagicMock()
        app.config.settings = {
            "fred_settings": {
                "api_key": "fake-key",
                "series_list": ["GOOD", "BAD"],
            }
        }

        good_summary = {
            "id": "GOOD",
            "title": "Successful series",
        }

        def get_summary(series_id, api_key):
            if series_id == "BAD":
                raise RuntimeError("FRED request failed")
            return good_summary

        load_function = FredView.load_all_series.__wrapped__

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch(
                "stockstui.ui.views.fred_view.fred_provider.get_series_summary",
                side_effect=get_summary,
            ),
        ):
            load_function(view)

        self.assertEqual(app.call_from_thread.call_count, 2)
        app.call_from_thread.assert_any_call(view._set_loading, True)
        app.call_from_thread.assert_any_call(
            view._populate_table,
            [good_summary],
        )

    def test_error_and_empty_messages_update_table(self):
        """Error and empty states should clear and update the table."""
        view = FredView()
        table = MagicMock()

        with patch.object(view, "query_one", return_value=table):
            view._show_error()

        self.assertFalse(table.loading)
        table.clear.assert_called_once_with()
        table.add_row.assert_called_once_with(
            "Error: API Key missing. Go to Configs > FRED Settings."
        )

        table.reset_mock()

        with patch.object(view, "query_one", return_value=table):
            view._display_empty()

        self.assertFalse(table.loading)
        table.clear.assert_called_once_with()
        table.add_row.assert_called_once_with(
            "No series configured. Go to Configs > FRED Settings to add data."
        )

    def test_populate_table_covers_remaining_formatting_branches(self):
        """Population should format extremes, neutral values, and missing aliases."""
        view = FredView()
        table = MagicMock()
        table.row_count = 1
        table.cursor_row = None

        app = MagicMock()
        app.theme_variables = {
            "success": "green",
            "error": "red",
            "warning": "yellow",
            "text-muted": "dim",
        }
        app.config.settings = {
            "fred_settings": {
                "series_aliases": {},
            }
        }

        summaries = [
            {
                "id": "HIGH",
                "title": "High range",
                "current": "N/A",
                "yoy_pct": -2.0,
                "roll_12": None,
                "roll_24": None,
                "z_10y": 2.5,
                "hist_min_10y": None,
                "hist_max_10y": None,
                "pct_of_range": 95,
                "date": "2026-01-01",
                "frequency": "Q",
                "units": "Percent",
            },
            {
                "id": "LOW",
                "title": "Low range",
                "current": None,
                "yoy_pct": 0,
                "z_10y": 0.5,
                "pct_of_range": 5,
            },
        ]

        with (
            patch.object(view, "query_one", return_value=table),
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
        ):
            view._populate_table(summaries)

        self.assertEqual(table.add_row.call_count, 2)

        first_row = table.add_row.call_args_list[0]
        first_values = first_row.args

        self.assertEqual(str(first_values[0]), "High range")
        self.assertEqual(str(first_values[1]), "N/A")
        self.assertEqual(str(first_values[2]), "-2.0%")
        self.assertEqual(str(first_values[5]), "+2.50")
        self.assertEqual(str(first_values[8]), "95%")
        self.assertEqual(str(first_values[11]), "Percent")
        self.assertEqual(first_row.kwargs["key"], "HIGH")

        second_row = table.add_row.call_args_list[1]
        second_values = second_row.args

        self.assertEqual(str(second_values[0]), "Low range")
        self.assertEqual(str(second_values[2]), "0.0%")
        self.assertEqual(str(second_values[5]), "+0.50")
        self.assertEqual(str(second_values[8]), "5%")

        self.assertEqual(table.cursor_coordinate, (0, 0))
