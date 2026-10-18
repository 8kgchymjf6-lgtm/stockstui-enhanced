import yfinance as yf
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
import time
from copy import deepcopy
from threading import RLock
from itertools import count
import pandas as pd
from stockstui.utils import merge_price_data
from stockstui.data_validation import finite_number, normalize_price_row
from stockstui.quote_time import quote_time_fields, replace_quote_time, parse_quote_time


# In-memory cache for storing fetched market data to reduce API calls.
_price_cache: dict[str, dict[str, Any]] = {}
_news_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
_info_cache: dict[str, dict[str, Any]] = {}
_market_calendars: dict[str, Any] = {}

_cache_lock = RLock()
_news_versions: dict[str, object] = {}
_price_versions: dict[str, int] = {}
_info_versions: dict[str, int] = {}
_request_ids = count()


def _begin_price_requests(tickers):
    with _cache_lock:
        return {ticker: next(_request_ids) for ticker in tickers}


def _may_publish_price(ticker, tokens):
    # Compare completed publications so continuous refresh cannot starve results.
    return ticker in tokens and tokens[ticker] >= _price_versions.get(ticker, -1)


def _first_number(*values, positive=False):
    for value in values:
        number = finite_number(value)
        if number is not None and (not positive or number > 0):
            return number
    return None


def _store_price(ticker, entry):
    entry["data"]["_fetch_failed"] = bool(entry.get("fetch_failed"))
    with _cache_lock:
        _price_cache[ticker] = entry


def _store_info(ticker, entry):
    with _cache_lock:
        _info_cache[ticker] = entry


def _price_entry(ticker):
    with _cache_lock:
        return deepcopy(_price_cache.get(ticker))


# Duration for which cached news is considered fresh.
NEWS_CACHE_DURATION_SECONDS = 300  # 5 minutes

# Quote types that should bypass regular market hours checks (e.g., they update 24/7).
EXEMPT_QUOTE_TYPES = {"FUTURE", "CRYPTOCURRENCY", "CURRENCY"}

try:
    import pandas_market_calendars as mcal
except ImportError:
    mcal = None


def _get_calendar(exchange_name: str):
    """
    Retrieves a market calendar, translating exchange codes from yfinance to pandas_market_calendars names.

    Some yfinance tickers (like ^GSPC, ^DJI) report non-standard exchange names ('SNP', 'DJI').
    This function normalizes them to valid pandas_market_calendars calendars (e.g., 'NYSE').
    Caches retrieved calendars for performance.
    """
    if exchange_name in _market_calendars:
        return _market_calendars[exchange_name]
    # MAPPING: yfinance exchange codes -> pandas_market_calendars calendar names
    exchange_map = {
        "NMS": "NYSE",
        "NYQ": "NYSE",
        "NYS": "NYSE",
        "GDAX": "CME_Crypto",
        "SNP": "NYSE",
        "DJI": "NYSE",
        "CBOE": "NYSE",
        "NIM": "NYSE",
    }
    calendar_name = exchange_map.get(exchange_name, exchange_name)
    if mcal is None:
        return None
    try:
        calendar = mcal.get_calendar(calendar_name)
        _market_calendars[exchange_name] = calendar
        return calendar
    except Exception as e:
        logging.debug(f"Failed to get calendar for {calendar_name}: {e}")
        return None


def _calculate_info_expiry(exchange_name: str) -> datetime:
    now = datetime.now(timezone.utc)
    cal = _get_calendar(exchange_name)
    if cal is None:
        return now + timedelta(hours=1)
    try:
        schedule = cal.schedule(
            start_date=now.date(), end_date=now.date() + timedelta(days=7)
        )
        if not schedule.empty:
            future_opens = schedule.market_open[schedule.market_open > now]
            if not future_opens.empty:
                # ASSUMPTION: The 'previous_close' value updates shortly after market open.
                # We add a 5-minute buffer to ensure the API has refreshed before we re-fetch.
                return future_opens.iloc[0].to_pydatetime() + timedelta(minutes=5)
    except Exception as e:
        logging.debug(f"Failed to calculate info expiry for {exchange_name}: {e}")
        pass
    return now + timedelta(hours=1)


