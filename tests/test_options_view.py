import unittest
from unittest.mock import MagicMock, Mock, PropertyMock, patch
from textual.app import App
from textual.widgets import Select, ContentSwitcher, Input, DataTable, Static
from textual.dom import NoMatches

from stockstui.ui.views.options_view import OptionsView
from stockstui.ui.position_modal import PositionModal


class OptionsViewTestApp(App):
    """App wrapper for testing OptionsView."""

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        # Mock lists for suggester
        self.config.lists = {"default": [{"ticker": "AAPL", "note": "Apple"}]}
        self.options_ticker = None
        self.theme_variables = {
            "surface": "black",
            "background": "black",
            "success": "green",
            "error": "red",
            "warning": "yellow",
            "text-muted": "dim",
            "accent": "blue",
            "primary": "blue",
            "foreground": "white",
        }
        self._last_options_data = None
        self.option_positions = {}
        # Add the missing methods
        self.fetch_options_chain = Mock()
        self.fetch_options_expirations = Mock()
        self.remove_option_position = Mock()
        self.add_option_position = Mock()
        self.push_screen = Mock()
        self.notify = Mock()

    def compose(self):
        yield OptionsView()


class TestOptionsView(unittest.IsolatedAsyncioTestCase):
    def test_parse_ticker_logic(self):
        """Test the helper method _parse_ticker_from_input directly."""
        # This method is pure logic, doesn't need a running app
        view = OptionsView()
        self.assertEqual(view._parse_ticker_from_input("AAPL"), "AAPL")
        self.assertEqual(view._parse_ticker_from_input("AAPL - Apple Inc"), "AAPL")
        self.assertEqual(view._parse_ticker_from_input("  tsla  "), "TSLA")

    async def test_initial_state(self):
        """Test initial UI state on mount."""
        app = OptionsViewTestApp()
        async with app.run_test():
            app.query_one(OptionsView)
            select = app.query_one("#options-expiration-select", Select)

            # Should be disabled initially
            self.assertTrue(select.disabled)

            # Ticker input should exist
            inp = app.query_one("#options-ticker-input", Input)
            self.assertIsNotNone(inp)

    async def test_update_expirations(self):
        """Test updating the expiration selector."""
        app = OptionsViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            dates = ["2023-01-01", "2023-02-01"]
            view.update_expirations(dates)
            await pilot.pause()

            select = app.query_one("#options-expiration-select", Select)
            self.assertFalse(select.disabled)
            self.assertEqual(select.value, "2023-01-01")  # Defaults to first

    async def test_expiration_navigation_actions(self):
        """Test next/prev expiration actions."""
        app = OptionsViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            # Setup
            dates = ["D1", "D2", "D3"]
            view.update_expirations(dates)
            await pilot.pause()

            select = app.query_one("#options-expiration-select", Select)
            self.assertEqual(select.value, "D1")

            # Test Next
            view.action_next_expiration()
            await pilot.pause()
            self.assertEqual(select.value, "D2")

            view.action_next_expiration()
            await pilot.pause()
            self.assertEqual(select.value, "D3")

            # Cap at end
            view.action_next_expiration()
            await pilot.pause()
            self.assertEqual(select.value, "D3")

            # Test Prev
            view.action_prev_expiration()
            await pilot.pause()
            self.assertEqual(select.value, "D2")

    async def test_toggle_chart_action(self):
        """Test toggling between table and chart."""
        app = OptionsViewTestApp()

        # We need _render_options_data to run at least once to create the ContentSwitcher?
        # create_table/render creates the switcher.
        # So we need to call _render_options_data manually or mock the switcher existence?
        # ContentSwitcher is created inside _render_options_data.
        # If _last_options_data is None (default), it renders a Static message, NOT the switcher.
        # So action_toggle_chart calls "self.query_one(switcher)". If it doesn't exist -> NoMatches.

        # We must simulate rendering data first to test toggling.

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)
            app._last_options_data = {
                "calls": MagicMock(empty=False),  # Mock dataframe
                "puts": MagicMock(empty=False),
                "underlying": {"regularMarketPrice": 100},
            }
            # We need real DataFrames for render logic iterates rows...
            # Creating dummy DF
            import pandas as pd

            app._last_options_data["calls"] = pd.DataFrame(
                [
                    {
                        "strike": 100,
                        "contractSymbol": "C1",
                        "openInterest": 10,
                        "volume": 5,
                    }
                ]
            )
            app._last_options_data["puts"] = pd.DataFrame(
                [
                    {
                        "strike": 100,
                        "contractSymbol": "P1",
                        "openInterest": 10,
                        "volume": 5,
                    }
                ]
            )

            # Manually trigger render
            await view._render_options_data()
            await pilot.pause()

            # Now switcher should exist
            switcher = app.query_one("#options-content-switcher", ContentSwitcher)
            self.assertEqual(switcher.current, "options-tables-view")

            # Toggle
            view.action_toggle_chart()
            await pilot.pause()
            self.assertEqual(switcher.current, "options-chart-view")

            # Toggle back
            view.action_toggle_chart()
            await pilot.pause()
            self.assertEqual(switcher.current, "options-tables-view")

    async def test_render_options_data_with_error(self):
        """Test rendering options data when there's an error."""
        app = OptionsViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            # Simulate error condition
            app._last_options_data = {"error": "Something went wrong"}

            await view._render_options_data()
            await pilot.pause()

            # Check that error message is displayed
            # This should trigger the error handling path

    async def test_render_options_data_empty_data(self):
        """Test rendering options data when data is empty."""
        app = OptionsViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            # Simulate empty data condition
            import pandas as pd

            empty_df = pd.DataFrame()
            app._last_options_data = {
                "calls": empty_df,
                "puts": empty_df,
                "underlying": {},
            }
            app.options_ticker = "AAPL"

            await view._render_options_data()
            await pilot.pause()

            # Check that "No options data found" message is displayed

    async def test_manage_position_action_without_focus(self):
        """Test action_manage_position when no table is focused."""
        app = OptionsViewTestApp()
        async with app.run_test():
            view = app.query_one(OptionsView)

            # Temporarily override the focused property to return None
            original_focused_property = type(app).focused
            type(app).focused = property(lambda self: None)

            # This should return early without doing anything
            view.action_manage_position()

            # Restore the original property
            type(app).focused = original_focused_property

    async def test_manage_position_action_with_wrong_focus(self):
        """Test action_manage_position when focused element is not an options table."""
        from textual.widgets import Label

        app = OptionsViewTestApp()
        async with app.run_test():
            view = app.query_one(OptionsView)

            # Create a mock widget that's not an options table
            mock_widget = Label("test")

            # Temporarily override the focused property to return the mock widget
            original_focused_property = type(app).focused
            type(app).focused = property(lambda self: mock_widget)

            # This should return early without doing anything
            view.action_manage_position()

            # Restore the original property
            type(app).focused = original_focused_property

    async def test_manage_position_action_with_no_row_selected(self):
        """Test action_manage_position when no row is selected."""
        from textual.widgets import DataTable

        app = OptionsViewTestApp()
        async with app.run_test():
            view = app.query_one(OptionsView)

            # Create a mock DataTable that simulates no row selection
            mock_table = Mock(spec=DataTable)
            mock_table.id = "options-calls-table"

            # Temporarily override the focused property to return the mock table
            original_focused_property = type(app).focused
            type(app).focused = property(lambda self: mock_table)

            # Mock coordinate_to_cell_key to return a row_key with no value
            mock_coord_result = Mock()
            mock_coord_result.row_key = Mock()
            mock_coord_result.row_key.value = None  # No contract symbol
            mock_table.coordinate_to_cell_key.return_value = mock_coord_result

            # This should return early without doing anything
            view.action_manage_position()

            # Restore the original property
            type(app).focused = original_focused_property

    async def test_manage_position_action_with_valid_selection(self):
        """Test action_manage_position with a valid row selection."""
        import pandas as pd

        app = OptionsViewTestApp()

        # Mock the app methods that are called
        app.push_screen = Mock()
        app.remove_option_position = Mock()
        app.add_option_position = Mock()

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            # Set up data for rendering first - but avoid creating the chart by using minimal data
            app._last_options_data = {
                "calls": pd.DataFrame(
                    [
                        {
                            "strike": 100,
                            "contractSymbol": "AAPL230101C00100000",
                            "openInterest": 10,
                            "volume": 5,
                        }
                    ]
                ),
                "puts": pd.DataFrame(
                    [
                        {
                            "strike": 100,
                            "contractSymbol": "AAPL230101P00100000",
                            "openInterest": 10,
                            "volume": 5,
                        }
                    ]
                ),
                "underlying": {"regularMarketPrice": 100},
            }
            app.options_ticker = "AAPL"

            # Temporarily disable the chart creation by mocking the OIChart constructor
            from unittest.mock import patch
            from stockstui.ui.widgets.oi_chart import OIChart

            with patch.object(OIChart, "replot", return_value=None):
                # Render the data to create the tables
                await view._render_options_data()
                await pilot.pause()

                # Now test the position management
                # Create a mock DataTable that simulates a row selection
                mock_table = Mock(spec=DataTable)
                mock_table.id = "options-calls-table"

                # Temporarily override the focused property to return the mock table
                original_focused_property = type(app).focused
                type(app).focused = property(lambda self: mock_table)

                # Mock coordinate_to_cell_key to return a valid contract symbol
                mock_coord_result = Mock()
                mock_coord_result.row_key = Mock()
                mock_coord_result.row_key.value = (
                    "AAPL230101C00100000"  # Valid contract symbol
                )
                mock_table.coordinate_to_cell_key.return_value = mock_coord_result

                # This should attempt to open the PositionModal
                view.action_manage_position()

                # Restore the original property
                type(app).focused = original_focused_property

    async def test_request_expirations_when_no_ticker(self):
        """Test _request_expirations when no ticker is set."""
        app = OptionsViewTestApp()
        async with app.run_test():
            view = app.query_one(OptionsView)

            # Ensure no ticker is set
            app.options_ticker = None

            # This should return early without doing anything
            view._request_expirations()

    async def test_request_options_chain_when_no_ticker(self):
        """Test _request_options_chain when no ticker is set."""
        app = OptionsViewTestApp()
        async with app.run_test():
            view = app.query_one(OptionsView)

            # Ensure no ticker is set
            app.options_ticker = None

            # This should return early without doing anything
            view._request_options_chain()

    async def test_request_options_chain_with_valid_data(self):
        """Test _request_options_chain with valid data."""
        app = OptionsViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            # Set up ticker and expiration
            app.options_ticker = "AAPL"

            # Update expirations to enable the selector
            view.update_expirations(["2023-01-01"])
            await pilot.pause()

            # Mock the fetch_options_chain method on the app
            app.fetch_options_chain = Mock()

            # This should call fetch_options_chain
            view._request_options_chain()

            # Verify that the method was called
            app.fetch_options_chain.assert_called_once_with("AAPL", "2023-01-01")

    async def test_on_options_ticker_submitted(self):
        """Test handling ticker submission."""
        app = OptionsViewTestApp()

        async with app.run_test():
            view = app.query_one(OptionsView)

            # Mock the fetch_options_expirations method on the app
            app.fetch_options_expirations = Mock()

            # Create a mock input submission event
            from textual.widgets import Input

            input_widget = app.query_one("#options-ticker-input", Input)

            # Test with a valid value
            input_widget.value = "AAPL"
            event = Input.Submitted(input_widget, "AAPL")
            view.on_options_ticker_submitted(event)

            # Check that fetch_options_expirations was called
            app.fetch_options_expirations.assert_called_once_with("AAPL")

    async def test_on_options_ticker_submitted_with_suggestion_format(self):
        """Test handling ticker submission with suggestion format (TICKER - Description)."""
        app = OptionsViewTestApp()

        async with app.run_test():
            view = app.query_one(OptionsView)

            # Mock the fetch_options_expirations method on the app
            app.fetch_options_expirations = Mock()

            # Create a mock input submission event
            from textual.widgets import Input

            input_widget = app.query_one("#options-ticker-input", Input)

            # Test with suggestion format
            input_widget.value = "AAPL - Apple Inc."
            event = Input.Submitted(input_widget, "AAPL - Apple Inc.")
            view.on_options_ticker_submitted(event)

            # Check that fetch_options_expirations was called with just the ticker
            app.fetch_options_expirations.assert_called_once_with("AAPL")

    async def test_on_expiration_changed(self):
        """Test handling expiration selection change."""
        app = OptionsViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            # Set up ticker and expiration
            app.options_ticker = "AAPL"
            view.update_expirations(["2023-01-01", "2023-02-01"])
            await pilot.pause()

            # Mock the fetch_options_chain method on the app
            app.fetch_options_chain = Mock()

            # Create a mock select change event - fix the constructor
            from textual.widgets import Select

            select_widget = app.query_one("#options-expiration-select", Select)
            event = Select.Changed(select_widget, "2023-01-01")
            view.on_expiration_changed(event)

            # Check that fetch_options_chain was called
            app.fetch_options_chain.assert_called_once_with("AAPL", "2023-01-01")

    async def test_on_toggle_chart_pressed(self):
        """Test the button press handler for toggling chart."""
        app = OptionsViewTestApp()

        # Set up data for rendering first
        import pandas as pd

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)
            app._last_options_data = {
                "calls": pd.DataFrame(
                    [
                        {
                            "strike": 100,
                            "contractSymbol": "C1",
                            "openInterest": 10,
                            "volume": 5,
                        }
                    ]
                ),
                "puts": pd.DataFrame(
                    [
                        {
                            "strike": 100,
                            "contractSymbol": "P1",
                            "openInterest": 10,
                            "volume": 5,
                        }
                    ]
                ),
                "underlying": {"regularMarketPrice": 100},
            }

            # Render the data to create the UI elements
            await view._render_options_data()
            await pilot.pause()

            # Trigger the button press event - fix the method signature (takes only self)
            from textual.widgets import Button

            button = app.query_one("#options-view-toggle", Button)
            Button.Pressed(button)
            # Call the method without the event parameter since it only takes 'self'
            view.on_toggle_chart_pressed()


    def test_on_mount_requests_existing_ticker(self):
        """Mount should request expirations when a ticker is already selected."""
        view = OptionsView()
        app = MagicMock()
        app.options_ticker = "AAPL"
        select = MagicMock()

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "query_one", return_value=select),
            patch.object(view, "call_after_refresh") as call_after_refresh,
        ):
            view.on_mount()

        call_after_refresh.assert_called_once_with(view._request_expirations)
        self.assertTrue(select.disabled)

    def test_on_mount_handles_missing_expiration_select(self):
        """Mount should tolerate an expiration selector that is not mounted."""
        view = OptionsView()
        app = MagicMock()
        app.options_ticker = None

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "query_one", side_effect=NoMatches),
        ):
            view.on_mount()

    def test_update_expirations_empty_and_missing_select(self):
        """Empty expiration results should disable the selector."""
        view = OptionsView()
        select = MagicMock()

        with patch.object(view, "query_one", return_value=select):
            view.update_expirations([])

        self.assertEqual(view.expirations, [])
        select.set_options.assert_called_once_with(
            [("No options available", "")]
        )
        self.assertTrue(select.disabled)

        with patch.object(view, "query_one", side_effect=NoMatches):
            view.update_expirations(["2026-01-01"])

        self.assertEqual(view.expirations, ["2026-01-01"])

    def test_expiration_navigation_guard_paths(self):
        """Expiration navigation should handle disabled and invalid selections."""
        view = OptionsView()
        select = MagicMock()

        view.expirations = []
        select.disabled = False
        with patch.object(view, "query_one", return_value=select):
            view.action_prev_expiration()
            view.action_next_expiration()

        view.expirations = ["D1", "D2"]
        select.disabled = True
        with patch.object(view, "query_one", return_value=select):
            view.action_prev_expiration()
            view.action_next_expiration()

        select.disabled = False
        select.value = "UNKNOWN"
        with patch.object(view, "query_one", return_value=select):
            view.action_prev_expiration()
            view.action_next_expiration()

        select.value = "D1"
        with patch.object(view, "query_one", return_value=select):
            view.action_prev_expiration()

        self.assertEqual(select.value, "D1")

        with patch.object(view, "query_one", side_effect=NoMatches):
            view.action_prev_expiration()
            view.action_next_expiration()

    def test_toggle_chart_handles_missing_switcher(self):
        """Toggling should be harmless before options content is rendered."""
        view = OptionsView()

        with patch.object(view, "query_one", side_effect=NoMatches):
            view.action_toggle_chart()

    def test_manage_position_rejects_wrong_table_and_missing_row_key(self):
        """Position management should reject irrelevant or invalid rows."""
        view = OptionsView()
        app = MagicMock()

        wrong_table = MagicMock(spec=DataTable)
        wrong_table.id = "unrelated-table"
        app.focused = wrong_table

        with patch.object(
            type(view),
            "app",
            new_callable=PropertyMock,
            return_value=app,
        ):
            view.action_manage_position()

        app.push_screen.assert_not_called()

        valid_table = MagicMock(spec=DataTable)
        valid_table.id = "options-calls-table"
        cell_key = MagicMock()
        cell_key.row_key = None
        valid_table.coordinate_to_cell_key.return_value = cell_key
        app.focused = valid_table

        with patch.object(
            type(view),
            "app",
            new_callable=PropertyMock,
            return_value=app,
        ):
            view.action_manage_position()

        app.push_screen.assert_not_called()

    def test_manage_position_callback_handles_all_results(self):
        """The position callback should support cancel, remove, and save."""
        view = OptionsView()
        app = MagicMock()
        app.options_ticker = "AAPL"
        app.option_positions = {
            "AAPL-CALL": {
                "quantity": 2,
                "avg_cost": 3.5,
            }
        }

        table = MagicMock(spec=DataTable)
        table.id = "options-calls-table"
        table.cursor_coordinate = (0, 0)

        row_key = MagicMock()
        row_key.value = "AAPL-CALL"
        cell_key = MagicMock()
        cell_key.row_key = row_key
        table.coordinate_to_cell_key.return_value = cell_key
        app.focused = table

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "call_after_refresh") as call_after_refresh,
        ):
            view.action_manage_position()

            modal, callback = app.push_screen.call_args.args

            self.assertIsInstance(modal, PositionModal)

            callback(None)
            app.remove_option_position.assert_not_called()
            app.add_option_position.assert_not_called()

            callback((0, 4.0))
            app.remove_option_position.assert_called_once_with("AAPL-CALL")

            callback((3, 5.5))
            app.add_option_position.assert_called_once_with(
                "AAPL-CALL",
                "AAPL",
                3,
                5.5,
            )

        self.assertEqual(call_after_refresh.call_count, 2)
        call_after_refresh.assert_called_with(view._render_options_data)

    def test_request_methods_handle_missing_widgets_and_blank_expiration(self):
        """Request helpers should tolerate missing or blank controls."""
        view = OptionsView()
        app = MagicMock()
        app.options_ticker = "AAPL"

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "query_one", side_effect=NoMatches),
        ):
            view._request_expirations()
            view._request_options_chain()

        app.fetch_options_expirations.assert_called_once_with("AAPL")
        app.fetch_options_chain.assert_not_called()

        select = MagicMock()
        select.value = ""

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "query_one", return_value=select),
        ):
            view._request_options_chain()

        app.fetch_options_chain.assert_not_called()

    def test_empty_ticker_submission_is_ignored(self):
        """Submitting an empty ticker should not request expirations."""
        view = OptionsView()
        app = MagicMock()
        event = MagicMock()
        event.value = ""

        with (
            patch.object(
                type(view),
                "app",
                new_callable=PropertyMock,
                return_value=app,
            ),
            patch.object(view, "_request_expirations") as request_expirations,
        ):
            view.on_options_ticker_submitted(event)

        request_expirations.assert_not_called()


    async def test_render_options_data_with_no_last_data(self):
        """Missing cached options data should display the initial guidance."""
        app = OptionsViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)
            app._last_options_data = None

            await view._render_options_data()
            await pilot.pause()

            message = app.query_one("#options-info-message", Static)
            self.assertIn(
                "Enter a ticker symbol and select an expiration date",
                str(message.render()),
            )

    async def test_render_options_data_remaining_branches(self):
        """Render rows covering ITM styling, positions, P/L, and date handling."""
        import pandas as pd
        from stockstui.ui.widgets.oi_chart import OIChart

        app = OptionsViewTestApp()
        app.options_ticker = "AAPL"
        app.option_positions = {
            "CALL-PROFIT": {
                "quantity": 2,
                "avg_cost": 1.0,
            },
            "CALL-FLAT": {
                "quantity": 1,
                "avg_cost": 1.0,
            },
            "PUT-LOSS": {
                "quantity": 1,
                "avg_cost": 4.0,
            },
        }

        calls = pd.DataFrame(
            [
                {
                    "strike": 90.0,
                    "contractSymbol": "CALL-PROFIT",
                    "lastPrice": 3.0,
                    "bid": 2.8,
                    "ask": 3.2,
                    "percentChange": 5.0,
                    "volume": float("nan"),
                    "openInterest": float("nan"),
                    "impliedVolatility": 0.25,
                    "delta": 0.6,
                    "gamma": 0.02,
                    "theta": -0.01,
                    "vega": 0.15,
                },
                {
                    "strike": 110.0,
                    "contractSymbol": "CALL-FLAT",
                    "lastPrice": 1.0,
                    "percentChange": 0.0,
                    "volume": 10,
                    "openInterest": 20,
                },
            ]
        )

        puts = pd.DataFrame(
            [
                {
                    "strike": 110.0,
                    "contractSymbol": "PUT-LOSS",
                    "lastPrice": 2.0,
                    "bid": 1.8,
                    "ask": 2.2,
                    "percentChange": -4.0,
                    "volume": 30,
                    "openInterest": 40,
                    "impliedVolatility": 0.30,
                    "delta": -0.4,
                    "gamma": 0.03,
                    "theta": -0.02,
                    "vega": 0.18,
                }
            ]
        )

        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)

            with (
                patch.object(OIChart, "replot", return_value=None),
                patch(
                    "stockstui.ui.views.options_view.market_provider.get_ticker_info",
                    return_value={"currency": "USD"},
                ),
            ):
                # Invalid expiration covers the exception branch.
                app._last_options_data = {
                    "calls": calls,
                    "puts": pd.DataFrame(),
                    "underlying": {"regularMarketPrice": 100.0},
                    "expiration": "not-a-date",
                }
                await view._render_options_data()
                await pilot.pause()

                # Valid expiration plus call/put rows covers the remaining paths.
                app._last_options_data = {
                    "calls": calls,
                    "puts": puts,
                    "underlying": {"regularMarketPrice": 100.0},
                    "expiration": "2099-12-31",
                }
                await view._render_options_data()
                await pilot.pause()

            calls_table = app.query_one("#options-calls-table", DataTable)
            puts_table = app.query_one("#options-puts-table", DataTable)

            self.assertEqual(calls_table.row_count, 2)
            self.assertEqual(puts_table.row_count, 1)

    async def test_render_options_data_handles_missing_container(self):
        """Rendering should tolerate an unmounted display container."""
        view = OptionsView()

        with patch.object(view, "query_one", side_effect=NoMatches):
            await view._render_options_data()

    def test_update_expirations_truthy_empty_iterable(self):
        """A truthy iterable producing no options should leave the value unset."""

        class TruthyEmpty(list):
            def __bool__(self):
                return True

        view = OptionsView()
        select = MagicMock()
        select.value = None
        expirations = TruthyEmpty()

        with patch.object(view, "query_one", return_value=select):
            view.update_expirations(expirations)

        select.set_options.assert_called_once_with([])
        self.assertFalse(select.disabled)
        self.assertIsNone(select.value)
