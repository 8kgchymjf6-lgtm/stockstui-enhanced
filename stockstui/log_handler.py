import logging
import threading
from typing import Any
from textual.app import App


class TextualHandler(logging.Handler):
    """
    A custom logging handler that forwards records to a Textual app's notification system.
    This allows any module in the application to send user-facing notifications
    using the standard logging library.
    """

    def __init__(self, app: App):
        """
        Initializes the handler.

        Args:
            app: The Textual App instance to which notifications will be sent.
        """
        super().__init__()
        self.app = app

    def emit(self, record: logging.LogRecord):
        """
        Processes a log record and displays it as a notification in the Textual app.
        This method is thread-safe.
        """
        # Check if TUI logs are suppressed in config
        app: Any = self.app
        if app.config.get_setting("suppress_tui_logs", False):
            return

        try:
            # Format the message using the handler's formatter
            message = self.format(record)

            # Map logging levels to notification severities
            severity = "information"
            if record.levelno >= logging.ERROR:
                severity = "error"
            elif record.levelno >= logging.WARNING:
                severity = "warning"

            # Textual rejects call_from_thread on its own event-loop thread.
            try:
                options = dict(title=record.levelname.capitalize(), severity=severity, timeout=8)
                if threading.get_ident() == app._thread_id:
                    app.notify(message, **options)
                else:
                    self.app.call_from_thread(self.app.notify, message, **options)
            except RuntimeError:
                # This can happen if a worker thread tries to log a message
                # after the app has already shut down. It's safe to ignore.
                # Logging here would recursively call this same handler.
                return
        except Exception:
            self.handleError(record)