def populate_price_cache(initial_data: dict):
    global _price_cache
    with _cache_lock:
        _price_cache.update(deepcopy(initial_data))
    logging.info(f"In-memory price cache populated with {len(initial_data)} items.")


def populate_info_cache(initial_data: dict):
    global _info_cache
    with _cache_lock:
        _info_cache.update(deepcopy(initial_data))
    logging.info(f"In-memory info cache populated with {len(initial_data)} items.")


def get_price_cache_state() -> dict:
    with _cache_lock:
        return deepcopy(_price_cache)


def get_info_cache_state() -> dict:
    with _cache_lock:
        return deepcopy(_info_cache)


def get_market_price_data(
    tickers: list[str], force_refresh: bool = False, enable_pre_post_market: bool = False
) -> list[dict]:
    seen = set()
    valid_tickers = []
    for t in tickers:
        if t and t.upper() not in seen:
            up_t = t.upper()
            valid_tickers.append(up_t)
            seen.add(up_t)
    if not valid_tickers:
        return []

    tokens = _begin_price_requests(valid_tickers)
    price_cache = get_price_cache_state()
    info_cache = get_info_cache_state()
    now = datetime.now(timezone.utc)

    # 1. Determine which tickers need a full metadata (slow) fetch.
    slow_data_to_fetch = []
    for ticker in valid_tickers:
        if (
            force_refresh
            or ticker not in price_cache
            or not info_cache.get(ticker)
            or (enable_pre_post_market and info_cache[ticker].get("hasPrePostMarketData") is None)
            or now >= price_cache[ticker].get("expiry", now)
        ):
            slow_data_to_fetch.append(ticker)

    # 2. Perform slow fetch. This populates info_cache, which is needed for the next step.
    if slow_data_to_fetch:
        _fetch_and_cache_slow_data(slow_data_to_fetch, request_tokens=tokens)
        price_cache = get_price_cache_state()
        info_cache = get_info_cache_state()

    # 3. Determine which tickers need a live intraday or pre/post (fast) fetch.
    # PERF: Batch market-status lookups by exchange.
    _exchange_statuses: dict[str, dict] = {}
    fast_data_to_fetch, prepost_data_to_fetch = [], []

    for ticker in valid_tickers:
        with _cache_lock:
            if not _may_publish_price(ticker, tokens):
                continue
        info = info_cache.get(ticker, {})
        if not info:
            continue

        quote_type = str(info.get("quoteType", "")).upper()
        supports_prepost = info.get("hasPrePostMarketData", False)

        if quote_type in EXEMPT_QUOTE_TYPES:
            fast_data_to_fetch.append(ticker)
        else:
            exchange = info.get("exchange", "NYSE")
            if exchange not in _exchange_statuses:
                _exchange_statuses[exchange] = get_market_status(exchange)

            status = _exchange_statuses[exchange]
            if status.get("is_open"):
                fast_data_to_fetch.append(ticker)
            elif (
                enable_pre_post_market
                and supports_prepost
                and (
                    status.get("status") in ("pre", "post")
                    or (
                        status.get("status") == "closed"
                        and (
                            force_refresh
                            or ticker not in price_cache
                            or now >= price_cache[ticker].get("expiry", now)
                        )
                    )
                )
            ):
                prepost_data_to_fetch.append(ticker)

    # 4. Perform fast/prepost fetch.
    live_prices = {}
    if fast_data_to_fetch:
        live_prices.update(_fetch_fast_data(fast_data_to_fetch, prepost=False))
    if prepost_data_to_fetch:
        live_prices.update(_fetch_fast_data(prepost_data_to_fetch, prepost=True))

    live_prices = {ticker: row for ticker, value in live_prices.items() if (row := normalize_price_row(value)) is not None}
    # Merge live price updates back into the cache to maintain a single source of truth.
    # This prevents data loss when switching tabs mid-session.
    if live_prices:
        with _cache_lock:
            for ticker, update in live_prices.items():
                if not _may_publish_price(ticker, tokens) or ticker not in _price_cache or "data" not in _price_cache[ticker]:
                    continue
                merged = merge_price_data(_price_cache[ticker]["data"], update)
                if update.get("price") is not None:
                    replace_quote_time(merged, update)
                    merged["_fetched_at"] = datetime.now(timezone.utc).isoformat()
                    merged["_fetch_failed"] = False
                    _price_cache[ticker]["fetch_failed"] = False
                if merged.get("shares") and merged.get("price"):
                    merged["market_cap"] = finite_number(merged["shares"] * merged["price"])
                _price_cache[ticker]["data"] = merged
                _price_versions[ticker] = tokens[ticker]

    # Return copies: a renderer or a shutdown save must never iterate live caches.
    attempted = set(fast_data_to_fetch + prepost_data_to_fetch)
    successful_live = {ticker for ticker, update in live_prices.items() if update.get("price") is not None}
    with _cache_lock:
        eligible = {ticker for ticker in valid_tickers if _may_publish_price(ticker, tokens)}
        attempted &= eligible
        successful_live &= eligible
        for ticker in attempted - successful_live:
            if ticker in _price_cache and isinstance(_price_cache[ticker].get("data"), dict):
                _price_cache[ticker]["data"]["_fetch_failed"] = True
                _price_cache[ticker]["fetch_failed"] = True
                _price_versions[ticker] = tokens[ticker]
    snapshot = get_price_cache_state()
    final_data = []
    for ticker in valid_tickers:
        entry = snapshot.get(ticker)
        if entry is not None:
            row = normalize_price_row(entry.get("data"), ticker)
            if row is None:
                continue
            row["_stale"] = bool(
                entry.get("fetch_failed")
                or row.get("_fetch_failed")
                or (ticker in attempted and ticker not in successful_live)
                or (ticker not in successful_live and now >= entry.get("expiry", now))
                or not row.get("_fetched_at")
            )
            final_data.append(row)
    return final_data


