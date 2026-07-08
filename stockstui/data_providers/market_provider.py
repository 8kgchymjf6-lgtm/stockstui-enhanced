import yfinance as yf
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
import time
import pandas as pd
from stockstui.utils import merge_price_data


# In-memory cache for storing fetched market data to reduce API calls.
_price_cache: dict[str, dict[str, Any]] = {}
_news_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
_info_cache: dict[str, dict[str, Any]] = {}
_market_calendars: dict[str, Any] = {}

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
    _price_cache.update(initial_data)
    logging.info(f"In-memory price cache populated with {len(initial_data)} items.")


def populate_info_cache(initial_data: dict):
    global _info_cache
    _info_cache.update(initial_data)
    logging.info(f"In-memory info cache populated with {len(initial_data)} items.")


def get_price_cache_state() -> dict:
    return _price_cache


def get_info_cache_state() -> dict:
    return _info_cache


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

    now = datetime.now(timezone.utc)

    # 1. Determine which tickers need a full metadata (slow) fetch.
    slow_data_to_fetch = []
    for ticker in valid_tickers:
        if (
            force_refresh
            or ticker not in _price_cache
            or now >= _price_cache[ticker].get("expiry", now)
        ):
            slow_data_to_fetch.append(ticker)

    # 2. Perform slow fetch. This populates _info_cache, which is needed for the next step.
    if slow_data_to_fetch:
        _fetch_and_cache_slow_data(slow_data_to_fetch)

    # 3. Determine which tickers need a live intraday or pre/post (fast) fetch.
    # PERF: Batch market-status lookups by exchange.
    _exchange_statuses: dict[str, dict] = {}
    fast_data_to_fetch, prepost_data_to_fetch = [], []

    for ticker in valid_tickers:
        info = _info_cache.get(ticker, {})
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
                            or ticker not in _price_cache
                            or now >= _price_cache[ticker].get("expiry", now)
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

    # Merge live price updates back into the cache to maintain a single source of truth.
    # This prevents data loss when switching tabs mid-session.
    if live_prices:
        for ticker, fast_data_update in live_prices.items():
            if ticker in _price_cache and "data" in _price_cache[ticker]:
                existing_data = _price_cache[ticker]["data"]
                merged_data = merge_price_data(existing_data, fast_data_update)

                # ASSUMPTION: yf.download() OHLCV batch download doesn't return market cap.
                # So we calculate the updated market cap by multiplying new price by cached shares.
                shares = merged_data.get("shares")
                price = merged_data.get("price")
                if shares and price:
                    merged_data["market_cap"] = shares * price

                _price_cache[ticker]["data"] = merged_data

    # Now that the cache is updated, construct the final list from it.
    final_data = []
    for ticker in valid_tickers:
        if ticker in _price_cache:
            final_data.append(_price_cache[ticker].get("data", {}))

    return final_data


