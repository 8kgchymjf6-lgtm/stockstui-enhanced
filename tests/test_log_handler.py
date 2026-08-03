import unittest
import logging
from unittest.mock import MagicMock

from stockstui.log_handler import TextualHandler


class TestLogHandler(unittest.TestCase):
    """Unit tests for the Textual log handler."""

    def test_log_emit_sends_notification(self):
        """Test that emitting log records calls the app's notify method."""
        mock_app = MagicMock()
        mock_app.notify = MagicMock()
        mock_app.config = MagicMock()
        mock_app.config.get_setting = MagicMock(return_value=False)

        handler = TextualHandler(app=mock_app)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Create a logger and add our handler
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        # Test different log levels
        logger.info("Informational message.")
        mock_app.call_from_thread.assert_called_with(
            mock_app.notify,
            "Informational message.",
            title="Info",
            severity="information",
            timeout=8,
        )

        logger.warning("A warning message.")
        mock_app.call_from_thread.assert_called_with(
            mock_app.notify,
            "A warning message.",
            title="Warning",
            severity="warning",
            timeout=8,
        )

        logger.error("An error message.")
        mock_app.call_from_thread.assert_called_with(
            mock_app.notify,
            "An error message.",
            title="Error",
            severity="error",
            timeout=8,
        )

        # Prevent logs from propagating to the root logger in the test runner
        logger.removeHandler(handler)

    def test_log_emit_suppressed(self):
        """Test that logs are suppressed when config setting is enabled."""
        mock_app = MagicMock()
        mock_app.notify = MagicMock()
        mock_app.config = MagicMock()
        mock_app.config.get_setting = MagicMock(return_value=True)

        handler = TextualHandler(app=mock_app)
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_logger_suppressed")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        # This should not call notify
        logger.info("Should be suppressed.")
        mock_app.call_from_thread.assert_not_called()

        logger.removeHandler(handler)


    def test_runtime_error_from_call_from_thread_is_ignored(self):
        """RuntimeError during shutdown should be handled without propagating."""
        mock_app = MagicMock()
        mock_app.notify = MagicMock()
        mock_app.config = MagicMock()
        mock_app.config.get_setting.return_value = False
        mock_app.call_from_thread.side_effect = RuntimeError("app stopped")

        handler = TextualHandler(app=mock_app)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Late worker message",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        mock_app.call_from_thread.assert_called_once()

    def test_unexpected_emit_error_calls_handle_error(self):
        """Unexpected formatting errors should be delegated to handleError."""
        mock_app = MagicMock()
        mock_app.config = MagicMock()
        mock_app.config.get_setting.return_value = False

        handler = TextualHandler(app=mock_app)
        handler.format = MagicMock(side_effect=ValueError("format failed"))
        handler.handleError = MagicMock()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Broken message",
            args=(),
            exc_info=None,
        )

        handler.emit(record)

        handler.handleError.assert_called_once_with(record)
        mock_app.call_from_thread.assert_not_called()