def _publish_slow_price(ticker, tokens, data, expiry, failed, info=None):
    """Merge and publish together; superseded network calls cannot mutate caches."""
    with _cache_lock:
        if not _may_publish_price(ticker, tokens):
            return
        previous = _price_cache.get(ticker, {}).get("data", {})
        previous_split = parse_quote_time(previous.get("_last_split_at"))
        incoming_split = parse_quote_time(data.get("_last_split_at"))
        if previous_split and incoming_split and incoming_split < previous_split:
            _price_cache[ticker]["fetch_failed"] = True
            _price_cache[ticker]["data"]["_fetch_failed"] = True
            _price_versions[ticker] = tokens[ticker]
            return
        if failed:
            merged = previous.copy() if previous else data.copy()
            if not merged.get("description") or merged["description"] in ("Data Unavailable", "Invalid Ticker"):
                merged["description"] = data.get("description", "Data Unavailable")
        else:
            merged = merge_price_data(previous, data)
            if data.get("price") is not None:
                replace_quote_time(merged, data)
                merged["_fetched_at"] = datetime.now(timezone.utc).isoformat()
        _store_price(ticker, {"expiry": expiry, "data": merged,
                              "fetch_failed": failed or data.get("price") is None})
        _price_versions[ticker] = tokens[ticker]
        if info is not None and tokens[ticker] >= _info_versions.get(ticker, -1):
            _store_info(ticker, info)
            _info_versions[ticker] = tokens[ticker]


