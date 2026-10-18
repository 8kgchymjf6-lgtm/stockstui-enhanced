"""Handle configuration failures at UI action and modal callback boundaries."""

from functools import wraps
from inspect import iscoroutinefunction
import logging
from stockstui.config_manager import ConfigSaveError
from textual.widgets import Switch, Select, ContentSwitcher
from textual.dom import NoMatches


def config_errors(function=None, *, app=None):
    def decorate(callback):
        def report(args, error):
            owner = app if app is not None else getattr(args[0], "app", args[0])
            logging.error("Configuration change not saved: %s", error)
            owner.notify(
                str(error), title="Change not saved", severity="error", timeout=12
            )
            # Recreate controls from committed settings, rather than showing a failed change.
            if hasattr(owner, "_rebuild_app"):
                owner._refresh_hidden_tabs()
                owner._rebuild_visible_columns()
                theme = owner.config.get_setting("theme")
                if theme in owner._available_theme_names:
                    owner.theme = theme
                    owner._update_theme_variables(theme)
                sub_view = None
                try:
                    sub_view = (
                        owner.query_one("#config-container")
                        .query_one(ContentSwitcher)
                        .current
                    )
                except NoMatches:
                    pass
                with owner.prevent(Switch.Changed, Select.Changed):
                    for widget_id, key in (
                        ("auto-refresh-switch", "auto_refresh"),
                        ("enable-pre-post-market-switch", "enable_pre_post_market"),
                        ("suppress-tui-logs-switch", "suppress_tui_logs"),
                    ):
                        try:
                            owner.query_one(
                                "#" + widget_id, Switch
                            ).value = owner.config.get_setting(key, False)
                        except NoMatches:
                            pass
                    for widget_id, key in (
                        ("theme-select", "theme"),
                        ("market-calendar-select", "market_calendar"),
                    ):
                        try:
                            owner.query_one(
                                "#" + widget_id, Select
                            ).value = owner.config.get_setting(key)
                        except NoMatches:
                            pass
                owner.call_later(
                    owner._rebuild_app,
                    new_active_category=owner.get_active_category(),
                    config_sub_view=sub_view,
                )

        if iscoroutinefunction(callback):

            @wraps(callback)
            async def async_action(*args, **kwargs):
                try:
                    return await callback(*args, **kwargs)
                except ConfigSaveError as error:
                    report(args, error)

            return async_action

        @wraps(callback)
        def action(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except ConfigSaveError as error:
                report(args, error)

        return action

    return decorate(function) if function is not None else decorate
