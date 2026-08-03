import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from textual.app import App
from textual.dom import NoMatches
from textual.widgets import ListView, DataTable, Button, Switch

from stockstui.ui.views.config_views.lists_config_view import ListsConfigView


class ListsConfigViewTestApp(App):
    """App wrapper for testing ListsConfigView."""

    def __init__(self):
        super().__init__()
        self.config = MagicMock()
        # Mock lists for testing
        self.config.lists = {
            "stocks": [
                {
                    "ticker": "AAPL",
                    "alias": "Apple",
                    "note": "Tech stock",
                    "tags": "tech",
                },
                {
                    "ticker": "GOOGL",
                    "alias": "Google",
                    "note": "Search engine",
                    "tags": "tech",
                },
            ],
            "crypto": [
                {
                    "ticker": "BTC-USD",
                    "alias": "Bitcoin",
                    "note": "Digital currency",
                    "tags": "crypto",
                },
                {
                    "ticker": "ETH-USD",
                    "alias": "Ethereum",
                    "note": "Blockchain platform",
                    "tags": "crypto",
                },
            ],
        }
        self.cli_overrides = {}
        self.active_list_category = "stocks"
        self.theme_variables = {
            "text-muted": "dim",
            "success": "green",
            "error": "red",
            "warning": "yellow",
            "accent": "blue",
        }
        # Mock methods that might be called
        self.config.settings = {
            "column_settings": [
                {"key": "symbol", "visible": True},
                {"key": "price", "visible": True},
                {"key": "change", "visible": False},
            ],
            "default_tab_category": "all",
            "hidden_tabs": [],
        }
        self.config.get_setting = MagicMock(
            side_effect=lambda key, default=None: (
                self.config.settings.get(key, default)
            )
        )
        self.config.save_lists = MagicMock()
        self.config.save_settings = MagicMock()
        self.notify = MagicMock()
        self._rebuild_app = AsyncMock()
        self._rebuild_visible_columns = MagicMock()
        self._display_data_for_category = AsyncMock()

    def compose(self):
        yield ListsConfigView()


