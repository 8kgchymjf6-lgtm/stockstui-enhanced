"""
Options data provider for fetching stock options chains using yfinance.
"""

import logging
import time
import yfinance as yf
from typing import Any
import datetime
from copy import deepcopy
from threading import RLock
import pandas as pd
import math
from stockstui.utils import black_scholes


# Cache for options data with TTL
_options_cache: dict[str, dict[str, Any]] = {}
_expirations_cache: dict[str, dict[str, Any]] = {}
OPTIONS_CACHE_TTL = 600  # 10 minutes in seconds


_cache_lock = RLock()
_cache_versions: dict[tuple[str, str], object] = {}


def _begin_request(cache, key, use_cache):
    namespace = "chain" if cache is _options_cache else "expirations"
    with _cache_lock:
        entry = cache.get(key)
        if use_cache and _is_cache_valid(entry):
            return deepcopy(entry["data"]), None
        token = object()
        _cache_versions[namespace, key] = token
        return None, token


def _publish(cache, key, token, data):
    namespace = "chain" if cache is _options_cache else "expirations"
    with _cache_lock:
        if _cache_versions.get((namespace, key)) is token:
            cache[key] = {"data": deepcopy(data), "timestamp": time.time()}


def normalize_options_data(data):
    """Preserve usable rows while making partial provider responses safe to display."""
    if not isinstance(data, dict):
        raise ValueError("Options response must be an object")
    result = data.copy()
    underlying = data.get("underlying")
    result["underlying"] = underlying.copy() if isinstance(underlying, dict) else {}
    for side in ("calls", "puts"):
        frame = data.get(side)
        if frame is None:
            frame = pd.DataFrame()
        if not isinstance(frame, pd.DataFrame):
            raise ValueError(f"Invalid {side} options data")
        frame = frame.copy()
        if not frame.empty:
            if "strike" not in frame or "contractSymbol" not in frame:
                frame = frame.iloc[:0]
            else:
                for column in ("strike", "lastPrice", "bid", "ask", "percentChange", "volume", "openInterest", "impliedVolatility", "delta", "gamma", "theta", "vega"):
                    if column not in frame:
                        frame[column] = float("nan")
                    frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
                    frame[column] = frame[column].where(frame[column].map(math.isfinite))
                valid_symbol = frame["contractSymbol"].map(lambda x: isinstance(x, str) and bool(x.strip()))
                frame = frame[valid_symbol & frame["strike"].notna() & (frame["strike"] >= 0)]
                frame = frame.drop_duplicates("contractSymbol")
        if frame.empty:
            # The chart still indexes these columns when the other side has rows.
            for column in ("strike", "openInterest"):
                frame[column] = pd.Series(dtype=float)
        result[side] = frame.reset_index(drop=True)
    return result


def _is_cache_valid(cache_entry: dict) -> bool:
    """Check if a cache entry is still valid based on TTL."""
    if not cache_entry:
        return False
    return (time.time() - cache_entry.get("timestamp", 0)) < OPTIONS_CACHE_TTL


def clear_options_cache(ticker: str | None = None):
    """
    Clear the options cache. If ticker is provided, only clear that ticker's cache.

    Args:
        ticker: Optional ticker symbol to clear specific cache, or None to clear all
    """
    with _cache_lock:
        if ticker:
            ticker_upper = ticker.upper()
            _expirations_cache.pop(ticker_upper, None)
            for key in list(_options_cache):
                if key.startswith(ticker_upper + "_"):
                    _options_cache.pop(key, None)
            for namespace, key in list(_cache_versions):
                if (namespace == "expirations" and key == ticker_upper) or (namespace == "chain" and key.startswith(ticker_upper + "_")):
                    _cache_versions.pop((namespace, key), None)
        else:
            _options_cache.clear()
            _expirations_cache.clear()
            _cache_versions.clear()


def get_available_expirations(
    ticker_symbol: str, use_cache: bool = True
) -> tuple[str, ...] | None:
    """
    Fetches available expiration dates for a ticker's options.

    Args:
        ticker_symbol: The stock ticker symbol (e.g., "AAPL")
        use_cache: Whether to use cached data if available

    Returns:
        Tuple of expiration date strings (YYYY-MM-DD format), or None on error
    """
    ticker_upper = ticker_symbol.upper()
    cache_key = ticker_upper

    cached, token = _begin_request(_expirations_cache, cache_key, use_cache)
    if token is None:
        return cached

    try:
        ticker = yf.Ticker(ticker_symbol)
        expirations = ticker.options

        if expirations:
            # Cache the result
            _publish(_expirations_cache, cache_key, token, expirations)
            return expirations
        return None
    except Exception as e:
        logging.error(f"Error fetching expirations for {ticker_symbol}: {e}")
        return None




