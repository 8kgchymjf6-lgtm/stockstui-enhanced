"""Validate configuration shapes without discarding the original files.

Repairs here are in-memory only. The manager protects any structurally damaged
file from saving, and retains a byte-for-byte recovery copy when possible.
"""

from copy import deepcopy
from stockstui.utils import RESERVED_LIST_NAMES
import math
from textual.color import Color, ColorParseError

MARKET_CALENDAR_CHOICES = [
    ("NYSE (US)", "NYSE"),
    ("TSX (Toronto)", "TSX"),
    ("BMF (Brazil)", "BMF"),
    ("LSE (London)", "LSE"),
    ("EUREX (Europe)", "EUREX"),
    ("SIX (Swiss)", "SIX"),
    ("OSE (Oslo)", "OSE"),
    ("JPX (Japan)", "JPX"),
    ("HKEX (Hong Kong)", "HKEX"),
    ("SSE (Shanghai)", "SSE"),
    ("ASX (Australia)", "ASX"),
    ("BSE (Bombay)", "BSE"),
    ("TASE (Tel Aviv)", "TASE"),
    ("CME (Chicago)", "CME"),
    ("CME Equity Futures", "CME_Equity"),
    ("CME Bond Futures", "CME_Bond"),
    ("CME Agriculture Futures", "CME_Agriculture"),
    ("CME Crypto Futures", "CME_Crypto"),
    ("CFE (CBOE Futures)", "CFE"),
    ("ICE Futures", "ICE"),
    ("SIFMA US Bonds", "SIFMAUS"),
    ("SIFMA UK Bonds", "SIFMAUK"),
    ("SIFMA JP Bonds", "SIFMAJP"),
]


