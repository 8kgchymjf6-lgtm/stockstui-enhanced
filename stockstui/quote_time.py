"""Keep provider quote times distinct from fetch times and intraday bar starts."""
from datetime import datetime, timezone
import math


def parse_quote_time(value) -> datetime | None:
    """Accept Unix seconds or an ISO/datetime value with an explicit timezone."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            if not math.isfinite(value) or value <= 0:
                return None
            stamp = datetime.fromtimestamp(value, timezone.utc)
        elif isinstance(value, datetime):
            stamp = value
        elif isinstance(value, str):
            stamp = datetime.fromisoformat(value)
        else:
            return None
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def quote_time_fields(value, kind: str) -> dict:
    stamp = parse_quote_time(value)
    return {
        "_quote_at": stamp.isoformat() if stamp else None,
        "_quote_time_kind": kind if stamp else None,
    }


def replace_quote_time(target: dict, update: dict) -> None:
    """A new price must not inherit the timestamp of the previous price."""
    stamp = parse_quote_time(update.get("_quote_at"))
    kind = update.get("_quote_time_kind")
    target.update(quote_time_fields(stamp, kind) if kind in ("quote", "bar_start")
                  else quote_time_fields(None, "quote"))


def format_quote_time(row: dict) -> str:
    stamp = parse_quote_time(row.get("_quote_at"))
    kind = row.get("_quote_time_kind")
    if stamp is None or kind not in ("quote", "bar_start"):
        return "quote time unknown"
    text = stamp.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"1m bar starts {text}" if kind == "bar_start" else f"quote {text}"
