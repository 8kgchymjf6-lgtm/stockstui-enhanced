import unittest
import webbrowser
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from rich.text import Text
from textual.actions import SkipAction
from textual.css.query import NoMatches
from textual.widgets import Button, DataTable, Input, Label, Tabs
from textual.widgets.data_table import CellDoesNotExist

from stockstui.main import (
    StocksTUI,
    substitute_colors,
)
from stockstui.ui.views.history_view import HistoryView
from stockstui.ui.views.options_view import OptionsView
from tests.test_utils import create_mocked_app


class TestMainHelpers(unittest.IsolatedAsyncioTestCase):
    """Focused tests for small state and helper methods in main.py."""

    def test_substitute_colors_handles_nested_values_and_missing_colors(self):
        template = {
            "primary": "$blue",
            "dark": True,
            "variables": {
                "success": "$green",
                "plain": "unchanged",
            },
            "number": 42,
        }
        palette = {
            "blue": "#0000ff",
            "green": "#00ff00",
        }

        result = substitute_colors(template, palette)

        self.assertEqual(result["primary"], "#0000ff")
        self.assertTrue(result["dark"])
        self.assertEqual(result["variables"]["success"], "#00ff00")
        self.assertEqual(result["variables"]["plain"], "unchanged")
        self.assertEqual(result["number"], 42)

        missing = substitute_colors({"error": "$red"}, {})
        self.assertEqual(missing["error"], "UNDEFINED_RED")

    def test_add_option_position_updates_database_and_memory(self):
        app = create_mocked_app()
        app.option_positions = {}

        app.add_option_position("AAPL-C", "AAPL", 2.0, 3.5)

        app.db_manager.save_option_position.assert_called_once_with(
            "AAPL-C",
            "AAPL",
            2.0,
            3.5,
        )
        self.assertEqual(
            app.option_positions["AAPL-C"],
            {
                "symbol": "AAPL-C",
                "ticker": "AAPL",
                "quantity": 2.0,
                "avg_cost": 3.5,
            },
        )
        app.notify.assert_called_once_with("Position saved: AAPL-C")

    def test_remove_option_position_handles_present_and_missing_symbols(self):
        app = create_mocked_app()
        app.option_positions = {
            "AAPL-C": {
                "symbol": "AAPL-C",
            }
        }
        app._pre_refresh_cursor_key = "row"
        app._pre_refresh_cursor_column = 3
        app._is_filter_refresh = True

        app.remove_option_position("AAPL-C")

        app.db_manager.delete_option_position.assert_called_once_with("AAPL-C")
        self.assertNotIn("AAPL-C", app.option_positions)
        app.notify.assert_called_with("Position removed: AAPL-C")
        self.assertIsNone(app._pre_refresh_cursor_key)
        self.assertIsNone(app._pre_refresh_cursor_column)
        self.assertFalse(app._is_filter_refresh)

        app.db_manager.reset_mock()
        app.notify.reset_mock()

        app.remove_option_position("UNKNOWN")

        app.db_manager.delete_option_position.assert_called_once_with("UNKNOWN")
        app.notify.assert_called_once_with("Position removed: UNKNOWN")

    def test_get_alias_map_excludes_hidden_lists_and_incomplete_items(self):
        app = create_mocked_app()
        app._hidden_tabs = {"hidden"}
        app.config.lists = {
            "visible": [
                {"ticker": "AAPL", "alias": "Apple"},
                {"ticker": "MSFT", "alias": ""},
                {"alias": "Missing ticker"},
            ],
            "hidden": [
                {"ticker": "TSLA", "alias": "Tesla"},
            ],
        }

        self.assertEqual(app._get_alias_map(), {"AAPL": "Apple"})

    def test_available_tags_respects_categories_and_hidden_lists(self):
        app = create_mocked_app()
        app._hidden_tabs = {"hidden"}
        app.config.lists = {
            "visible": [
                {"ticker": "AAPL", "tags": "tech, growth"},
                {"ticker": "MSFT", "tags": "tech; value"},
                {"ticker": "EMPTY", "tags": ""},
            ],
            "hidden": [
                {"ticker": "TSLA", "tags": "cars, growth"},
            ],
        }

        self.assertEqual(
            app._get_available_tags_for_category("all"),
            ["growth", "tech", "value"],
        )
        self.assertEqual(
            app._get_available_tags_for_category("visible"),
            ["growth", "tech", "value"],
        )
        self.assertEqual(
            app._get_available_tags_for_category("hidden"),
            [],
        )
        self.assertEqual(
            app._get_available_tags_for_category("unknown"),
            [],
        )

    def test_filter_symbols_by_tags_preserves_order_and_removes_duplicates(self):
        app = create_mocked_app()
        app._hidden_tabs = set()
        app.config.lists = {
            "one": [
                {"ticker": "AAPL", "tags": "tech, growth"},
                {"ticker": "MSFT", "tags": "tech"},
            ],
            "two": [
                {"ticker": "AAPL", "tags": "growth"},
                {"ticker": "TSLA", "tags": "cars"},
            ],
        }

        app.active_tag_filter = []
        symbols = ["AAPL", "MSFT", "TSLA"]
        self.assertIs(app._filter_symbols_by_tags("all", symbols), symbols)

        app.active_tag_filter = ["tech"]
        self.assertEqual(
            app._filter_symbols_by_tags("all", symbols),
            ["AAPL", "MSFT"],
        )

        app.active_tag_filter = ["cars"]
        self.assertEqual(
            app._filter_symbols_by_tags("two", symbols),
            ["TSLA"],
        )

        app._hidden_tabs = {"two"}
        self.assertEqual(
            app._filter_symbols_by_tags("two", symbols),
            [],
        )

    def test_load_and_register_themes_skips_invalid_themes(self):
        app = create_mocked_app()
        app.config.themes = {
            "valid": {
                "dark": True,
                "palette": {
                    "blue": "#111111",
                    "cyan": "#222222",
                    "orange": "#333333",
                    "green": "#444444",
                    "yellow": "#555555",
                    "red": "#666666",
                    "bg3": "#777777",
                    "bg2": "#888888",
                    "bg1": "#999999",
                    "bg0": "#aaaaaa",
                    "fg0": "#bbbbbb",
                    "fg1": "#cccccc",
                    "fg2": "#dddddd",
                    "fg3": "#eeeeee",
                },
            },
            "no-palette": {},
            "missing-color": {
                "palette": {
                    "blue": "#111111",
                },
            },
        }

        with patch.object(app, "register_theme") as register_theme:
            app._load_and_register_themes()

        register_theme.assert_called_once()
        self.assertEqual(app._available_theme_names, ["valid"])
        self.assertIn("valid", app._processed_themes)
        self.assertNotIn("no-palette", app._processed_themes)
        self.assertNotIn("missing-color", app._processed_themes)

        valid = app._processed_themes["valid"]
        self.assertTrue(valid["dark"])
        self.assertNotIn("UNDEFINED_", str(valid))

    def test_update_theme_variables_and_active_category_guards(self):
        app = create_mocked_app()
        app._processed_themes = {
            "custom": {
                "primary": "p",
                "secondary": "s",
                "accent": "a",
                "success": "ok",
                "warning": "warn",
                "error": "err",
                "foreground": "fg",
                "background": "bg",
                "surface": "surface",
                "variables": {
                    "price": "cyan",
                },
            }
        }

        app._update_theme_variables("custom")
        self.assertEqual(app.theme_variables["primary"], "p")
        self.assertEqual(app.theme_variables["price"], "cyan")

        previous = dict(app.theme_variables)
        app._update_theme_variables("unknown")
        self.assertEqual(app.theme_variables, previous)

        app._last_active_category = "news"
        self.assertEqual(app.get_active_category(), "news")

        app._last_active_category = None
        app.tab_map = [{"name": "All", "category": "all"}]
        tabs = MagicMock(spec=Tabs)
        tabs.active = "tab-1"

        with patch.object(app, "query_one", return_value=tabs):
            self.assertEqual(app.get_active_category(), "all")

        tabs.active = "invalid"
        with patch.object(app, "query_one", return_value=tabs):
            self.assertIsNone(app.get_active_category())

        with patch.object(app, "query_one", side_effect=NoMatches):
            self.assertIsNone(app.get_active_category())

    def test_manage_price_refresh_timer_paths(self):
        app = create_mocked_app()

        old_timer = MagicMock()
        app.price_refresh_timer = old_timer
        app.config.get_setting.side_effect = lambda key, default=None: {
            "auto_refresh": False,
        }.get(key, default)

        app._manage_price_refresh_timer()

        old_timer.stop.assert_called_once_with()
        self.assertIsNone(app.price_refresh_timer)

        app.config.get_setting.side_effect = lambda key, default=None: {
            "auto_refresh": True,
            "refresh_interval": "15",
        }.get(key, default)
        new_timer = MagicMock()

        with patch.object(app, "set_interval", return_value=new_timer) as set_interval:
            app._manage_price_refresh_timer()

        self.assertIs(app.price_refresh_timer, new_timer)
        self.assertEqual(set_interval.call_args.args[0], 15.0)

        app.price_refresh_timer = None
        app.config.get_setting.side_effect = lambda key, default=None: {
            "auto_refresh": True,
            "refresh_interval": "invalid",
        }.get(key, default)

        with patch.object(app, "set_interval") as set_interval:
            app._manage_price_refresh_timer()

        set_interval.assert_not_called()

    async def test_on_key_tracks_key_and_handles_open_mode(self):
        app = create_mocked_app()
        event = MagicMock()
        event.key = "n"
        app._open_mode = True
        app.action_handle_open_key = AsyncMock()

        await app.on_key(event)

        self.assertIs(app.last_key, event)
        app.action_handle_open_key.assert_awaited_once_with("n")
        event.stop.assert_called_once_with()

        event.reset_mock()
        app.action_handle_open_key.reset_mock()
        event.key = "x"

        await app.on_key(event)

        app.action_handle_open_key.assert_not_awaited()
        event.stop.assert_not_called()

    def test_dismiss_or_unfocus_blurs_input_and_handles_errors(self):
        app = create_mocked_app()
        input_widget = Input()

        with (
            patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=input_widget,
            ),
            patch.object(input_widget, "blur") as blur,
        ):
            app.action_dismiss_or_unfocus()

        blur.assert_called_once_with()

        with (
            patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=None,
            ),
            patch.object(app, "action_back_or_dismiss") as back,
        ):
            app.action_dismiss_or_unfocus()

        back.assert_called_once_with()

        with (
            patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=None,
            ),
            patch.object(
                app,
                "action_back_or_dismiss",
                side_effect=RuntimeError("test error"),
            ),
            patch("stockstui.main.logging.error") as log_error,
        ):
            app.action_dismiss_or_unfocus()

        log_error.assert_called_once()
        self.assertIn("test error", log_error.call_args.args[0])

    def test_restore_status_label_paths(self):
        app = create_mocked_app()
        label = MagicMock(spec=Label)
        app._original_status_text = "Previous status"

        with patch.object(app, "query_one", return_value=label):
            app._restore_status_label()

        label.update.assert_called_once_with("Previous status")

        label.reset_mock()
        app._original_status_text = None

        with patch.object(app, "query_one", return_value=label):
            app._restore_status_label()

        label.update.assert_not_called()

        with patch.object(app, "query_one", side_effect=NoMatches):
            app._restore_status_label()

    def test_start_refresh_loops_success_and_failure(self):
        app = create_mocked_app()
        app.action_refresh = MagicMock()
        app._manage_price_refresh_timer = MagicMock()
        app._update_market_status_display = MagicMock()
        app.config.get_setting.return_value = "NYSE"

        status = {"status": "open"}
        with patch(
            "stockstui.main.market_provider.get_market_status",
            return_value=status,
        ) as get_status:
            app._start_refresh_loops()

        app.action_refresh.assert_called_once_with()
        app._manage_price_refresh_timer.assert_called_once_with()
        get_status.assert_called_once_with("NYSE")
        app._update_market_status_display.assert_called_once_with(status)

        app._update_market_status_display.reset_mock()

        with (
            patch(
                "stockstui.main.market_provider.get_market_status",
                side_effect=RuntimeError("offline"),
            ),
            patch("stockstui.main.logging.error") as log_error,
        ):
            app._start_refresh_loops()

        app._update_market_status_display.assert_not_called()
        log_error.assert_called_once()

    def test_update_tag_filter_status_for_all_and_hidden_category(self):
        app = create_mocked_app()
        tag_filter = MagicMock()
        app._hidden_tabs = {"hidden"}
        app.config.lists = {
            "visible": [
                {"ticker": "AAPL"},
                {"ticker": "MSFT"},
                {"ticker": "AAPL"},
            ],
            "hidden": [
                {"ticker": "TSLA"},
            ],
        }
        app._filter_symbols_by_tags = MagicMock(return_value=["AAPL"])

        with (
            patch.object(app, "query_one", return_value=tag_filter),
            patch.object(app, "get_active_category", return_value="all"),
        ):
            app._update_tag_filter_status()

        args = tag_filter.update_filter_status.call_args.args
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1], 2)

        tag_filter.reset_mock()
        app._filter_symbols_by_tags.return_value = []

        with (
            patch.object(app, "query_one", return_value=tag_filter),
            patch.object(app, "get_active_category", return_value="hidden"),
        ):
            app._update_tag_filter_status()

        tag_filter.update_filter_status.assert_called_once_with(0, 0)

        with patch.object(app, "query_one", side_effect=NoMatches):
            app._update_tag_filter_status()

    def test_select_tab_and_copy_text_paths(self):
        app = create_mocked_app()
        tabs = MagicMock(spec=Tabs)
        tabs.tab_count = 3

        with patch.object(app, "query_one", return_value=tabs):
            app.action_select_tab(2)

        self.assertEqual(tabs.active, "tab-2")

        tabs.active = None
        with patch.object(app, "query_one", return_value=tabs):
            app.action_select_tab(4)

        self.assertIsNone(tabs.active)

        with patch.object(app, "query_one", side_effect=NoMatches):
            app.action_select_tab(1)

        screen = MagicMock()
        screen.get_selected_text.return_value = "copied text"

        with (
            patch.object(
                type(app),
                "screen",
                new_callable=PropertyMock,
                return_value=screen,
            ),
            patch.object(app, "copy_to_clipboard") as copy_to_clipboard,
        ):
            app.action_copy_text()

        copy_to_clipboard.assert_called_once_with("copied text")

        screen.get_selected_text.return_value = None
        with (
            patch.object(
                type(app),
                "screen",
                new_callable=PropertyMock,
                return_value=screen,
            ),
            self.assertRaises(SkipAction),
        ):
            app.action_copy_text()

    def test_schedule_market_status_refresh_intervals(self):
        app = create_mocked_app()
        app.config.get_setting.return_value = "NYSE"
        timer = MagicMock()

        now = datetime.now(timezone.utc)
        cases = [
            (
                {
                    "status": "open",
                    "next_close": now + timedelta(minutes=10),
                },
                30,
            ),
            (
                {
                    "status": "open",
                    "next_close": now + timedelta(hours=2),
                },
                300,
            ),
            (
                {
                    "status": "closed",
                    "next_open": now + timedelta(minutes=10),
                },
                30,
            ),
            (
                {
                    "status": "closed",
                    "next_open": now + timedelta(hours=1),
                },
                300,
            ),
            (
                {
                    "status": "closed",
                    "next_open": now + timedelta(hours=5),
                },
                3600,
            ),
            (
                {
                    "status": "unknown",
                },
                300,
            ),
        ]

        for status, expected_interval in cases:
            with self.subTest(status=status):
                old_timer = MagicMock()
                app.market_status_timer = old_timer

                with patch.object(
                    app,
                    "set_timer",
                    return_value=timer,
                ) as set_timer:
                    app._schedule_next_market_status_refresh(status)

                old_timer.stop.assert_called_once_with()
                self.assertEqual(set_timer.call_args.args[0], expected_interval)
                self.assertIs(app.market_status_timer, timer)

    def test_action_refresh_deduplicates_and_handles_categories(self):
        app = create_mocked_app()
        app._hidden_tabs = {"hidden"}
        app.config.lists = {
            "one": [
                {"ticker": "AAPL"},
                {"ticker": "MSFT"},
            ],
            "two": [
                {"ticker": "AAPL"},
                {"ticker": "TSLA"},
            ],
            "hidden": [
                {"ticker": "HIDDEN"},
            ],
        }
        app.config.get_setting.side_effect = lambda key, default=None: {
            "enable_pre_post_market": True,
        }.get(key, default)
        app._filter_symbols_by_tags = MagicMock(
            side_effect=lambda category, symbols: symbols
        )

        table = MagicMock(spec=DataTable)
        table.row_count = 0

        with (
            patch.object(app, "get_active_category", return_value="all"),
            patch.object(app, "query_one", return_value=table),
        ):
            app.action_refresh(force=True)

        table.loading = True
        app.fetch_prices.assert_called_once_with(
            ["AAPL", "MSFT", "TSLA"],
            force=True,
            category="all",
            enable_pre_post_market=True,
        )

        app.fetch_prices.reset_mock()

        with (
            patch.object(app, "get_active_category", return_value="one"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            app.action_refresh()

        app.fetch_prices.assert_called_once_with(
            ["AAPL", "MSFT"],
            force=False,
            category="one",
            enable_pre_post_market=True,
        )

        app.fetch_prices.reset_mock()
        app._filter_symbols_by_tags.side_effect = None
        app._filter_symbols_by_tags.return_value = []

        with (
            patch.object(app, "get_active_category", return_value="one"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            app.action_refresh()

        app.fetch_prices.assert_not_called()

        with patch.object(app, "get_active_category", return_value="history"):
            app.action_refresh()

        app.fetch_prices.assert_not_called()

    def test_toggle_help_paths(self):
        app = create_mocked_app()
        app.action_hide_help_panel = MagicMock()
        app.action_show_help_panel = MagicMock()

        with patch.object(app, "query", return_value=[MagicMock()]):
            app.action_toggle_help()

        app.action_hide_help_panel.assert_called_once_with()
        app.action_show_help_panel.assert_not_called()

        app.action_hide_help_panel.reset_mock()

        with patch.object(app, "query", return_value=[]):
            app.action_toggle_help()

        app.action_show_help_panel.assert_called_once_with()
        app.action_hide_help_panel.assert_not_called()

    def test_toggle_tag_filter_guard_and_missing_widget(self):
        app = create_mocked_app()

        with patch.object(app, "get_active_category", return_value="history"):
            app.action_toggle_tag_filter()

        app.bell.assert_called_once_with()

        app.bell.reset_mock()

        with (
            patch.object(app, "get_active_category", return_value="all"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            app.action_toggle_tag_filter()

        app.bell.assert_called_once_with()

    def test_toggle_tag_filter_shows_hides_and_focuses_button(self):
        app = create_mocked_app()
        tag_filter = MagicMock()
        tag_filter.available_tags = ["tech"]
        tag_filter.display = False
        first_button = MagicMock(spec=Button)
        tag_filter.query_one.return_value = first_button

        with (
            patch.object(app, "get_active_category", return_value="all"),
            patch.object(app, "query_one", return_value=tag_filter),
        ):
            app.action_toggle_tag_filter()

        self.assertTrue(tag_filter.display)
        first_button.focus.assert_called_once_with()

        first_button.reset_mock()

        with (
            patch.object(app, "get_active_category", return_value="all"),
            patch.object(app, "query_one", return_value=tag_filter),
        ):
            app.action_toggle_tag_filter()

        self.assertFalse(tag_filter.display)
        first_button.focus.assert_not_called()

        tag_filter.display = False
        tag_filter.query_one.side_effect = NoMatches

        with (
            patch.object(app, "get_active_category", return_value="all"),
            patch.object(app, "query_one", return_value=tag_filter),
        ):
            app.action_toggle_tag_filter()

        self.assertTrue(tag_filter.display)

    def test_toggle_tag_filter_without_available_tags(self):
        app = create_mocked_app()
        tag_filter = MagicMock()
        tag_filter.available_tags = []

        with (
            patch.object(app, "get_active_category", return_value="all"),
            patch.object(app, "query_one", return_value=tag_filter),
        ):
            app.action_toggle_tag_filter()

        app.notify.assert_called_once_with(
            "No tags available for this list.",
            severity="information",
        )
        app.bell.assert_called_once_with()

    def test_move_cursor_with_tabs_and_generic_widget(self):
        app = create_mocked_app()
        tabs = Tabs()

        with (
            patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=tabs,
            ),
            patch.object(tabs, "action_previous_tab") as previous,
            patch.object(tabs, "action_next_tab") as next_tab,
        ):
            app.action_move_cursor("left")
            previous.assert_called_once_with()
            next_tab.assert_not_called()

            previous.reset_mock()
            app.action_move_cursor("right")
            next_tab.assert_called_once_with()
            previous.assert_not_called()

        class CursorWidget:
            def __init__(self):
                self.action_cursor_up = MagicMock()

        cursor_widget = CursorWidget()

        with patch.object(
            type(app),
            "focused",
            new_callable=PropertyMock,
            return_value=cursor_widget,
        ):
            app.action_move_cursor("up")

        cursor_widget.action_cursor_up.assert_called_once_with()

    def test_move_cursor_scrolls_when_no_focused_cursor_action(self):
        app = create_mocked_app()
        scrollable = MagicMock()

        with (
            patch.object(
                type(app),
                "focused",
                new_callable=PropertyMock,
                return_value=None,
            ),
            patch.object(
                app,
                "_get_active_scrollable_widget",
                return_value=scrollable,
            ),
        ):
            app.action_move_cursor("up")
            scrollable.scroll_up.assert_called_once_with(duration=0.5)

            app.action_move_cursor("down")
            scrollable.scroll_down.assert_called_once_with(duration=0.5)

            scrollable.reset_mock()
            app.action_move_cursor("left")

        scrollable.scroll_up.assert_not_called()
        scrollable.scroll_down.assert_not_called()

    def test_get_primary_view_widget_simple_categories(self):
        app = create_mocked_app()

        cases = [
            ("history", "#history-ticker-input"),
            ("news", "#news-ticker-input"),
            ("options", "#options-ticker-input"),
            ("fred", "#fred-summary-table"),
            ("all", "#price-table"),
            ("stocks", "#price-table"),
        ]

        for category, expected_selector in cases:
            with self.subTest(category=category):
                widget = MagicMock()

                with (
                    patch.object(
                        app,
                        "get_active_category",
                        return_value=category,
                    ),
                    patch.object(
                        app,
                        "query_one",
                        return_value=widget,
                    ) as query_one,
                ):
                    result = app._get_primary_view_widget()

                self.assertIs(result, widget)
                query_one.assert_called_once_with(expected_selector)

        with (
            patch.object(app, "get_active_category", return_value=None),
            patch.object(app, "query_one") as query_one,
        ):
            self.assertIsNone(app._get_primary_view_widget())

        query_one.assert_not_called()

        with (
            patch.object(app, "get_active_category", return_value="history"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            self.assertIsNone(app._get_primary_view_widget())

    def test_get_primary_view_widget_debug_paths(self):
        app = create_mocked_app()
        debug_view = MagicMock()
        button = MagicMock(spec=Button)
        debug_view.query_one.return_value = button

        with (
            patch.object(app, "get_active_category", return_value="debug"),
            patch.object(app, "query_one", return_value=debug_view),
        ):
            result = app._get_primary_view_widget()

        self.assertIs(result, button)
        debug_view.query_one.assert_called_once_with(".debug-buttons Button")

        debug_table = MagicMock()

        def query_side_effect(selector):
            if selector == "DebugView":
                raise NoMatches()
            if selector == "#debug-table":
                return debug_table
            raise AssertionError(f"Unexpected selector: {selector}")

        with (
            patch.object(app, "get_active_category", return_value="debug"),
            patch.object(app, "query_one", side_effect=query_side_effect),
        ):
            result = app._get_primary_view_widget()

        self.assertIs(result, debug_table)

    def test_get_active_scrollable_widget_paths(self):
        app = create_mocked_app()
        primary = MagicMock()
        output_container = MagicMock()
        news_output = MagicMock()
        history_output = MagicMock()

        output_container.query_one.side_effect = lambda selector: {
            "#news-output-display": news_output,
            "#history-display-container": history_output,
        }[selector]

        with patch.object(
            app,
            "_get_primary_view_widget",
            return_value=None,
        ):
            self.assertIsNone(app._get_active_scrollable_widget())

        config_container = MagicMock()

        with (
            patch.object(
                app,
                "_get_primary_view_widget",
                return_value=primary,
            ),
            patch.object(app, "get_active_category", return_value="configs"),
            patch.object(
                app,
                "query_one",
                return_value=config_container,
            ) as query_one,
        ):
            result = app._get_active_scrollable_widget()

        self.assertIs(result, config_container)
        query_one.assert_called_once_with("#config-container")

        for category, expected in [
            ("news", news_output),
            ("history", history_output),
            ("all", output_container),
        ]:
            with self.subTest(category=category):
                with (
                    patch.object(
                        app,
                        "_get_primary_view_widget",
                        return_value=primary,
                    ),
                    patch.object(
                        app,
                        "get_active_category",
                        return_value=category,
                    ),
                    patch.object(
                        app,
                        "query_one",
                        return_value=output_container,
                    ),
                ):
                    result = app._get_active_scrollable_widget()

                self.assertIs(result, expected)

    async def test_display_data_for_forced_config_view(self):
        app = create_mocked_app()
        app._force_config_sub_view = "lists"

        output_container = MagicMock()
        config_container = MagicMock()
        status_bar = MagicMock()

        def query_side_effect(selector, *args):
            if selector == "#output-container":
                return output_container
            if selector == "#config-container":
                return config_container
            if selector == "#status-bar-container":
                return status_bar
            raise AssertionError(f"Unexpected selector: {selector}")

        with patch.object(app, "query_one", side_effect=query_side_effect):
            await app._display_data_for_category("configs")

        self.assertTrue(config_container.display)
        self.assertFalse(output_container.display)
        self.assertFalse(status_bar.display)
        config_container.show_lists.assert_called_once_with()
        config_container.show_general.assert_not_called()
        config_container.show_portfolios.assert_not_called()
        self.assertIsNone(app._force_config_sub_view)

    async def test_display_data_preserves_current_config_view(self):
        app = create_mocked_app()
        app._force_config_sub_view = None

        cases = [
            ("main", "show_main"),
            ("general", "show_general"),
            ("lists", "show_lists"),
            ("portfolios", "show_portfolios"),
            ("unknown", "show_main"),
        ]

        for current, expected_method in cases:
            with self.subTest(current=current):
                output_container = MagicMock()
                config_container = MagicMock()
                status_bar = MagicMock()
                switcher = MagicMock()
                switcher.current = current
                config_container.query_one.return_value = switcher

                def query_side_effect(
                    selector,
                    *args,
                    output_container=output_container,
                    config_container=config_container,
                    status_bar=status_bar,
                ):
                    if selector == "#output-container":
                        return output_container
                    if selector == "#config-container":
                        return config_container
                    if selector == "#status-bar-container":
                        return status_bar
                    raise AssertionError(f"Unexpected selector: {selector}")

                with patch.object(app, "query_one", side_effect=query_side_effect):
                    await app._display_data_for_category("configs")

                getattr(config_container, expected_method).assert_called_once_with()
                self.assertTrue(config_container.display)
                self.assertFalse(output_container.display)
                self.assertFalse(status_bar.display)

    async def test_display_data_uses_existing_and_new_special_views(self):
        app = create_mocked_app()
        app._force_config_sub_view = None

        config_container = MagicMock()
        status_bar = MagicMock()

        existing_view = MagicMock()
        output_container = MagicMock()
        output_container.query_one.return_value = existing_view

        def existing_query(selector, *args):
            if selector == "#output-container":
                return output_container
            if selector == "#config-container":
                return config_container
            if selector == "#status-bar-container":
                return status_bar
            raise AssertionError(f"Unexpected selector: {selector}")

        with patch.object(app, "query_one", side_effect=existing_query):
            await app._display_data_for_category("history")

        output_container.query_one.assert_called_once_with("#history-view")
        self.assertEqual(output_container.current, "history-view")
        output_container.mount.assert_not_called()
        self.assertFalse(config_container.display)
        self.assertTrue(output_container.display)
        self.assertTrue(status_bar.display)

        new_view = MagicMock()
        output_container = MagicMock()
        output_container.query_one.side_effect = NoMatches
        output_container.mount = AsyncMock()

        def missing_query(selector, *args):
            if selector == "#output-container":
                return output_container
            if selector == "#config-container":
                return config_container
            if selector == "#status-bar-container":
                return status_bar
            raise AssertionError(f"Unexpected selector: {selector}")

        with (
            patch.object(app, "query_one", side_effect=missing_query),
            patch("stockstui.main.HistoryView", return_value=new_view) as view_class,
        ):
            await app._display_data_for_category("history")

        view_class.assert_called_once_with(id="history-view")
        output_container.mount.assert_awaited_once_with(new_view)
        self.assertEqual(output_container.current, "history-view")

    async def test_display_data_empty_price_category(self):
        app = create_mocked_app()
        app._force_config_sub_view = None
        app._visible_columns = ["Ticker", "Price"]
        app.config.lists = {"empty": []}
        app._filter_symbols_by_tags = MagicMock(return_value=[])
        app._get_available_tags_for_category = MagicMock(return_value=[])

        output_container = MagicMock()
        config_container = MagicMock()
        status_bar = MagicMock()
        price_container = MagicMock()
        price_table = MagicMock()

        output_container.query_one.return_value = price_container

        def price_query(selector, *args):
            if selector == "#tag-filter":
                raise NoMatches()
            if selector == "#price-table":
                return price_table
            raise AssertionError(f"Unexpected price selector: {selector}")

        price_container.query_one.side_effect = price_query

        def app_query(selector, *args):
            if selector == "#output-container":
                return output_container
            if selector == "#config-container":
                return config_container
            if selector == "#status-bar-container":
                return status_bar
            raise AssertionError(f"Unexpected app selector: {selector}")

        with patch.object(app, "query_one", side_effect=app_query):
            await app._display_data_for_category("empty")

        self.assertEqual(output_container.current, "price-table-container")
        price_table.clear.assert_called_once_with(columns=True)
        price_table.add_column.assert_any_call("Ticker", key="Ticker")
        price_table.add_column.assert_any_call("Price", key="Price")
        price_table.add_row.assert_called_once_with(
            "[dim]No symbols in list 'empty'. Add some in the Configs tab.[/dim]"
        )
        app.fetch_prices.assert_not_called()

    def test_fetch_prices_worker_success_cancelled_and_error(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        method = StocksTUI.fetch_prices.__wrapped__

        with (
            patch(
                "stockstui.main.market_provider.get_market_price_data",
                return_value=[{"symbol": "AAPL"}],
            ) as provider,
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, ["AAPL"], True, "stocks", True)

        provider.assert_called_once_with(
            ["AAPL"],
            force_refresh=True,
            enable_pre_post_market=True,
        )
        app.post_message.assert_called_once()

        app.post_message.reset_mock()
        worker.is_cancelled = True

        with (
            patch(
                "stockstui.main.market_provider.get_market_price_data",
                return_value=[],
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, ["AAPL"], False, "stocks")

        app.post_message.assert_not_called()

        worker.is_cancelled = False
        with (
            patch(
                "stockstui.main.market_provider.get_market_price_data",
                side_effect=RuntimeError("network"),
            ),
            patch("stockstui.main.logging.error") as log_error,
        ):
            method(app, ["AAPL"], False, "stocks")

        log_error.assert_called_once()
        self.assertIn("network", log_error.call_args.args[0])

    def test_fetch_market_status_worker_paths(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        method = StocksTUI.fetch_market_status.__wrapped__

        with (
            patch(
                "stockstui.main.market_provider.get_market_status",
                return_value={"status": "open"},
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "NYSE")

        app.post_message.assert_called_once()

        app.post_message.reset_mock()
        worker.is_cancelled = True

        with (
            patch(
                "stockstui.main.market_provider.get_market_status",
                return_value={"status": "closed"},
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "NYSE")

        app.post_message.assert_not_called()

        with (
            patch(
                "stockstui.main.market_provider.get_market_status",
                side_effect=RuntimeError("calendar error"),
            ),
            patch("stockstui.main.logging.error") as log_error,
        ):
            method(app, "NYSE")

        log_error.assert_called_once()

    def test_fetch_news_worker_paths(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        method = StocksTUI.fetch_news.__wrapped__

        with patch("stockstui.main.get_current_worker", return_value=worker):
            method(app, " , ")

        app.post_message.assert_called_once()

        app.post_message.reset_mock()

        with (
            patch(
                "stockstui.main.market_provider.get_news_for_tickers",
                return_value=[{"title": "News"}],
            ) as provider,
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "aapl, msft")

        provider.assert_called_once_with(["AAPL", "MSFT"])
        app.post_message.assert_called_once()

        app.post_message.reset_mock()

        with (
            patch(
                "stockstui.main.market_provider.get_news_for_tickers",
                side_effect=RuntimeError("news error"),
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
            patch("stockstui.main.logging.error") as log_error,
        ):
            method(app, "AAPL")

        log_error.assert_called_once()
        app.post_message.assert_called_once()

        app.post_message.reset_mock()
        worker.is_cancelled = True

        with (
            patch(
                "stockstui.main.market_provider.get_news_for_tickers",
                side_effect=RuntimeError("cancelled error"),
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL")

        app.post_message.assert_not_called()

    def test_fetch_historical_data_worker_paths(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        method = StocksTUI.fetch_historical_data.__wrapped__

        with (
            patch(
                "stockstui.main.market_provider.get_historical_data",
                return_value={"history": True},
            ) as provider,
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL", "1y", "1d")

        provider.assert_called_once_with("AAPL", "1y", "1d")
        app.post_message.assert_called_once()

        app.post_message.reset_mock()
        worker.is_cancelled = True

        with (
            patch(
                "stockstui.main.market_provider.get_historical_data",
                return_value={},
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL", "1mo")

        app.post_message.assert_not_called()

        with (
            patch(
                "stockstui.main.market_provider.get_historical_data",
                side_effect=RuntimeError("history error"),
            ),
            patch("stockstui.main.logging.error") as log_error,
        ):
            method(app, "AAPL", "1mo")

        log_error.assert_called_once()

    def test_fetch_options_expirations_worker_paths(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        method = StocksTUI.fetch_options_expirations.__wrapped__

        with (
            patch(
                "stockstui.main.options_provider.get_available_expirations",
                return_value=("2027-01-15",),
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL")

        app.post_message.assert_called_once()

        app.post_message.reset_mock()

        with (
            patch(
                "stockstui.main.options_provider.get_available_expirations",
                return_value=None,
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL")

        app.post_message.assert_called_once()

        app.post_message.reset_mock()

        with (
            patch(
                "stockstui.main.options_provider.get_available_expirations",
                side_effect=RuntimeError("options error"),
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
            patch("stockstui.main.logging.error") as log_error,
        ):
            method(app, "AAPL")

        log_error.assert_called_once()
        app.post_message.assert_called_once()

    def test_fetch_options_chain_worker_paths(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        method = StocksTUI.fetch_options_chain.__wrapped__

        options_data = {
            "calls": ["call"],
            "puts": ["put"],
            "underlying": 200.0,
        }

        with (
            patch(
                "stockstui.main.options_provider.get_options_chain",
                return_value=options_data,
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL", "2027-01-15")

        app.post_message.assert_called_once()

        app.post_message.reset_mock()

        with (
            patch(
                "stockstui.main.options_provider.get_options_chain",
                return_value=None,
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
        ):
            method(app, "AAPL", "2027-01-15")

        self.assertEqual(
            app._last_options_data,
            {"error": "Could not fetch options data for AAPL"},
        )
        app.post_message.assert_not_called()

        with (
            patch(
                "stockstui.main.options_provider.get_options_chain",
                side_effect=RuntimeError("chain error"),
            ),
            patch("stockstui.main.get_current_worker", return_value=worker),
            patch("stockstui.main.logging.error") as log_error,
        ):
            method(app, "AAPL", "2027-01-15")

        log_error.assert_called_once()
        self.assertEqual(app._last_options_data, {"error": "chain error"})

    def test_debug_workers_post_results(self):
        app = create_mocked_app()
        app.post_message = MagicMock()
        worker = MagicMock()
        worker.is_cancelled = False

        cases = [
            (
                StocksTUI.run_info_comparison_test.__wrapped__,
                ("AAPL",),
                "stockstui.main.market_provider.get_ticker_info_comparison",
                {
                    "fast": {"price": 1},
                    "slow": {"price": 2},
                    "batch": {},
                    "prepost": {},
                },
            ),
            (
                StocksTUI.run_ticker_debug_test.__wrapped__,
                (["AAPL"],),
                "stockstui.main.market_provider.run_ticker_debug_test",
                [{"ticker": "AAPL"}],
            ),
            (
                StocksTUI.run_list_debug_test.__wrapped__,
                ({"stocks": ["AAPL"]},),
                "stockstui.main.market_provider.run_list_debug_test",
                [{"list": "stocks"}],
            ),
            (
                StocksTUI.run_cache_test.__wrapped__,
                ({"stocks": ["AAPL"]},),
                "stockstui.main.market_provider.run_cache_test",
                [{"cached": True}],
            ),
        ]

        for method, args, provider_path, result in cases:
            with self.subTest(method=method.__name__):
                app.post_message.reset_mock()

                with (
                    patch(provider_path, return_value=result),
                    patch(
                        "stockstui.main.get_current_worker",
                        return_value=worker,
                    ),
                    patch(
                        "stockstui.main.time.perf_counter",
                        side_effect=[10.0, 10.25],
                    ),
                ):
                    method(app, *args)

                app.post_message.assert_called_once()

        worker.is_cancelled = True
        app.post_message.reset_mock()

        with (
            patch(
                "stockstui.main.market_provider.run_cache_test",
                return_value=[],
            ),
            patch(
                "stockstui.main.get_current_worker",
                return_value=worker,
            ),
            patch(
                "stockstui.main.time.perf_counter",
                side_effect=[1.0, 2.0],
            ),
        ):
            StocksTUI.run_cache_test.__wrapped__(app, {})

        app.post_message.assert_not_called()

    def test_style_and_populate_price_table_covers_value_variants(self):
        app = create_mocked_app()
        app.theme_variables = {
            "price": "cyan",
            "success": "green",
            "error": "red",
            "text-muted": "dim",
        }
        app._visible_columns = [
            "Ticker",
            "Description",
            "Price",
            "Change",
            "% Change",
            "All Time High",
            "% Off ATH",
            "Volume",
            "EPS",
            "PE Ratio",
            "Beta",
            "Div Yield",
            "Custom",
        ]
        app.flash_cell = MagicMock()
        table = MagicMock(spec=DataTable)

        rows = [
            {
                "Description": "Missing ticker",
            },
            {
                "Ticker": "AAPL",
                "Description": "Invalid Ticker",
                "Price": 100.0,
                "Change": 2.0,
                "% Change": 0.02,
                "All Time High": 110.0,
                "% Off ATH": -0.05,
                "Volume": "N/A",
                "EPS": 5.0,
                "PE Ratio": 10.0,
                "Beta": 0.8,
                "Div Yield": "4.5%",
                "Custom": "N/A",
                "_currency_symbol": "DKK",
                "_change_direction": "up",
            },
            {
                "Ticker": "MSFT",
                "Description": "N/A",
                "Price": None,
                "Change": -2.0,
                "% Change": -0.02,
                "All Time High": None,
                "% Off ATH": -0.20,
                "Volume": 1000,
                "EPS": -2.0,
                "PE Ratio": 20.0,
                "Beta": 1.2,
                "Div Yield": "2.5%",
                "Custom": "value",
                "_currency_symbol": "$",
                "_change_direction": "down",
            },
            {
                "Ticker": "TSLA",
                "Description": "Tesla",
                "Price": 200.0,
                "Change": 0.0,
                "% Change": 0.0,
                "All Time High": 400.0,
                "% Off ATH": -0.50,
                "Volume": 2000,
                "EPS": 0.0,
                "PE Ratio": 40.0,
                "Beta": 1.7,
                "Div Yield": "1.0%",
                "Custom": "other",
                "_currency_symbol": "$",
            },
            {
                "Ticker": "NOVO-B.CO",
                "Description": "Novo Nordisk",
                "Price": 600.0,
                "Change": None,
                "% Change": None,
                "All Time High": 900.0,
                "% Off ATH": None,
                "Volume": "N/A",
                "EPS": "N/A",
                "PE Ratio": "N/A",
                "Beta": "N/A",
                "Div Yield": "N/A",
                "Custom": None,
                "_currency_symbol": "DKK",
            },
            {
                "Ticker": "BAD",
                "Description": "Bad values",
                "Price": 1.0,
                "Change": None,
                "% Change": None,
                "All Time High": None,
                "% Off ATH": None,
                "Volume": "N/A",
                "EPS": "invalid",
                "PE Ratio": "invalid",
                "Beta": "invalid",
                "Div Yield": "invalid",
                "Custom": "N/A",
            },
            {
                "Ticker": "HIGHBETA",
                "Description": "High beta",
                "Price": 10.0,
                "Change": 1.0,
                "% Change": 0.1,
                "All Time High": 11.0,
                "% Off ATH": -0.01,
                "Volume": 50,
                "EPS": 1.0,
                "PE Ratio": 30.0,
                "Beta": 2.1,
                "Div Yield": "0.0%",
                "Custom": "value",
            },
        ]

        app._style_and_populate_price_table(table, rows)

        # Rækken uden ticker springes over.
        self.assertEqual(table.add_row.call_count, 6)

        added_keys = [call.kwargs["key"] for call in table.add_row.call_args_list]
        self.assertEqual(
            added_keys,
            ["AAPL", "MSFT", "TSLA", "NOVO-B.CO", "BAD", "HIGHBETA"],
        )

        app.flash_cell.assert_any_call(
            "AAPL",
            "Change",
            "positive",
        )
        app.flash_cell.assert_any_call(
            "AAPL",
            "% Change",
            "positive",
        )
        app.flash_cell.assert_any_call(
            "MSFT",
            "Change",
            "negative",
        )
        app.flash_cell.assert_any_call(
            "MSFT",
            "% Change",
            "negative",
        )
        self.assertEqual(app.flash_cell.call_count, 4)

    def test_update_market_status_display_paths(self):
        app = create_mocked_app()
        app.theme_variables = {
            "status-open": "green",
        }
        label = MagicMock(spec=Label)
        app._schedule_next_market_status_refresh = MagicMock()

        with (
            patch(
                "stockstui.main.formatter.format_market_status",
                return_value=None,
            ),
            patch.object(app, "query_one", return_value=label),
        ):
            app._update_market_status_display({"status": "unknown"})

        label.update.assert_called_once()
        app._schedule_next_market_status_refresh.assert_not_called()

        label.reset_mock()

        with (
            patch(
                "stockstui.main.formatter.format_market_status",
                return_value=(
                    "Market: ",
                    [("Open", "status-open")],
                ),
            ),
            patch.object(app, "query_one", return_value=label),
        ):
            status = {"status": "open"}
            app._update_market_status_display(status)

        label.update.assert_called_once()
        app._schedule_next_market_status_refresh.assert_called_once_with(status)

        app._schedule_next_market_status_refresh.reset_mock()

        with (
            patch(
                "stockstui.main.formatter.format_market_status",
                return_value=("Market: ", []),
            ),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            app._update_market_status_display({"status": "closed"})

        app._schedule_next_market_status_refresh.assert_not_called()

    async def test_market_status_updated_delegates_to_display(self):
        app = create_mocked_app()
        app._update_market_status_display = MagicMock()
        message = MagicMock()
        message.status = {"status": "open"}

        await app.on_market_status_updated(message)

        app._update_market_status_display.assert_called_once_with({"status": "open"})

    async def test_historical_data_updated_paths(self):
        app = create_mocked_app()
        message = MagicMock()
        message.data = {"history": True}

        display_container = MagicMock()
        history_view = MagicMock()
        history_view._render_historical_data = AsyncMock()

        def query_side_effect(selector, *args):
            if selector == "#history-display-container":
                return display_container
            if selector is HistoryView:
                return history_view
            raise AssertionError(f"Unexpected selector: {selector}")

        with patch.object(app, "query_one", side_effect=query_side_effect):
            await app.on_historical_data_updated(message)

        self.assertFalse(display_container.loading)
        self.assertEqual(app._last_historical_data, {"history": True})
        history_view._render_historical_data.assert_awaited_once_with()

        app._last_historical_data = None

        with patch.object(app, "query_one", side_effect=NoMatches):
            await app.on_historical_data_updated(message)

        self.assertIsNone(app._last_historical_data)

        display_container = MagicMock()

        def missing_view(selector, *args):
            if selector == "#history-display-container":
                return display_container
            if selector is HistoryView:
                raise NoMatches()
            raise AssertionError(f"Unexpected selector: {selector}")

        with patch.object(app, "query_one", side_effect=missing_view):
            await app.on_historical_data_updated(message)

        self.assertEqual(app._last_historical_data, {"history": True})

    async def test_options_expirations_updated_paths(self):
        app = create_mocked_app()
        app.options_ticker = "AAPL"

        message = MagicMock()
        message.ticker = "AAPL"
        message.expirations = ("2027-01-15", "2027-02-19")

        options_view = MagicMock()

        with (
            patch.object(app, "get_active_category", return_value="options"),
            patch.object(app, "query_one", return_value=options_view),
        ):
            await app.on_options_expirations_updated(message)

        options_view.update_expirations.assert_called_once_with(
            ["2027-01-15", "2027-02-19"]
        )

        options_view.reset_mock()
        message.expirations = None

        with (
            patch.object(app, "get_active_category", return_value="options"),
            patch.object(app, "query_one", return_value=options_view),
        ):
            await app.on_options_expirations_updated(message)

        options_view.update_expirations.assert_called_once_with([])

        options_view.reset_mock()

        with (
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one") as query_one,
        ):
            await app.on_options_expirations_updated(message)

        query_one.assert_not_called()

        message.ticker = "MSFT"
        with (
            patch.object(app, "get_active_category", return_value="options"),
            patch.object(app, "query_one") as query_one,
        ):
            await app.on_options_expirations_updated(message)

        query_one.assert_not_called()

        message.ticker = "AAPL"
        with (
            patch.object(app, "get_active_category", return_value="options"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_options_expirations_updated(message)

    async def test_options_data_updated_paths(self):
        app = create_mocked_app()

        message = MagicMock()
        message.ticker = "AAPL"
        message.expiration = "2027-01-15"
        message.calls_data = ["call"]
        message.puts_data = ["put"]
        message.underlying = 200.0

        display_container = MagicMock()
        options_view = MagicMock()
        options_view._render_options_data = AsyncMock()

        def query_side_effect(selector, *args):
            if selector == "#options-display-container":
                return display_container
            if selector is OptionsView:
                return options_view
            raise AssertionError(f"Unexpected selector: {selector}")

        with patch.object(app, "query_one", side_effect=query_side_effect):
            await app.on_options_data_updated(message)

        self.assertFalse(display_container.loading)
        self.assertEqual(
            app._last_options_data,
            {
                "ticker": "AAPL",
                "expiration": "2027-01-15",
                "calls": ["call"],
                "puts": ["put"],
                "underlying": 200.0,
            },
        )
        options_view._render_options_data.assert_awaited_once_with()

        app._last_options_data = None

        with patch.object(app, "query_one", side_effect=NoMatches):
            await app.on_options_data_updated(message)

        self.assertIsNone(app._last_options_data)

        display_container = MagicMock()

        def missing_view(selector, *args):
            if selector == "#options-display-container":
                return display_container
            if selector is OptionsView:
                raise NoMatches()
            raise AssertionError(f"Unexpected selector: {selector}")

        with patch.object(app, "query_one", side_effect=missing_view):
            await app.on_options_data_updated(message)

        self.assertIsNotNone(app._last_options_data)

    async def test_news_data_updated_success_error_and_visibility(self):
        app = create_mocked_app()
        app.news_ticker = "AAPL"

        message = MagicMock()
        message.tickers_str = "AAPL"
        message.data = [{"title": "News"}]

        news_view = MagicMock()
        formatted = ("Rendered news", ["https://example.test"])

        with (
            patch(
                "stockstui.main.formatter.format_news_for_display",
                return_value=formatted,
            ) as formatter_mock,
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one", return_value=news_view),
        ):
            await app.on_news_data_updated(message)

        formatter_mock.assert_called_once_with([{"title": "News"}])
        self.assertEqual(app._news_content_for_ticker, "AAPL")
        self.assertEqual(app._last_news_content, formatted)
        news_view.update_content.assert_called_once_with(*formatted)

        news_view.reset_mock()
        message.data = None

        with (
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one", return_value=news_view),
        ):
            await app.on_news_data_updated(message)

        self.assertIn("Could not retrieve news", app._last_news_content[0])
        self.assertEqual(app._last_news_content[1], [])
        news_view.update_content.assert_called_once()

        news_view.reset_mock()
        message.data = [{"title": "Other"}]

        with (
            patch(
                "stockstui.main.formatter.format_news_for_display",
                return_value=("Other news", []),
            ),
            patch.object(app, "get_active_category", return_value="history"),
            patch.object(app, "query_one") as query_one,
        ):
            await app.on_news_data_updated(message)

        query_one.assert_not_called()

        with (
            patch(
                "stockstui.main.formatter.format_news_for_display",
                return_value=("Other news", []),
            ),
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_news_data_updated(message)

    async def test_price_data_updated_ignores_irrelevant_and_missing_table(self):
        app = create_mocked_app()
        app.config.lists = {
            "stocks": [{"ticker": "AAPL"}],
            "crypto": [{"ticker": "BTC-USD"}],
        }

        message = MagicMock()
        message.category = "stocks"
        message.data = [{"symbol": "AAPL", "price": 100.0}]

        with (
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one") as query_one,
        ):
            await app.on_price_data_updated(message)

        query_one.assert_not_called()
        self.assertIn("stocks", app._last_refresh_times)

        with (
            patch.object(app, "get_active_category", return_value="stocks"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_price_data_updated(message)

        message.category = "all"
        with (
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one") as query_one,
        ):
            await app.on_price_data_updated(message)

        query_one.assert_not_called()
        self.assertIn("all", app._last_refresh_times)
        self.assertIn("stocks", app._last_refresh_times)
        self.assertIn("crypto", app._last_refresh_times)

    async def test_ticker_info_comparison_updated_paths(self):
        app = create_mocked_app()
        app.theme_variables = {
            "text-muted": "dim",
            "warning": "yellow",
        }

        buttons = [MagicMock(), MagicMock()]
        table = MagicMock(spec=DataTable)

        message = MagicMock()
        message.fast_info = {"price": 1}
        message.slow_info = {"price": 2}
        message.batch_info = {"price": 1}
        message.prepost_info = {"price": 1}

        rows = [
            ("Price", "1", "1", "1", "2", True),
            ("Name", "N/A", "N/A", "N/A", "N/A", False),
        ]

        with (
            patch.object(app, "query", return_value=buttons),
            patch.object(app, "query_one", return_value=table),
            patch(
                "stockstui.main.formatter.format_info_comparison",
                return_value=rows,
            ) as format_mock,
        ):
            await app.on_ticker_info_comparison_updated(message)

        for button in buttons:
            self.assertFalse(button.disabled)

        self.assertFalse(table.loading)
        table.clear.assert_called_once_with()
        self.assertEqual(table.add_row.call_count, 2)
        format_mock.assert_called_once_with(
            message.fast_info,
            message.slow_info,
            message.batch_info,
            message.prepost_info,
        )

        with (
            patch.object(app, "query", return_value=[]),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_ticker_info_comparison_updated(message)

    async def test_ticker_debug_data_updated_latency_branches(self):
        app = create_mocked_app()
        app.theme_variables = {
            "success": "green",
            "error": "red",
            "latency-high": "red",
            "latency-medium": "yellow",
            "latency-low": "blue",
            "text-muted": "dim",
            "warning": "yellow",
        }

        button = MagicMock()
        table = MagicMock(spec=DataTable)
        label = MagicMock(spec=Label)

        message = MagicMock()
        message.data = [{"symbol": "AAPL"}]
        message.total_time = 3.25

        rows = [
            ("FAST", True, "Fast ticker", 0.25),
            ("MED", True, "N/A", 1.0),
            ("SLOW", False, "Invalid ticker", 3.0),
        ]

        def query_one(selector, *args):
            if selector == "#debug-table":
                return table
            if selector == "#last-refresh-time":
                return label
            raise AssertionError(f"Unexpected selector: {selector}")

        with (
            patch.object(app, "query", return_value=[button]),
            patch.object(app, "query_one", side_effect=query_one),
            patch(
                "stockstui.main.formatter.format_ticker_debug_data_for_table",
                return_value=rows,
            ),
        ):
            await app.on_ticker_debug_data_updated(message)

        self.assertFalse(button.disabled)
        self.assertFalse(table.loading)
        table.clear.assert_called_once_with()
        self.assertEqual(table.add_row.call_count, 3)
        label.update.assert_called_once()

        with (
            patch.object(app, "query", return_value=[]),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_ticker_debug_data_updated(message)

    async def test_list_debug_data_updated_latency_branches(self):
        app = create_mocked_app()
        app.theme_variables = {
            "latency-high": "red",
            "latency-medium": "yellow",
            "latency-low": "blue",
            "text-muted": "dim",
            "warning": "yellow",
        }

        button = MagicMock()
        table = MagicMock(spec=DataTable)
        label = MagicMock(spec=Label)

        message = MagicMock()
        message.data = [{"list": "stocks"}]
        message.total_time = 8.0

        rows = [
            ("Fast", 2, 1.0),
            ("Medium", 3, 3.0),
            ("Slow", 4, 6.0),
            ("N/A", 0, 0.0),
        ]

        def query_one(selector, *args):
            if selector == "#debug-table":
                return table
            if selector == "#last-refresh-time":
                return label
            raise AssertionError(f"Unexpected selector: {selector}")

        with (
            patch.object(app, "query", return_value=[button]),
            patch.object(app, "query_one", side_effect=query_one),
            patch(
                "stockstui.main.formatter.format_list_debug_data_for_table",
                return_value=rows,
            ),
        ):
            await app.on_list_debug_data_updated(message)

        self.assertFalse(button.disabled)
        self.assertFalse(table.loading)
        table.clear.assert_called_once_with()
        self.assertEqual(table.add_row.call_count, 4)
        label.update.assert_called_once()

        with (
            patch.object(app, "query", return_value=[]),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_list_debug_data_updated(message)

    async def test_cache_test_data_updated_paths(self):
        app = create_mocked_app()
        app.theme_variables = {
            "price": "cyan",
            "text-muted": "dim",
        }

        button = MagicMock()
        table = MagicMock(spec=DataTable)
        label = MagicMock(spec=Label)

        message = MagicMock()
        message.data = [{"list": "stocks"}]
        message.total_time = 0.0125

        rows = [
            ("Stocks", 3, 0.001),
            ("N/A", 0, 0.0),
        ]

        def query_one(selector, *args):
            if selector == "#debug-table":
                return table
            if selector == "#last-refresh-time":
                return label
            raise AssertionError(f"Unexpected selector: {selector}")

        with (
            patch.object(app, "query", return_value=[button]),
            patch.object(app, "query_one", side_effect=query_one),
            patch(
                "stockstui.main.formatter.format_cache_test_data_for_table",
                return_value=rows,
            ),
        ):
            await app.on_cache_test_data_updated(message)

        self.assertFalse(button.disabled)
        self.assertFalse(table.loading)
        table.clear.assert_called_once_with()
        self.assertEqual(table.add_row.call_count, 2)
        label.update.assert_called_once()

        first_latency = table.add_row.call_args_list[0].args[2]
        self.assertEqual(first_latency.plain, "1.000 ms")

        with (
            patch.object(app, "query", return_value=[]),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.on_cache_test_data_updated(message)

    def test_apply_price_table_sort_value_branches(self):
        app = create_mocked_app()
        table = MagicMock(spec=DataTable)
        captured_keys = []

        def run_sort(*, key, reverse):
            captured_keys.append(
                {
                    "reverse": reverse,
                    "values": [
                        key((Text("Zulu"),)),
                        key((Text("alpha"),)),
                        key((Text("N/A"),)),
                        key(()),
                    ],
                }
            )

        table.sort.side_effect = run_sort
        table.get_column_index.return_value = 0

        app._sort_column_key = None
        with patch.object(app, "query_one") as query_one:
            app._apply_price_table_sort()
        query_one.assert_not_called()

        app._sort_column_key = "Description"
        app._sort_reverse = True

        with patch.object(app, "query_one", return_value=table):
            app._apply_price_table_sort()

        self.assertEqual(
            captured_keys[0],
            {
                "reverse": True,
                "values": [
                    (0, "zulu"),
                    (0, "alpha"),
                    (1, 0),
                    (1, 0),
                ],
            },
        )

        captured_keys.clear()
        app._sort_column_key = "Volume"
        app._sort_reverse = False

        def run_numeric_sort(*, key, reverse):
            captured_keys.append(
                {
                    "reverse": reverse,
                    "values": [
                        key((Text("1.5M"),)),
                        key((Text("$2,000"),)),
                        key((Text("-3.5K"),)),
                        key((Text("4B"),)),
                        key((Text("2T"),)),
                        key((Text("not numeric"),)),
                        key((Text("Invalid Ticker"),)),
                    ],
                }
            )

        table.sort.side_effect = run_numeric_sort

        with patch.object(app, "query_one", return_value=table):
            app._apply_price_table_sort()

        self.assertEqual(
            captured_keys[0],
            {
                "reverse": False,
                "values": [
                    (0, 1_500_000.0),
                    (0, 2_000.0),
                    (0, -3_500.0),
                    (0, 4_000_000_000.0),
                    (0, 2_000_000_000_000.0),
                    (1, 0),
                    (1, 0),
                ],
            },
        )

        table.get_column_index.side_effect = CellDoesNotExist()

        def run_missing_column(*, key, reverse):
            self.assertEqual(key((Text("100"),)), (1, 0))

        table.sort.side_effect = run_missing_column

        with patch.object(app, "query_one", return_value=table):
            app._apply_price_table_sort()

        with (
            patch.object(app, "query_one", side_effect=NoMatches),
            patch("stockstui.main.logging.error") as log_error,
        ):
            app._apply_price_table_sort()

        log_error.assert_called_once()

    def test_apply_history_table_sort_value_branches(self):
        app = create_mocked_app()
        table = MagicMock(spec=DataTable)
        table.get_column_index.return_value = 0
        captured = []

        app._history_sort_column_key = None

        with patch.object(app, "query_one") as query_one:
            app._apply_history_table_sort()

        query_one.assert_not_called()

        app._history_sort_column_key = "Date"
        app._history_sort_reverse = True

        def run_date_sort(*, key, reverse):
            captured.append(
                (
                    reverse,
                    [
                        key((Text("2026-08-04"),)),
                        key((Text("2025-01-01"),)),
                        key(()),
                    ],
                )
            )

        table.sort.side_effect = run_date_sort

        with patch.object(app, "query_one", return_value=table):
            app._apply_history_table_sort()

        self.assertEqual(
            captured[0],
            (
                True,
                [
                    (0, "2026-08-04"),
                    (0, "2025-01-01"),
                    (1, 0),
                ],
            ),
        )

        captured.clear()
        app._history_sort_column_key = "Close"
        app._history_sort_reverse = False

        def run_numeric_sort(*, key, reverse):
            captured.append(
                (
                    reverse,
                    [
                        key((Text("$1,234.50"),)),
                        key((Text("-25.5"),)),
                        key((Text("N/A"),)),
                    ],
                )
            )

        table.sort.side_effect = run_numeric_sort

        with patch.object(app, "query_one", return_value=table):
            app._apply_history_table_sort()

        self.assertEqual(
            captured[0],
            (
                False,
                [
                    (0, 1234.5),
                    (0, -25.5),
                    (1, 0),
                ],
            ),
        )

        table.get_column_index.side_effect = CellDoesNotExist()

        def run_missing_column(*, key, reverse):
            self.assertEqual(key((Text("100"),)), (1, 0))

        table.sort.side_effect = run_missing_column

        with patch.object(app, "query_one", return_value=table):
            app._apply_history_table_sort()

        with (
            patch.object(app, "query_one", side_effect=NoMatches),
            patch("stockstui.main.logging.error") as log_error,
        ):
            app._apply_history_table_sort()

        log_error.assert_called_once()

    def test_flash_and_unflash_cell_paths(self):
        app = create_mocked_app()
        app.theme_variables = {
            "success": "#00ff00",
            "error": "#ff0000",
            "background": "#000000",
        }

        table = MagicMock(spec=DataTable)
        original = Text("2.50", justify="right")
        table.get_cell.return_value = original
        timer_callbacks = []

        app.set_timer = MagicMock(
            side_effect=lambda delay, callback: timer_callbacks.append(
                (delay, callback)
            )
        )
        app.unflash_cell = MagicMock()

        with patch.object(app, "query_one", return_value=table):
            app.flash_cell("AAPL", "Change", "positive")

        table.update_cell.assert_called_once()
        args = table.update_cell.call_args.args
        self.assertEqual(args[0:2], ("AAPL", "Change"))
        self.assertIsInstance(args[2], Text)
        self.assertEqual(args[2].plain, "2.50")
        self.assertFalse(table.update_cell.call_args.kwargs["update_width"])

        self.assertEqual(len(timer_callbacks), 1)
        self.assertEqual(timer_callbacks[0][0], 0.8)

        timer_callbacks[0][1]()

        app.unflash_cell.assert_called_once_with(
            "AAPL",
            "Change",
            original,
        )

        table.reset_mock()
        table.get_cell.return_value = "plain string"

        with patch.object(app, "query_one", return_value=table):
            app.flash_cell("AAPL", "Change", "negative")

        table.update_cell.assert_not_called()

        with patch.object(app, "query_one", side_effect=NoMatches):
            app.flash_cell("AAPL", "Change", "positive")

        table = MagicMock(spec=DataTable)

        with patch.object(app, "query_one", return_value=table):
            StocksTUI.unflash_cell(
                app,
                "AAPL",
                "Change",
                original,
            )

        table.update_cell.assert_called_once_with(
            "AAPL",
            "Change",
            original,
            update_width=False,
        )

        with patch.object(app, "query_one", side_effect=NoMatches):
            StocksTUI.unflash_cell(
                app,
                "AAPL",
                "Change",
                original,
            )

    def test_main_datatable_row_selected_paths(self):
        app = create_mocked_app()
        app.notify = MagicMock()

        event = MagicMock()
        event.row_key.value = "AAPL"

        app.on_main_datatable_row_selected(event)

        self.assertEqual(app.news_ticker, "AAPL")
        self.assertEqual(app.history_ticker, "AAPL")
        app.notify.assert_called_once_with("Selected AAPL for news/history tabs.")

        app.notify.reset_mock()
        event.row_key.value = None

        app.on_main_datatable_row_selected(event)

        app.notify.assert_not_called()

    def test_price_header_and_sort_state_paths(self):
        app = create_mocked_app()
        app._apply_price_table_sort = MagicMock()

        event = MagicMock()
        event.column_key.value = "Price"

        app.on_price_table_header_selected(event)

        self.assertEqual(app._sort_column_key, "Price")
        self.assertTrue(app._sort_reverse)
        app._apply_price_table_sort.assert_called_once_with()

        app._apply_price_table_sort.reset_mock()
        app._set_and_apply_sort("Price", "keyboard")

        self.assertFalse(app._sort_reverse)
        app._apply_price_table_sort.assert_called_once_with()

        app._apply_price_table_sort.reset_mock()
        app._set_and_apply_sort("Description", "click")

        self.assertEqual(app._sort_column_key, "Description")
        self.assertFalse(app._sort_reverse)
        app._apply_price_table_sort.assert_called_once_with()

        app._apply_price_table_sort.reset_mock()
        app._set_and_apply_sort("Custom", "click")

        self.assertEqual(app._sort_column_key, "Custom")
        self.assertFalse(app._sort_reverse)
        app._apply_price_table_sort.assert_called_once_with()

    def test_history_sort_state_paths(self):
        app = create_mocked_app()
        app._apply_history_table_sort = MagicMock()

        app._history_sort_column_key = None
        app._history_sort_reverse = False

        app._set_and_apply_history_sort("Date", "click")

        self.assertEqual(app._history_sort_column_key, "Date")
        self.assertTrue(app._history_sort_reverse)
        app._apply_history_table_sort.assert_called_once_with()

        app._apply_history_table_sort.reset_mock()
        app._set_and_apply_history_sort("Date", "keyboard")

        self.assertFalse(app._history_sort_reverse)
        app._apply_history_table_sort.assert_called_once_with()

        app._apply_history_table_sort.reset_mock()
        app._set_and_apply_history_sort("Close", "click")

        self.assertEqual(app._history_sort_column_key, "Close")
        self.assertFalse(app._history_sort_reverse)
        app._apply_history_table_sort.assert_called_once_with()

    def test_enter_sort_mode_paths(self):
        app = create_mocked_app()
        app.bell = MagicMock()

        label = MagicMock(spec=Label)
        label.renderable = "Previous status"

        app._sort_mode = True
        with patch.object(app, "get_active_category") as get_category:
            app.action_enter_sort_mode()

        get_category.assert_not_called()

        app._sort_mode = False
        with (
            patch.object(app, "get_active_category", return_value="history"),
            patch.object(app, "query_one", return_value=label),
        ):
            app.action_enter_sort_mode()

        self.assertTrue(app._sort_mode)
        self.assertEqual(app._original_status_text, "Previous status")
        label.update.assert_called_once()
        self.assertIn("SORT BY", label.update.call_args.args[0])
        self.assertIn("\\[d]ate", label.update.call_args.args[0])

        label.reset_mock()
        app._sort_mode = False

        with (
            patch.object(app, "get_active_category", return_value="stocks"),
            patch.object(app, "query_one", return_value=label),
        ):
            app.action_enter_sort_mode()

        self.assertTrue(app._sort_mode)
        label.update.assert_called_once()
        self.assertIn("\\[p]rice", label.update.call_args.args[0])

        app._sort_mode = False
        with (
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one") as query_one,
        ):
            app.action_enter_sort_mode()

        self.assertFalse(app._sort_mode)
        query_one.assert_not_called()
        app.bell.assert_called_once_with()

        app._sort_mode = False
        with (
            patch.object(app, "get_active_category", return_value="stocks"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            app.action_enter_sort_mode()

        self.assertFalse(app._sort_mode)

    async def test_undo_sort_and_focus_input_paths(self):
        app = create_mocked_app()
        app._display_data_for_category = AsyncMock()

        app._sort_column_key = "Price"
        app._sort_reverse = True

        with patch.object(app, "get_active_category", return_value="stocks"):
            await app._undo_sort()

        self.assertIsNone(app._sort_column_key)
        self.assertFalse(app._sort_reverse)
        app._display_data_for_category.assert_awaited_once_with("stocks")

        app._display_data_for_category.reset_mock()

        with patch.object(app, "get_active_category", return_value=None):
            await app._undo_sort()

        app._display_data_for_category.assert_not_awaited()

        widget = MagicMock()

        with patch.object(
            app,
            "_get_primary_view_widget",
            return_value=widget,
        ):
            app.action_focus_input()

        widget.focus.assert_called_once_with()

        with patch.object(
            app,
            "_get_primary_view_widget",
            return_value=None,
        ):
            app.action_focus_input()

    async def test_enter_open_mode_paths(self):
        app = create_mocked_app()
        app.action_handle_sort_key = AsyncMock()
        app.action_handle_open_key = AsyncMock()
        app.bell = MagicMock()

        app._sort_mode = True
        app._open_mode = False

        await app.action_enter_open_mode()

        app.action_handle_sort_key.assert_awaited_once_with("o")

        app.action_handle_sort_key.reset_mock()
        app._sort_mode = False
        app._open_mode = True

        await app.action_enter_open_mode()

        app.action_handle_open_key.assert_awaited_once_with("o")

        app.action_handle_open_key.reset_mock()
        app._open_mode = False

        price_table = MagicMock()
        price_table.cursor_row = 0

        status_label = MagicMock(spec=Label)
        status_label.renderable = "Old status"

        def query_one(selector, *args):
            if selector == "#price-table":
                return price_table
            if selector == "#last-refresh-time":
                return status_label
            raise AssertionError(f"Unexpected selector: {selector}")

        with (
            patch.object(app, "get_active_category", return_value="stocks"),
            patch.object(app, "query_one", side_effect=query_one),
        ):
            await app.action_enter_open_mode()

        self.assertTrue(app._open_mode)
        self.assertEqual(app._original_status_text, "Old status")
        status_label.update.assert_called_once()
        self.assertIn("OPEN IN", status_label.update.call_args.args[0])

        app._open_mode = False
        app.bell.reset_mock()
        price_table.cursor_row = -1

        with (
            patch.object(app, "get_active_category", return_value="stocks"),
            patch.object(app, "query_one", return_value=price_table),
        ):
            await app.action_enter_open_mode()

        self.assertFalse(app._open_mode)
        app.bell.assert_called_once_with()

        app.bell.reset_mock()

        with (
            patch.object(app, "get_active_category", return_value="news"),
            patch.object(app, "query_one") as query_one_mock,
        ):
            await app.action_enter_open_mode()

        query_one_mock.assert_not_called()
        app.bell.assert_called_once_with()

        app.bell.reset_mock()

        with (
            patch.object(app, "get_active_category", return_value="stocks"),
            patch.object(app, "query_one", side_effect=NoMatches),
        ):
            await app.action_enter_open_mode()

        app.bell.assert_called_once_with()

    async def test_handle_open_key_navigation_paths(self):
        app = create_mocked_app()
        app.action_back_or_dismiss = MagicMock()
        app.notify = MagicMock()

        app._open_mode = False

        with patch.object(app, "query_one") as query_one:
            await app.action_handle_open_key("n")

        query_one.assert_not_called()

        app._open_mode = True
        price_table = MagicMock()
        price_table.cursor_row = -1

        with patch.object(app, "query_one", return_value=price_table):
            await app.action_handle_open_key("n")

        app.action_back_or_dismiss.assert_called_once_with()

        app.action_back_or_dismiss.reset_mock()
        price_table.cursor_row = 0
        price_table.coordinate_to_cell_key.return_value.row_key.value = None

        with patch.object(app, "query_one", return_value=price_table):
            await app.action_handle_open_key("n")

        app.action_back_or_dismiss.assert_called_once_with()

        cases = [
            ("n", "news", "news_ticker"),
            ("h", "history", "history_ticker"),
            ("o", "options", "options_ticker"),
        ]

        app.tab_map = [
            {"category": "stocks"},
            {"category": "news"},
            {"category": "history"},
            {"category": "options"},
        ]

        for key, category, ticker_attribute in cases:
            with self.subTest(key=key):
                app.action_back_or_dismiss.reset_mock()
                price_table.cursor_row = 0
                price_table.coordinate_to_cell_key.return_value.row_key.value = "AAPL"
                tabs = MagicMock(spec=Tabs)

                def query_one(selector, *args, tabs=tabs):
                    if selector == "#price-table":
                        return price_table
                    if selector is Tabs:
                        return tabs
                    raise AssertionError(f"Unexpected selector: {selector}")

                with patch.object(
                    app,
                    "query_one",
                    side_effect=query_one,
                ):
                    await app.action_handle_open_key(key)

                self.assertEqual(
                    getattr(app, ticker_attribute),
                    "AAPL",
                )
                expected_index = next(
                    i
                    for i, item in enumerate(app.tab_map, start=1)
                    if item["category"] == category
                )
                self.assertEqual(tabs.active, f"tab-{expected_index}")
                app.action_back_or_dismiss.assert_called_once_with()

        app.action_back_or_dismiss.reset_mock()
        app.tab_map = [{"category": "stocks"}]

        with patch.object(app, "query_one", return_value=price_table):
            await app.action_handle_open_key("n")

        app.notify.assert_called_with(
            "Tab 'news' not found",
            severity="error",
        )
        app.action_back_or_dismiss.assert_called_once_with()

        app.action_back_or_dismiss.reset_mock()

        with patch.object(app, "query_one", side_effect=NoMatches):
            await app.action_handle_open_key("n")

        app.action_back_or_dismiss.assert_called_once_with()

    async def test_handle_open_key_yahoo_paths(self):
        app = create_mocked_app()
        app._open_mode = True
        app.notify = MagicMock()
        app.action_back_or_dismiss = MagicMock()

        price_table = MagicMock()
        price_table.cursor_row = 0
        price_table.coordinate_to_cell_key.return_value.row_key.value = "AAPL"

        with (
            patch.object(app, "query_one", return_value=price_table),
            patch("stockstui.main.webbrowser.open") as browser_open,
        ):
            await app.action_handle_open_key("y")

        browser_open.assert_called_once_with("https://finance.yahoo.com/quote/AAPL")
        app.notify.assert_any_call("Opening Yahoo Finance for AAPL...")
        app.action_back_or_dismiss.assert_called_once_with()

        app.notify.reset_mock()
        app.action_back_or_dismiss.reset_mock()

        with (
            patch.object(app, "query_one", return_value=price_table),
            patch(
                "stockstui.main.webbrowser.open",
                side_effect=webbrowser.Error("no browser"),
            ),
        ):
            await app.action_handle_open_key("y")

        app.notify.assert_any_call(
            "No web browser found. Please configure your system's default browser.",
            severity="error",
            timeout=8,
        )
        app.action_back_or_dismiss.assert_called_once_with()

        app.notify.reset_mock()
        app.action_back_or_dismiss.reset_mock()

        with (
            patch.object(app, "query_one", return_value=price_table),
            patch(
                "stockstui.main.webbrowser.open",
                side_effect=RuntimeError("browser failed"),
            ),
        ):
            await app.action_handle_open_key("y")

        app.notify.assert_any_call(
            "Failed to open browser: browser failed",
            severity="error",
        )
        app.action_back_or_dismiss.assert_called_once_with()

    async def test_handle_sort_key_paths(self):
        app = create_mocked_app()
        app._undo_sort = AsyncMock()
        app._set_and_apply_sort = MagicMock()
        app._set_and_apply_history_sort = MagicMock()
        app.action_back_or_dismiss = MagicMock()
        app.notify = MagicMock()

        app._sort_mode = False

        with patch.object(app, "get_active_category") as get_category:
            await app.action_handle_sort_key("p")

        get_category.assert_not_called()

        app._sort_mode = True
        app._visible_columns = [
            "Description",
            "Price",
            "Change",
            "% Change",
            "Ticker",
        ]

        with patch.object(
            app,
            "get_active_category",
            return_value="stocks",
        ):
            await app.action_handle_sort_key("u")

        app._undo_sort.assert_awaited_once_with()
        app.action_back_or_dismiss.assert_called_once_with()

        app.action_back_or_dismiss.reset_mock()

        with patch.object(
            app,
            "get_active_category",
            return_value="stocks",
        ):
            await app.action_handle_sort_key("p")

        app._set_and_apply_sort.assert_called_once_with(
            "Price",
            "key 'p'",
        )
        app.action_back_or_dismiss.assert_called_once_with()

        app._set_and_apply_sort.reset_mock()
        app.action_back_or_dismiss.reset_mock()

        with patch.object(
            app,
            "get_active_category",
            return_value="history",
        ):
            await app.action_handle_sort_key("H")

        app._set_and_apply_history_sort.assert_called_once_with(
            "High",
            "key 'H'",
        )
        app.action_back_or_dismiss.assert_called_once_with()

        app.action_back_or_dismiss.reset_mock()

        with patch.object(
            app,
            "get_active_category",
            return_value="stocks",
        ):
            await app.action_handle_sort_key("H")

        app.action_back_or_dismiss.assert_not_called()

        app._visible_columns = ["Description", "Ticker"]
        app.notify.reset_mock()

        with patch.object(
            app,
            "get_active_category",
            return_value="stocks",
        ):
            await app.action_handle_sort_key("p")

        app.notify.assert_called_once_with(
            "Price column is hidden.",
            severity="warning",
        )
        app.action_back_or_dismiss.assert_called_once_with()

        app._undo_sort.reset_mock()
        app.action_back_or_dismiss.reset_mock()

        with patch.object(
            app,
            "get_active_category",
            return_value="history",
        ):
            await app.action_handle_sort_key("u")

        app._undo_sort.assert_not_awaited()
        app.action_back_or_dismiss.assert_not_called()


if __name__ == "__main__":
    unittest.main()