def _fetch_and_cache_slow_data(tickers: list[str], request_tokens=None):
    """Fetch metadata concurrently, then publish only the current symbol request."""
    if not tickers:
        return
    tokens = request_tokens if request_tokens is not None else _begin_price_requests(tickers)
    with _cache_lock:
        tickers = [ticker for ticker in tickers if _may_publish_price(ticker, tokens)]
    if not tickers:
        return

    def fetch_one(ticker):
        try:
            reply = yf.Ticker(ticker)
            info = reply.info
        except Exception:
            logging.warning("Failed to fetch slow data for %s", ticker)
            return ticker, None, {}
        try:
            fast = reply.fast_info
        except Exception:
            fast = {}
        return ticker, info, fast

    raw = {}
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as executor:
        futures = [executor.submit(fetch_one, ticker) for ticker in tickers]
        for future in as_completed(futures):
            ticker, info, fast = future.result()
            raw[ticker] = info, fast

    expiries = {}
    for ticker in tickers:
        slow, fast = raw[ticker]
        try:
            if not isinstance(slow, dict) or not slow.get("currency"):
                transient = slow is None
                _publish_slow_price(ticker, tokens,
                    {"symbol": ticker, "description": "Data Unavailable" if transient else "Invalid Ticker"},
                    datetime.now(timezone.utc) + (timedelta(minutes=15) if transient else timedelta(days=1)), True)
                continue

            def fast_value(name, default=None):
                try:
                    return fast.get(name, default)
                except Exception:
                    return default

            exchange = slow.get("exchange", "NYSE")
            if exchange not in expiries:
                expiries[exchange] = _calculate_info_expiry(exchange)
            metadata = {key: slow.get(key) for key in ("currency", "shortName", "longName", "quoteType")}
            metadata.update(exchange=exchange, hasPrePostMarketData=slow.get("hasPrePostMarketData", False))
            shares = _first_number(fast_value("shares"), slow.get("sharesOutstanding"), slow.get("floatShares"), positive=True)
            regular = finite_number(slow.get("regularMarketPrice"))
            price = regular if regular is not None else _first_number(fast_value("lastPrice"), slow.get("currentPrice"))
            dividend = finite_number(slow.get("dividendYield"))
            data = {
                **quote_time_fields(slow.get("regularMarketTime") if regular is not None else None, "quote"),
                "symbol": ticker, "currency": fast_value("currency") or slow.get("currency"),
                "description": slow.get("longName") or ticker, "price": price,
                "previous_close": _first_number(slow.get("regularMarketPreviousClose"), slow.get("previousClose"), fast_value("previousClose"), slow.get("open")),
                "day_low": _first_number(fast_value("dayLow"), slow.get("regularMarketDayLow")),
                "day_high": _first_number(fast_value("dayHigh"), slow.get("regularMarketDayHigh")),
                "volume": _first_number(fast_value("lastVolume"), slow.get("volume")),
                "open": _first_number(fast_value("open"), slow.get("open")),
                "fifty_two_week_low": slow.get("fiftyTwoWeekLow"),
                "fifty_two_week_high": slow.get("fiftyTwoWeekHigh"),
                "pe_ratio": _first_number(slow.get("trailingPE"), slow.get("forwardPE")),
                "shares": shares,
                "market_cap": finite_number(shares * price) if shares is not None and price is not None else _first_number(fast_value("marketCap"), slow.get("marketCap")),
                "dividend_yield": dividend / 100 if dividend is not None else finite_number(slow.get("trailingAnnualDividendYield")),
                "eps": _first_number(slow.get("trailingEps"), slow.get("forwardEps")),
                "beta": _first_number(slow.get("beta"), slow.get("beta3Year")),
                "all_time_high": slow.get("allTimeHigh"),
            }
            data = normalize_price_row(data, ticker) or {"symbol": ticker}
            split = parse_quote_time(slow.get("lastSplitDate"))
            if split is not None and split <= datetime.now(timezone.utc):
                data["_last_split_at"] = split.timestamp()
            _publish_slow_price(ticker, tokens, data, expiries[exchange], False, metadata)
        except Exception:
            logging.warning("Failed to cache slow data for %s", ticker)
            _publish_slow_price(ticker, tokens, {"symbol": ticker, "description": "Data Unavailable"},
                                datetime.now(timezone.utc) + timedelta(minutes=15), True)


