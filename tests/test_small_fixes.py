"""User-visible regressions found in the follow-up review of simple edge cases."""

from contextlib import ExitStack
from datetime import datetime as RealDateTime
import io
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
from rich.console import Console
from textual.app import App
from textual.widgets import ContentSwitcher, DataTable, RadioButton, Static

from stockstui.main import StocksTUI, run_cli_output
from stockstui.parser import create_arg_parser
from stockstui.presentation.formatter import format_market_status
from stockstui.ui.views.config_view import ConfigContainer
from stockstui.ui.views.config_views.fred_config_view import FredConfigView
from stockstui.ui.views.fred_view import FredView, FredDataTable
from stockstui.ui.views.options_view import OptionsView
from stockstui.ui.widgets.oi_chart import OIChart
from stockstui.ui.widgets.vim_radio_set import VimRadioSet
from tests.test_fred_config_view import FredConfigTestApp
from tests.test_fred_view import FredViewTestApp
from tests.test_options_view import OptionsViewTestApp


class TestSimpleDisplay(unittest.TestCase):
    def test_unknown_market_is_not_reported_closed(self):
        for status in ("unknown", "unexpected"):
            with self.subTest(status=status):
                parts = format_market_status(
                    {"status": status, "calendar": "TEST", "is_open": True}
                )[1]
                self.assertEqual(parts[0], ("UNKNOWN ", "text-muted"))

    def test_cli_aliases_are_literal_text(self):
        app_config = SimpleNamespace(
            settings={},
            themes={},
            lists={"mine": [{"ticker": "TEST", "alias": "Name [/broken]", "note": ""}]},
            get_setting=lambda key, default=None: default,
        )
        output = io.StringIO()
        with (
            patch("stockstui.main.ConfigManager", return_value=app_config),
            patch(
                "stockstui.main.Console", return_value=Console(file=output, width=120)
            ),
            patch(
                "stockstui.main.market_provider.get_market_price_data",
                return_value=[{"symbol": "TEST", "price": 10, "previous_close": 9}],
            ),
        ):
            run_cli_output(create_arg_parser().parse_args(["-o", "mine"]))
        self.assertIn("Name [/broken]", output.getvalue())

    def test_cli_fred_aliases_are_literal_text(self):
        app_config = SimpleNamespace(
            settings={
                "fred_settings": {
                    "api_key": "fake",
                    "series_list": ["TEST"],
                    "series_aliases": {"TEST": "Series [/broken]"},
                }
            },
            themes={},
            lists={},
            get_setting=lambda key, default=None: default,
        )
        output = io.StringIO()
        with (
            patch("stockstui.main.ConfigManager", return_value=app_config),
            patch(
                "stockstui.main.Console", return_value=Console(file=output, width=120)
            ),
            patch(
                "stockstui.main.fred_provider.get_series_summary",
                return_value={"id": "TEST", "current": 10},
            ),
        ):
            run_cli_output(create_arg_parser().parse_args(["-o", "fred"]))
        self.assertIn("Series [/broken]", output.getvalue())

    def test_cli_derived_overflow_is_unavailable(self):
        app_config = SimpleNamespace(
            settings={},
            themes={},
            lists={"mine": [{"ticker": "TEST"}]},
            get_setting=lambda key, default=None: default,
        )
        output = io.StringIO()
        with (
            patch("stockstui.main.ConfigManager", return_value=app_config),
            patch(
                "stockstui.main.Console", return_value=Console(file=output, width=120)
            ),
            patch(
                "stockstui.main.market_provider.get_market_price_data",
                return_value=[
                    {"symbol": "TEST", "price": 1e308, "previous_close": -1e308}
                ],
            ),
        ):
            run_cli_output(create_arg_parser().parse_args(["-o", "mine"]))
        self.assertNotIn("inf", output.getvalue().lower())

    def test_oi_chart_extreme_counts_finish_with_finite_coordinates(self):
        calls = pd.DataFrame({"strike": [100.0], "openInterest": [1.7e308]})
        empty = pd.DataFrame(columns=["strike", "openInterest"])
        chart = OIChart(calls, empty, 100)
        plot = MagicMock()
        app = SimpleNamespace(theme_variables={})
        steps = 0
        original = sys.gettrace()

        def trace(frame, event, arg):
            nonlocal steps
            if event == "line" and frame.f_code is OIChart.replot.__code__:
                steps += 1
                if steps > 2000:
                    raise AssertionError(
                        "Chart did not finish within a bounded number of operations"
                    )
            return trace

        with (
            patch.object(OIChart, "plt", new_callable=PropertyMock, return_value=plot),
            patch.object(OIChart, "app", new_callable=PropertyMock, return_value=app),
        ):
            try:
                sys.settrace(trace)
                chart.replot()
            finally:
                sys.settrace(original)
        values = plot.multiple_bar.call_args.args[1]
        self.assertTrue(
            all(math.isfinite(v) and v <= 1e100 for side in values for v in side)
        )
        ticks, labels = plot.yticks.call_args.args
        self.assertLessEqual(len(ticks), 12)
        self.assertTrue(all(math.isfinite(tick) for tick in ticks))
        self.assertTrue(any("e+308" in label for label in labels))
        # Exercise the actual renderer as well as inspecting plotting coordinates.
        with patch.object(OIChart, "app", new_callable=PropertyMock, return_value=app):
            chart.plt.plotsize(80, 20)
            chart.replot()
            rendered = chart.plt.build()
        self.assertIsInstance(rendered, str)
        self.assertIn("e+308", rendered)


