import unittest
from unittest.mock import MagicMock
from pathlib import Path
import asyncio
import threading

from rich.text import Text

from stockstui.main import StocksTUI
from stockstui.utils import (
    slugify,
    extract_cell_text,
    parse_tags,
    format_tags,
    match_tags,
    merge_price_data,
)

# Define the root path of the application package.
TEST_APP_ROOT = Path(__file__).resolve().parent.parent / "stockstui"


async def create_test_app() -> StocksTUI:
    """
    Creates a fully mocked, composed instance of the StocksTUI app for testing.
    """
    app = create_mocked_app()

    app._loop = asyncio.get_running_loop()
    app._thread_id = threading.get_ident()

    with app._context():
        screen = app.get_default_screen()
        app.install_screen(screen, "_default")
        await app.push_screen("_default")

    app.mount()
    await app.workers.wait_for_complete()
    await asyncio.sleep(0.01)
    setattr(app, "push_screen", MagicMock())

    return app


def create_mocked_app() -> StocksTUI:
    """
    Creates a StocksTUI app with mocks but does NOT mount it.
    Suitable for use with app.run_test().
    """
    app = StocksTUI()

    # Replace core components with mocks
    # Use setattr to avoid Mypy errors when mocking App attributes
    setattr(app, "config", MagicMock())
    setattr(app, "db_manager", MagicMock())
    setattr(app, "portfolio_manager", MagicMock())
    setattr(app, "notify", MagicMock())
    setattr(app, "bell", MagicMock())
    setattr(app, "fetch_prices", MagicMock())
    setattr(app, "fetch_news", MagicMock())
    setattr(app, "fetch_historical_data", MagicMock())

    # Test theme expectations: use gruvbox_soft_dark (as requested)
    def get_setting_side_effect(key, default=None):
        if key == "theme":
            return "gruvbox_soft_dark"
        if key == "market_calendar":
            return "NYSE"
        return default

    getattr(app, "config").get_setting.side_effect = get_setting_side_effect
    app.config.lists = {"stocks": [], "crypto": [], "news": [], "debug": []}

    # Register a dummy theme to satisfy app requirements
    from textual.theme import Theme

    app.register_theme(
        Theme(
            name="gruvbox_soft_dark",
            primary="#d79921",
            secondary="#458588",
            background="#282828",
            surface="#3c3836",
            error="#cc241d",
            warning="#d65d0e",
            success="#98971a",
            accent="#b16286",
            dark=True,
            variables={
                "price": "cyan",
                "latency-high": "red",
                "latency-medium": "yellow",
                "latency-low": "blue",
                "text-muted": "#808080",
                "status-open": "green",
                "status-pre": "yellow",
                "status-post": "yellow",
                "status-closed": "red",
                "button-foreground": "white",
                "scrollbar": "black",
                "scrollbar-hover": "#808080",
            },
        )
    )
    # Mock _available_theme_names to include our dummy theme so on_mount doesn't try to reload
    app._available_theme_names = ["gruvbox_soft_dark"]

    # Updated tab map to match actual app structure
    app.tab_map = [
        {"name": "All", "category": "all"},
        {"name": "Stocks", "category": "stocks"},
        {"name": "Crypto", "category": "crypto"},
        {"name": "News", "category": "news"},
        {"name": "Debug", "category": "debug"},
        {"name": "History", "category": "history"},
        {"name": "Configs", "category": "configs"},
    ]
    # Do not mock _rebuild_app so that tabs are actually created
    # app._rebuild_app = MagicMock()

    return app


