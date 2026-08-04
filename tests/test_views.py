import unittest
import webbrowser
from unittest.mock import MagicMock, patch, AsyncMock

from textual.app import App
from textual.widgets import DataTable, Input, Markdown
from textual.theme import Theme
from textual.dom import NoMatches
from rich.text import Text
from textual import on

from stockstui.common import TickerDebugDataUpdated
from stockstui.ui.views.debug_view import DebugView
from stockstui.ui.views.news_view import NewsView
from stockstui.ui.views.config_view import ConfigContainer
from stockstui.ui.views.config_views.lists_config_view import ListsConfigView
from stockstui.presentation import formatter


class ViewsTestApp(App):
    """A minimal app for testing individual views."""

    def __init__(self, view_to_test):
        super().__init__()
        self.view_to_test = view_to_test
        # Mock necessary app attributes that views might access
        self.config = MagicMock()
        self.config.lists.values.return_value = []
        self.config.get_setting.return_value = "default_theme"
        self.config.themes = {"default_theme": {"palette": {}}}
        self.config.settings = {"theme": "default_theme", "auto_refresh": False}
        self.cli_overrides = {}
        self.news_ticker = None
        self._news_content_for_ticker = None
        self._last_news_content = None
        self.fetch_news = MagicMock()
        self.theme_variables = {}
        self.active_list_category = "stocks"
        self.market_status_timer = None
        self.fetch_market_status = MagicMock()
        self._rebuild_app = AsyncMock()
        self._manage_price_refresh_timer = MagicMock()

    def on_mount(self):
        # Correctly register a valid Theme object before mounting.
        default_theme = Theme(name="default_theme", primary="blue", dark=True)
        self.register_theme(default_theme)
        self.mount(self.view_to_test)

    def run_ticker_debug_test(self, symbols):
        """Mock method for testing."""
        pass

    @on(TickerDebugDataUpdated)
    async def on_ticker_debug_data_updated(self, message: TickerDebugDataUpdated):
        """This handler is a simplified version of the one in the main app."""
        try:
            view = self.query_one(DebugView)
            dt = view.query_one("#debug-table", DataTable)
            dt.loading = False
            dt.clear()
            rows = formatter.format_ticker_debug_data_for_table(message.data)
            for row in rows:
                dt.add_row(*row)
        except Exception:
            pass