def _calculate_greeks_for_chain(chain_df, underlying_price, expiration_date, flag):
    """
    Helper to calculate Greeks for a DataFrame of options.

    Args:
        chain_df: DataFrame containing option data
        underlying_price: Current price of underlying asset
        expiration_date: Expiration date string (YYYY-MM-DD)
        flag: 'c' for Call, 'p' for Put
    """
    if chain_df is None or chain_df.empty or not underlying_price:
        return chain_df

    # Constants for calculation
    RISK_FREE_RATE = 0.045  # 4.5% approximation

    # Calculate time to expiration in years
    try:
        exp_dt = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
        now = datetime.datetime.now()
        # Add end of day time (16:00) to expiration for better precision
        exp_dt = exp_dt.replace(hour=16, minute=0, second=0)

        diff = exp_dt - now
        days_to_exp = diff.total_seconds() / (24 * 3600)
        T = days_to_exp / 365.0
    except Exception:
        T = 0

    # Initialize Greek columns
    greeks_list = []

    for _, row in chain_df.iterrows():
        strike = row.get("strike", 0)
        iv = row.get("impliedVolatility", 0)

        # Calculate Greeks
        greeks = black_scholes.calculate_greeks(
            flag=flag, S=underlying_price, K=strike, T=T, r=RISK_FREE_RATE, sigma=iv
        )
        greeks_list.append(greeks)

    # Add columns to DataFrame
    if greeks_list:
        import pandas as pd

        greeks_df = pd.DataFrame(greeks_list)
        # Concatenate original df with greeks
        # Reset index to ensure alignment
        chain_df = chain_df.reset_index(drop=True)
        chain_df = pd.concat([chain_df, greeks_df], axis=1)

    return chain_df


def get_options_chain(
    ticker_symbol: str, expiration_date: str | None = None, use_cache: bool = True
):
    """
    Fetches the options chain for a ticker and expiration date.

    Args:
        ticker_symbol: The stock ticker symbol (e.g., "AAPL")
        expiration_date: Specific expiration date (YYYY-MM-DD), or None for nearest
        use_cache: Whether to use cached data if available

    Returns:
        Dictionary with 'calls', 'puts', and 'underlying' keys, or None on error.
        calls and puts are pandas DataFrames.
    """
    ticker_upper = ticker_symbol.upper()
    cache_key = f"{ticker_upper}_{expiration_date or 'nearest'}"

    cached, token = _begin_request(_options_cache, cache_key, use_cache)
    if token is None:
        return cached

    try:
        ticker = yf.Ticker(ticker_symbol)
        options_chain = ticker.option_chain(date=expiration_date)

        # Get underlying price
        underlying = options_chain.underlying
        underlying = underlying if isinstance(underlying, dict) else {}
        underlying_price = underlying.get("regularMarketPrice")

        # If expiration_date is None (nearest), we need to know what it is for Greek calc
        # But yfinance option_chain(date=None) returns the nearest,
        # however we might not know exactly which date that is without checking ticker.options[0]
        # For now, if date is missing, Greeks might be slightly off if we don't know T.
        # But usually the UI passes a specific date.

        calc_date = expiration_date
        if not calc_date:
            # Try to guess or fetch expirations if not provided (though usually it is)
            # For MVP, if no date provided, skip Greeks or use 0
            pass

        calls_df = options_chain.calls
        puts_df = options_chain.puts

        if calc_date and underlying_price:
            calls_df = _calculate_greeks_for_chain(
                calls_df, underlying_price, calc_date, "c"
            )
            puts_df = _calculate_greeks_for_chain(
                puts_df, underlying_price, calc_date, "p"
            )

        result = normalize_options_data({
            "calls": calls_df,
            "puts": puts_df,
            "underlying": underlying,
            "expiration": calc_date,
        })

        # Cache the result
        _publish(_options_cache, cache_key, token, result)

        return result
    except ValueError as e:
        # Specific error for invalid expiration date
        logging.error(f"Invalid expiration date for {ticker_symbol}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error fetching options chain for {ticker_symbol}: {e}")
        return None
