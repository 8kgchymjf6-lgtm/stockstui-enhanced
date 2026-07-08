from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label
from textual.containers import Vertical, Horizontal
from textual.app import ComposeResult
from textual import on

# FIX: Changed 'from common import ...' to an absolute import from the package root.
from stockstui.common import NotEmpty
from stockstui.utils import slugify, parse_tags, format_tags


class ConfirmDeleteModal(ModalScreen[bool]):
    """A modal dialog for confirming a deletion, optionally requiring text input for confirmation."""

    def __init__(
        self, item_name: str, prompt: str, require_typing: bool = False
    ) -> None:
        """
        Args:
            item_name: The name of the item being deleted (used for confirmation typing).
            prompt: The message displayed to the user.
            require_typing: If True, the user must type `item_name` to enable the delete button.
        """
        super().__init__()
        self.item_name = item_name
        self.prompt_text = prompt
        self.require_typing = require_typing

    def compose(self) -> ComposeResult:
        """Creates the layout for the confirmation modal."""
        with Vertical(id="dialog"):
            yield Label(self.prompt_text)
            if self.require_typing:
                yield Input(placeholder=self.item_name, id="confirmation_input")
            with Horizontal(id="dialog-buttons"):
                yield Button(
                    "Delete", variant="error", id="delete", disabled=self.require_typing
                )
                yield Button("Cancel", id="cancel")

    @on(Input.Changed, "#confirmation_input")
    def on_input_changed(self, event: Input.Changed) -> None:
        """Enables/disables the delete button based on confirmation input."""
        self.query_one("#delete", Button).disabled = event.value != self.item_name

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismisses the modal, returning True if delete was pressed, False otherwise."""
        self.dismiss(event.button.id == "delete")


class ListModal(ModalScreen[str | None]):
    """A shared base modal dialog for list operations (adding, renaming, etc.)."""

    def __init__(self, value: str = "", placeholder: str = "List Name", is_edit: bool = False) -> None:
        super().__init__()
        self.value = value
        self.placeholder = placeholder
        self.is_edit = is_edit

    def compose(self) -> ComposeResult:
        """Creates the layout for the list modal, sharing input structure and buttons."""
        label_text = "Enter new list name:" if self.is_edit else "Enter new list name (e.g., 'crypto'):"
        button_label = "Save" if self.is_edit else "Add"
        button_id = "save" if self.is_edit else "add"
        with Vertical(id="dialog"):
            yield Label(label_text)
            yield Input(
                value=self.value,
                placeholder=self.placeholder,
                id="list-name-input",
                validators=[NotEmpty()]
            )
            with Horizontal(id="dialog-buttons"):
                yield Button(button_label, variant="primary", id=button_id)
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focuses the input field immediately on mount to ensure a seamless, keyboard-friendly workflow, letting the user start typing without needing to manually click or tab to focus."""
        self.query_one(Input).focus()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses, dismissing the modal with the slugified list name or None."""
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        input_widget = self.query_one(Input)
        target_id = "save" if self.is_edit else "add"
        if (
            event.button.id == target_id
            and input_widget.validate(input_widget.value).is_valid
        ):
            self.dismiss(slugify(input_widget.value))


class EditListModal(ListModal):
    """A modal dialog for editing the name of an existing list."""

    def __init__(self, current_name: str) -> None:
        super().__init__(value=current_name, is_edit=True)


class AddListModal(ListModal):
    """A modal dialog for adding a new list."""

    def __init__(self) -> None:
        super().__init__(is_edit=False)



class TickerModal(ModalScreen[tuple[str, str, str, str] | list[tuple[str, str, str, str]] | None]):
    """A shared base modal dialog for ticker operations (adding, editing, etc.).

    Supports single-ticker mode (edit, or add without commas) and multi-ticker mode
    (add with comma-separated tickers). In multi-ticker mode, alias and note fields
    are hidden because they are per-ticker specific. Tags remain visible since they
    can be applied to all tickers at once.
    """

    def __init__(
        self,
        ticker: str = "",
        alias: str = "",
        note: str = "",
        tags: str = "",
        is_edit: bool = False,
        context: str = "list"
    ) -> None:
        super().__init__()
        self.ticker = ticker
        self.alias = alias
        self.note = note
        self.tags = tags
        self.is_edit = is_edit
        self.context = context
        # Tracks whether multi-ticker mode is active (commas detected in ticker input)
        self._multi_ticker_mode = False

    def compose(self) -> ComposeResult:
        """Creates the layout for the ticker modal, sharing inputs and placeholder hints."""
        with Vertical(id="dialog"):
            if self.is_edit:
                yield Label("Edit ticker details:")
            else:
                yield Label("Add stock to portfolio:" if self.context == "portfolio" else "Enter new ticker details:")

            yield Input(
                value=self.ticker,
                placeholder="Ticker(s) (e.g., AAPL or AAPL,MSFT,GOOG)" if not self.is_edit else "Ticker (e.g., AAPL)",
                id="ticker-input",
                validators=[NotEmpty()],
            )

            if self.context != "portfolio":
                yield Input(
                    value=self.alias,
                    placeholder="Alias (optional, e.g., Apple)",
                    id="alias-input",
                )
                yield Input(
                    value=self.note,
                    placeholder="Note (optional, e.g., Personal reminder)",
                    id="note-input",
                )

            yield Input(
                value=self.tags,
                placeholder="Tags (optional, e.g., tech growth)",
                id="tags-input",
            )

            button_label = "Save" if self.is_edit else "Add"
            button_id = "save" if self.is_edit else "add"
            with Horizontal(id="dialog-buttons"):
                yield Button(button_label, variant="primary", id=button_id)
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focuses the ticker input field immediately on mount to enable a smooth, keyboard-driven experience, letting the user start typing the symbol immediately."""
        self.query_one("#ticker-input").focus()

    @on(Input.Changed, "#ticker-input")
    def _on_ticker_input_changed(self, event: Input.Changed) -> None:
        """Dynamically hides alias and note fields when commas are detected in the ticker
        input, since those fields are per-ticker specific and don't apply in bulk-add mode.
        Only applies in add mode (not edit) and non-portfolio context."""
        if self.is_edit or self.context == "portfolio":
            return

        has_comma = "," in event.value
        if has_comma != self._multi_ticker_mode:
            self._multi_ticker_mode = has_comma
            try:
                alias_input = self.query_one("#alias-input", Input)
                note_input = self.query_one("#note-input", Input)
                if has_comma:
                    # Clear and hide alias/note since they don't apply to bulk adds
                    alias_input.value = ""
                    note_input.value = ""
                    alias_input.display = False
                    note_input.display = False
                else:
                    alias_input.display = True
                    note_input.display = True
            except Exception:
                pass

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses, dismissing the modal with formatted ticker details or None.

        In multi-ticker mode (commas in ticker input), returns a list of (ticker, '', '', tags)
        tuples. In single-ticker mode, returns a single (ticker, alias, note, tags) tuple."""
        if event.button.id == "cancel":
            self.dismiss(None)
            return

        ticker_input = self.query_one("#ticker-input", Input)
        if (
            event.button.id in ("add", "save")
            and ticker_input.validate(ticker_input.value).is_valid
        ):
            raw_value = ticker_input.value.strip()
            tags_input = self.query_one("#tags-input", Input).value.strip()
            tags = format_tags(parse_tags(tags_input))

            if self.context == "portfolio":
                # For portfolio context, return ticker with tags
                self.dismiss((raw_value.upper(), "", "", tags))
            elif self._multi_ticker_mode:
                # Multi-ticker mode: parse comma-separated tickers, skip empties
                tickers = [
                    t.strip().upper()
                    for t in raw_value.split(",")
                    if t.strip()
                ]
                # Return list of tuples with empty alias/note for each ticker
                result = [(t, "", "", tags) for t in tickers]
                self.dismiss(result)
            else:
                # Single-ticker mode: include alias and note
                # Do NOT default alias to the ticker symbol so the app
                # can fall back to the fetched description when alias is not set.
                alias = self.query_one("#alias-input", Input).value.strip()
                note = self.query_one("#note-input", Input).value.strip()
                self.dismiss((ticker_input.value.strip().upper(), alias, note, tags))


class AddTickerModal(TickerModal):
    """A modal dialog for adding a new ticker to a list or portfolio."""

    def __init__(self, context: str = "list") -> None:
        super().__init__(is_edit=False, context=context)


class AddFredSeriesModal(ModalScreen[tuple[str, str, str, str] | None]):
    """A modal dialog for adding a new FRED series."""

    def compose(self) -> ComposeResult:
        """Creates the layout for the add FRED series modal."""
        with Vertical(id="dialog"):
            yield Label("Enter new FRED series details:")
            yield Input(
                placeholder="Series ID (e.g., GDP)",
                id="series-input",
                validators=[NotEmpty()],
            )
            yield Input(placeholder="Alias (optional, e.g., US GDP)", id="alias-input")
            with Horizontal(id="dialog-buttons"):
                yield Button("Add", variant="primary", id="add")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focuses the series input field immediately on mount to enable a smooth, keyboard-driven experience, letting the user start typing the FRED Series ID immediately."""
        self.query_one("#series-input").focus()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses, dismissing the modal with series details or None."""
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        series_input = self.query_one("#series-input", Input)
        if (
            event.button.id == "add"
            and series_input.validate(series_input.value).is_valid
        ):
            series_id = series_input.value.strip().upper()
            alias = self.query_one("#alias-input", Input).value.strip() or series_id
            # Maintain tuple format (ticker, alias, note, tags) for compatibility
            self.dismiss((series_id, alias, "", ""))


class EditTickerModal(TickerModal):
    """A modal dialog for editing an existing ticker's details."""

    def __init__(self, ticker: str, alias: str, note: str, tags: str = "") -> None:
        super().__init__(
            ticker=ticker,
            alias=alias,
            note=note,
            tags=tags,
            is_edit=True,
            context="list"
        )