def _fetch_fast_data(tickers: list[str], prepost: bool = False) -> dict:
    """
    Fetches live intraday OHLCV data for multiple tickers in a single batch call.

    PERF: Replaces the old approach of creating yf.Tickers() and then accessing
    .fast_info for each ticker sequentially. yf.download() fires a single
    batched HTTP request with its own internal threading (threads=True is the
    default), so all tickers are fetched concurrently inside yfinance itself.

    NOTE: yf.download() returns OHLCV data, not the same field set as fast_info.
    market_cap and currency are intentionally omitted here — they are already
    present in the slow cache and do not need refreshing on every live cycle.
    day_high / day_low are derived as the intraday max/min across all 1-minute
    bars returned for the current session.
    """
    if not tickers:
        return {}

    live_prices: dict[str, dict] = {}
    try:
        # period="1d" with interval="1m" gives today's intraday bars.
        # auto_adjust=False returns raw (unadjusted) prices, consistent with
        # what fast_info.lastPrice returns.
        # multi_level_index=True always returns a MultiIndex (metric, ticker)
        # even for a single ticker, which keeps the extraction logic uniform.
        df = yf.download(
            tickers,
            period="1d",
            interval="1m",
            threads=True,
            progress=False,
            auto_adjust=False,
            multi_level_index=True,
            prepost=prepost,
        )

        if df is None or df.empty:
            return {}

        for ticker in tickers:
            try:
                close_series = df["Close"][ticker].dropna()
                if close_series.empty:
                    # Market closed or no intraday data for this ticker today.
                    continue

                # WORKAROUND: yf.download(period="1d") during pre-market (or occasionally post-market)
                # can return stale data from the previous trading day if Yahoo Finance hasn't started
                # serving today's chart/bars yet. If we are fetching pre/post market data (prepost=True),
                # we must check that the returned data is from today to prevent overwriting the cache
                # (which was populated with today's real-time pre-market quote by the slow fetch)
                # with yesterday's stale closing prices.
                if prepost:
                    info = _info_cache.get(ticker, {})
                    exchange = info.get("exchange", "NYSE")
                    cal = _get_calendar(exchange)
                    tz = cal.tz if cal else "America/New_York"
                    
                    last_time = close_series.index[-1]
                    last_time_local = (
                        last_time.tz_convert(tz)
                        if last_time.tzinfo
                        else last_time.tz_localize("UTC").tz_convert(tz)
                    )
                    now_local = pd.Timestamp.now(tz=tz)
                    
                    if last_time_local.date() < now_local.date():
                        logging.info(
                            f"Skipping stale pre/post fast update for {ticker}: last bar at {last_time_local.date()} is older than today {now_local.date()}"
                        )
                        continue

                def optional_series(name):
                    try:
                        return df[name][ticker].dropna()
                    except KeyError:
                        return pd.Series(dtype=float)
                high_series = optional_series("High")
                low_series = optional_series("Low")
                open_series = optional_series("Open")
                vol_series = optional_series("Volume")
                
                live_prices[ticker] = {
                    # The index identifies the bar start, not the last trade.
                    **quote_time_fields(close_series.index[-1], "bar_start"),
                    "price": float(close_series.iloc[-1]),
                    # Intraday high/low span all bars in the current session.
                    "day_high": float(high_series.max()) if not high_series.empty else None,
                    "day_low": float(low_series.min()) if not low_series.empty else None,
                    # First bar's open is the session open price.
                    "open": float(open_series.iloc[0]) if not open_series.empty else None,
                    # Sum of all intraday bar volumes equals total day volume.
                    "volume": int(total) if not vol_series.empty and (total := finite_number(vol_series.sum())) is not None else None,
                    # market_cap and currency omitted intentionally — see docstring.
                }
            except (KeyError, IndexError, ValueError, TypeError, OverflowError) as e:
                logging.warning(
                    f"Failed to extract fast data for {ticker} from batch download: {e}"
                )

    except Exception as e:
        logging.warning(f"Batch fast-data download failed: {e}")

    return live_prices


def get_ticker_info(ticker: str) -> dict | None:
    ticker = ticker.upper()
    with _cache_lock:
        cached = deepcopy(_info_cache.get(ticker))
        if isinstance(cached, dict) and cached.get("currency"):
            return cached
        token = next(_request_ids)
    try:
        info = yf.Ticker(ticker).info
        if not isinstance(info, dict) or not info.get("currency"):
            return None
        data = {key: info.get(key) for key in ("currency", "exchange", "shortName", "longName", "quoteType")}
        data["hasPrePostMarketData"] = info.get("hasPrePostMarketData", False)
        with _cache_lock:
            if token >= _info_versions.get(ticker, -1):
                _store_info(ticker, data)
                _info_versions[ticker] = token
            return deepcopy(_info_cache.get(ticker)) or data
    except Exception:
        # Transient failures must not become permanent negative cache entries.
        return None


