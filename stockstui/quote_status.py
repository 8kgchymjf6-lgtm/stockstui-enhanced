"""Pure presentation of fetch age, quote age and cache warnings."""

from datetime import datetime
from typing import Any, Mapping, Sequence
from stockstui.quote_time import parse_quote_time, format_quote_time

QuoteRows = Sequence[Mapping[str, Any]]


def status_display(text: str, data: QuoteRows | None = None) -> tuple[str, str]:
    details = []
    fetch_times = []
    for row in data or []:
        fetched = parse_quote_time(row.get("_fetched_at"))
        if fetched:
            fetch_times.append(fetched)
        fetched_text = (
            fetched.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            if fetched
            else "unknown"
        )
        state = "; cached/unverified" if row.get("_stale", True) else ""
        details.append(
            f"{row.get('symbol', '?')}: {format_quote_time(row)}; fetched {fetched_text}{state}"
        )
    # Preserve the original status-bar appearance; details stay in the tooltip.
    display_text = text
    if data is not None:
        fetch_text = (
            min(fetch_times).astimezone().strftime("%H:%M:%S")
            if fetch_times
            else "Unknown"
        )
        display_text = f"Last Refresh: {fetch_text}"
    return display_text, text + ("\n" + "\n".join(details) if details else "")


def summarize_quotes(data: QuoteRows) -> str:
    timestamps: list[datetime] = []
    stale: list[str] = []
    for row in data:
        try:
            stamp = datetime.fromisoformat(row.get("_fetched_at", ""))
            if stamp.tzinfo is not None:
                timestamps.append(stamp)
        except (ValueError, TypeError):
            pass
        if row.get("_stale", True):
            stale.append(str(row.get("symbol", "?")))
    oldest = (
        min(timestamps).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if timestamps
        else "unknown"
    )
    quote_times: dict[str, list[datetime]] = {"quote": [], "bar_start": []}
    unknown = []
    for row in data:
        quote_stamp = parse_quote_time(row.get("_quote_at"))
        kind = row.get("_quote_time_kind")
        if quote_stamp is not None and isinstance(kind, str) and kind in quote_times:
            quote_times[kind].append(quote_stamp)
        else:
            unknown.append(str(row.get("symbol", "?")))
    parts = []
    for kind, title in (
        ("quote", "Oldest quote"),
        ("bar_start", "Oldest 1m bar start"),
    ):
        if quote_times[kind]:
            parts.append(
                f"{title}: {min(quote_times[kind]).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
    if unknown:
        parts.append(f"Quote time unknown: {len(unknown)}")
    parts.append(f"Oldest known fetch: {oldest}")
    text = "; ".join(parts)
    if stale:
        warning = "cached/unverified: " + ", ".join(stale[:3])
        if len(stale) > 3:
            warning += f" (+{len(stale) - 3})"
        text = warning + "; " + text
    return text