def _valid_interval(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 1
    except OverflowError:
        return False


def validate_config(filename: str, value, defaults: dict) -> tuple[dict, list[str]]:
    issues = []
    if not isinstance(value, dict):
        issues.append("top level must be an object")
        value = {} if filename == "lists.json" else deepcopy(defaults)
    result = deepcopy(value)

    def replace_invalid(container, key, valid, fallback, path=""):
        if key in container and not valid(container[key]):
            issues.append(path + key)
            container[key] = deepcopy(fallback)

    def strings(value):
        return isinstance(value, list) and all(
            isinstance(item, str) and item.strip() for item in value
        )

    def clean_strings(value, path):
        if not isinstance(value, list):
            issues.append(path)
            return []
        result = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or item in result:
                issues.append(path)
            else:
                result.append(item)
        return result

    if filename == "settings.json":
        for key, fallback in {
            "theme": "gruvbox_soft_dark",
            "default_tab_category": "all",
        }.items():
            replace_invalid(
                result,
                key,
                lambda item: isinstance(item, str) and bool(item.strip()),
                defaults.get(key, fallback),
            )
        for key in ("auto_refresh", "enable_pre_post_market", "suppress_tui_logs"):
            replace_invalid(
                result,
                key,
                lambda item: isinstance(item, bool),
                defaults.get(key, False),
            )
        replace_invalid(
            result,
            "refresh_interval",
            _valid_interval,
            300.0,
        )
        replace_invalid(
            result,
            "market_calendar",
            lambda item: (
                item in {name for _, name in MARKET_CALENDAR_CHOICES}
                if isinstance(item, str)
                else False
            ),
            "NYSE",
        )
        replace_invalid(result, "hidden_tabs", strings, defaults.get("hidden_tabs", []))
        if "column_settings" in result:
            columns = result["column_settings"]
            if not isinstance(columns, list):
                issues.append("column_settings")
                result["column_settings"] = deepcopy(
                    defaults.get("column_settings", [])
                )
            else:
                valid = []
                seen = set()
                for column in columns:
                    if (
                        not isinstance(column, dict)
                        or not isinstance(column.get("key"), str)
                        or not column["key"].strip()
                        or not isinstance(column.get("visible", True), bool)
                        or column["key"] in seen
                    ):
                        issues.append("column_settings entry")
                        continue
                    seen.add(column["key"])
                    valid.append({"visible": True, **column})
                result["column_settings"] = valid
        replace_invalid(
            result,
            "fred_settings",
            lambda item: isinstance(item, dict),
            defaults.get("fred_settings", {}),
        )
        if isinstance(result.get("fred_settings"), dict):
            fred = result["fred_settings"]
            replace_invalid(
                fred,
                "api_key",
                lambda item: isinstance(item, str),
                "",
                "fred_settings.",
            )
            if "series_list" in fred:
                fred["series_list"] = clean_strings(
                    fred["series_list"], "fred_settings.series_list"
                )
            for key in ("series_aliases", "series_descriptions"):
                replace_invalid(
                    fred,
                    key,
                    lambda item: (
                        isinstance(item, dict)
                        and all(isinstance(v, str) for v in item.values())
                    ),
                    {},
                    "fred_settings.",
                )
    elif filename == "lists.json":
        result = {}
        for name, items in value.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or name in RESERVED_LIST_NAMES
                or not name.isprintable()
                or not isinstance(items, list)
            ):
                issues.append("invalid watchlist")
                continue
            result[name] = []
            seen = set()
            for item in items:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("ticker"), str)
                    or not item["ticker"].strip()
                ):
                    issues.append("invalid ticker entry")
                    continue
                ticker = item["ticker"].strip().upper()
                if ticker in seen:
                    issues.append("duplicate ticker")
                    continue
                seen.add(ticker)
                row = deepcopy(item)
                row["ticker"] = ticker
                for key in ("alias", "note", "tags"):
                    if row.get(key) is None:
                        if key in row:
                            row[key] = ""
                    elif not isinstance(row[key], str):
                        issues.append("invalid ticker " + key)
                        row[key] = ""
                result[name].append(row)
    elif filename == "portfolios.json":
        replace_invalid(result, "portfolios", lambda item: isinstance(item, dict), {})
        replace_invalid(result, "settings", lambda item: isinstance(item, dict), {})
        portfolios = result.setdefault("portfolios", {})
        for key, data in list(portfolios.items()):
            if not isinstance(data, dict):
                issues.append("invalid portfolio")
                del portfolios[key]
                continue
            for field in ("name", "description", "created", "modified"):
                replace_invalid(data, field, lambda item: isinstance(item, str), "")
            if "tickers" in data:
                data["tickers"] = clean_strings(data["tickers"], "portfolio tickers")
            else:
                data["tickers"] = []
        settings = result.setdefault("settings", {})
        replace_invalid(
            settings, "default_portfolio", lambda item: isinstance(item, str), "default"
        )
        for key in ("migration_completed", "auto_add_to_default"):
            replace_invalid(settings, key, lambda item: isinstance(item, bool), False)
        # PortfolioManager must not try to save a new default into a protected file.
        if issues and "default" not in portfolios:
            portfolios["default"] = {
                "name": "Default Portfolio",
                "description": "",
                "tickers": [],
                "created": "",
                "modified": "",
            }
    elif filename == "themes.json":
        required = {
            "blue",
            "cyan",
            "orange",
            "green",
            "yellow",
            "red",
            "bg3",
            "bg2",
            "bg1",
            "bg0",
            "fg0",
            "fg1",
            "fg2",
            "fg3",
        }
        for name, theme in list(result.items()):
            if not isinstance(theme, dict) or not isinstance(
                theme.get("palette"), dict
            ):
                issues.append("invalid theme")
                del result[name]
                continue
            replace_invalid(theme, "dark", lambda item: isinstance(item, bool), False)
            palette = theme["palette"]
            palette_valid = True
            for key in required & palette.keys():
                color = palette[key]
                try:
                    if not isinstance(color, str):
                        raise ValueError("color must be text")
                    Color.parse(color)
                except (ColorParseError, ValueError):
                    palette_valid = False
                    break
            if not palette_valid or not required.issubset(palette):
                issues.append("invalid theme palette")
                del result[name]
        if issues:
            # Keep a known fallback, retaining all valid custom themes.
            for name, theme in defaults.items():
                result.setdefault(name, deepcopy(theme))
        elif not result:
            result = deepcopy(defaults)
    return result, list(dict.fromkeys(issues))