class TestUtils(unittest.TestCase):
    """Unit tests for utility functions."""

    def test_slugify(self):
        self.assertEqual(slugify("My List Name"), "my_list_name")
        self.assertEqual(slugify("  Spaces  "), "spaces")
        self.assertEqual(slugify("Multiple   Spaces"), "multiple___spaces")
        self.assertEqual(slugify("UPPER"), "upper")

    def test_extract_cell_text(self):
        self.assertEqual(extract_cell_text(Text("Rich Text")), "Rich Text")
        self.assertEqual(extract_cell_text(None), "")
        self.assertEqual(extract_cell_text("Plain String"), "Plain String")
        self.assertEqual(extract_cell_text(123), "123")
        self.assertEqual(extract_cell_text("  trimmed  "), "trimmed")

    def test_parse_tags(self):
        self.assertEqual(parse_tags("tech, growth, value"), ["tech", "growth", "value"])
        self.assertEqual(parse_tags("tech;growth value"), ["tech", "growth", "value"])
        self.assertEqual(parse_tags("  "), [])
        self.assertEqual(parse_tags(None), [])
        self.assertEqual(parse_tags("tech, TECH, Growth"), ["tech", "growth"])
        self.assertEqual(parse_tags("a, b, a"), ["a", "b"])

    def test_format_tags(self):
        self.assertEqual(format_tags(["tech", "growth"]), "tech, growth")
        self.assertEqual(format_tags([]), "")
        self.assertEqual(format_tags(["single"]), "single")


    def test_merge_price_data_invalid_existing_all_time_high(self):
        """A valid new high should replace an unreadable cached high."""
        existing = {
            "price": 100.0,
            "all_time_high": "invalid",
        }
        new_data = {
            "all_time_high": 150.0,
        }

        result = merge_price_data(existing, new_data)

        self.assertEqual(result["all_time_high"], 150.0)
        self.assertEqual(
            existing["all_time_high"],
            "invalid",
            "The original dictionary must not be mutated",
        )

    def test_merge_price_data_ignores_invalid_new_all_time_high(self):
        """Unreadable new all-time-high values must not corrupt the cache."""
        existing = {
            "price": 100.0,
            "all_time_high": 150.0,
        }

        result = merge_price_data(
            existing,
            {"all_time_high": "not-a-number"},
        )

        self.assertEqual(result["all_time_high"], 150.0)

    def test_merge_price_data_ignores_invalid_price_fields(self):
        """Malformed comparison fields should not break high validation."""
        existing = {
            "all_time_high": 150.0,
            "price": 100.0,
        }
        new_data = {
            "price": "invalid",
            "day_high": object(),
            "fifty_two_week_high": None,
        }

        result = merge_price_data(existing, new_data)

        self.assertEqual(result["all_time_high"], 150.0)
        self.assertEqual(result["price"], "invalid")
        self.assertIs(result["day_high"], new_data["day_high"])
        self.assertNotIn("fifty_two_week_high", result)

    def test_merge_price_data_raises_high_from_price_fields(self):
        """Observed market highs should correct a stale cached all-time high."""
        existing = {
            "all_time_high": 150.0,
            "price": 145.0,
            "day_high": 148.0,
            "fifty_two_week_high": 149.0,
        }
        new_data = {
            "price": 160.0,
            "day_high": 170.0,
            "fifty_two_week_high": 165.0,
        }

        result = merge_price_data(existing, new_data)

        self.assertEqual(result["all_time_high"], 170.0)

    def test_merge_price_data_preserves_values_when_update_is_none(self):
        """None values must not overwrite valid cached market data."""
        existing = {
            "price": 100.0,
            "day_high": 105.0,
            "all_time_high": 150.0,
        }
        new_data = {
            "price": None,
            "day_high": None,
            "all_time_high": None,
            "volume": 1000,
        }

        result = merge_price_data(existing, new_data)

        self.assertEqual(result["price"], 100.0)
        self.assertEqual(result["day_high"], 105.0)
        self.assertEqual(result["all_time_high"], 150.0)
        self.assertEqual(result["volume"], 1000)

    def test_merge_price_data_accepts_first_valid_all_time_high(self):
        """A positive high should be stored when no cached high exists."""
        result = merge_price_data(
            {"price": 100.0},
            {"all_time_high": 125.0},
        )

        self.assertEqual(result["all_time_high"], 125.0)

    def test_merge_price_data_rejects_non_positive_all_time_high(self):
        """Zero or negative highs must not replace a valid cached high."""
        existing = {"all_time_high": 150.0}

        for invalid_high in (0, -10):
            with self.subTest(invalid_high=invalid_high):
                result = merge_price_data(
                    existing,
                    {"all_time_high": invalid_high},
                )
                self.assertEqual(result["all_time_high"], 150.0)

    def test_merge_price_data_handles_invalid_cached_all_time_high(self):
        """An unreadable cached high should not crash final validation."""
        existing = {
            "all_time_high": "invalid",
            "price": 100.0,
        }

        result = merge_price_data(existing, {})

        self.assertEqual(result["all_time_high"], "invalid")
        self.assertEqual(result["price"], 100.0)

    def test_match_tags(self):
        item_tags = ["tech", "growth"]
        self.assertTrue(match_tags(item_tags, ["growth"]))
        self.assertTrue(match_tags(item_tags, ["tech", "value"]))
        self.assertFalse(match_tags(item_tags, ["value"]))
        self.assertTrue(match_tags(item_tags, []))
        self.assertFalse(match_tags([], ["tech"]))
        self.assertTrue(match_tags([], []))
