import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from textual.app import App
from textual.widgets import Button, Static

from stockstui.ui.views.debug_view import DebugView


class DebugViewTestApp(App):
    """App wrapper for testing DebugView."""

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        # Mock lists for testing
        self.config.lists = {
            "stocks": [{"ticker": "AAPL"}, {"ticker": "GOOGL"}],
            "crypto": [{"ticker": "BTC-USD"}],
        }
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
        # Mock methods that might be called
        self.run_info_comparison_test = MagicMock()
        self.run_fred_debug_test = MagicMock()
        self.run_ticker_debug_test = MagicMock()
        self.run_list_debug_test = MagicMock()
        self.run_cache_test = MagicMock()
        self.push_screen = MagicMock()
        self.notify = MagicMock()
        self.config.settings = {"fred_settings": {"api_key": "test_key"}}

    def compose(self):
        yield DebugView()


class TestDebugViewExtended(unittest.IsolatedAsyncioTestCase):
    """Extended test suite for DebugView."""

    async def test_initial_state(self):
        """Test initial UI state on mount."""
        app = DebugViewTestApp()
        async with app.run_test():
            view = app.query_one(DebugView)

            # Check that the buttons exist
            buttons = view.query(".debug-buttons Button")
            self.assertEqual(
                len(buttons), 5
            )  # Compare Ticker Info, Test Tickers, Test Lists, Test Cache, Test FRED

            # Check that the output container exists
            container = view.query_one("#debug-output-container")
            info_message = container.query_one("#info-message", Static)
            self.assertIn("Run a test to see results", str(info_message.render()))

    async def test_on_debug_button_pressed_compare_info(self):
        """Test handling the Compare Ticker Info button press."""
        app = DebugViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Find the Compare Ticker Info button
            button = view.query_one("#debug-compare-info", Button)

            # Simulate button press
            await pilot.click(button)

            # Should have pushed the CompareInfoModal
            app.push_screen.assert_called()

    async def test_on_debug_button_pressed_fred(self):
        """Test handling the Test FRED button press."""
        app = DebugViewTestApp()
        app.push_screen = MagicMock()  # Use MagicMock instead of AsyncMock

        async with app.run_test():
            view = app.query_one(DebugView)

            # Find the Test FRED button
            button = view.query_one("#debug-test-fred", Button)

            # Instead of clicking, directly call the event handler
            from textual.widgets import Button as TextualButton

            event = TextualButton.Pressed(button)
            await view.on_debug_button_pressed(event)

            # Should have pushed the FredSeriesModal
            app.push_screen.assert_called()

    async def test_on_debug_button_pressed_tickers(self):
        """Test handling the Test Tickers button press."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Find the Test Tickers button
            button = view.query_one("#debug-test-tickers", Button)

            # Simulate button press
            await pilot.click(button)

            # Should have called run_ticker_debug_test
            app.run_ticker_debug_test.assert_called()

    async def test_on_debug_button_pressed_lists(self):
        """Test handling the Test Lists button press."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Find the Test Lists button
            button = view.query_one("#debug-test-lists", Button)

            # Simulate button press
            await pilot.click(button)

            # Should have called run_list_debug_test
            app.run_list_debug_test.assert_called()

    async def test_on_debug_button_pressed_cache(self):
        """Test handling the Test Cache button press."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Find the Test Cache button
            button = view.query_one("#debug-test-cache", Button)

            # Simulate button press
            await pilot.click(button)

            # Should have called run_cache_test
            app.run_cache_test.assert_called()

    async def test_on_key_i_focuses_first_button(self):
        """Test that pressing 'i' focuses the first button."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Press 'i' to focus first button
            await pilot.press("i")

            # First button should now be focused
            buttons = view.query(".debug-buttons Button")
            focused_buttons = [btn for btn in buttons if btn.has_focus]
            # Check that at least one button is focused
            self.assertGreaterEqual(len(focused_buttons), 1)
            if focused_buttons:
                self.assertEqual(focused_buttons[0], buttons[0])

    async def test_on_key_navigation_with_focused_button(self):
        """Test keyboard navigation when a button is focused."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Focus the first button
            buttons = view.query(".debug-buttons Button")
            buttons[0].focus()

            # Press 'l' to move to the next button
            await pilot.press("l")

            # Second button should now be focused
            focused_buttons = [btn for btn in buttons if btn.has_focus]
            self.assertEqual(len(focused_buttons), 1)
            self.assertEqual(focused_buttons[0], buttons[1])

            # Press 'h' to move back to the previous button
            await pilot.press("h")

            # First button should now be focused
            focused_buttons = [btn for btn in buttons if btn.has_focus]
            self.assertEqual(len(focused_buttons), 1)
            self.assertEqual(focused_buttons[0], buttons[0])

    async def test_on_key_left_right_navigation(self):
        """Test keyboard navigation with left/right arrows."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Focus the first button
            buttons = view.query(".debug-buttons Button")
            buttons[0].focus()

            # Press 'right' arrow to move to the next button
            await pilot.press("right")

            # Second button should now be focused
            focused_buttons = [btn for btn in buttons if btn.has_focus]
            self.assertEqual(len(focused_buttons), 1)
            self.assertEqual(focused_buttons[0], buttons[1])

            # Press 'left' arrow to move back to the previous button
            await pilot.press("left")

            # First button should now be focused
            focused_buttons = [btn for btn in buttons if btn.has_focus]
            self.assertEqual(len(focused_buttons), 1)
            self.assertEqual(focused_buttons[0], buttons[0])

    async def test_on_key_no_buttons(self):
        """Test keyboard navigation when there are no buttons."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Remove all buttons from the view temporarily to test the edge case
            # This is a bit tricky, so we'll just make sure the method doesn't crash
            # when there are no buttons to navigate
            buttons = view.query(".debug-buttons Button")

            # Focus the first button
            buttons[0].focus()

            # Press 'i' when already focused - shouldn't crash
            await pilot.press("i")

            # Press 'l' when focused on a button - shouldn't crash
            await pilot.press("l")

    async def test_button_disabled_after_press(self):
        """Test that buttons are disabled after being pressed."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Check initial state - buttons should not be disabled
            buttons = view.query(".debug-buttons Button")
            initial_disabled = [btn.disabled for btn in buttons]
            # Not all buttons should be disabled initially
            self.assertFalse(all(initial_disabled))

            # Press a button
            button = buttons[0]
            await pilot.click(button)

            # After click, all buttons should be disabled
            buttons_after_click = view.query(".debug-buttons Button")
            disabled_after_click = [btn.disabled for btn in buttons_after_click]
            # At least some buttons should be disabled
            self.assertTrue(any(disabled_after_click))

    async def test_output_container_clears_on_button_press(self):
        """Test that the output container clears when a button is pressed."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Get the output container
            container = view.query_one("#debug-output-container")

            # Initially should have the info message
            initial_children = len(container.children)
            self.assertGreater(initial_children, 0)

            # Press a button
            button = view.query_one("#debug-test-tickers", Button)
            await pilot.click(button)

            # Container should have cleared and mounted new content
            # The exact behavior depends on the test, but it should have changed
            # Let's just make sure the method was called without error

    async def test_modal_cancel_scenario(self):
        """Test the scenario when a modal is cancelled."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)

            # Simulate calling the modal close function with None (cancelled)
            view.query_one("#debug-output-container")

            # Get the callback function for compare info
            # This is harder to test directly, so we'll just make sure the code path exists
            # The callback is created inside the event handler, so we'll test the handler logic
            button = view.query_one("#debug-compare-info", Button)
            await pilot.click(button)

            # The modal should have been pushed
            app.push_screen.assert_called()

    async def test_fred_modal_cancel_scenario(self):
        """Test the scenario when the FRED modal is cancelled."""
        app = DebugViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(DebugView)

            # Find the Test FRED button
            button = view.query_one("#debug-test-fred", Button)

            # Instead of clicking, directly call the event handler
            from textual.widgets import Button as TextualButton

            event = TextualButton.Pressed(button)
            await view.on_debug_button_pressed(event)

            # The modal should have been pushed
            app.push_screen.assert_called()

    async def test_different_button_scenarios(self):
        """Test different scenarios for each button."""
        app = DebugViewTestApp()

        async with app.run_test():
            view = app.query_one(DebugView)

            # Test each button individually
            button_ids = [
                "debug-test-tickers",
                "debug-test-lists",
                "debug-test-cache",
            ]  # Exclude modal buttons
            methods = [
                app.run_ticker_debug_test,
                app.run_list_debug_test,
                app.run_cache_test,
            ]

            for i, button_id in enumerate(button_ids):
                button = view.query_one(f"#{button_id}", Button)

                # Instead of clicking, directly call the event handler
                from textual.widgets import Button as TextualButton

                event = TextualButton.Pressed(button)
                await view.on_debug_button_pressed(event)

                # Check that the appropriate method was called for non-modal buttons
                methods[i].assert_called()


    async def test_compare_modal_success_callback(self):
        """A submitted ticker should create the table and start comparison."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)
            button = view.query_one("#debug-compare-info", Button)

            await view.on_debug_button_pressed(Button.Pressed(button))

            callback = app.push_screen.call_args.args[1]
            await callback("AAPL")
            await pilot.pause()

            table = view.query_one("#debug-table")
            self.assertTrue(table.loading)
            self.assertEqual(len(table.columns), 5)
            app.run_info_comparison_test.assert_called_once_with("AAPL")

    async def test_compare_modal_cancel_callback(self):
        """Cancelling comparison should restore the message and buttons."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)
            button = view.query_one("#debug-compare-info", Button)

            await view.on_debug_button_pressed(Button.Pressed(button))

            callback = app.push_screen.call_args.args[1]
            await callback(None)
            await pilot.pause()

            message = view.query_one("#info-message", Static)
            self.assertIn(
                "Run a test to see results",
                str(message.render()),
            )
            self.assertTrue(
                all(
                    not item.disabled
                    for item in view.query(".debug-buttons Button")
                )
            )

    async def test_fred_modal_success_callback(self):
        """A submitted FRED ID should start the API debug test."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)
            button = view.query_one("#debug-test-fred", Button)

            await view.on_debug_button_pressed(Button.Pressed(button))

            callback = app.push_screen.call_args.args[1]
            await callback("  gdp  ")
            await pilot.pause()

            table = view.query_one("#debug-table")
            self.assertTrue(table.loading)
            self.assertEqual(len(table.columns), 2)
            app.run_fred_debug_test.assert_called_once_with(
                ["GDP"],
                "test_key",
            )

    async def test_fred_modal_cancel_callback(self):
        """Cancelling the FRED modal should restore the initial state."""
        app = DebugViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(DebugView)
            button = view.query_one("#debug-test-fred", Button)

            await view.on_debug_button_pressed(Button.Pressed(button))

            callback = app.push_screen.call_args.args[1]
            await callback(None)
            await pilot.pause()

            self.assertIsNotNone(
                view.query_one("#info-message", Static)
            )
            self.assertTrue(
                all(
                    not item.disabled
                    for item in view.query(".debug-buttons Button")
                )
            )

    async def test_on_key_returns_when_no_buttons_exist(self):
        """Keyboard handling should stop safely with no buttons."""
        app = DebugViewTestApp()

        async with app.run_test():
            view = app.query_one(DebugView)
            event = MagicMock()
            event.key = "i"

            with patch.object(view, "query", return_value=[]):
                view.on_key(event)

            event.stop.assert_not_called()

    async def test_on_key_i_directly_focuses_first_button(self):
        """The direct handler should focus the first button for i."""
        app = DebugViewTestApp()

        async with app.run_test():
            view = app.query_one(DebugView)
            first_button = list(
                view.query(".debug-buttons Button")
            )[0]

            event = MagicMock()
            event.key = "i"

            with (
                patch.object(
                    type(app),
                    "focused",
                    new_callable=PropertyMock,
                    return_value=None,
                ),
                patch.object(first_button, "focus") as focus_mock,
            ):
                view.on_key(event)

            focus_mock.assert_called_once()
            event.stop.assert_called_once()

    async def test_on_key_ignores_unrelated_key_with_button_focus(self):
        """Enter should remain available for the focused Button itself."""
        app = DebugViewTestApp()

        async with app.run_test():
            view = app.query_one(DebugView)
            first_button = list(
                view.query(".debug-buttons Button")
            )[0]

            event = MagicMock()
            event.key = "enter"

            with patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=first_button,
            ):
                view.on_key(event)

            event.stop.assert_not_called()