def _fetch_and_cache_slow_data(tickers: list[str]):
    """
    Fetches full metadata (info + fast_info) for a batch of tickers in parallel.

    PERF: Previously this iterated sequentially, waiting for each HTTP response
    before starting the next. Now each ticker is fetched in its own thread via
    ThreadPoolExecutor, cutting wall-clock time from O(n * latency) to roughly
    O(latency) for typical list sizes.

    Cache writes happen only after all futures complete so the module-level
    dicts (_price_cache, _info_cache) are never touched from multiple threads.

    PERF: _calculate_info_expiry() is also memoised per exchange within the
    batch — the calendar schedule DataFrame is built once per exchange rather
    than once per ticker.
    """
    if not tickers:
        return

    def _fetch_one(ticker: str) -> tuple[str, dict | None, object | None]:
        """Fetch info for a single ticker. Runs inside the thread pool."""
        try:
            tkr = yf.Ticker(ticker)
            return ticker, tkr.info, tkr.fast_info
        except Exception:
            logging.warning(f"Failed to fetch slow data for {ticker}")
            return ticker, None, None

    # Cap threads to avoid hammering yfinance rate-limits on very large lists.
    max_workers = min(len(tickers), 8)
    raw_results: dict[str, tuple[dict | None, object | None]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(future_to_ticker):
            ticker, slow_info, fast_info = future.result()
            raw_results[ticker] = (slow_info, fast_info)

    # PERF: Cache _calculate_info_expiry() per exchange so the Pandas calendar
    # schedule query runs once per exchange per batch instead of once per ticker.
    exchange_expiry_cache: dict[str, datetime] = {}

    # Write to module-level caches sequentially (no concurrent access).
    # Preserve the original ticker order for predictability.
    for ticker in tickers:
        slow_info, fast_info = raw_results.get(ticker, (None, None))
        try:
            if slow_info and slow_info.get("currency"):
                exchange = slow_info.get("exchange", "NYSE")
                _info_cache[ticker] = {
                    "currency": slow_info.get("currency"),
                    "exchange": exchange,
                    "shortName": slow_info.get("shortName"),
                    "longName": slow_info.get("longName"),
                    "quoteType": slow_info.get("quoteType"),
                    "hasPrePostMarketData": slow_info.get("hasPrePostMarketData", False),
                }
                if exchange not in exchange_expiry_cache:
                    exchange_expiry_cache[exchange] = _calculate_info_expiry(exchange)
                # yfinance returns objects that behave like dicts but Mypy doesn't always recognize them
                fi: Any = fast_info
                si: Any = slow_info

                # Fetch shares to enable market cap calculations during fast updates
                shares = None
                try:
                    shares = fi.get("shares")
                except Exception:
                    pass
                if not shares:
                    shares = si.get("sharesOutstanding") or si.get("floatShares")

                new_data = {
                    "symbol": ticker,
                    "currency": fi.get("currency", si.get("currency", "USD")),
                    "description": si.get("longName", ticker),
                    "price": fi.get("lastPrice")
                    or si.get("currentPrice")
                    or si.get("regularMarketPrice"),
                    "previous_close": si.get("regularMarketPreviousClose")
                    or si.get("previousClose")
                    or fi.get("previousClose")
                    or si.get("open"),
                    "day_low": fi.get("dayLow") or si.get("regularMarketDayLow"),
                    "day_high": fi.get("dayHigh") or si.get("regularMarketDayHigh"),
                    "volume": fi.get("lastVolume") or si.get("volume"),
                    "open": fi.get("open") or si.get("open"),
                    "fifty_two_week_low": si.get("fiftyTwoWeekLow"),
                    "fifty_two_week_high": si.get("fiftyTwoWeekHigh"),
                    "pe_ratio": si.get("trailingPE") or si.get("forwardPE"),
                    "shares": shares,
                    # Fallback to API-reported market cap if price or shares is missing/None
                    "market_cap": (shares * (fi.get("lastPrice") or si.get("currentPrice") or si.get("regularMarketPrice")))
                    if shares and (fi.get("lastPrice") or si.get("currentPrice") or si.get("regularMarketPrice"))
                    else (fi.get("marketCap") or si.get("marketCap")),
                    "dividend_yield": fi.get("dividendYield")
                    or si.get("trailingAnnualDividendYield"),
                    "eps": si.get("trailingEps") or si.get("forwardEps"),
                    "beta": si.get("beta") or si.get("beta3Year"),
                    "all_time_high": si.get("allTimeHigh"),
                }

                existing_entry = _price_cache.get(ticker)
                if existing_entry and "data" in existing_entry:
                    merged_data = merge_price_data(existing_entry["data"], new_data)
                else:
                    merged_data = new_data

                _price_cache[ticker] = {
                    "expiry": exchange_expiry_cache[exchange],
                    "data": merged_data,
                }
            else:
                # If slow_info is None, it means _fetch_one caught an exception (fetch failed).
                # If slow_info is a dict but has no currency, it's an invalid ticker.
                # In either case, we merge or keep existing cached data to avoid N/A corruption on transient failures.
                description = "Data Unavailable" if slow_info is None else "Invalid Ticker"
                existing_entry = _price_cache.get(ticker)
                if existing_entry and "data" in existing_entry:
                    merged_data = existing_entry["data"].copy()
                    if "description" not in merged_data or merged_data["description"] in ("Data Unavailable", "Invalid Ticker"):
                        merged_data["description"] = description
                else:
                    merged_data = {"symbol": ticker, "description": description}

                # If transient failure (slow_info is None), set short expiry so we retry later.
                # If permanent failure (Invalid Ticker), cache for 1 day.
                expiry_delta = timedelta(minutes=15) if slow_info is None else timedelta(days=1)
                _price_cache[ticker] = {
                    "expiry": datetime.now(timezone.utc) + expiry_delta,
                    "data": merged_data,
                }
        except Exception:
            logging.warning(f"Failed to cache slow data for {ticker}")
            existing_entry = _price_cache.get(ticker)
            if existing_entry and "data" in existing_entry:
                merged_data = existing_entry["data"]
            else:
                merged_data = {"symbol": ticker, "description": "Data Unavailable"}
            _price_cache[ticker] = {
                "expiry": datetime.now(timezone.utc) + timedelta(minutes=15),
                "data": merged_data,
            }


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

                high_series = df["High"][ticker].dropna()
                low_series = df["Low"][ticker].dropna()
                open_series = df["Open"][ticker].dropna()
                vol_series = df["Volume"][ticker].dropna()
                
                live_prices[ticker] = {
                    # Last 1-minute close is the most recent trade price.
                    "price": float(close_series.iloc[-1]),
                    # Intraday high/low span all bars in the current session.
                    "day_high": float(high_series.max()) if not high_series.empty else None,
                    "day_low": float(low_series.min()) if not low_series.empty else None,
                    # First bar's open is the session open price.
                    "open": float(open_series.iloc[0]) if not open_series.empty else None,
                    # Sum of all intraday bar volumes equals total day volume.
                    "volume": int(vol_series.sum()) if not vol_series.empty else None,
                    # market_cap and currency omitted intentionally — see docstring.
                }
            except (KeyError, IndexError, ValueError, TypeError) as e:
                logging.warning(
                    f"Failed to extract fast data for {ticker} from batch download: {e}"
                )

    except Exception as e:
        logging.warning(f"Batch fast-data download failed: {e}")

    return live_prices


def get_ticker_info(ticker: str) -> dict | None:
    if ticker in _info_cache:
        return _info_cache[ticker]
    try:
        info = yf.Ticker(ticker).info
        if not info or not info.get("currency"):
            _info_cache[ticker] = {}
            return None
        _info_cache[ticker] = {
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "shortName": info.get("shortName"),
            "longName": info.get("longName"),
            "quoteType": info.get("quoteType"),
            "hasPrePostMarketData": info.get("hasPrePostMarketData", False),
        }
        return _info_cache[ticker]
    except Exception:
        _info_cache[ticker] = {}
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


def get_news_for_tickers(tickers: list[str]) -> list[dict] | None:
    all_news, seen_urls = [], set()
    for ticker in tickers:
        news_items = get_news_data(ticker)
        if news_items:
            for item in news_items:
                if (link := item.get("link")) and link not in seen_urls:
                    all_news.append(item)
                    seen_urls.add(link)
    if not all_news:
        return None if len(tickers) > 0 else []
    all_news.sort(key=lambda x: x["publish_datetime_utc"], reverse=True)
    return all_news


def get_news_data(ticker: str) -> list[dict] | None:
    if not ticker:
        return []
    normalized_ticker = ticker.upper()
    now = datetime.now(timezone.utc)
    if normalized_ticker in _news_cache:
        timestamp, cached_data = _news_cache[normalized_ticker]
        if (now - timestamp).total_seconds() < NEWS_CACHE_DURATION_SECONDS:
            return cached_data
    info = get_ticker_info(ticker)
    if not info:
        return None
    raw_news = yf.Ticker(normalized_ticker).news
    if not raw_news:
        return []
    processed_news = []
    for item in raw_news:
        content = item.get("content", {})
        if not content:
            continue
        publish_time_utc = None
        publish_time_str = "N/A"
        if pub_date_str := content.get("pubDate"):
            try:
                publish_time_utc = datetime.fromisoformat(
                    pub_date_str.replace("Z", "+00:00")
                )
                publish_time_str = publish_time_utc.astimezone().strftime(
                    "%Y-%m-%d %H:%M %Z"
                )
            except (ValueError, TypeError):
                publish_time_str = pub_date_str
        processed_news.append(
            {
                "source_ticker": normalized_ticker,
                "title": content.get("title", "N/A"),
                "summary": content.get("summary", "N/A"),
                "publisher": content.get("provider", {}).get("displayName", "N/A"),
                "link": content.get("canonicalUrl", {}).get("url", "#"),
                "publish_time": publish_time_str,
                "publish_datetime_utc": publish_time_utc,
            }
        )
    _news_cache[normalized_ticker] = (datetime.now(timezone.utc), processed_news)
    return processed_news


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
    entry = _price_cache.get(ticker.upper())
    return entry.get("data") if entry else None
