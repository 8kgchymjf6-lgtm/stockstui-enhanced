import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from textual.app import App, ComposeResult
from textual.widgets import Button
from textual.dom import NoMatches

from stockstui.ui.widgets.tag_filter import TagFilterWidget, TagFilterChanged


class TagFilterApp(App):
    """A minimal app for testing the TagFilterWidget."""

    CSS = """
    TagFilterWidget {
        height: auto;
        width: 100%;
        border: solid green;
    }
    """

    def __init__(self, widget_to_test):
        super().__init__()
        self.widget = widget_to_test

    def compose(self) -> ComposeResult:
        yield self.widget


class TestTagFilterWidget(unittest.IsolatedAsyncioTestCase):
    """Comprehensive tests for the TagFilterWidget."""

    async def test_tag_filter_with_empty_tags(self):
        """Test widget behavior with an empty tag list."""
        widget = TagFilterWidget(available_tags=[], id="tag-filter")
        app = TagFilterApp(widget)

        async with app.run_test():
            # The widget should still mount and function without errors
            self.assertEqual(
                len(widget.query("Button")), 0
            )  # No buttons should be present

    async def test_tag_filter_with_duplicate_tags(self):
        """Test that duplicate tags are handled gracefully."""
        widget = TagFilterWidget(
            available_tags=["tech", "tech", "value"], id="tag-filter"
        )
        app = TagFilterApp(widget)

        async with app.run_test():
            # Should deduplicate tags, resulting in 3 buttons (tech, value, clear)
            self.assertEqual(len(widget.query("Button")), 3)
            self.assertIsNotNone(widget.query_one("#tag-button-tech"))
            self.assertIsNotNone(widget.query_one("#tag-button-value"))

    async def test_tag_selection_and_message_emission(self):
        """Test that clicking tag buttons selects them and emits a message."""
        tags = ["tech", "growth"]
        widget = TagFilterWidget(available_tags=tags, id="tag-filter")
        app = TagFilterApp(widget)

        # Capture TagFilterChanged messages
        messages = []

        def capture_message(message):
            if isinstance(message, TagFilterChanged):
                messages.append(message)

        # Set up the message capturing
        original_post_message = app.post_message

        def custom_post_message(message):
            capture_message(message)
            return original_post_message(message)

        app.post_message = custom_post_message

        async with app.run_test() as pilot:
            # Clear initial messages from mount
            messages.clear()

            # Simulate click on tech button
            tech_button = widget.query_one("#tag-button-tech")
            event = Button.Pressed(tech_button)
            widget.on_tag_button_pressed(event)

            # Wait for message to be processed
            await pilot.pause(0.1)

            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].tags, ["tech"])
            self.assertEqual(widget.query_one("#tag-button-tech").variant, "primary")

            # Simulate click on growth button
            growth_button = widget.query_one("#tag-button-growth")
            event = Button.Pressed(growth_button)
            widget.on_tag_button_pressed(event)

            await pilot.pause(0.1)

            # Check that the last message contains both tags
            if messages:
                self.assertEqual(set(messages[-1].tags), {"tech", "growth"})

    async def test_tag_filter_clear_functionality(self):
        """Test that the clear button resets all selections."""
        tags = ["tech", "growth", "value"]
        widget = TagFilterWidget(available_tags=tags, id="tag-filter")
        app = TagFilterApp(widget)

        # Capture TagFilterChanged messages
        messages = []

        def capture_message(message):
            if isinstance(message, TagFilterChanged):
                messages.append(message)

        # Set up the message capturing
        original_post_message = app.post_message

        def custom_post_message(message):
            capture_message(message)
            return original_post_message(message)

        app.post_message = custom_post_message

        async with app.run_test() as pilot:
            # Clear initial messages from mount
            messages.clear()

            # Select a tag directly
            tech_button = widget.query_one("#tag-button-tech")
            event = Button.Pressed(tech_button)
            widget.on_tag_button_pressed(event)
            await pilot.pause(0.1)

            if messages:
                self.assertEqual(messages[-1].tags, ["tech"])

            # Clear the filter directly
            clear_button = widget.query_one("#clear-filter-button")
            event_clear = Button.Pressed(clear_button)
            widget.on_clear_button_pressed(event_clear)
            await pilot.pause(0.1)

            if messages:
                self.assertEqual(messages[-1].tags, [])
            self.assertEqual(widget.query_one("#tag-button-tech").variant, "default")


    async def test_selected_tag_can_be_deselected(self):
        """Clicking a selected tag again should remove its selection."""
        widget = TagFilterWidget(
            available_tags=["tech"],
            id="tag-filter",
        )
        app = TagFilterApp(widget)

        async with app.run_test() as pilot:
            button = widget.query_one("#tag-button-tech")

            widget.on_tag_button_pressed(Button.Pressed(button))
            await pilot.pause()

            self.assertIn("tech", widget.selected_tags)
            self.assertEqual(button.variant, "primary")

            widget.on_tag_button_pressed(Button.Pressed(button))
            await pilot.pause()

            self.assertNotIn("tech", widget.selected_tags)
            self.assertEqual(button.variant, "default")

    async def test_update_filter_status_shows_filtered_count(self):
        """The status label should show reduced result counts."""
        widget = TagFilterWidget(
            available_tags=["tech"],
            id="tag-filter",
        )
        app = TagFilterApp(widget)

        async with app.run_test():
            widget.selected_tags.add("tech")
            widget.update_filter_status(
                filtered_count=2,
                total_count=5,
            )

            label = widget.query_one("#filter-status")
            self.assertEqual(
                str(label.render()),
                "Showing 2 of 5",
            )

    async def test_update_filter_status_clears_when_counts_match(self):
        """No status text is needed when every item is still visible."""
        widget = TagFilterWidget(
            available_tags=["tech"],
            id="tag-filter",
        )
        app = TagFilterApp(widget)

        async with app.run_test():
            widget.selected_tags.add("tech")
            widget.update_filter_status(
                filtered_count=5,
                total_count=5,
            )

            label = widget.query_one("#filter-status")
            self.assertEqual(str(label.render()), "")

    async def test_update_filter_status_clears_without_selection(self):
        """The status should be blank when no tags are selected."""
        widget = TagFilterWidget(
            available_tags=["tech"],
            id="tag-filter",
        )
        app = TagFilterApp(widget)

        async with app.run_test():
            widget.update_filter_status(
                filtered_count=2,
                total_count=5,
            )

            label = widget.query_one("#filter-status")
            self.assertEqual(str(label.render()), "")

    def test_on_key_ignores_non_button_focus(self):
        """Keyboard navigation should only run when a button is focused."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = object()
        event = MagicMock()
        event.key = "right"

        with patch.object(
            TagFilterWidget,
            "app",
            new_callable=PropertyMock,
            return_value=app_mock,
        ):
            widget.on_key(event)

        event.stop.assert_not_called()

    def test_on_key_handles_horizontal_navigation(self):
        """Left and right keys should use sequential focus movement."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = Button("Focused")
        screen_mock = MagicMock()

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(
                TagFilterWidget,
                "screen",
                new_callable=PropertyMock,
                return_value=screen_mock,
            ),
        ):
            left_event = MagicMock()
            left_event.key = "left"
            widget.on_key(left_event)

            right_event = MagicMock()
            right_event.key = "right"
            widget.on_key(right_event)

        screen_mock.focus_previous.assert_called_once()
        screen_mock.focus_next.assert_called_once()
        left_event.stop.assert_called_once()
        right_event.stop.assert_called_once()

    def test_on_key_handles_vertical_navigation(self):
        """Up and down keys should delegate to grid navigation."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = Button("Focused")

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(
                widget,
                "_navigate_vertical",
            ) as navigate_mock,
        ):
            down_event = MagicMock()
            down_event.key = "down"
            widget.on_key(down_event)

            up_event = MagicMock()
            up_event.key = "up"
            widget.on_key(up_event)

        navigate_mock.assert_any_call(direction="down")
        navigate_mock.assert_any_call(direction="up")
        self.assertEqual(navigate_mock.call_count, 2)
        down_event.stop.assert_called_once()
        up_event.stop.assert_called_once()

    def test_navigate_vertical_selects_closest_button(self):
        """Vertical movement should focus the nearest x-position."""
        widget = TagFilterWidget(["tech"])

        focused = MagicMock()
        focused.region = SimpleNamespace(x=10, y=0)

        closest = MagicMock()
        closest.region = SimpleNamespace(x=12, y=20)

        farther = MagicMock()
        farther.region = SimpleNamespace(x=100, y=20)

        app_mock = MagicMock()
        app_mock.focused = focused

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(
                widget,
                "query",
                return_value=[focused, closest, farther],
            ),
        ):
            widget._navigate_vertical("down")

        closest.focus.assert_called_once()
        farther.focus.assert_not_called()

    def test_navigate_vertical_wraps_upward(self):
        """Moving up from the first row should wrap to the last row."""
        widget = TagFilterWidget(["tech"])

        focused = MagicMock()
        focused.region = SimpleNamespace(x=20, y=0)

        last_row = MagicMock()
        last_row.region = SimpleNamespace(x=25, y=40)

        app_mock = MagicMock()
        app_mock.focused = focused

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(
                widget,
                "query",
                return_value=[focused, last_row],
            ),
        ):
            widget._navigate_vertical("up")

        last_row.focus.assert_called_once()

    def test_navigate_vertical_falls_back_after_error(self):
        """Grid failures should fall back to sequential navigation."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = MagicMock()
        screen_mock = MagicMock()

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(
                TagFilterWidget,
                "screen",
                new_callable=PropertyMock,
                return_value=screen_mock,
            ),
            patch.object(
                widget,
                "query",
                side_effect=RuntimeError("layout unavailable"),
            ),
        ):
            widget._navigate_vertical("down")
            widget._navigate_vertical("up")

        screen_mock.focus_next.assert_called_once()
        screen_mock.focus_previous.assert_called_once()


    def test_update_filter_status_handles_missing_label(self):
        """Missing status labels should be ignored safely."""
        widget = TagFilterWidget(["tech"])

        with patch.object(
            widget,
            "query_one",
            side_effect=NoMatches("missing"),
        ):
            widget.update_filter_status(
                filtered_count=1,
                total_count=2,
            )

    def test_on_key_ignores_unhandled_key(self):
        """Unrelated keys should not trigger navigation."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = Button("Focused")
        event = MagicMock()
        event.key = "enter"

        with patch.object(
            TagFilterWidget,
            "app",
            new_callable=PropertyMock,
            return_value=app_mock,
        ):
            widget.on_key(event)

        event.stop.assert_not_called()

    def test_navigate_vertical_returns_without_focus(self):
        """Vertical navigation should stop when nothing is focused."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = None

        with patch.object(
            TagFilterWidget,
            "app",
            new_callable=PropertyMock,
            return_value=app_mock,
        ):
            widget._navigate_vertical("down")

    def test_navigate_vertical_returns_without_buttons(self):
        """Vertical navigation should stop when no buttons exist."""
        widget = TagFilterWidget(["tech"])
        app_mock = MagicMock()
        app_mock.focused = MagicMock()

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(widget, "query", return_value=[]),
        ):
            widget._navigate_vertical("down")

    def test_navigate_vertical_returns_when_focus_row_is_unknown(self):
        """Navigation should stop if the focused row is not in the button grid."""
        widget = TagFilterWidget(["tech"])

        focused = MagicMock()
        focused.region = SimpleNamespace(x=10, y=99)

        button = MagicMock()
        button.region = SimpleNamespace(x=10, y=0)

        app_mock = MagicMock()
        app_mock.focused = focused

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(widget, "query", return_value=[button]),
        ):
            widget._navigate_vertical("down")

        button.focus.assert_not_called()

    def test_navigate_vertical_wraps_downward(self):
        """Moving down from the last row should wrap to the first row."""
        widget = TagFilterWidget(["tech"])

        first_row = MagicMock()
        first_row.region = SimpleNamespace(x=20, y=0)

        focused = MagicMock()
        focused.region = SimpleNamespace(x=25, y=40)

        app_mock = MagicMock()
        app_mock.focused = focused

        with (
            patch.object(
                TagFilterWidget,
                "app",
                new_callable=PropertyMock,
                return_value=app_mock,
            ),
            patch.object(
                widget,
                "query",
                return_value=[first_row, focused],
            ),
        ):
            widget._navigate_vertical("down")

        first_row.focus.assert_called_once()
