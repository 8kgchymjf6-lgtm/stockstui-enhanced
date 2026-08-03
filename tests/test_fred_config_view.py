import unittest
from types import SimpleNamespace
from textual.app import App
from textual.widgets import DataTable, Input, Button, Switch
from textual.dom import NoMatches
from unittest.mock import MagicMock, AsyncMock, PropertyMock, patch

from stockstui.ui.views.config_views.fred_config_view import FredConfigView
from stockstui.ui.modals import AddFredSeriesModal


class FredConfigTestApp(App):
    """App for testing FredConfigView."""

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        self.config.get_setting.return_value = []
        self.config.settings = {
            "hidden_tabs": [],
            "fred_settings": {
                "api_key": "fake_key",
                "series_list": ["TEST1", "TEST2"],
                "series_aliases": {"TEST1": "Alias1"},
                "series_descriptions": {},
            }
        }
        self.theme_variables = {"text-muted": "dim"}
        self.notify = MagicMock()
        self._rebuild_app = AsyncMock()

    def compose(self):
        yield FredConfigView()


class TestFredConfigView(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Save the real function before replacing it with a mock for mount tests.
        self.real_fetch_descriptions = FredConfigView._fetch_descriptions.__wrapped__
        self.patcher = patch(
            "stockstui.ui.views.config_views.fred_config_view."
            "FredConfigView._fetch_descriptions"
        )
        self.mock_fetch = self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()

    async def test_initial_population(self):
        """Test table populates on mount."""
        app = FredConfigTestApp()
        async with app.run_test():
            table = app.query_one(DataTable)
            self.assertEqual(table.row_count, 2)

            # Check row 1
            row1 = table.get_row("TEST1")
            self.assertEqual(row1[0], "TEST1")
            self.assertIn("Alias1", str(row1[1]))

    async def test_save_api_key(self):
        """Test saving API key."""
        app = FredConfigTestApp()
        # Increase size to ensure visibility
        async with app.run_test(size=(120, 40)) as pilot:
            inp = app.query_one("#fred-api-key-input", Input)

            # Change value
            inp.value = "new_key"

            # Use programmatic press to avoid OutOfBounds issues with scrolling/layout in test env
            app.query_one("#save-fred-api-key", Button).press()
            await pilot.pause()

            # Check config updated
            settings = app.config.settings["fred_settings"]
            self.assertEqual(settings["api_key"], "new_key")
            app.config.save_settings.assert_called()

    async def test_remove_series(self):
        """Test removing a series."""
        app = FredConfigTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            table = app.query_one(DataTable)

            # Select row 0 (TEST1)
            table.focus()
            table.cursor_coordinate = (0, 0)

            app.query_one("#remove-fred-series", Button).press()
            await pilot.pause()

            # Verify removed from settings
            settings = app.config.settings["fred_settings"]
            self.assertNotIn("TEST1", settings["series_list"])
            self.assertNotIn("TEST1", settings["series_aliases"])

            # Verify table updated
            self.assertEqual(table.row_count, 1)

    async def test_move_series_down(self):
        """Test moving series down."""
        app = FredConfigTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            table = app.query_one(DataTable)

            # List is [TEST1, TEST2]
            # Select TEST1 (index 0)
            table.focus()
            table.cursor_coordinate = (0, 0)

            app.query_one("#move-fred-series-down", Button).press()
            await pilot.pause()

            # New list should be [TEST2, TEST1]
            settings = app.config.settings["fred_settings"]
            self.assertEqual(settings["series_list"], ["TEST2", "TEST1"])

    async def test_add_series_flow(self):
        """Test adding a series via modal callback simulation."""
        app = FredConfigTestApp()

        # Mock push_screen to capture callback
        app.push_screen = MagicMock()

        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#add-fred-series", Button).press()
            await pilot.pause()

            # Verify push_screen called with AddFredSeriesModal
            app.push_screen.assert_called_once()
            args, _ = app.push_screen.call_args
            self.assertIsInstance(args[0], AddFredSeriesModal)
            callback = args[1]

            # Simulate modal returning ("NEW", "New Alias", "Note", "Tags")
            # (Note: AddTickerModal/AddFredSeriesModal return tuple)
            callback(("NEW_SERIES", "New Alias", "", ""))
            await pilot.pause()

            # Verify config updated
            settings = app.config.settings["fred_settings"]
            self.assertIn("NEW_SERIES", settings["series_list"])
            self.assertEqual(settings["series_aliases"]["NEW_SERIES"], "New Alias")

    async def test_toggle_fred_visibility(self):
        """Test toggling FRED tab visibility."""
        app = FredConfigTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            switch = app.query_one("#fred-visibility-switch", Switch)
            self.assertTrue(switch.value)

            # Programmatically change switch to False
            switch.value = False
            await pilot.pause()

            # Verify hidden_tabs updated to include 'fred'
            self.assertIn("fred", app.config.settings["hidden_tabs"])
            app._rebuild_app.assert_called_once_with("configs", config_sub_view="fred")

            # Toggle back to True
            switch.value = True
            await pilot.pause()

            # Verify 'fred' removed from hidden_tabs
            self.assertNotIn("fred", app.config.settings["hidden_tabs"])


    async def test_cached_description_is_displayed(self):
        """Cached descriptions should be shown without displaying Loading."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"]["series_descriptions"] = {
            "TEST1": "Cached description",
            "TEST2": "Second description",
        }

        async with app.run_test():
            table = app.query_one(DataTable)
            row = table.get_row("TEST1")

            self.assertEqual(str(row[2]), "Cached description")

    async def test_save_api_key_ignored_while_loading(self):
        """Mount-time population must not accidentally save settings."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            app.config.save_settings.reset_mock()

            view._loading = True
            view.on_save_api_key()

            app.config.save_settings.assert_not_called()

    async def test_save_api_key_initializes_default_series(self):
        """Saving a key should create the default series list when absent."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"] = {
            "api_key": "",
        }

        async with app.run_test():
            view = app.query_one(FredConfigView)
            view.query_one("#fred-api-key-input", Input).value = "new-key"

            view.on_save_api_key()

            settings = app.config.settings["fred_settings"]
            self.assertEqual(
                settings["series_list"],
                ["GDP", "CPIAUCSL", "UNRATE"],
            )
            self.assertEqual(settings["api_key"], "new-key")

    async def test_add_series_callback_ignores_cancel(self):
        """A cancelled add modal should leave settings unchanged."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            original_list = list(
                app.config.settings["fred_settings"]["series_list"]
            )

            view.on_add_series()
            callback = app.push_screen.call_args.args[1]
            callback(None)

            self.assertEqual(
                app.config.settings["fred_settings"]["series_list"],
                original_list,
            )
            app.config.save_settings.assert_not_called()

    async def test_add_series_rejects_duplicate(self):
        """An existing series should not be added twice."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            view.on_add_series()
            callback = app.push_screen.call_args.args[1]
            callback(("test1", "Duplicate", "", ""))

            settings = app.config.settings["fred_settings"]
            self.assertEqual(
                settings["series_list"].count("TEST1"),
                1,
            )
            app.notify.assert_called_with(
                "Series already in list.",
                severity="warning",
            )

    async def test_add_series_without_distinct_alias(self):
        """An alias equal to the ID should not be stored separately."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            view.on_add_series()
            callback = app.push_screen.call_args.args[1]
            callback(("new_series", "NEW_SERIES", "", ""))

            settings = app.config.settings["fred_settings"]
            self.assertIn("NEW_SERIES", settings["series_list"])
            self.assertNotIn(
                "NEW_SERIES",
                settings.get("series_aliases", {}),
            )

    async def test_row_selection_opens_edit_flow(self):
        """Selecting a table row should invoke the edit action."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            view.on_edit_series = MagicMock()

            view.on_row_selected()

            view.on_edit_series.assert_called_once()

    async def test_move_series_up(self):
        """The second series should be movable to the first position."""
        app = FredConfigTestApp()

        async with app.run_test(size=(120, 40)) as pilot:
            table = app.query_one(DataTable)
            table.focus()
            table.cursor_coordinate = (1, 0)

            app.query_one("#move-fred-series-up", Button).press()
            await pilot.pause()

            settings = app.config.settings["fred_settings"]
            self.assertEqual(
                settings["series_list"],
                ["TEST2", "TEST1"],
            )


    async def test_fetch_descriptions_saves_titles_and_refreshes(self):
        """Fetched titles should be cached and trigger a table refresh."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            app.call_from_thread = MagicMock()
            app.config.settings["fred_settings"]["series_descriptions"] = {}

            with patch(
                "stockstui.data_providers.fred_provider.get_series_info",
                side_effect=[
                    {"title": "First title"},
                    {"title": "Second title"},
                ],
            ) as get_info:
                view._refresh_table_with_cache = MagicMock()
                self.real_fetch_descriptions(
                    view,
                    ["TEST1", "TEST2"],
                    "fake_key",
                )

            descriptions = app.config.settings["fred_settings"][
                "series_descriptions"
            ]
            self.assertEqual(descriptions["TEST1"], "First title")
            self.assertEqual(descriptions["TEST2"], "Second title")
            self.assertEqual(get_info.call_count, 2)
            app.config.save_settings.assert_called()
            app.call_from_thread.assert_called_with(
                view._refresh_table_with_cache
            )

    async def test_fetch_descriptions_falls_back_to_series_id(self):
        """Missing API metadata should fall back to the series ID."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            app.call_from_thread = MagicMock()
            app.config.settings["fred_settings"].pop(
                "series_descriptions",
                None,
            )

            with patch(
                "stockstui.data_providers.fred_provider.get_series_info",
                return_value=None,
            ):
                view._refresh_table_with_cache = MagicMock()
                self.real_fetch_descriptions(
                    view,
                    ["TEST1"],
                    "fake_key",
                )

            descriptions = app.config.settings["fred_settings"][
                "series_descriptions"
            ]
            self.assertEqual(descriptions["TEST1"], "TEST1")

    async def test_fetch_descriptions_handles_save_failure(self):
        """A config save failure should be logged without stopping refresh."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            app.call_from_thread = MagicMock()
            app.config.save_settings.side_effect = RuntimeError(
                "save failed"
            )

            with patch(
                "stockstui.data_providers.fred_provider.get_series_info",
                return_value={"title": "Title"},
            ), self.assertLogs(level="ERROR"):
                view._refresh_table_with_cache = MagicMock()
                self.real_fetch_descriptions(
                    view,
                    ["TEST1"],
                    "fake_key",
                )

            app.call_from_thread.assert_called_with(
                view._refresh_table_with_cache
            )

    async def test_refresh_table_with_cache_updates_cells(self):
        """Cached descriptions should update the description column."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"]["series_descriptions"] = {
            "TEST1": "Updated title"
        }

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)

            view._refresh_table_with_cache()

            row = table.get_row("TEST1")
            self.assertEqual(str(row[2]), "Updated title")
            self.assertFalse(table.loading)

    async def test_refresh_table_skips_uninitialized_table(self):
        """A table without all columns should be ignored safely."""
        view = FredConfigView()
        table = MagicMock()
        table.columns = {}

        with patch.object(
            view,
            "query_one",
            return_value=table,
        ):
            view._refresh_table_with_cache()

        self.assertFalse(table.loading)

    async def test_refresh_table_handles_missing_view(self):
        """A replaced view should not cause an exception."""
        view = FredConfigView()

        with patch.object(
            view,
            "query_one",
            side_effect=NoMatches("missing"),
        ):
            view._refresh_table_with_cache()


    async def test_keyboard_i_focuses_first_button(self):
        """The i key should request focus for the first action button."""
        app = FredConfigTestApp()

        async with app.run_test(size=(120, 40)):
            view = app.query_one(FredConfigView)
            save_button = view.query_one("#save-fred-api-key", Button)

            event = MagicMock()
            event.key = "i"

            with patch.object(save_button, "focus") as focus_mock:
                view.on_key(event)

            focus_mock.assert_called_once()
            event.stop.assert_called_once()

    async def test_keyboard_navigation_cycles_buttons(self):
        """j/down and k/up should cycle through the action buttons."""
        app = FredConfigTestApp()

        async with app.run_test(size=(120, 40)):
            view = app.query_one(FredConfigView)
            save_button = view.query_one("#save-fred-api-key", Button)
            add_button = view.query_one("#add-fred-series", Button)

            down_event = MagicMock()
            down_event.key = "down"

            with (
                patch.object(
                    type(app),
                    "focused",
                    new_callable=PropertyMock,
                    return_value=save_button,
                ),
                patch.object(add_button, "focus") as add_focus,
            ):
                view.on_key(down_event)

            add_focus.assert_called_once()
            down_event.stop.assert_called_once()

            up_event = MagicMock()
            up_event.key = "up"

            with (
                patch.object(
                    type(app),
                    "focused",
                    new_callable=PropertyMock,
                    return_value=add_button,
                ),
                patch.object(save_button, "focus") as save_focus,
            ):
                view.on_key(up_event)

            save_focus.assert_called_once()
            up_event.stop.assert_called_once()

    async def test_visibility_change_ignored_while_loading(self):
        """Mount-time switch changes must not save or rebuild the app."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            view._loading = True
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_fred_visibility_changed(
                SimpleNamespace(value=False)
            )

            app.config.save_settings.assert_not_called()
            app._rebuild_app.assert_not_called()

    async def test_edit_series_requires_selection(self):
        """Editing without a selected row should show a warning."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = MagicMock()
            table.cursor_row = -1

            with patch.object(view, "query_one", return_value=table):
                view.on_edit_series()

            app.notify.assert_called_with(
                "Select a series to edit.",
                severity="warning",
            )

    async def test_edit_series_updates_alias(self):
        """The edit callback should store a new alias."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)
            table.cursor_coordinate = (0, 0)

            view.on_edit_series()

            callback = app.push_screen.call_args.args[1]
            callback("Updated Alias")

            aliases = app.config.settings["fred_settings"]["series_aliases"]
            self.assertEqual(aliases["TEST1"], "Updated Alias")
            app.config.save_settings.assert_called()

    async def test_edit_series_removes_empty_alias(self):
        """Clearing an alias should remove it from the alias mapping."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)
            table.cursor_coordinate = (0, 0)

            view.on_edit_series()

            callback = app.push_screen.call_args.args[1]
            callback("")

            aliases = app.config.settings["fred_settings"]["series_aliases"]
            self.assertNotIn("TEST1", aliases)

    async def test_edit_series_callback_ignores_cancel(self):
        """A cancelled edit should leave settings unchanged."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)
            table.cursor_coordinate = (0, 0)
            original_aliases = dict(
                app.config.settings["fred_settings"]["series_aliases"]
            )

            view.on_edit_series()
            callback = app.push_screen.call_args.args[1]
            callback(None)

            self.assertEqual(
                app.config.settings["fred_settings"]["series_aliases"],
                original_aliases,
            )

    async def test_remove_series_requires_selection(self):
        """Removing without a selected row should show a warning."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = MagicMock()
            table.cursor_row = -1

            with patch.object(view, "query_one", return_value=table):
                view.on_remove_series()

            app.notify.assert_called_with(
                "Select a series to remove.",
                severity="warning",
            )

    async def test_move_series_edge_positions_do_nothing(self):
        """The first item cannot move up and the last cannot move down."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)

            app.config.save_settings.reset_mock()

            table.cursor_coordinate = (0, 0)
            view.on_move_series_up()

            table.cursor_coordinate = (1, 0)
            view.on_move_series_down()

            self.assertEqual(
                app.config.settings["fred_settings"]["series_list"],
                ["TEST1", "TEST2"],
            )
            app.config.save_settings.assert_not_called()


    async def test_refresh_table_logs_cell_update_failure(self):
        """A missing table row should be logged without stopping refresh."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"]["series_descriptions"] = {
            "UNKNOWN": "Unknown title"
        }

        async with app.run_test():
            view = app.query_one(FredConfigView)

            with self.assertLogs(level="ERROR") as logs:
                view._refresh_table_with_cache()

            self.assertTrue(
                any(
                    "Failed to update cell for UNKNOWN" in message
                    for message in logs.output
                )
            )

    async def test_visibility_noop_states_still_save(self):
        """Already-correct visibility states should remain unchanged."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            app.config.get_setting.return_value = []
            await view.on_fred_visibility_changed(
                SimpleNamespace(value=True)
            )
            self.assertNotIn(
                "fred",
                app.config.settings["hidden_tabs"],
            )

            app.config.get_setting.return_value = ["fred"]
            await view.on_fred_visibility_changed(
                SimpleNamespace(value=False)
            )
            self.assertIn(
                "fred",
                app.config.settings["hidden_tabs"],
            )

    async def test_add_series_creates_alias_mapping(self):
        """Adding the first distinct alias should create its mapping."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"].pop(
            "series_aliases",
            None,
        )
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            view.on_add_series()
            callback = app.push_screen.call_args.args[1]
            callback(("NEW", "New alias", "", ""))

            aliases = app.config.settings["fred_settings"][
                "series_aliases"
            ]
            self.assertEqual(aliases["NEW"], "New alias")

    async def test_edit_series_returns_without_row_key(self):
        """Editing should stop safely when the selected row has no key."""
        app = FredConfigTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            table = MagicMock()
            table.cursor_row = 0
            table.coordinate_to_cell_key.return_value.row_key = None

            with patch.object(view, "query_one", return_value=table):
                view.on_edit_series()

            app.push_screen.assert_not_called()

    async def test_edit_series_creates_alias_mapping(self):
        """Editing should create the alias mapping when it is absent."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"].pop(
            "series_aliases",
            None,
        )
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)
            table.cursor_coordinate = (0, 0)

            view.on_edit_series()
            callback = app.push_screen.call_args.args[1]
            callback("Created alias")

            aliases = app.config.settings["fred_settings"][
                "series_aliases"
            ]
            self.assertEqual(aliases["TEST1"], "Created alias")

    async def test_edit_empty_alias_when_none_exists(self):
        """Clearing an absent alias should still complete safely."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"]["series_aliases"] = {}
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)
            table.cursor_coordinate = (0, 0)

            view.on_edit_series()
            callback = app.push_screen.call_args.args[1]
            callback("")

            self.assertEqual(
                app.config.settings["fred_settings"]["series_aliases"],
                {},
            )

    async def test_remove_series_returns_without_row_key(self):
        """Removing should stop safely when the selected row has no key."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            table = MagicMock()
            table.cursor_row = 0
            table.coordinate_to_cell_key.return_value.row_key = None

            with patch.object(view, "query_one", return_value=table):
                view.on_remove_series()

            app.config.save_settings.assert_not_called()

    async def test_remove_series_not_present_does_nothing(self):
        """A keyed row absent from settings should not trigger a save."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            table = MagicMock()
            table.cursor_row = 0
            table.coordinate_to_cell_key.return_value.row_key.value = "MISSING"

            app.config.save_settings.reset_mock()

            with patch.object(view, "query_one", return_value=table):
                view.on_remove_series()

            app.config.save_settings.assert_not_called()

    async def test_remove_series_without_alias_mapping(self):
        """Removing should work when no alias mapping exists."""
        app = FredConfigTestApp()
        app.config.settings["fred_settings"].pop(
            "series_aliases",
            None,
        )

        async with app.run_test():
            view = app.query_one(FredConfigView)
            table = app.query_one(DataTable)
            table.cursor_coordinate = (0, 0)

            view.on_remove_series()

            self.assertNotIn(
                "TEST1",
                app.config.settings["fred_settings"]["series_list"],
            )

    async def test_move_up_ignores_index_outside_settings(self):
        """A table index beyond the settings list should not mutate data."""
        app = FredConfigTestApp()

        async with app.run_test():
            view = app.query_one(FredConfigView)

            table = MagicMock()
            table.cursor_row = 5

            app.config.save_settings.reset_mock()

            with patch.object(view, "query_one", return_value=table):
                view.on_move_series_up()

            self.assertEqual(
                app.config.settings["fred_settings"]["series_list"],
                ["TEST1", "TEST2"],
            )
            app.config.save_settings.assert_not_called()