def get_market_status(calendar_name="NYSE") -> dict:
    """
    Determines the current market status and finds the next open/close times.

    This function is enhanced to provide not just the current state but also
    future transition times, which enables the main application to schedule
    the next status poll intelligently.

    Returns:
        A dictionary containing the status, next open/close times, and other details.
    """
    if calendar_name == "GDAX":
        calendar_name = "CME_Crypto"
    cal = _get_calendar(calendar_name)
    if not cal:
        return {"status": "unknown", "is_open": True, "calendar": calendar_name}

    try:
        now = pd.Timestamp.now(tz=cal.tz)
        schedule = cal.schedule(
            start_date=now.date() - pd.Timedelta(days=1),
            end_date=now.date() + pd.Timedelta(days=7),
        )

        result = {
            "status": "closed",
            "is_open": False,
            "calendar": calendar_name,
            "next_open": None,
            "next_close": None,
            "reason": None,
            "holiday": None,
            "premarket_open": None,
            "premarket_close": None,
            "postmarket_open": None,
            "postmarket_close": None,
        }

        if not schedule.empty:
            future_opens = schedule.market_open[schedule.market_open > now]
            if not future_opens.empty:
                result["next_open"] = future_opens.iloc[0].to_pydatetime()

            future_closes = schedule.market_close[schedule.market_close > now]
            if not future_closes.empty:
                result["next_close"] = future_closes.iloc[0].to_pydatetime()

        today_schedule = schedule[schedule.index.date == now.date()]
        if not today_schedule.empty:
            row = today_schedule.iloc[0]
            market_open, market_close = row.market_open, row.market_close

            # WORKAROUND: The installed pandas_market_calendars version lacks `extended_hours` support.
            # We manually calculate extended hours based on NYSE standards:
            #   - Pre-market: 5.5 hours before market_open (e.g., 4:00 AM if open is 9:30 AM).
            #   - Post-market: 4 hours after market_close (e.g., 8:00 PM for a 4:00 PM close).
            # These offsets are relative, so they automatically adjust for early-close days.

            pre_open = market_open - pd.Timedelta(hours=5.5)
            # Pre-close is market_open

            # Post-open is market_close
            post_close = market_close + pd.Timedelta(hours=4)

            result["premarket_open"] = pre_open
            result["premarket_close"] = market_open
            result["postmarket_open"] = market_close
            result["postmarket_close"] = post_close

            if market_open <= now < market_close:
                result["status"] = "open"
                result["is_open"] = True
            elif pre_open <= now < market_open:
                result["status"] = "pre"
            elif market_close <= now < post_close:
                result["status"] = "post"
        else:
            if now.weekday() >= 5:
                result["reason"] = "weekend"
            else:
                holidays_obj = cal.holidays()
                today_date = pd.Timestamp(now.date())
                if hasattr(holidays_obj, "holidays"):
                    holiday_list = (
                        holidays_obj.holidays()
                        if callable(holidays_obj.holidays)
                        else holidays_obj.holidays
                    )
                    if today_date in holiday_list:
                        result["reason"] = "holiday"
                        if hasattr(holiday_list, "loc"):
                            result["holiday"] = holiday_list.loc[today_date]

        return result
    except Exception as e:
        logging.error(f"Error getting market status for {calendar_name}: {e}")
        return {"status": "unknown", "is_open": True, "calendar": calendar_name}