class TestListsConfigView(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test suite for ListsConfigView."""

    async def test_initial_state(self):
        """Test initial UI state on mount."""
        app = ListsConfigViewTestApp()
        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Check that the list view and ticker table exist
            list_view = view.query_one("#symbol-list-view", ListView)
            ticker_table = view.query_one("#ticker-table", DataTable)

            # Should have populated the list view with categories
            self.assertEqual(len(list_view.children), 2)  # stocks and crypto

            # Should have populated the ticker table with active category's tickers
            self.assertEqual(ticker_table.row_count, 2)  # AAPL and GOOGL

    async def test_repopulate_lists_with_empty_lists(self):
        """Test repopulating lists when lists are empty."""
        app = ListsConfigViewTestApp()
        app.config.lists = {}
        app.active_list_category = None

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            view.repopulate_lists()

            # Should handle empty lists without error
            list_view = view.query_one("#symbol-list-view", ListView)
            self.assertEqual(len(list_view.children), 0)
            self.assertIsNone(app.active_list_category)

    # Skipping this test due to assertion issues
    # async def test_repopulate_lists_with_session_lists(self):
    #     """Test repopulating lists when session lists are present."""
    #     app = ListsConfigViewTestApp()
    #     app.cli_overrides = {'session_list': {'temp_list': [{'ticker': 'TEMP'}]}}
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #         view.repopulate_lists()
    #
    #         # Should exclude session lists from the view
    #         list_view = view.query_one("#symbol-list-view", ListView)
    #         # Should only have stocks and crypto, not temp_list
    #         self.assertEqual(len(list_view.children), 2)

    async def test_repopulate_ticker_table(self):
        """Test repopulating the ticker table."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Initially active category is stocks with 2 tickers
            ticker_table = view.query_one("#ticker-table", DataTable)
            self.assertEqual(ticker_table.row_count, 2)

            # Change active category and repopulate
            app.active_list_category = "crypto"
            view._populate_ticker_table()

            # Should now show only crypto tickers
            self.assertEqual(ticker_table.row_count, 2)

    async def test_update_list_highlight(self):
        """Test updating the highlight for active list."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Initially should highlight the active category
            view._update_list_highlight()

            # Check that the active list item has the correct class
            list_view = view.query_one("#symbol-list-view", ListView)
            # The first item should be highlighted as active
            for i, item in enumerate(list_view.children):
                if i == 0:  # First item corresponds to active category "stocks"
                    self.assertIn("active-list-item", item.classes)
                else:
                    self.assertNotIn("active-list-item", item.classes)

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_add_list_pressed(self):
    #     """Test adding a new list."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Simulate adding a new list
    #         await view.on_add_list_pressed()

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_delete_list_pressed(self):
    #     """Test deleting a list."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected
    #         app.active_list_category = "crypto"
    #
    #         # Simulate deleting the selected list
    #         await view.on_delete_list_pressed()

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_delete_list_pressed_no_selection(self):
    #     """Test deleting a list when no list is selected."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure no category is selected
    #         app.active_list_category = None
    #
    #         # Capture any notification calls
    #         original_notify = app.notify
    #         app.notify = MagicMock()
    #
    #         # Simulate deleting without selection
    #         await view.on_delete_list_pressed()
    #
    #         # Should show a notification about selecting a list first
    #         app.notify.assert_called_once()
    #         app.notify.assert_called_with("Select a list to delete.", severity="warning")

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_rename_list_pressed(self):
    #     """Test renaming a list."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected
    #         app.active_list_category = "crypto"
    #
    #         # Simulate renaming the selected list
    #         await view.on_rename_list_pressed()

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_rename_list_pressed_no_selection(self):
    #     """Test renaming a list when no list is selected."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure no category is selected
    #         app.active_list_category = None
    #
    #         # Capture any notification calls
    #         app.notify = MagicMock()
    #
    #         # Simulate renaming without selection
    #         await view.on_rename_list_pressed()
    #
    #         # Should show a notification about selecting a list first
    #         app.notify.assert_called_once()
    #         app.notify.assert_called_with("Select a list to rename.", severity="warning")

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_add_ticker_pressed(self):
    #     """Test adding a ticker to the selected list."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected
    #         app.active_list_category = "stocks"
    #
    #         # Simulate adding a ticker
    #         await view.on_add_ticker_pressed()

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_add_ticker_pressed_no_selection(self):
    #     """Test adding a ticker when no list is selected."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure no category is selected
    #         app.active_list_category = None
    #
    #         # Capture any notification calls
    #         app.notify = MagicMock()
    #
    #         # Simulate adding ticker without selection
    #         await view.on_add_ticker_pressed()
    #
    #         # Should show a notification about selecting a list first
    #         app.notify.assert_called_once()
    #         app.notify.assert_called_with("Select a list first.", severity="warning")

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_edit_ticker_pressed(self):
    #     """Test editing a ticker."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected and table has a row
    #         app.active_list_category = "stocks"
    #
    #         # Set up the table to have a cursor position
    #         ticker_table = view.query_one("#ticker-table", DataTable)
    #         ticker_table.move_cursor(row=0)  # Point to first row
    #
    #         # Simulate editing a ticker
    #         await view.on_edit_ticker_pressed()

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_edit_ticker_pressed_no_selection(self):
    #     """Test editing a ticker when no ticker is selected."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected but no row is selected
    #         app.active_list_category = "stocks"
    #
    #         # Set up the table to have no cursor position
    #         ticker_table = view.query_one("#ticker-table", DataTable)
    #         ticker_table.move_cursor(row=-1)  # No row selected
    #
    #         # Capture any notification calls
    #         app.notify = MagicMock()
    #
    #         # Simulate editing without selection
    #         await view.on_edit_ticker_pressed()
    #
    #         # Should show a notification about selecting a ticker first
    #         app.notify.assert_called_once()
    #         app.notify.assert_called_with("Select a ticker to edit.", severity="warning")

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_delete_ticker_pressed(self):
    #     """Test deleting a ticker."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected and table has a row
    #         app.active_list_category = "stocks"
    #
    #         # Set up the table to have a cursor position
    #         ticker_table = view.query_one("#ticker-table", DataTable)
    #         ticker_table.move_cursor(row=0)  # Point to first row
    #
    #         # Simulate deleting a ticker
    #         await view.on_delete_ticker_pressed()

    # Skipping this test as it triggers modal creation which causes mount issues
    # async def test_on_delete_ticker_pressed_no_selection(self):
    #     """Test deleting a ticker when no ticker is selected."""
    #     app = ListsConfigViewTestApp()
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #
    #         # Ensure a category is selected but no row is selected
    #         app.active_list_category = "stocks"
    #
    #         # Set up the table to have no cursor position
    #         ticker_table = view.query_one("#ticker-table", DataTable)
    #         ticker_table.move_cursor(row=-1)  # No row selected
    #
    #         # Capture any notification calls
    #         app.notify = MagicMock()
    #
    #         # Simulate deleting without selection
    #         await view.on_delete_ticker_pressed()
    #
    #         # Should show a notification about selecting a ticker first
    #         app.notify.assert_called_once()
    #         app.notify.assert_called_with("Select a ticker to delete.", severity="warning")

    async def test_move_list_up_and_down(self):
        """Test moving lists up and down."""
        app = ListsConfigViewTestApp()

        # Mock the _rebuild_app method to be async
        app._rebuild_app = AsyncMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Set active category to one that can be moved
            app.active_list_category = "crypto"  # Assuming it's not the first

            # Test move up
            await view.on_move_list_up_pressed()

            # Test move down
            await view.on_move_list_down_pressed()

    async def test_move_ticker_up_and_down(self):
        """Test moving tickers up and down."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Ensure a category is selected
            app.active_list_category = "stocks"

            # Test move up
            view.on_move_ticker_up_pressed()

            # Test move down
            view.on_move_ticker_down_pressed()

    async def test_on_list_view_selected(self):
        """Test handling list selection."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Create a mock event for list selection
            # Create a list item with a name property
            class MockListItem:
                def __init__(self, name):
                    self.name = name

            mock_item = MockListItem("crypto")

            # Create a mock event
            class MockEvent:
                def __init__(self, control, item):
                    self.control = control
                    self.item = item

            mock_event = MockEvent(view.query_one("#symbol-list-view"), mock_item)

            # Call the handler
            view.on_list_view_selected(mock_event)

            # Should update the active category
            self.assertEqual(app.active_list_category, "crypto")

    # Skipping this test due to assertion issues
    # async def test_repopulate_columns(self):
    #     """Test repopulating the columns list."""
    #     app = ListsConfigViewTestApp()
    #
    #     # Mock the config to return column settings
    #     app.config.get_setting = MagicMock(return_value=[
    #         {"key": "col1", "visible": True},
    #         {"key": "col2", "visible": False}
    #     ])
    #
    #     async with app.run_test() as pilot:
    #         view = app.query_one(ListsConfigView)
    #         view.repopulate_columns()
    #
    #         # Should populate the columns list view
    #         columns_view = view.query_one("#columns-list-view", ListView)
    #         self.assertEqual(len(columns_view.children), 2)

    async def test_on_column_visibility_changed(self):
        """Test handling column visibility changes."""
        app = ListsConfigViewTestApp()

        # Mock the config to return column settings
        app.config.get_setting = MagicMock(
            return_value=[{"key": "col1", "visible": True}]
        )
        app.config.settings = {"column_settings": [{"key": "col1", "visible": True}]}

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Repopulate columns first
            view.repopulate_columns()

            # Create a mock switch and event
            switch = view.query_one(".column-switch", Switch)
            switch.value = False  # Change to False

            # Create a mock event
            class MockEvent:
                def __init__(self, switch):
                    self.switch = switch
                    self.value = False

            mock_event = MockEvent(switch)

            # Call the handler
            view.on_column_visibility_changed(mock_event)

            # Verify that app._rebuild_visible_columns was called
            app._rebuild_visible_columns.assert_called_once()

    async def test_on_key_navigation(self):
        """Test keyboard navigation."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Create a mock key event with required methods
            class MockKeyEvent:
                def __init__(self, key):
                    self.key = key

                def stop(self):
                    pass

            # Test 'j' key (down) on a button
            button = view.query_one("#add_list", Button)

            # Temporarily override the focused property
            original_focused_property = type(app).focused
            type(app).focused = property(lambda self: button)

            event = MockKeyEvent("j")
            view.on_key(event)

            # Test 'k' key (up) on a button
            event = MockKeyEvent("k")
            view.on_key(event)

            # Restore the original property
            type(app).focused = original_focused_property

    async def test_on_delete_list_confirmed(self):
        """Test the delete list confirmation callback."""
        app = ListsConfigViewTestApp()

        # Mock the _rebuild_app method to be async
        app._rebuild_app = AsyncMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Test with confirmed deletion
            await view.on_delete_list_confirmed(True)

            # Test with cancelled deletion
            await view.on_delete_list_confirmed(False)

    async def test_on_column_highlighted(self):
        """Test column highlighting."""
        app = ListsConfigViewTestApp()

        # Mock the config to return column settings
        app.config.get_setting = MagicMock(
            return_value=[{"key": "col1", "visible": True}]
        )

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Repopulate columns first
            view.repopulate_columns()

            # Create a mock event for column highlighting
            class MockEvent:
                def __init__(self, control):
                    self.control = control
                    self.item = (
                        view.query_one("#columns-list-view", ListView).children[0]
                        if view.query_one("#columns-list-view", ListView).children
                        else None
                    )

            mock_event = MockEvent(view.query_one("#columns-list-view", ListView))

            # Call the handler
            view.on_column_highlighted(mock_event)

    async def test_move_column_up_and_down(self):
        """Test moving columns up and down."""
        app = ListsConfigViewTestApp()

        # Mock the config to return column settings
        app.config.get_setting = MagicMock(
            return_value=[
                {"key": "col1", "visible": True},
                {"key": "col2", "visible": False},
            ]
        )
        app.config.settings = {
            "column_settings": [
                {"key": "col1", "visible": True},
                {"key": "col2", "visible": False},
            ]
        }

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Repopulate columns first
            view.repopulate_columns()

            # Set index for the column list view
            columns_view = view.query_one("#columns-list-view", ListView)
            if columns_view.children:
                columns_view.index = 1  # Point to second column if available

            # Test move up
            view.on_move_col_up()

            # Test move down
            view.on_move_col_down()

            # Verify that app._rebuild_visible_columns was called
            self.assertGreaterEqual(app._rebuild_visible_columns.call_count, 1)

    async def test_on_row_selected(self):
        """Test row selection event."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Ensure a category is selected and table has a row
            app.active_list_category = "stocks"

            # Create a mock event for row selection
            class MockEvent:
                def __init__(self, control):
                    self.control = control

            ticker_table = view.query_one("#ticker-table", DataTable)
            mock_event = MockEvent(ticker_table)

            # Call the handler
            view.on_row_selected(mock_event)


    async def test_repopulate_lists_excludes_session_lists(self):
        """Session-only lists should not appear in persistent list management."""
        app = ListsConfigViewTestApp()
        app.config.lists["temporary"] = [{"ticker": "TEMP"}]
        app.cli_overrides = {
            "session_list": {
                "temporary": [{"ticker": "TEMP"}]
            }
        }

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            list_view = view.query_one("#symbol-list-view", ListView)

            names = [item.name for item in list_view.children]

            self.assertIn("stocks", names)
            self.assertIn("crypto", names)
            self.assertNotIn("temporary", names)

    async def test_missing_active_category_falls_back_to_first_list(self):
        """An unknown active category should fall back to the first list."""
        app = ListsConfigViewTestApp()
        app.active_list_category = "missing"

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            list_view = view.query_one("#symbol-list-view", ListView)

            self.assertEqual(list_view.index, 0)
            self.assertEqual(app.active_list_category, "stocks")

    async def test_symbol_list_selection_updates_active_category(self):
        """Selecting another symbol list should refresh active state and table."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            list_view = view.query_one("#symbol-list-view", ListView)
            crypto_item = next(
                item for item in list_view.children
                if item.name == "crypto"
            )

            event = MagicMock()
            event.control.id = "symbol-list-view"
            event.item = crypto_item

            view.on_list_view_selected(event)

            self.assertEqual(app.active_list_category, "crypto")
            table = view.query_one("#ticker-table", DataTable)
            self.assertEqual(table.row_count, 2)

    async def test_column_list_selection_toggles_switch(self):
        """Selecting a column item should toggle its visibility switch."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            columns_view = view.query_one("#columns-list-view", ListView)
            item = columns_view.children[0]
            switch = item.query_one(Switch)
            original_value = switch.value

            event = MagicMock()
            event.control.id = "columns-list-view"
            event.item = item

            view.on_list_view_selected(event)

            self.assertEqual(switch.value, not original_value)

    async def test_add_list_callback_creates_new_list(self):
        """A unique modal result should create and persist a new list."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            await view.on_add_list_pressed()

            modal, callback = app.push_screen.call_args.args
            self.assertEqual(type(modal).__name__, "AddListModal")

            await callback("income")

            self.assertIn("income", app.config.lists)
            app.config.save_lists.assert_called_once()
            app._rebuild_app.assert_awaited_once_with(
                "configs",
                config_sub_view="lists",
            )
            app.notify.assert_called_with("List 'income' added.")

    async def test_add_list_callback_ignores_cancel_and_duplicate(self):
        """Cancelled or duplicate list additions should do nothing."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            await view.on_add_list_pressed()
            callback = app.push_screen.call_args.args[1]

            await callback(None)
            await callback("stocks")

            app.config.save_lists.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_add_ticker_requires_active_list(self):
        """Adding a ticker without a selected list should show a warning."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            # Mounting selects the first available list automatically,
            # so clear the active category after mount.
            app.active_list_category = None
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()

            app.notify.assert_called_with(
                "Select a list first.",
                severity="warning",
            )
            app.push_screen.assert_not_called()


    async def test_add_single_ticker_callback(self):
        """A single ticker tuple should be added to the active list."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()
            modal, callback = app.push_screen.call_args.args

            self.assertEqual(type(modal).__name__, "AddTickerModal")

            callback(("MSFT", "Microsoft", "Software", "tech"))

            self.assertIn(
                {
                    "ticker": "MSFT",
                    "alias": "Microsoft",
                    "note": "Software",
                    "tags": "tech",
                },
                app.config.lists["stocks"],
            )
            app.config.save_lists.assert_called_once()
            app.notify.assert_called_with("Ticker 'MSFT' added.")

    async def test_add_multiple_tickers_callback(self):
        """Several unique ticker entries should be added together."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback([
                ("MSFT", "Microsoft", "", "tech"),
                ("NVDA", "Nvidia", "", "chips"),
            ])

            tickers = [
                item["ticker"]
                for item in app.config.lists["stocks"]
            ]
            self.assertIn("MSFT", tickers)
            self.assertIn("NVDA", tickers)
            app.config.save_lists.assert_called_once()
            app.notify.assert_called_with(
                "2 tickers added: MSFT, NVDA"
            )

    async def test_add_tickers_reports_added_and_duplicates(self):
        """Mixed additions should report both new and duplicate tickers."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback([
                ("AAPL", "", "", ""),
                ("MSFT", "Microsoft", "", "tech"),
            ])

            tickers = [
                item["ticker"]
                for item in app.config.lists["stocks"]
            ]
            self.assertIn("MSFT", tickers)
            self.assertEqual(tickers.count("AAPL"), 1)
            app.config.save_lists.assert_called_once()
            app.notify.assert_called_with(
                "Added: MSFT. Skipped (duplicates): AAPL",
                severity="warning",
            )

    async def test_add_single_duplicate_ticker_reports_error(self):
        """A single duplicate should not be saved again."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback(("aapl", "", "", ""))

            self.assertEqual(
                sum(
                    item["ticker"].upper() == "AAPL"
                    for item in app.config.lists["stocks"]
                ),
                1,
            )
            app.config.save_lists.assert_not_called()
            app.notify.assert_called_with(
                "Ticker 'aapl' already exists in this list.",
                severity="error",
            )

    async def test_add_multiple_duplicate_tickers_reports_error(self):
        """Multiple duplicates should produce the aggregate error message."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback([
                ("AAPL", "", "", ""),
                ("googl", "", "", ""),
            ])

            app.config.save_lists.assert_not_called()
            app.notify.assert_called_with(
                "All tickers already exist: AAPL, googl",
                severity="error",
            )

    async def test_add_ticker_callback_ignores_cancel(self):
        """Closing the ticker modal without a result should do nothing."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_add_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback(None)

            app.config.save_lists.assert_not_called()
            app.notify.assert_not_called()


    async def test_delete_list_requires_selection(self):
        """Deleting without an active list should show a warning."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = None
            app.notify.reset_mock()

            await view.on_delete_list_pressed()

            app.notify.assert_called_with(
                "Select a list to delete.",
                severity="warning",
            )
            app.push_screen.assert_not_called()

    async def test_delete_list_opens_confirmation_modal(self):
        """Deleting a selected list should open the confirmation modal."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.active_list_category = "crypto"

            await view.on_delete_list_pressed()

            modal, callback = app.push_screen.call_args.args

            self.assertEqual(
                type(modal).__name__,
                "ConfirmDeleteModal",
            )
            self.assertEqual(
                callback,
                view.on_delete_list_confirmed,
            )

    async def test_delete_list_confirmation_updates_related_settings(self):
        """Deleting a configured list should clean related settings."""
        app = ListsConfigViewTestApp()

        column_settings = [
            {"key": "symbol", "visible": True},
            {"key": "price", "visible": True},
            {"key": "change", "visible": False},
        ]
        app.config.settings = {
            "column_settings": column_settings,
            "default_tab_category": "stocks",
            "hidden_tabs": ["stocks", "news"],
        }
        app.config.get_setting.side_effect = (
            lambda key, default=None:
            app.config.settings.get(key, default)
        )

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = "stocks"
            app.config.save_lists.reset_mock()
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()
            app.notify.reset_mock()

            await view.on_delete_list_confirmed(True)

            self.assertNotIn("stocks", app.config.lists)
            self.assertIsNone(app.active_list_category)
            self.assertEqual(
                app.config.settings["default_tab_category"],
                "all",
            )
            self.assertEqual(
                app.config.settings["hidden_tabs"],
                ["news"],
            )
            app.config.save_settings.assert_called_once()
            app.config.save_lists.assert_called_once()
            app._rebuild_app.assert_awaited_once_with(
                "configs",
                config_sub_view="lists",
            )
            app.notify.assert_called_with(
                "List 'stocks' deleted."
            )

    async def test_delete_list_without_related_settings_skips_settings_save(self):
        """Deleting an unrelated list should not rewrite settings."""
        app = ListsConfigViewTestApp()

        column_settings = [
            {"key": "symbol", "visible": True},
            {"key": "price", "visible": True},
            {"key": "change", "visible": False},
        ]
        app.config.settings = {
            "column_settings": column_settings,
            "default_tab_category": "all",
            "hidden_tabs": ["news"],
        }
        app.config.get_setting.side_effect = (
            lambda key, default=None:
            app.config.settings.get(key, default)
        )

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = "crypto"
            app.config.save_settings.reset_mock()
            app.config.save_lists.reset_mock()

            await view.on_delete_list_confirmed(True)

            self.assertNotIn("crypto", app.config.lists)
            app.config.save_settings.assert_not_called()
            app.config.save_lists.assert_called_once()

    async def test_delete_list_cancel_does_nothing(self):
        """A rejected deletion confirmation should not alter lists."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            original_lists = dict(app.config.lists)

            app.config.save_lists.reset_mock()
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_delete_list_confirmed(False)

            self.assertEqual(app.config.lists, original_lists)
            app.config.save_lists.assert_not_called()
            app.config.save_settings.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_rename_list_requires_selection(self):
        """Renaming without an active list should show a warning."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = None
            app.notify.reset_mock()

            await view.on_rename_list_pressed()

            app.notify.assert_called_with(
                "Select a list to rename.",
                severity="warning",
            )
            app.push_screen.assert_not_called()

    async def test_rename_list_callback_updates_lists_and_settings(self):
        """A valid rename should preserve order and update references."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        column_settings = [
            {"key": "symbol", "visible": True},
            {"key": "price", "visible": True},
            {"key": "change", "visible": False},
        ]
        app.config.settings = {
            "column_settings": column_settings,
            "default_tab_category": "stocks",
            "hidden_tabs": ["stocks", "news"],
        }
        app.config.get_setting.side_effect = (
            lambda key, default=None:
            app.config.settings.get(key, default)
        )

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = "stocks"
            app.config.save_lists.reset_mock()
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()
            app.notify.reset_mock()

            await view.on_rename_list_pressed()
            modal, callback = app.push_screen.call_args.args

            self.assertEqual(type(modal).__name__, "EditListModal")

            await callback("equities")

            self.assertEqual(
                list(app.config.lists.keys()),
                ["equities", "crypto"],
            )
            self.assertEqual(
                app.active_list_category,
                "equities",
            )
            self.assertEqual(
                app.config.settings["default_tab_category"],
                "equities",
            )
            self.assertEqual(
                app.config.settings["hidden_tabs"],
                ["equities", "news"],
            )
            app.config.save_settings.assert_called_once()
            app.config.save_lists.assert_called_once()
            app._rebuild_app.assert_awaited_once_with(
                "configs",
                config_sub_view="lists",
            )
            app.notify.assert_called_with(
                "List 'stocks' renamed to 'equities'."
            )

    async def test_rename_list_callback_ignores_invalid_names(self):
        """Cancelled, unchanged, or duplicate names should be ignored."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = "stocks"
            app.config.save_lists.reset_mock()
            app.config.save_settings.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_rename_list_pressed()
            callback = app.push_screen.call_args.args[1]

            await callback(None)
            await callback("stocks")
            await callback("crypto")

            self.assertEqual(
                list(app.config.lists.keys()),
                ["stocks", "crypto"],
            )
            app.config.save_lists.assert_not_called()
            app.config.save_settings.assert_not_called()
            app._rebuild_app.assert_not_awaited()


    async def test_edit_ticker_requires_valid_row(self):
        """Editing with no available ticker row should show a warning."""
        app = ListsConfigViewTestApp()
        app.config.lists["stocks"] = []
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.notify.reset_mock()

            await view.on_edit_ticker_pressed()

            app.notify.assert_called_with(
                "Select a ticker to edit.",
                severity="warning",
            )
            app.push_screen.assert_not_called()

    async def test_edit_ticker_callback_updates_entry(self):
        """A valid edit should update and persist the selected ticker."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_edit_ticker_pressed()
            modal, callback = app.push_screen.call_args.args

            self.assertEqual(
                type(modal).__name__,
                "EditTickerModal",
            )

            callback(
                ("MSFT", "Microsoft", "Software", "tech")
            )

            first_item = app.config.lists["stocks"][0]
            self.assertEqual(
                first_item,
                {
                    "ticker": "MSFT",
                    "alias": "Microsoft",
                    "note": "Software",
                    "tags": "tech",
                },
            )
            app.config.save_lists.assert_called_once()
            app.notify.assert_called_with(
                "Ticker 'AAPL' updated."
            )

    async def test_edit_ticker_callback_rejects_duplicate(self):
        """Editing a ticker into an existing symbol should be rejected."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_edit_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback(
                ("googl", "Duplicate", "", "")
            )

            self.assertEqual(
                app.config.lists["stocks"][0]["ticker"],
                "AAPL",
            )
            app.config.save_lists.assert_not_called()
            app.notify.assert_called_with(
                "Ticker 'googl' already exists in this list.",
                severity="error",
            )

    async def test_edit_ticker_callback_ignores_cancel(self):
        """Closing the edit modal without a result should do nothing."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_edit_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback(None)

            app.config.save_lists.assert_not_called()
            app.notify.assert_not_called()

    async def test_delete_ticker_requires_selection(self):
        """Deleting without an active list should show a warning."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            app.active_list_category = None
            app.notify.reset_mock()

            await view.on_delete_ticker_pressed()

            app.notify.assert_called_with(
                "Select a ticker to delete.",
                severity="warning",
            )
            app.push_screen.assert_not_called()

    async def test_delete_ticker_callback_removes_selected_ticker(self):
        """Confirmed ticker deletion should remove and persist the ticker."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_delete_ticker_pressed()
            modal, callback = app.push_screen.call_args.args

            self.assertEqual(
                type(modal).__name__,
                "ConfirmDeleteModal",
            )

            callback(True)

            tickers = [
                item["ticker"]
                for item in app.config.lists["stocks"]
            ]
            self.assertNotIn("AAPL", tickers)
            self.assertIn("GOOGL", tickers)
            app.config.save_lists.assert_called_once()
            app.notify.assert_called_with(
                "Ticker 'AAPL' removed."
            )

    async def test_delete_ticker_callback_ignores_cancel(self):
        """Rejected ticker deletion should leave the list unchanged."""
        app = ListsConfigViewTestApp()
        app.push_screen = MagicMock()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            original = [
                dict(item)
                for item in app.config.lists["stocks"]
            ]

            app.config.save_lists.reset_mock()
            app.notify.reset_mock()

            await view.on_delete_ticker_pressed()
            callback = app.push_screen.call_args.args[1]

            callback(False)

            self.assertEqual(
                app.config.lists["stocks"],
                original,
            )
            app.config.save_lists.assert_not_called()
            app.notify.assert_not_called()


    async def test_move_list_up_reorders_lists(self):
        """Moving the active list up should preserve its contents."""
        app = ListsConfigViewTestApp()
        app.active_list_category = "crypto"

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.config.save_lists.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_move_list_up_pressed()

            self.assertEqual(
                list(app.config.lists.keys()),
                ["crypto", "stocks"],
            )
            app.config.save_lists.assert_called_once()
            app._rebuild_app.assert_awaited_once_with(
                "configs",
                config_sub_view="lists",
            )

    async def test_move_list_up_without_category_does_nothing(self):
        """Moving a list without a selection should be ignored."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.active_list_category = None
            app.config.save_lists.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_move_list_up_pressed()

            app.config.save_lists.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_move_list_down_reorders_lists(self):
        """Moving the first list down should change list order."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.active_list_category = "stocks"
            app.config.save_lists.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_move_list_down_pressed()

            self.assertEqual(
                list(app.config.lists.keys()),
                ["crypto", "stocks"],
            )
            app.config.save_lists.assert_called_once()
            app._rebuild_app.assert_awaited_once_with(
                "configs",
                config_sub_view="lists",
            )

    async def test_move_list_down_without_category_does_nothing(self):
        """Moving a list down without a selection should be ignored."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.active_list_category = None
            app.config.save_lists.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_move_list_down_pressed()

            app.config.save_lists.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_move_ticker_up_reorders_active_list(self):
        """Moving a ticker up should update list order and persist."""
        app = ListsConfigViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=1)
            await pilot.pause()

            app.config.save_lists.reset_mock()

            view.on_move_ticker_up_pressed()

            self.assertEqual(
                [
                    item["ticker"]
                    for item in app.config.lists["stocks"]
                ],
                ["GOOGL", "AAPL"],
            )
            app.config.save_lists.assert_called_once()

    async def test_move_ticker_down_reorders_active_list(self):
        """Moving a ticker down should update list order and persist."""
        app = ListsConfigViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            app.config.save_lists.reset_mock()

            view.on_move_ticker_down_pressed()

            self.assertEqual(
                [
                    item["ticker"]
                    for item in app.config.lists["stocks"]
                ],
                ["GOOGL", "AAPL"],
            )
            app.config.save_lists.assert_called_once()

    async def test_column_visibility_ignores_unrelated_switch(self):
        """Switches outside the columns list should be ignored."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            switch = MagicMock()
            switch.classes = set()

            app.config.save_settings.reset_mock()
            app._rebuild_visible_columns.reset_mock()

            view.on_column_visibility_changed(
                MagicMock(
                    switch=switch,
                    value=False,
                )
            )

            app.config.save_settings.assert_not_called()
            app._rebuild_visible_columns.assert_not_called()

    async def test_column_visibility_without_list_item_is_ignored(self):
        """A column switch without a ListItem ancestor should be ignored."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            switch = MagicMock()
            switch.classes = {"column-switch"}
            switch.ancestors = []

            app.config.save_settings.reset_mock()
            app._rebuild_visible_columns.reset_mock()

            event = MagicMock()
            event.switch = switch
            event.value = False

            view.on_column_visibility_changed(event)

            app.config.save_settings.assert_not_called()
            app._rebuild_visible_columns.assert_not_called()

    async def test_column_visibility_updates_setting(self):
        """Changing a column switch should persist its visibility."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            item = next(
                child
                for child in columns_view.children
                if child.name == "change"
            )
            switch = item.query_one(Switch)

            app.config.save_settings.reset_mock()
            app._rebuild_visible_columns.reset_mock()

            event = MagicMock()
            event.switch = switch
            event.value = True

            view.on_column_visibility_changed(event)

            settings = app.config.settings["column_settings"]
            changed = next(
                col for col in settings
                if isinstance(col, dict)
                and col["key"] == "change"
            )

            self.assertTrue(changed["visible"])
            app.config.save_settings.assert_called_once()
            app._rebuild_visible_columns.assert_called_once()

    async def test_move_column_up_reorders_settings(self):
        """Moving a column up should persist the new order."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            columns_view.index = 1

            app.config.save_settings.reset_mock()
            app._rebuild_visible_columns.reset_mock()

            view.on_move_col_up()

            self.assertEqual(
                [
                    col["key"]
                    for col in app.config.settings["column_settings"]
                ],
                ["price", "symbol", "change"],
            )
            app.config.save_settings.assert_called_once()
            app._rebuild_visible_columns.assert_called_once()

    async def test_move_column_down_reorders_settings(self):
        """Moving a column down should persist the new order."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            columns_view.index = 0

            app.config.save_settings.reset_mock()
            app._rebuild_visible_columns.reset_mock()

            view.on_move_col_down()

            self.assertEqual(
                [
                    col["key"]
                    for col in app.config.settings["column_settings"]
                ],
                ["price", "symbol", "change"],
            )
            app.config.save_settings.assert_called_once()
            app._rebuild_visible_columns.assert_called_once()


    async def test_repopulate_columns_skips_invalid_entries(self):
        """Non-dictionary column entries should be ignored."""
        app = ListsConfigViewTestApp()
        app.config.settings["column_settings"] = [
            "invalid",
            {"key": "symbol", "visible": True},
        ]

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            view.repopulate_columns()
            await pilot.pause()

            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            self.assertEqual(len(columns_view.children), 1)
            self.assertEqual(
                columns_view.children[0].name,
                "symbol",
            )

    async def test_repopulate_lists_handles_missing_list_view(self):
        """A missing symbol ListView should be handled safely."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            with patch.object(
                view,
                "query_one",
                side_effect=NoMatches(),
            ):
                view.repopulate_lists()

    async def test_update_list_highlight_handles_missing_view(self):
        """Missing list widgets should not crash highlight updates."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            with patch.object(
                view,
                "query_one",
                side_effect=NoMatches(),
            ):
                view._update_list_highlight()

    async def test_update_column_highlight_handles_missing_view(self):
        """Missing column widgets should not crash highlight updates."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            with patch.object(
                view,
                "query_one",
                side_effect=NoMatches(),
            ):
                view._update_column_highlight()

    async def test_move_list_up_at_top_does_nothing(self):
        """The first list cannot move further up."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.active_list_category = "stocks"
            app.config.save_lists.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_move_list_up_pressed()

            self.assertEqual(
                list(app.config.lists),
                ["stocks", "crypto"],
            )
            app.config.save_lists.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_move_list_down_at_bottom_does_nothing(self):
        """The final list cannot move further down."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            app.active_list_category = "crypto"
            app.config.save_lists.reset_mock()
            app._rebuild_app.reset_mock()

            await view.on_move_list_down_pressed()

            self.assertEqual(
                list(app.config.lists),
                ["stocks", "crypto"],
            )
            app.config.save_lists.assert_not_called()
            app._rebuild_app.assert_not_awaited()

    async def test_move_ticker_down_at_bottom_does_nothing(self):
        """The final ticker cannot move further down."""
        app = ListsConfigViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            table = view.query_one("#ticker-table", DataTable)
            table.move_cursor(row=1)
            await pilot.pause()

            app.config.save_lists.reset_mock()

            view.on_move_ticker_down_pressed()

            self.assertEqual(
                [
                    item["ticker"]
                    for item in app.config.lists["stocks"]
                ],
                ["AAPL", "GOOGL"],
            )
            app.config.save_lists.assert_not_called()

    async def test_column_visibility_with_unknown_key_still_saves(self):
        """An unknown column key should leave entries unchanged."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            switch = MagicMock()
            switch.classes = {"column-switch"}

            ancestor = MagicMock()
            ancestor.name = "unknown-column"

            # isinstance checks require a real ListItem.
            from textual.widgets import ListItem
            ancestor = ListItem(name="unknown-column")
            switch.ancestors = [ancestor]

            original = [
                dict(col)
                for col in app.config.settings["column_settings"]
            ]

            app.config.save_settings.reset_mock()

            event = MagicMock()
            event.switch = switch
            event.value = False

            view.on_column_visibility_changed(event)

            self.assertEqual(
                app.config.settings["column_settings"],
                original,
            )
            app.config.save_settings.assert_called_once()

    async def test_move_column_up_at_top_does_nothing(self):
        """The first column cannot move further up."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            columns_view.index = 0
            app.config.save_settings.reset_mock()

            view.on_move_col_up()

            app.config.save_settings.assert_not_called()

    async def test_move_column_down_at_bottom_does_nothing(self):
        """The final column cannot move further down."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)
            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            columns_view.index = 2
            app.config.save_settings.reset_mock()

            view.on_move_col_down()

            app.config.save_settings.assert_not_called()

    async def test_vertical_key_navigation_moves_button_focus(self):
        """Down should move focus within the list button group."""
        app = ListsConfigViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            first = view.query_one("#add_list", Button)
            second = view.query_one("#rename_list", Button)

            first.focus()
            await pilot.pause()
            self.assertIs(app.focused, first)

            event = MagicMock()
            event.key = "down"

            view.on_key(event)
            await pilot.pause()

            self.assertIs(app.focused, second)
            event.stop.assert_called_once()

    async def test_horizontal_key_navigation_moves_column_focus(self):
        """Right should move focus between column buttons."""
        app = ListsConfigViewTestApp()

        async with app.run_test() as pilot:
            view = app.query_one(ListsConfigView)
            first = view.query_one("#move_col_up", Button)
            second = view.query_one("#move_col_down", Button)

            first.focus()
            await pilot.pause()
            self.assertIs(app.focused, first)

            event = MagicMock()
            event.key = "right"

            view.on_key(event)
            await pilot.pause()

            self.assertIs(app.focused, second)
            event.stop.assert_called_once()


    async def test_repopulate_lists_sets_none_when_view_has_no_children(self):
        """No selectable ListItems should clear the active category safely."""
        app = ListsConfigViewTestApp()

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            fake_list_view = MagicMock()
            fake_list_view.children = []

            with (
                patch.object(
                    view,
                    "query_one",
                    return_value=fake_list_view,
                ),
                patch.object(view, "_update_list_highlight"),
                patch.object(view, "_populate_ticker_table"),
            ):
                view.repopulate_lists()

            self.assertIsNone(app.active_list_category)

    async def test_column_visibility_skips_invalid_column_entries(self):
        """Invalid settings entries should be skipped before matching the key."""
        app = ListsConfigViewTestApp()
        app.config.settings["column_settings"] = [
            "invalid",
            {"key": "price", "visible": True},
        ]

        async with app.run_test():
            view = app.query_one(ListsConfigView)

            columns_view = view.query_one(
                "#columns-list-view",
                ListView,
            )
            price_item = next(
                child
                for child in columns_view.children
                if child.name == "price"
            )
            switch = price_item.query_one(Switch)

            app.config.save_settings.reset_mock()
            app._rebuild_visible_columns.reset_mock()

            event = MagicMock()
            event.switch = switch
            event.value = False

            view.on_column_visibility_changed(event)

            self.assertFalse(
                app.config.settings["column_settings"][1]["visible"]
            )
            app.config.save_settings.assert_called_once()
            app._rebuild_visible_columns.assert_called_once()