class TestDebugView(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the DebugView."""

    async def test_debug_view_populates_table(self):
        """Test that the view correctly populates its table on message."""
        view = DebugView()
        app = ViewsTestApp(view)

        async with app.run_test() as pilot:
            await pilot.click("#debug-test-tickers")
            await pilot.pause()

            message = TickerDebugDataUpdated(
                data=[
                    {
                        "symbol": "AAPL",
                        "is_valid": True,
                        "description": "Apple",
                        "latency": 0.5,
                    }
                ],
                total_time=0.5,
            )
            app.post_message(message)
            await pilot.pause()

            table = view.query_one(DataTable)
            self.assertEqual(table.row_count, 1)
            self.assertEqual(str(table.get_cell_at((0, 0))), "AAPL")


class TestNewsView(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the NewsView."""

    async def test_news_view_fetches_on_submit(self):
        """Test that submitting the input triggers a news fetch."""
        view = NewsView()
        app = ViewsTestApp(view)
        async with app.run_test() as pilot:
            input_widget = view.query_one("#news-ticker-input")
            input_widget.value = "TSLA"
            view.on_news_ticker_submitted(input_widget.Submitted(input_widget, "TSLA"))
            await pilot.pause()
            app.fetch_news.assert_called_once_with("TSLA")

    @patch("webbrowser.open")
    async def test_news_view_link_navigation(self, mock_webbrowser_open):
        """Test cycling through and opening links in the news view."""
        view = NewsView()
        app = ViewsTestApp(view)
        async with app.run_test() as pilot:
            markdown_content = (
                "**[Title 1](link1)**\n\n---\n**[Title 2](link2)**\n\n---\n"
            )
            urls = ["link1", "link2"]
            view.update_content(markdown_content, urls)
            await pilot.pause()

            # Cycle forward
            await pilot.press("tab")
            self.assertEqual(view._current_link_index, 0)
            await pilot.press("tab")
            self.assertEqual(view._current_link_index, 1)
            await pilot.press("tab")  # Wraps around
            self.assertEqual(view._current_link_index, 0)

            # Cycle backward
            await pilot.press("shift+tab")  # Wraps around
            self.assertEqual(view._current_link_index, 1)

            # Open link
            await pilot.press("enter")
            mock_webbrowser_open.assert_called_once_with("link2")


    async def test_news_view_mount_uses_cached_content(self):
        """Cached content for the active ticker should be restored on mount."""
        view = NewsView()
        app = ViewsTestApp(view)
        app.news_ticker = "AAPL"
        app._news_content_for_ticker = "AAPL"
        app._last_news_content = ("[Cached](https://example.com)", ["https://example.com"])

        async with app.run_test() as pilot:
            await pilot.pause()

            markdown = view.query_one(Markdown)
            self.assertFalse(markdown.loading)
            self.assertEqual(view._link_urls, ["https://example.com"])
            self.assertEqual(view._current_link_index, -1)
            app.fetch_news.assert_not_called()

    async def test_news_view_mount_fetches_uncached_content(self):
        """A ticker without matching cached content should trigger a fetch."""
        view = NewsView()
        app = ViewsTestApp(view)
        app.news_ticker = "MSFT"
        app._news_content_for_ticker = "AAPL"
        app._last_news_content = ("Old content", ["old-link"])

        async with app.run_test() as pilot:
            await pilot.pause()

            markdown = view.query_one(Markdown)
            self.assertTrue(markdown.loading)
            app.fetch_news.assert_called_once_with("MSFT")

    async def test_news_view_empty_submit_resets_state(self):
        """An empty submission should clear cached and link-navigation state."""
        view = NewsView()
        app = ViewsTestApp(view)

        async with app.run_test() as pilot:
            input_widget = view.query_one(Input)

            view._link_urls = ["link"]
            view._current_link_index = 0
            view._original_markdown = "[Title](link)"
            app._last_news_content = ("content", ["link"])
            app._news_content_for_ticker = "AAPL"

            view.on_news_ticker_submitted(
                input_widget.Submitted(input_widget, "")
            )

            self.assertEqual(view._link_urls, [])
            self.assertEqual(view._current_link_index, -1)
            self.assertEqual(view._original_markdown, "")
            self.assertIsNone(app._last_news_content)
            self.assertIsNone(app._news_content_for_ticker)
            app.fetch_news.assert_not_called()

    async def test_news_view_highlight_fallbacks_and_empty_navigation(self):
        """Non-string content, no selection, and empty link lists are harmless."""
        view = NewsView()
        app = ViewsTestApp(view)

        async with app.run_test() as pilot:
            await pilot.pause()

            markdown = view.query_one(Markdown)

            view._original_markdown = Text("Plain content")
            view._current_link_index = 0
            with patch.object(markdown, "update") as update:
                view._highlight_current_link()
                update.assert_called_once_with(view._original_markdown)

            view._original_markdown = "[Title](link)"
            view._current_link_index = -1
            with patch.object(markdown, "update") as update:
                view._highlight_current_link()
                update.assert_called_once_with("[Title](link)")

            view._link_urls = []
            view.action_cycle_links()
            view.action_cycle_links_backward()
            view.action_open_link()

            self.assertEqual(view._current_link_index, -1)

    async def test_news_view_backward_navigation_moves_focus(self):
        """Backward navigation should move focus from input to Markdown."""
        view = NewsView()
        app = ViewsTestApp(view)

        async with app.run_test() as pilot:
            view.update_content(
                "[Title 1](link1)\n\n[Title 2](link2)",
                ["link1", "link2"],
            )
            await pilot.pause()

            input_widget = view.query_one(Input)
            markdown = view.query_one(Markdown)

            await pilot.click("#news-ticker-input")
            await pilot.pause()
            self.assertTrue(input_widget.has_focus)

            view._current_link_index = 1
            view.action_cycle_links_backward()
            await pilot.pause()

            self.assertTrue(markdown.has_focus)
            self.assertEqual(view._current_link_index, 0)

    async def test_news_view_open_link_error_handling(self):
        """Browser, index, and unexpected errors should notify the user."""
        class BrokenLinks(list):
            def __getitem__(self, index):
                raise IndexError("broken index")

        view = NewsView()
        app = ViewsTestApp(view)

        async with app.run_test() as pilot:
            await pilot.pause()

            with patch.object(app, "notify") as notify:
                view._link_urls = ["https://example.com"]
                view._current_link_index = 0

                with patch(
                    "stockstui.ui.views.news_view.webbrowser.open",
                    side_effect=webbrowser.Error("no browser"),
                ):
                    view.action_open_link()

                self.assertEqual(notify.call_args.kwargs["severity"], "error")
                self.assertEqual(notify.call_args.kwargs["timeout"], 8)

                notify.reset_mock()
                view._link_urls = BrokenLinks(["broken"])
                view._current_link_index = 0
                view.action_open_link()

                notify.assert_called_once_with(
                    "Internal error: Invalid link index.",
                    severity="error",
                )

                notify.reset_mock()
                view._link_urls = ["https://example.com"]
                view._current_link_index = 0

                with patch(
                    "stockstui.ui.views.news_view.webbrowser.open",
                    side_effect=RuntimeError("browser failure"),
                ):
                    view.action_open_link()

                notify.assert_called_with(
                    "An unexpected error occurred: browser failure",
                    severity="error",
                )

    def test_news_view_single_link_skips_scrolling(self):
        """A single highlighted link should not calculate scroll position."""
        view = NewsView()
        markdown = MagicMock()
        markdown.virtual_size.height = 200
        markdown.container_size.height = 100

        view._original_markdown = "[Title](link1)"
        view._link_urls = ["link1"]
        view._current_link_index = 0

        with patch.object(view, "query_one", return_value=markdown):
            view._highlight_current_link()

        markdown.update.assert_called_once_with("[➤ Title](link1)")
        markdown.scroll_to.assert_not_called()

    def test_news_view_scrolls_to_highlighted_link(self):
        """Highlighted links should scroll proportionally in long content."""
        view = NewsView()
        markdown = MagicMock()
        markdown.virtual_size.height = 300
        markdown.container_size.height = 100

        view._original_markdown = (
            "[Title 1](link1)\n"
            "[Title 2](link2)\n"
            "[Title 3](link3)"
        )
        view._link_urls = ["link1", "link2", "link3"]
        view._current_link_index = 1

        with patch.object(view, "query_one", return_value=markdown):
            view._highlight_current_link()

        markdown.update.assert_called_once_with(
            "[Title 1](link1)\n"
            "[➤ Title 2](link2)\n"
            "[Title 3](link3)"
        )
        markdown.scroll_to.assert_called_once_with(
            y=100.0,
            duration=0.2,
        )

class TestConfigContainer(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the main ConfigContainer."""

    async def test_config_container_navigation(self):
        """Test the view switching and history logic."""
        container = ConfigContainer()
        app = ViewsTestApp(container)
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "main")

            container.show_lists()
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "lists")

            container.action_go_back()
            await pilot.pause()
            self.assertEqual(container.query_one("ContentSwitcher").current, "main")


    def test_config_container_switch_view_edge_cases(self):
        """Repeated navigation and missing focus targets should be harmless."""
        container = ConfigContainer()
        switcher = MagicMock()
        switcher.current = "main"

        focus_target = MagicMock()
        query_result = MagicMock()
        query_result.first.return_value = focus_target

        container._history = ["main"]

        with (
            patch.object(container, "query_one", return_value=switcher),
            patch.object(container, "query", return_value=query_result),
        ):
            container._switch_view("general")

        self.assertEqual(switcher.current, "general")
        self.assertEqual(container._history, ["main", "general"])
        focus_target.focus.assert_called_once()

        # The requested view is already the latest history entry.
        switcher.current = "main"
        container._history = ["general"]

        with (
            patch.object(container, "query_one", return_value=switcher),
            patch.object(container, "query", return_value=query_result),
        ):
            container._switch_view("general")

        self.assertEqual(container._history, ["general"])

        # The switcher is already displaying the requested view.
        switcher.current = "general"

        with (
            patch.object(container, "query_one", return_value=switcher),
            patch.object(container, "query", side_effect=NoMatches),
        ):
            container._switch_view("general")

        self.assertEqual(container._history, ["general"])

    def test_config_container_go_back_edge_cases(self):
        """Back navigation should handle missing views and empty history."""
        container = ConfigContainer()
        switcher = MagicMock()
        container._history = ["main", "lists"]

        with (
            patch.object(container, "query_one", return_value=switcher),
            patch.object(container, "query", side_effect=NoMatches),
        ):
            result = container.action_go_back()

        self.assertTrue(result)
        self.assertEqual(switcher.current, "main")
        self.assertEqual(container._history, ["main"])

        self.assertFalse(container.action_go_back())

    def test_config_container_show_main(self):
        """Showing the main view should reset navigation history."""
        container = ConfigContainer()
        switcher = MagicMock()
        switcher.current = "lists"

        focus_target = MagicMock()
        query_result = MagicMock()
        query_result.first.return_value = focus_target

        container._history = ["main", "lists"]

        with (
            patch.object(container, "query_one", return_value=switcher),
            patch.object(container, "query", return_value=query_result),
        ):
            container.show_main()

        self.assertEqual(switcher.current, "main")
        self.assertEqual(container._history, ["main"])
        focus_target.focus.assert_called_once()

        # Also cover an already-active main view with no focus target.
        switcher.current = "main"

        with (
            patch.object(container, "query_one", return_value=switcher),
            patch.object(container, "query", side_effect=NoMatches),
        ):
            container.show_main()

        self.assertEqual(container._history, ["main"])

    def test_config_container_public_view_methods(self):
        """Public navigation methods should delegate to the correct view IDs."""
        container = ConfigContainer()

        with patch.object(container, "_switch_view") as switch_view:
            container.show_general()
            container.show_lists()
            container.show_portfolios()
            container.show_fred()

        self.assertEqual(
            switch_view.call_args_list,
            [
                unittest.mock.call("general"),
                unittest.mock.call("lists"),
                unittest.mock.call("portfolios"),
                unittest.mock.call("fred"),
            ],
        )

class TestListsConfigView(unittest.IsolatedAsyncioTestCase):
    """Unit tests for the ListsConfigView."""

    async def test_repopulate_lists_and_tickers(self):
        """Test that the list and ticker tables populate from app config."""
        view = ListsConfigView()
        app = ViewsTestApp(view)

        app.config.lists = {
            "stocks": [{"ticker": "AAPL", "alias": "Apple"}],
            "crypto": [{"ticker": "BTC-USD", "alias": "Bitcoin"}],
        }
        app.active_list_category = "stocks"

        async with app.run_test() as pilot:
            await pilot.pause()

            list_view = view.query_one("#symbol-list-view")
            self.assertEqual(list_view.index, 0)
            self.assertEqual(len(list_view.children), 2)

            ticker_table = view.query_one("#ticker-table")
            self.assertEqual(ticker_table.row_count, 1)
            self.assertEqual(str(ticker_table.get_cell_at((0, 0))), "AAPL")
