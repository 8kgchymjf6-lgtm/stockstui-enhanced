import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from textual.app import App
from textual.widgets import Button

from stockstui.ui.views.config_view import ConfigContainer
from stockstui.ui.views.config_views.main_config_view import MainConfigView


class MainConfigTestApp(App):
    """App wrapper for testing MainConfigView."""

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        self.config.settings = {
            "fred_settings": {"api_key": ""},
            "hidden_tabs": [],
        }
        self.config.get_setting.return_value = []
        self.theme_variables = {"text-muted": "dim"}
        self.cli_overrides = {}

    def compose(self):
        yield ConfigContainer()


class TestMainConfigView(unittest.IsolatedAsyncioTestCase):
    """Test suite for MainConfigView."""

    async def test_button_navigation(self):
        """Test buttons navigate to correct configuration screens."""
        app = MainConfigTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            container = app.query_one(ConfigContainer)

            # Initially we should be on main
            self.assertEqual(container.query_one("ContentSwitcher").current, "main")

            # Click "General Settings" button
            await pilot.click("#goto-general")
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "general")

            # Go back
            container.action_go_back()
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "main")

            # Click "Watchlists" button
            await pilot.click("#goto-lists")
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "lists")

            # Go back
            container.action_go_back()
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "main")

            # Click "FRED Settings" button
            await pilot.click("#goto-fred")
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "fred")


    async def test_keyboard_navigation_cycles_buttons(self):
        """Down and up should move focus through the config buttons."""
        app = MainConfigTestApp()

        async with app.run_test(size=(120, 40)):
            view = app.query_one(MainConfigView)
            general = view.query_one("#goto-general", Button)
            lists = view.query_one("#goto-lists", Button)
            fred = view.query_one("#goto-fred", Button)

            down_event = MagicMock()
            down_event.key = "down"

            with (
                patch.object(
                    type(app),
                    "focused",
                    new_callable=PropertyMock,
                    return_value=general,
                ),
                patch.object(lists, "focus") as lists_focus,
            ):
                view.on_key(down_event)

            lists_focus.assert_called_once()
            down_event.stop.assert_called_once()

            up_event = MagicMock()
            up_event.key = "up"

            with (
                patch.object(
                    type(app),
                    "focused",
                    new_callable=PropertyMock,
                    return_value=general,
                ),
                patch.object(fred, "focus") as fred_focus,
            ):
                view.on_key(up_event)

            fred_focus.assert_called_once()
            up_event.stop.assert_called_once()

    async def test_keyboard_navigation_ignores_non_button_focus(self):
        """Navigation keys should be ignored when focus is not on a button."""
        app = MainConfigTestApp()

        async with app.run_test(size=(120, 40)):
            view = app.query_one(MainConfigView)
            event = MagicMock()
            event.key = "down"

            with patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=None,
            ):
                view.on_key(event)

            event.stop.assert_not_called()

    async def test_keyboard_navigation_ignores_unrelated_key(self):
        """Unrelated keys should not move focus."""
        app = MainConfigTestApp()

        async with app.run_test(size=(120, 40)):
            view = app.query_one(MainConfigView)
            button = view.query_one("#goto-general", Button)
            event = MagicMock()
            event.key = "enter"

            with patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=button,
            ):
                view.on_key(event)

            event.stop.assert_not_called()

    def test_portfolio_button_handler_calls_container(self):
        """The portfolio handler branch should call show_portfolios."""
        view = MainConfigView()
        container = MagicMock()
        button = Button("Portfolios", id="goto-portfolios")
        event = Button.Pressed(button)

        with patch.object(
            view,
            "query_ancestor",
            return_value=container,
        ):
            view.on_button_pressed(event)

        container.show_portfolios.assert_called_once()