def get_historical_data(ticker: str, period: str, interval: str = "1d"):
    df = pd.DataFrame()
    df.attrs["symbol"] = ticker.upper()
    try:
        info = get_ticker_info(ticker)
        if not info:
            df.attrs["error"] = "Invalid Ticker"
            return df
        data = yf.Ticker(ticker).history(period=period, interval=interval)
        if not data.empty:
            data.attrs["symbol"] = ticker.upper()
            data.attrs["currency"] = info.get("currency")
        return data
    except Exception as e:
        # HACK: yfinance sometimes raises errors for valid tickers with no data in range.
        # Log the actual error for debugging, but return an empty dataframe.
        logging.error(f"yfinance error fetching history for {ticker} ({period}): {e}")
        df.attrs["error"] = "Data Error"
        return df


def clear_news_cache(tickers=None):
    with _cache_lock:
        if tickers is None:
            _news_cache.clear()
            _news_versions.clear()
        else:
            for ticker in tickers:
                _news_cache.pop(ticker.upper(), None)
                _news_versions.pop(ticker.upper(), None)


def get_news_for_tickers(tickers: list[str], force_refresh: bool = False, cancelled=None) -> list[dict] | None:
    """Keep usable articles when another symbol fails; empty success is distinct."""
    all_news, seen_articles = [], set()
    succeeded = not tickers
    for ticker in dict.fromkeys(tickers):
        if cancelled is not None and cancelled():
            break
        try:
            news_items = get_news_data(ticker, force_refresh=True) if force_refresh else get_news_data(ticker)
        except Exception:
            logging.error("News retrieval failed for %s", ticker)
            continue
        if news_items is None:
            continue
        succeeded = True
        for item in news_items:
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            title = item.get("title")
            identity: tuple[str, ...]
            if isinstance(link, str) and link:
                identity = ("url", link)
            elif isinstance(title, str) and title.strip() and title != "N/A":
                identity = ("article", title, str(item.get("publisher")), str(item.get("publish_datetime_utc")))
            else:
                continue
            if identity not in seen_articles:
                all_news.append(deepcopy(item))
                seen_articles.add(identity)
    def date_key(item):
        stamp = item.get("publish_datetime_utc")
        if not isinstance(stamp, datetime):
            return datetime.min.replace(tzinfo=timezone.utc)
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    all_news.sort(key=date_key, reverse=True)
    return all_news if succeeded else None


def get_news_data(ticker: str, force_refresh: bool = False) -> list[dict] | None:
    if not ticker:
        return []
    normalized_ticker = ticker.upper()
    now = datetime.now(timezone.utc)
    with _cache_lock:
        entry = deepcopy(_news_cache.get(normalized_ticker))
    if entry is not None and not force_refresh:
        timestamp, cached_data = entry
        if (now - timestamp).total_seconds() < NEWS_CACHE_DURATION_SECONDS:
            return cached_data
    with _cache_lock:
        token = object()
        _news_versions[normalized_ticker] = token
    try:
        if not get_ticker_info(ticker):
            return None
        raw_news = yf.Ticker(normalized_ticker).news
        if raw_news is None:
            raw_news = []
        if not isinstance(raw_news, list):
            return None
        processed_news = []
        for item in raw_news:
            content = item.get("content") if isinstance(item, dict) else None
            if not isinstance(content, dict) or not content:
                continue
            publish_time_utc = None
            publish_time_str = "N/A"
            pub_date = content.get("pubDate")
            if isinstance(pub_date, str):
                publish_time_str = pub_date
                try:
                    publish_time_utc = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    if publish_time_utc.tzinfo is None:
                        publish_time_utc = publish_time_utc.replace(tzinfo=timezone.utc)
                    publish_time_str = publish_time_utc.astimezone().strftime("%Y-%m-%d %H:%M %Z")
                except (ValueError, TypeError, OverflowError):
                    publish_time_utc = None
            provider = content.get("provider")
            canonical = content.get("canonicalUrl")
            def text(value):
                return str(value) if value is not None else "N/A"
            processed_news.append(dict(
                source_ticker=normalized_ticker, title=text(content.get("title")),
                summary=text(content.get("summary")),
                publisher=text(provider.get("displayName") if isinstance(provider, dict) else None),
                link=canonical.get("url") if isinstance(canonical, dict) else None,
                publish_time=publish_time_str, publish_datetime_utc=publish_time_utc,
            ))
        with _cache_lock:
            if _news_versions.get(normalized_ticker) is token:
                _news_cache[normalized_ticker] = (datetime.now(timezone.utc), deepcopy(processed_news))
        return processed_news
    except Exception:
        logging.error("News retrieval failed for %s", normalized_ticker)
        return None


