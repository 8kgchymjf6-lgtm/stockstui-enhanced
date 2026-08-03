import unittest

from textual.app import App
from stockstui.ui.modals import (
    ConfirmDeleteModal,
    AddListModal,
    EditListModal,
    AddTickerModal,
    EditTickerModal,
    CreatePortfolioModal,
    EditPortfolioModal,
)
from stockstui.ui.position_modal import PositionModal
from stockstui.ui.quick_edit_ticker_modal import QuickEditTickerModal


class ModalsTestApp(App):
    """A minimal app for testing modals."""

    pass


class TestModals(unittest.IsolatedAsyncioTestCase):
    """
    Unit tests for all modal dialogs.
    These tests verify that modals compose correctly and return the expected
    data when their buttons are pressed.
    """

    async def test_confirm_delete_modal(self):
        """Test the ConfirmDeleteModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            # Test confirm
            await pilot.app.push_screen(
                ConfirmDeleteModal("item", "Delete?"), set_result
            )
            await pilot.pause()
            await pilot.click("#delete")
            await pilot.pause()
            self.assertTrue(result)

            # Test cancel
            await pilot.app.push_screen(
                ConfirmDeleteModal("item", "Delete?"), set_result
            )
            await pilot.pause()
            await pilot.click("#cancel")
            await pilot.pause()
            self.assertFalse(result)

    async def test_add_list_modal(self):
        """Test the AddListModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = ""  # Use a non-None default

            def set_result(r):
                nonlocal result
                result = r

            # Test add
            await pilot.app.push_screen(AddListModal(), set_result)
            await pilot.pause()
            await pilot.press("t", "e", "s", "t", " ", "l", "i", "s", "t")
            await pilot.click("#add")
            await pilot.pause()
            self.assertEqual(result, "test_list")

            # Test cancel
            await pilot.app.push_screen(AddListModal(), set_result)
            await pilot.pause()
            await pilot.click("#cancel")
            await pilot.pause()
            self.assertIsNone(result)

    async def test_edit_list_modal(self):
        """Test the EditListModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = ""

            def set_result(r):
                nonlocal result
                result = r

            current_value = "old_name"
            await pilot.app.push_screen(EditListModal(current_value), set_result)
            await pilot.pause()

            # FIX: Clear the input before typing to prevent overwriting selected text.
            for _ in current_value:
                await pilot.press("backspace")
            await pilot.press("n", "e", "w", "_", "n", "a", "m", "e")

            await pilot.click("#save")
            await pilot.pause()
            self.assertEqual(result, "new_name")

    async def test_add_ticker_modal(self):
        """Test the AddTickerModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            await pilot.app.push_screen(AddTickerModal(), set_result)
            await pilot.pause()
            await pilot.press(
                "a",
                "a",
                "p",
                "l",
                "tab",
                "a",
                "p",
                "p",
                "l",
                "e",
                "tab",
                "n",
                "o",
                "t",
                "e",
                "tab",
                "t",
                "a",
                "g",
            )
            await pilot.click("#add")
            await pilot.pause()
            self.assertEqual(result, ("AAPL", "apple", "note", "tag"))

    async def test_add_ticker_modal_empty_alias(self):
        """Test the AddTickerModal when alias and note inputs are left blank."""
        # Ensure that when alias and note are not set, they are returned as empty strings
        # rather than being auto-filled with the ticker symbol or default strings.
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            await pilot.app.push_screen(AddTickerModal(), set_result)
            await pilot.pause()
            await pilot.press(
                "a",
                "a",
                "p",
                "l",
            )
            await pilot.click("#add")
            await pilot.pause()
            self.assertEqual(result, ("AAPL", "", "", ""))

    async def test_add_ticker_modal_multi_ticker(self):
        """Test the AddTickerModal with comma-separated tickers (multi-ticker mode).

        When commas are present in the ticker input, the modal should return a list
        of tuples instead of a single tuple, and alias/note should be empty for each."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            await pilot.app.push_screen(AddTickerModal(), set_result)
            await pilot.pause()
            # Type "AAPL,MSFT,GOOG" into the ticker input
            await pilot.press(
                "a", "a", "p", "l",
                "comma",
                "m", "s", "f", "t",
                "comma",
                "g", "o", "o", "g",
            )
            await pilot.click("#add")
            await pilot.pause()
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0], ("AAPL", "", "", ""))
            self.assertEqual(result[1], ("MSFT", "", "", ""))
            self.assertEqual(result[2], ("GOOG", "", "", ""))

    async def test_add_ticker_modal_multi_ticker_with_tags(self):
        """Test that tags are applied to all tickers in multi-ticker mode.

        Tags are NOT per-ticker specific (unlike alias/note), so they should
        propagate to every ticker in the comma-separated list."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            await pilot.app.push_screen(AddTickerModal(), set_result)
            await pilot.pause()
            # Type "V,MA" into the ticker input
            await pilot.press(
                "v",
                "comma",
                "m", "a",
            )
            # Tab to tags input (alias/note are hidden, so one tab goes to tags)
            await pilot.press("tab")
            await pilot.press("t", "e", "c", "h")
            await pilot.click("#add")
            await pilot.pause()
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0], ("V", "", "", "tech"))
            self.assertEqual(result[1], ("MA", "", "", "tech"))

    async def test_edit_ticker_modal(self):
        """Test the EditTickerModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            current_alias = "alias"
            await pilot.app.push_screen(
                EditTickerModal("TICK", current_alias, "note", "tags"), set_result
            )
            await pilot.pause()
            await pilot.press("tab")  # Focus the alias input

            # FIX: Clear and re-type to avoid selection issues.
            for _ in current_alias:
                await pilot.press("backspace")
            await pilot.press("n", "e", "w", "_", "a", "l", "i", "a", "s")

            await pilot.click("#save")
            await pilot.pause()
            self.assertEqual(result, ("TICK", "new_alias", "note", "tags"))

    async def test_create_portfolio_modal(self):
        """Test the CreatePortfolioModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            await pilot.app.push_screen(CreatePortfolioModal(), set_result)
            await pilot.pause()
            await pilot.press("n", "a", "m", "e", "tab", "d", "e", "s", "c")
            await pilot.click("#create")
            await pilot.pause()
            self.assertEqual(result, ("name", "desc"))

    async def test_edit_portfolio_modal(self):
        """Test the EditPortfolioModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            current_name = "old"
            await pilot.app.push_screen(
                EditPortfolioModal(current_name, "old_desc"), set_result
            )
            await pilot.pause()

            # FIX: Clear and re-type to avoid selection issues.
            for _ in current_name:
                await pilot.press("backspace")
            await pilot.press("n", "e", "w", "_", "n", "a", "m", "e")

            await pilot.click("#save")
            await pilot.pause()
            self.assertEqual(result, ("new_name", "old_desc"))

    async def test_position_modal(self):
        """Test the PositionModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            # Test Save
            await pilot.app.push_screen(
                PositionModal("AAPL", {"quantity": 10, "avg_cost": 150.0}), set_result
            )
            await pilot.pause()

            # Clear inputs
            await pilot.click("#quantity-input")
            # Clear existing value (check modal init for value)
            # Init with quantity 10 -> "10" (length 2)
            for _ in range(5):
                await pilot.press("backspace", "delete")
            await pilot.press("2", "0")

            await pilot.click("#cost-input")
            # Init with avg_cost 150.0 -> "150.0" (length 5)
            for _ in range(10):
                await pilot.press("backspace", "delete")
            await pilot.press("1", "5", "5")

            await pilot.click("#save")
            await pilot.pause()

            self.assertEqual(result, (20.0, 155.0))

            # Test Delete
            result = None
            await pilot.app.push_screen(
                PositionModal("AAPL", {"quantity": 10}), set_result
            )
            await pilot.pause()
            await pilot.click("#delete")
            await pilot.pause()
            self.assertEqual(result, (0.0, 0.0))


    async def test_quick_edit_ticker_modal_note_field(self):
        """Switching to note should load the note and allow an empty value."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = QuickEditTickerModal(
                "AAPL",
                "stocks",
                {
                    "alias": "Apple",
                    "note": "Long-term holding",
                    "tags": "tech",
                },
            )
            await pilot.app.push_screen(modal)
            await pilot.pause()

            field_select = modal.query_one("#field-select")
            field_select.value = "note"
            await pilot.pause()

            value_input = modal.query_one("#value-input")
            self.assertEqual(value_input.value, "Long-term holding")
            self.assertEqual(value_input.validators, [])

    async def test_quick_edit_ticker_modal_tags_field(self):
        """Switching to tags should load tags and remove alias validation."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = QuickEditTickerModal(
                "AAPL",
                "stocks",
                {
                    "alias": "Apple",
                    "note": "",
                    "tags": "tech, growth",
                },
            )
            await pilot.app.push_screen(modal)
            await pilot.pause()

            field_select = modal.query_one("#field-select")
            field_select.value = "tags"
            await pilot.pause()

            value_input = modal.query_one("#value-input")
            self.assertEqual(value_input.value, "tech, growth")
            self.assertEqual(value_input.validators, [])

    async def test_quick_edit_ticker_modal_alias_field_restores_validator(self):
        """Returning to alias should restore its value and NotEmpty validator."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = QuickEditTickerModal(
                "AAPL",
                "stocks",
                {
                    "alias": "Apple",
                    "note": "Note",
                    "tags": "tech",
                },
            )
            await pilot.app.push_screen(modal)
            await pilot.pause()

            field_select = modal.query_one("#field-select")
            field_select.value = "note"
            await pilot.pause()
            field_select.value = "alias"
            await pilot.pause()

            value_input = modal.query_one("#value-input")
            self.assertEqual(value_input.value, "Apple")
            self.assertEqual(len(value_input.validators), 1)

    async def test_quick_edit_ticker_modal_cancel(self):
        """Cancel should dismiss the modal with None."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = "unchanged"

            def set_result(value):
                nonlocal result
                result = value

            await pilot.app.push_screen(
                QuickEditTickerModal(
                    "AAPL",
                    "stocks",
                    {"alias": "Apple"},
                ),
                set_result,
            )
            await pilot.pause()

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertIsNone(result)

    async def test_quick_edit_ticker_modal_rejects_empty_alias(self):
        """Whitespace-only aliases should not dismiss the modal."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = QuickEditTickerModal(
                "AAPL",
                "stocks",
                {"alias": "Apple"},
            )
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            value_input = modal.query_one("#value-input")
            value_input.value = "   "

            await pilot.click("#save")
            await pilot.pause()

            self.assertIsNone(result)
            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_quick_edit_ticker_modal_formats_tags(self):
        """Saved tags should be parsed, normalized, and deduplicated."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = QuickEditTickerModal(
                "AAPL",
                "stocks",
                {
                    "alias": "Apple",
                    "tags": "old",
                },
            )
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            field_select = modal.query_one("#field-select")
            field_select.value = "tags"
            await pilot.pause()

            value_input = modal.query_one("#value-input")
            value_input.value = "Tech; growth, TECH"

            await pilot.click("#save")
            await pilot.pause()

            self.assertEqual(result, ("tags", "tech, growth"))

    async def test_quick_edit_ticker_modal(self):
        """Test the QuickEditTickerModal."""
        app = ModalsTestApp()
        async with app.run_test() as pilot:
            result = None

            def set_result(r):
                nonlocal result
                result = r

            # Test Edit Alias (Default)
            ticker_data = {"alias": "OldAlias", "note": "Note", "tags": "tag1"}
            await pilot.app.push_screen(
                QuickEditTickerModal("AAPL", "stocks", ticker_data), set_result
            )
            await pilot.pause()

            # Should be focused on value input of alias
            # Clear and type new alias
            await pilot.click("#value-input")
            # 'OldAlias' length is 8
            for _ in range(15):
                await pilot.press("backspace", "delete")
            await pilot.press("N", "e", "w", "A", "l", "i", "a", "s")

            await pilot.click("#save")
            await pilot.pause()

            self.assertEqual(result, ("alias", "NewAlias"))