class CompareInfoModal(ModalScreen[str | None]):
    """A modal dialog to get a ticker symbol for the info comparison debug test."""

    def compose(self) -> ComposeResult:
        """Creates the layout for the compare info modal."""
        with Vertical(id="dialog"):
            yield Label("Enter ticker symbol to compare info:")
            yield Input(
                placeholder="e.g., AAPL", id="ticker-input", validators=[NotEmpty()]
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Run Test", variant="primary", id="run")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focuses the input field immediately on mount to enable a smooth, keyboard-driven experience, letting the user start typing the symbol immediately."""
        self.query_one(Input).focus()

    def _submit(self) -> None:
        """Validates the input and dismisses the modal with the uppercase ticker symbol."""
        ticker_input = self.query_one("#ticker-input", Input)
        if ticker_input.validate(ticker_input.value).is_valid:
            self.dismiss(ticker_input.value.strip().upper())

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses (Run Test or Cancel)."""
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "run":
            self._submit()

    @on(Input.Submitted, "#ticker-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handles input submission (Enter key), triggering the submit logic."""
        self._submit()


class PortfolioModal(ModalScreen[tuple[str, str] | None]):
    """A shared base modal dialog for portfolio operations (creating, editing)."""

    def __init__(self, name: str = "", description: str = "", is_edit: bool = False) -> None:
        super().__init__()
        self.portfolio_name = name
        self.portfolio_description = description
        self.is_edit = is_edit

    def compose(self) -> ComposeResult:
        """Creates the layout for the portfolio modal, sharing input structure and buttons."""
        title_text = "Edit Portfolio" if self.is_edit else "Create New Portfolio"
        button_label = "Save" if self.is_edit else "Create"
        button_id = "save" if self.is_edit else "create"
        with Vertical(id="dialog"):
            yield Label(title_text)
            yield Input(
                value=self.portfolio_name,
                placeholder="Portfolio Name",
                id="name-input",
                validators=[NotEmpty()],
            )
            yield Input(
                value=self.portfolio_description,
                placeholder="Description (optional)",
                id="description-input"
            )
            with Horizontal(id="dialog-buttons"):
                yield Button(button_label, variant="primary", id=button_id)
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focuses the name input field immediately on mount to ensure a seamless, keyboard-friendly workflow, letting the user start typing the portfolio name without needing to click."""
        self.query_one("#name-input").focus()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses, dismissing the modal with updated details or None."""
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        name_input = self.query_one("#name-input", Input)
        target_id = "save" if self.is_edit else "create"
        if (
            event.button.id == target_id
            and name_input.validate(name_input.value).is_valid
        ):
            name = name_input.value.strip()
            description = self.query_one("#description-input", Input).value.strip()
            self.dismiss((name, description))


class CreatePortfolioModal(PortfolioModal):
    """A modal dialog for creating a new portfolio."""

    def __init__(self) -> None:
        super().__init__(is_edit=False)


class EditPortfolioModal(PortfolioModal):
    """A modal dialog for editing an existing portfolio."""

    def __init__(self, current_name: str, current_description: str) -> None:
        super().__init__(name=current_name, description=current_description, is_edit=True)



class ConfirmAddToAllPortfoliosModal(ModalScreen[bool]):
    """A modal dialog for confirming when adding a stock to all portfolios."""

    def __init__(self, ticker: str, portfolio_count: int) -> None:
        """
        Args:
            ticker: The ticker being added
            portfolio_count: Number of portfolios it will be added to
        """
        super().__init__()
        self.ticker = ticker
        self.portfolio_count = portfolio_count

    def compose(self) -> ComposeResult:
        """Creates the layout for the confirmation modal."""
        with Vertical(id="dialog"):
            yield Label(f"Add {self.ticker} to all {self.portfolio_count} portfolios?")
            yield Label(
                "This will add the stock to every portfolio you have created.",
                classes="dim",
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Add to All", variant="primary", id="confirm")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismisses the modal, returning True if confirmed, False otherwise."""
        self.dismiss(event.button.id == "confirm")


class FredSeriesModal(ModalScreen[str | None]):
    """A modal dialog to get a FRED series ID for the FRED API debug test."""

    def compose(self) -> ComposeResult:
        """Creates the layout for the FRED series modal."""
        with Vertical(id="dialog"):
            yield Label("Enter FRED series ID:")
            yield Input(
                placeholder="e.g., GDP, CPIAUCSL, UNRATE",
                id="fred-series-input",
                validators=[NotEmpty()],
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Submit", variant="primary", id="submit")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focuses the FRED series input field immediately on mount to enable a smooth, keyboard-driven experience, letting the user start typing the FRED Series ID immediately."""
        self.query_one("#fred-series-input", Input).focus()

    @on(Input.Submitted, "#fred-series-input")
    def on_input_submitted(self) -> None:
        """Handle Enter key press in the input field."""
        self.query_one("#submit", Button).press()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "submit":
            input_widget = self.query_one("#fred-series-input", Input)
            if input_widget.is_valid:
                self.dismiss(input_widget.value.strip().upper())
            else:
                # Show validation errors
                for error in input_widget.errors:
                    self.app.notify(str(error), severity="error")