class TestSimpleUI(unittest.IsolatedAsyncioTestCase):
    async def test_empty_fred_configuration_actions_are_safe(self):
        app = FredConfigTestApp()
        app.config.settings["fred_settings"]["series_list"] = []
        app.push_screen = MagicMock()
        with patch.object(FredConfigView, "_fetch_descriptions"):
            async with app.run_test():
                view = app.query_one(FredConfigView)
                view.on_edit_series()
                view.on_remove_series()
                app.push_screen.assert_not_called()

    async def test_enter_edits_fred_configuration_cell(self):
        app = FredConfigTestApp()
        app.push_screen = MagicMock()
        app.config.settings["fred_settings"]["series_descriptions"] = {
            "TEST1": "One",
            "TEST2": "Two",
        }
        with patch.object(FredConfigView, "_fetch_descriptions"):
            async with app.run_test() as pilot:
                app.query_one(DataTable).focus()
                await pilot.pause()
                self.assertIs(app.focused, app.query_one(DataTable))
                await pilot.press("enter")
                await pilot.pause()
                app.push_screen.assert_called_once()

    async def test_empty_fred_summary_actions_are_safe(self):
        app = FredViewTestApp()
        app.config.settings["fred_settings"]["series_list"] = []
        app.push_screen = MagicMock()
        async with app.run_test():
            view = app.query_one(FredView)
            app.query_one(FredDataTable).clear()
            self.assertEqual(app.query_one(FredDataTable).row_count, 0)
            with patch("stockstui.ui.views.fred_view.webbrowser.open") as browser:
                view.action_edit_series()
                view.action_open_series()
                app.push_screen.assert_not_called()
                browser.assert_not_called()

    async def test_empty_options_side_position_action_is_safe(self):
        app = OptionsViewTestApp()
        async with app.run_test() as pilot:
            view = app.query_one(OptionsView)
            table = DataTable(id="options-calls-table")
            await view.query_one("#options-display-container").mount(table)
            table.focus()
            await pilot.pause()
            view.action_manage_position()
            app.push_screen.assert_not_called()

    async def test_expiration_today_shows_zero_days(self):
        class Clock(RealDateTime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 18, 15, 0)

        app = OptionsViewTestApp()
        async with app.run_test():
            app._last_options_data = {
                "calls": pd.DataFrame({"strike": [100], "contractSymbol": ["TESTC"]}),
                "puts": pd.DataFrame(),
                "underlying": {},
                "expiration": "2026-10-18",
            }
            with patch("stockstui.ui.views.options_view.datetime", Clock):
                await app.query_one(OptionsView)._render_options_data()
            text = str(app.query_one(".options-info-header", Static).renderable)
            self.assertIn("Days to Expiration: 0", text)

    async def test_vim_j_k_navigate_radio_choices(self):
        class RadioApp(App):
            def compose(self):
                yield VimRadioSet(RadioButton("one", value=True), RadioButton("two"))

        app = RadioApp()
        async with app.run_test() as pilot:
            radios = app.query_one(VimRadioSet)
            radios.focus()
            await pilot.press("j", "space")
            await pilot.pause()
            self.assertEqual(str(radios.pressed_button.label), "two")
            await pilot.press("k", "space")
            await pilot.pause()
            self.assertEqual(str(radios.pressed_button.label), "one")

    async def test_rebuild_preserves_fred_settings_page(self):
        with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
            stack.enter_context(
                patch(
                    "stockstui.config_manager.dirs",
                    SimpleNamespace(
                        user_config_dir=str(Path(root) / "config"),
                        user_cache_dir=str(Path(root) / "cache"),
                    ),
                )
            )
            stack.enter_context(
                patch(
                    "stockstui.main.market_provider.get_market_price_data",
                    return_value=[],
                )
            )
            stack.enter_context(
                patch(
                    "stockstui.main.market_provider.get_market_status", return_value={}
                )
            )
            stack.enter_context(patch.object(FredView, "load_all_series"))
            app = StocksTUI(cli_overrides={"configs": True})
            try:
                async with app.run_test(size=(140, 45)) as pilot:
                    await pilot.pause()
                    container = app.query_one(ConfigContainer)
                    container.show_fred()
                    await pilot.pause()
                    with patch.object(
                        container, "show_fred", wraps=container.show_fred
                    ) as show:
                        await app._rebuild_app("configs", config_sub_view="fred")
                        self.assertGreater(show.call_count, 0)
                    self.assertEqual(
                        container.query_one(ContentSwitcher).current, "fred"
                    )
            finally:
                app.db_manager.close()