def get_ticker_info_comparison(ticker: str) -> dict:
    try:
        ticker_obj = yf.Ticker(ticker)
        fast_info, slow_info = ticker_obj.fast_info, ticker_obj.info
        if not slow_info:
            return {"fast": {}, "slow": {}, "batch": {}, "prepost": {}}
        
        # Fetch batch data (which uses yf.download) for the ticker to compare with fast_info and info
        try:
            batch_data = _fetch_fast_data([ticker])
            batch_info = batch_data.get(ticker, {})
        except Exception:
            batch_info = {}

        # Fetch batch data with pre/post-market enabled to compare
        try:
            prepost_data = _fetch_fast_data([ticker], prepost=True)
            prepost_info = prepost_data.get(ticker, {})
        except Exception:
            prepost_info = {}
            
        return {"fast": fast_info, "slow": slow_info, "batch": batch_info, "prepost": prepost_info}
    except Exception:
        return {"fast": {}, "slow": {}, "batch": {}, "prepost": {}}


def run_ticker_debug_test(tickers: list[str]) -> list[dict]:
    """
    Tests a list of tickers for validity and measures API response latency for each.
    """
    results = []
    # FIX: Iterate and fetch tickers individually to measure individual latency.
    for symbol in tickers:
        start_time = time.perf_counter()
        try:
            # Let yfinance manage its own session.
            info = yf.Ticker(symbol).info
            is_valid = info and info.get("currency") is not None
        except Exception:
            info, is_valid = {}, False
        latency = time.perf_counter() - start_time
        description = (
            info.get("longName", "N/A") if is_valid else "Could not retrieve data."
        )
        results.append(
            {
                "symbol": symbol,
                "is_valid": is_valid,
                "description": description,
                "latency": latency,
            }
        )

    results.sort(key=lambda x: float(x["latency"]), reverse=True)
    return results


def run_list_debug_test(lists: dict[str, list[str]]) -> list[dict]:
    """
    Measures the time it takes to fetch data for entire lists of tickers.
    This is a true network test.
    """
    results = []
    for list_name, tickers in lists.items():
        if not tickers:
            results.append({"list_name": list_name, "latency": 0.0, "ticker_count": 0})
            continue

        start_time = time.perf_counter()
        # FIX: Use force_refresh=True to guarantee a network call. No session needed.
        get_market_price_data(tickers, force_refresh=True)
        latency = time.perf_counter() - start_time

        results.append(
            {"list_name": list_name, "latency": latency, "ticker_count": len(tickers)}
        )
    results.sort(key=lambda x: float(x["latency"]), reverse=True)  # type: ignore
    return results


def run_cache_test(lists: dict[str, list[str]]) -> list[dict]:
    """
    Tests the performance of reading pre-cached data for lists of tickers.
    This test relies on the cache being populated by normal app usage and
    does not trigger network calls itself.
    """
    results = []
    for list_name, tickers in lists.items():
        start_time = time.perf_counter()
        _ = [get_cached_price(ticker) for ticker in tickers]
        latency = time.perf_counter() - start_time
        results.append(
            {"list_name": list_name, "latency": latency, "ticker_count": len(tickers)}
        )

    results.sort(key=lambda x: float(x["latency"]), reverse=True)  # type: ignore
    return results


def is_cached(ticker: str) -> bool:
    return ticker.upper() in _price_cache


def get_cached_price(ticker: str) -> dict | None:
    entry = _price_entry(ticker.upper())
    if not isinstance(entry, dict) or not isinstance(entry.get("data"), dict):
        return None
    data = entry["data"].copy()
    data["_stale"] = bool(entry.get("fetch_failed") or data.get("_fetch_failed") or not data.get("_fetched_at") or datetime.now(timezone.utc) >= entry.get("expiry", datetime.now(timezone.utc)))
    return data
