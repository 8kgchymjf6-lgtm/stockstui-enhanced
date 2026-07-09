import unittest
from unittest.mock import MagicMock

from textual.css.query import NoMatches

from tests.test_utils import create_test_app
from stockstui.common import FredDebugDataUpdated


class TestGetActiveCategoryKeyErrorRegression(unittest.IsolatedAsyncioTestCase):
    """
    Regression tests for Bug #6:
    get_active_category() was missing KeyError from its except clause, so a stale
    tab_map (which can happen during an app rebuild) would propagate an uncaught
    KeyError to any caller instead of gracefully returning None.
    """

    async def asyncSetUp(self):
        self.app = await create_test_app()

    def test_returns_none_when_tab_map_entry_missing_category_key(self):
        """Regression: a tab_map entry without a 'category' key must return None, not raise KeyError."""
        # ASSUMPTION: tab_map[0] exists but is missing the 'category' key.
        # This mimics a partially-constructed tab_map entry during an app rebuild.
        self.app.tab_map = [{"name": "All"}]  # No 'category' key — would cause KeyError
        self.app._last_active_category = None  # Force live query path

        # Mock the Tabs widget to report tab-1 as active (maps to index 0)
        mock_tabs = MagicMock()
        mock_tabs.active = "tab-1"
        self.app.query_one = MagicMock(return_value=mock_tabs)

        # Before the fix: raises KeyError("category")
        # After the fix:  returns None
        result = self.app.get_active_category()
        self.assertIsNone(result, "Should return None when tab_map entry is missing 'category' key")

    def test_returns_none_when_tab_id_exceeds_tab_map_bounds(self):
        """IndexError path: a tab ID pointing beyond the tab_map list must return None."""
        # Only one tab in tab_map, but active tab ID points to index 4 (out of range)
        self.app.tab_map = [{"name": "All", "category": "all"}]
        self.app._last_active_category = None

        mock_tabs = MagicMock()
        mock_tabs.active = "tab-5"  # int("5") - 1 = 4; tab_map[4] raises IndexError
        self.app.query_one = MagicMock(return_value=mock_tabs)

        result = self.app.get_active_category()
        self.assertIsNone(result, "Should return None when tab ID exceeds tab_map bounds")


class TestFredDebugHandlerKeyErrorRegression(unittest.IsolatedAsyncioTestCase):
    """
    Regression tests for Bug #5:
    on_fred_debug_data_updated() had two identical `except NoMatches:` clauses.
    The second was dead code and could never execute. More critically, a KeyError
    raised by accessing obs['date'] or obs['value'] on a malformed observation dict
    would propagate uncaught, crashing the FRED debug handler.
    """

    async def asyncSetUp(self):
        self.app = await create_test_app()

    async def test_handler_survives_malformed_obs_missing_date_key(self):
        """Regression: A KeyError from a malformed obs dict missing 'date' must not crash the handler."""
        # ASSUMPTION: The FRED API (or a bug in parsing) can return an obs dict without 'date'.
        # This previously would cause an uncaught KeyError in the inner loop on:
        #   dt.add_row(f"  {obs['date']}", f"  {obs['value']}")
        malformed_data = [
            {
                "_section": "Observations",
                "id": "SERIES1",
                "observations": [
                    {"value": "100.0"},  # Missing 'date' key — KeyError trigger
                ],
            }
        ]

        # Replace query_one with a mock that returns a usable DataTable-like object
        mock_dt = MagicMock()
        mock_label = MagicMock()

        def query_one_side_effect(selector, *args, **kwargs):
            if "#debug-table" in str(selector):
                return mock_dt
            if "#last-refresh-time" in str(selector):
                return mock_label
            if ".debug-buttons" in str(selector):
                return MagicMock()
            raise NoMatches(f"No match for {selector}")

        self.app.query_one = MagicMock(side_effect=query_one_side_effect)

        # Mock .query() for button iteration (also called in the handler)
        self.app.query = MagicMock(return_value=[])

        message = FredDebugDataUpdated(data=malformed_data, total_time=0.1)

        # Before the fix: raises KeyError("date"), crashing the handler
        # After the fix:  handler catches KeyError and silently continues
        try:
            await self.app.on_fred_debug_data_updated(message)
        except KeyError as e:
            self.fail(f"on_fred_debug_data_updated raised KeyError unexpectedly: {e}")

    async def test_handler_survives_malformed_obs_missing_value_key(self):
        """Regression: A KeyError from a malformed obs dict missing 'value' must not crash the handler."""
        malformed_data = [
            {
                "_section": "Observations",
                "id": "SERIES2",
                "observations": [
                    {"date": "2023-01-01"},  # Missing 'value' key — KeyError trigger
                ],
            }
        ]

        mock_dt = MagicMock()
        mock_label = MagicMock()

        def query_one_side_effect(selector, *args, **kwargs):
            if "#debug-table" in str(selector):
                return mock_dt
            if "#last-refresh-time" in str(selector):
                return mock_label
            raise NoMatches(f"No match for {selector}")

        self.app.query_one = MagicMock(side_effect=query_one_side_effect)
        self.app.query = MagicMock(return_value=[])

        message = FredDebugDataUpdated(data=malformed_data, total_time=0.1)

        try:
            await self.app.on_fred_debug_data_updated(message)
        except KeyError as e:
            self.fail(f"on_fred_debug_data_updated raised KeyError unexpectedly: {e}")
