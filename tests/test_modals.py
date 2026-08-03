import unittest
from unittest.mock import MagicMock, patch

from textual.app import App
from stockstui.ui.modals import (
    ConfirmDeleteModal,
    AddListModal,
    EditListModal,
    AddTickerModal,
    EditTickerModal,
    CreatePortfolioModal,
    EditPortfolioModal,
    AddFredSeriesModal,
    CompareInfoModal,
    ConfirmAddToAllPortfoliosModal,
    FredSeriesModal,
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


    async def test_confirm_delete_modal_requires_matching_text(self):
        """Delete should remain disabled until the exact item name is entered."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = ConfirmDeleteModal(
                "AAPL",
                "Delete AAPL?",
                require_typing=True,
            )
            await pilot.app.push_screen(modal)
            await pilot.pause()

            delete_button = modal.query_one("#delete")
            confirmation_input = modal.query_one("#confirmation_input")

            self.assertTrue(delete_button.disabled)

            confirmation_input.value = "MSFT"
            await pilot.pause()
            self.assertTrue(delete_button.disabled)

            confirmation_input.value = "AAPL"
            await pilot.pause()
            self.assertFalse(delete_button.disabled)

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_add_list_modal_rejects_empty_name(self):
        """An empty list name should not dismiss the modal."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = AddListModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#add")
            await pilot.pause()

            self.assertIsNone(result)
            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_add_ticker_modal_cancel(self):
        """Cancel should dismiss the ticker modal with None."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = "unchanged"

            def set_result(value):
                nonlocal result
                result = value

            await pilot.app.push_screen(
                AddTickerModal(),
                set_result,
            )
            await pilot.pause()

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertIsNone(result)

    async def test_add_ticker_modal_portfolio_context(self):
        """Portfolio mode should return ticker and tags without alias or note."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = AddTickerModal(context="portfolio")
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            self.assertEqual(len(modal.query("#alias-input")), 0)
            self.assertEqual(len(modal.query("#note-input")), 0)

            modal.query_one("#ticker-input").value = "aapl"
            modal.query_one("#tags-input").value = "Tech; growth"
            await pilot.pause()

            await pilot.click("#add")
            await pilot.pause()

            self.assertEqual(
                result,
                ("AAPL", "", "", "tech, growth"),
            )

    async def test_multi_ticker_fields_reappear_in_single_mode(self):
        """Alias and note fields should reappear when commas are removed."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = AddTickerModal()
            await pilot.app.push_screen(modal)
            await pilot.pause()

            ticker_input = modal.query_one("#ticker-input")
            alias_input = modal.query_one("#alias-input")
            note_input = modal.query_one("#note-input")

            ticker_input.value = "AAPL,MSFT"
            await pilot.pause()

            self.assertFalse(alias_input.display)
            self.assertFalse(note_input.display)

            ticker_input.value = "AAPL"
            await pilot.pause()

            self.assertTrue(alias_input.display)
            self.assertTrue(note_input.display)

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_add_ticker_modal_rejects_empty_ticker(self):
        """An empty ticker should leave the modal open."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = AddTickerModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#add")
            await pilot.pause()

            self.assertIsNone(result)
            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()


    async def test_add_fred_series_modal_adds_series(self):
        """A valid FRED series should be normalized and returned."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = AddFredSeriesModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            modal.query_one("#series-input").value = "gdp"
            modal.query_one("#alias-input").value = "US GDP"

            await pilot.click("#add")
            await pilot.pause()

            self.assertEqual(result, ("GDP", "US GDP", "", ""))

    async def test_add_fred_series_modal_defaults_alias(self):
        """A blank alias should default to the normalized series ID."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = AddFredSeriesModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            modal.query_one("#series-input").value = "unrate"

            await pilot.click("#add")
            await pilot.pause()

            self.assertEqual(result, ("UNRATE", "UNRATE", "", ""))

    async def test_add_fred_series_modal_cancel_and_invalid_input(self):
        """Empty input should be rejected, while cancel should return None."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = "unchanged"

            def set_result(value):
                nonlocal result
                result = value

            modal = AddFredSeriesModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#add")
            await pilot.pause()

            self.assertEqual(result, "unchanged")
            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertIsNone(result)

    async def test_compare_info_modal_submit_and_cancel(self):
        """Compare modal should support both submit and cancel."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = CompareInfoModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            modal.query_one("#ticker-input").value = "aapl"
            await pilot.click("#run")
            await pilot.pause()

            self.assertEqual(result, "AAPL")

            result = "unchanged"
            modal = CompareInfoModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertIsNone(result)

    async def test_compare_info_modal_enter_submits(self):
        """Submitting the input with Enter should use the same validation path."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = CompareInfoModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            ticker_input = modal.query_one("#ticker-input")
            ticker_input.value = "msft"
            ticker_input.focus()

            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(result, "MSFT")

    async def test_confirm_add_to_all_portfolios_modal(self):
        """Confirmation and cancellation should return True and False."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            results = []

            await pilot.app.push_screen(
                ConfirmAddToAllPortfoliosModal("AAPL", 3),
                results.append,
            )
            await pilot.pause()

            await pilot.click("#confirm")
            await pilot.pause()

            self.assertEqual(results[-1], True)

            await pilot.app.push_screen(
                ConfirmAddToAllPortfoliosModal("MSFT", 2),
                results.append,
            )
            await pilot.pause()

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertEqual(results[-1], False)

    async def test_fred_series_modal_submit_and_cancel(self):
        """Valid FRED input should submit uppercase, while cancel returns None."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = FredSeriesModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            modal.query_one("#fred-series-input").value = "cpi"
            await pilot.click("#submit")
            await pilot.pause()

            self.assertEqual(result, "CPI")

            result = "unchanged"
            modal = FredSeriesModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertIsNone(result)

    async def test_fred_series_modal_enter_presses_submit(self):
        """Enter in the FRED input should activate the submit button."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = FredSeriesModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            fred_input = modal.query_one("#fred-series-input")
            fred_input.value = "gdp"
            fred_input.focus()

            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(result, "GDP")


    def test_ticker_input_change_handles_missing_fields(self):
        """Missing alias/note widgets should not crash ticker-mode changes."""
        modal = AddTickerModal()
        modal._multi_ticker_mode = False

        event = MagicMock()
        event.value = "AAPL,MSFT"

        with patch.object(
            modal,
            "query_one",
            side_effect=RuntimeError("widgets unavailable"),
        ):
            modal._on_ticker_input_changed(event)

        self.assertTrue(modal._multi_ticker_mode)

    async def test_compare_info_modal_rejects_empty_input(self):
        """Empty comparison input should leave the modal open."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = None

            def set_result(value):
                nonlocal result
                result = value

            modal = CompareInfoModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#run")
            await pilot.pause()

            self.assertIsNone(result)
            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_compare_info_modal_ignores_unknown_button(self):
        """Buttons other than run and cancel should not dismiss the modal."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = CompareInfoModal()
            await pilot.app.push_screen(modal)
            await pilot.pause()

            unknown_button = MagicMock()
            unknown_button.id = "other"
            modal.on_button_pressed(MagicMock(button=unknown_button))

            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_portfolio_modal_cancel_and_invalid_name(self):
        """Empty names should be rejected, and cancel should return None."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            result = "unchanged"

            def set_result(value):
                nonlocal result
                result = value

            modal = CreatePortfolioModal()
            await pilot.app.push_screen(modal, set_result)
            await pilot.pause()

            await pilot.click("#create")
            await pilot.pause()

            self.assertEqual(result, "unchanged")
            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

            self.assertIsNone(result)

    async def test_fred_series_modal_rejects_invalid_input(self):
        """Invalid FRED input should notify the user and remain open."""
        app = ModalsTestApp()
        app.notify = MagicMock()

        async with app.run_test() as pilot:
            modal = FredSeriesModal()
            await pilot.app.push_screen(modal)
            await pilot.pause()

            await pilot.click("#submit")
            await pilot.pause()

            self.assertIs(pilot.app.screen, modal)
            app.notify.assert_called()

            await pilot.click("#cancel")
            await pilot.pause()

    async def test_fred_series_modal_ignores_unknown_button(self):
        """Unknown button events should not dismiss the FRED modal."""
        app = ModalsTestApp()

        async with app.run_test() as pilot:
            modal = FredSeriesModal()
            await pilot.app.push_screen(modal)
            await pilot.pause()

            unknown_button = MagicMock()
            unknown_button.id = "other"
            modal.on_button_pressed(MagicMock(button=unknown_button))

            self.assertIs(pilot.app.screen, modal)

            await pilot.click("#cancel")
            await pilot.pause()

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
