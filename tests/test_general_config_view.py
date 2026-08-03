import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from textual.app import App
from textual.widgets import Input, ListView, Select, Switch

from stockstui.ui.views.config_views.general_config_view import (
    GeneralConfigView,
)


class GeneralConfigTestApp(App):
    """Minimal Textual app for testing GeneralConfigView."""

    def __init__(self):
        super().__init__()

        self.config = MagicMock()
        self.config.settings = {
            "auto_refresh": False,
            "enable_pre_post_market": False,
            "suppress_tui_logs": False,
            "refresh_interval": 30.0,
            "default_tab_category": "stocks",
            "theme": "test-theme",
            "market_calendar": "NYSE",
            "hidden_tabs": ["news"],
        }
        self.config.lists = {
            "stocks": [],
            "crypto": [],
            "news": [],
        }

        def get_setting(key, default=None):
            return self.config.settings.get(key, default)

        self.config.get_setting.side_effect = get_setting

        self.notify = MagicMock()
        self._manage_price_refresh_timer = MagicMock()
        self._update_theme_variables = MagicMock()
        self.fetch_market_status = MagicMock()
        self._rebuild_app = AsyncMock()
        self.market_status_timer = MagicMock()


    def compose(self):
        yield GeneralConfigView()


class TestGeneralConfigView(unittest.IsolatedAsyncioTestCase):
    async def test_visible_tabs_are_populated_without_duplicates(self):
        """Static and dynamic tabs should appear once in the list."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            list_view = view.query_one(
                "#visible-tabs-list-view",
                ListView,
            )

            names = [item.name for item in list_view.children]

            self.assertEqual(names.count("news"), 1)
            self.assertIn("all", names)
            self.assertIn("stocks", names)
            self.assertIn("crypto", names)
            self.assertIn("history", names)
            self.assertIn("options", names)
            self.assertIn("fred", names)
            self.assertIn("debug", names)
            self.assertFalse(view._loading)

    async def test_valid_refresh_interval_is_saved(self):
        """A valid numeric interval should be stored and activated."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            interval_input = view.query_one(
                "#refresh-interval-input",
                Input,
            )
            interval_input.value = "45"

            view.on_update_refresh_button_pressed()

            self.assertEqual(
                app.config.settings["refresh_interval"],
                45.0,
            )
            app.config.save_settings.assert_called()
            app._manage_price_refresh_timer.assert_called_once()
            app.notify.assert_called_with(
                "Refresh interval updated."
            )

    async def test_invalid_refresh_interval_reports_error(self):
        """An invalid interval should not alter the configuration."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            interval_input = view.query_one(
                "#refresh-interval-input",
                Input,
            )
            interval_input.value = "not-a-number"

            app.config.save_settings.reset_mock()
            view.on_update_refresh_button_pressed()

            self.assertEqual(
                app.config.settings["refresh_interval"],
                30.0,
            )
            app.config.save_settings.assert_not_called()
            app.notify.assert_called()
            self.assertEqual(
                app.notify.call_args.kwargs["severity"],
                "error",
            )

    async def test_setting_switches_update_config(self):
        """The three general switches should save their new states."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)

            view.on_enable_pre_post_market_switch_changed(
                SimpleNamespace(value=True)
            )
            view.on_switch_changed(
                SimpleNamespace(value=True)
            )
            view.on_suppress_logs_switch_changed(
                SimpleNamespace(value=True)
            )

            self.assertTrue(
                app.config.settings["enable_pre_post_market"]
            )
            self.assertTrue(app.config.settings["auto_refresh"])
            self.assertTrue(
                app.config.settings["suppress_tui_logs"]
            )
            app._manage_price_refresh_timer.assert_called_once()
            self.assertEqual(
                app.config.save_settings.call_count,
                3,
            )

    async def test_switch_changes_are_ignored_while_loading(self):
        """Mount-time switch events must not save configuration."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            view._loading = True
            app.config.save_settings.reset_mock()
            app._manage_price_refresh_timer.reset_mock()

            event = SimpleNamespace(value=True)
            view.on_enable_pre_post_market_switch_changed(event)
            view.on_switch_changed(event)
            view.on_suppress_logs_switch_changed(event)

            app.config.save_settings.assert_not_called()
            app._manage_price_refresh_timer.assert_not_called()

    async def test_default_tab_selection_is_saved(self):
        """Selecting a default tab should update its setting."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)

            event = SimpleNamespace(
                value="crypto",
                select=SimpleNamespace(id="default-tab-select"),
            )
            view.on_select_changed(event)

            self.assertEqual(
                app.config.settings["default_tab_category"],
                "crypto",
            )
            app.config.save_settings.assert_called_once()

    async def test_theme_selection_updates_theme(self):
        """Selecting a theme should apply it and refresh theme variables."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)

            event = MagicMock()
            event.value = "new-theme"
            event.select.id = "theme-select"

            with patch.object(
                type(app),
                "theme",
                new_callable=PropertyMock,
            ) as theme_mock:
                view.on_select_changed(event)

            self.assertEqual(
                app.config.settings["theme"],
                "new-theme",
            )
            theme_mock.assert_called_with("new-theme")
            app._update_theme_variables.assert_called_once_with(
                "new-theme"
            )

    async def test_market_calendar_selection_restarts_status(self):
        """Changing calendar should stop the old timer and fetch new status."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)

            event = SimpleNamespace(
                value="LSE",
                select=SimpleNamespace(
                    id="market-calendar-select"
                ),
            )
            view.on_select_changed(event)

            self.assertEqual(
                app.config.settings["market_calendar"],
                "LSE",
            )
            app.market_status_timer.stop.assert_called_once()
            app.fetch_market_status.assert_called_once_with("LSE")

    async def test_blank_and_loading_select_events_are_ignored(self):
        """Blank values and loading-time events should not save."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            app.config.save_settings.reset_mock()

            blank_event = SimpleNamespace(
                value=Select.BLANK,
                select=SimpleNamespace(id="default-tab-select"),
            )
            view.on_select_changed(blank_event)

            view._loading = True
            normal_event = SimpleNamespace(
                value="crypto",
                select=SimpleNamespace(id="default-tab-select"),
            )
            view.on_select_changed(normal_event)

            app.config.save_settings.assert_not_called()

    async def test_hiding_visible_tab_updates_config(self):
        """Turning off a tab switch should add its key to hidden_tabs."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            list_view = view.query_one(
                "#visible-tabs-list-view",
                ListView,
            )
            stocks_item = next(
                item
                for item in list_view.children
                if item.name == "stocks"
            )
            switch = stocks_item.query_one(Switch)

            await view.on_tab_visibility_toggled(
                SimpleNamespace(
                    switch=switch,
                    value=False,
                )
            )

            self.assertIn(
                "stocks",
                app.config.settings["hidden_tabs"],
            )
            app.config.save_settings.assert_called()
            app._rebuild_app.assert_awaited_with("configs")

    async def test_showing_hidden_tab_updates_config(self):
        """Turning on a hidden tab should remove it from hidden_tabs."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            list_view = view.query_one(
                "#visible-tabs-list-view",
                ListView,
            )
            news_item = next(
                item
                for item in list_view.children
                if item.name == "news"
            )
            switch = news_item.query_one(Switch)

            await view.on_tab_visibility_toggled(
                SimpleNamespace(
                    switch=switch,
                    value=True,
                )
            )

            self.assertNotIn(
                "news",
                app.config.settings["hidden_tabs"],
            )
            app._rebuild_app.assert_awaited_with("configs")

    async def test_tab_visibility_ignores_unrelated_switch(self):
        """Switches without the tab-switch class should be ignored."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()

            unrelated_switch = view.query_one(
                "#auto-refresh-switch",
                Switch,
            )

            await view.on_tab_visibility_toggled(
                SimpleNamespace(
                    switch=unrelated_switch,
                    value=True,
                )
            )

            app.config.save_settings.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_tab_visibility_ignored_while_loading(self):
        """Tab switch events during population must not save settings."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            list_view = view.query_one(
                "#visible-tabs-list-view",
                ListView,
            )
            item = list_view.children[0]
            switch = item.query_one(Switch)

            view._loading = True
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_tab_visibility_toggled(
                SimpleNamespace(
                    switch=switch,
                    value=False,
                )
            )

            app.config.save_settings.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_tab_visibility_returns_without_list_item(self):
        """A tab-style switch without a ListItem ancestor should be ignored."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()

            switch = MagicMock()
            switch.classes = {"tab-switch"}
            switch.ancestors = []

            await view.on_tab_visibility_toggled(
                SimpleNamespace(
                    switch=switch,
                    value=False,
                )
            )

            app.config.save_settings.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_selecting_tab_item_toggles_switch(self):
        """Selecting a visible-tabs row should toggle its switch."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            list_view = view.query_one(
                "#visible-tabs-list-view",
                ListView,
            )
            item = next(
                child
                for child in list_view.children
                if child.name == "stocks"
            )
            switch = item.query_one(Switch)
            original_value = switch.value

            view.on_tab_selected(
                SimpleNamespace(item=item)
            )

            self.assertEqual(
                switch.value,
                not original_value,
            )

    async def test_market_calendar_without_existing_timer(self):
        """Calendar changes should work when no old timer exists."""
        app = GeneralConfigTestApp()
        app.market_status_timer = None

        async with app.run_test():
            view = app.query_one(GeneralConfigView)

            event = SimpleNamespace(
                value="TSX",
                select=SimpleNamespace(
                    id="market-calendar-select"
                ),
            )
            view.on_select_changed(event)

            self.assertEqual(
                app.config.settings["market_calendar"],
                "TSX",
            )
            app.fetch_market_status.assert_called_once_with("TSX")

    async def test_invalid_interval_without_failure_details(self):
        """The generic validation message should be used without failures."""
        app = GeneralConfigTestApp()

        async with app.run_test():
            view = app.query_one(GeneralConfigView)
            interval_input = view.query_one(
                "#refresh-interval-input",
                Input,
            )

            validation_result = SimpleNamespace(
                is_valid=False,
                failures=[],
            )

            with patch.object(
                interval_input,
                "validate",
                return_value=validation_result,
            ):
                view.on_update_refresh_button_pressed()

            app.notify.assert_called_with(
                "Invalid interval value.",
                severity="error",
            )

if __name__ == "__main__":
    unittest.main()
