import requests
import math
from copy import deepcopy
from threading import RLock
import logging
import numpy as np
from datetime import datetime, timezone
from calendar import monthrange
from typing import Optional, Dict, List, Any

BASE_URL = "https://api.stlouisfed.org/fred"
_series_cache: Dict[str, Any] = {}
_info_cache: Dict[str, Any] = {}
_cache_lock = RLock()
_cache_versions: dict[tuple[str, str], object] = {}


def clear_cache(series=None):
    with _cache_lock:
        keys = {key.upper() for key in series} if series is not None else set(_series_cache) | set(_info_cache) | {key for _, key in _cache_versions}
        for key in keys:
            _series_cache.pop(key, None)
            _info_cache.pop(key, None)
            _cache_versions.pop(("observations", key), None)
            _cache_versions.pop(("info", key), None)

CACHE_DURATION_SECONDS = 300  # 5 minutes

# ASSUMPTION: 3000 observations covers 10+ years of daily data (~2520 trading days)
# and plenty for weekly (520), monthly (120), or quarterly (40).
OBSERVATION_LIMIT = 3000


def _observations(value):
    if not isinstance(value, list):
        raise ValueError("Observations must be a list")
    rows = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str):
            continue
        try:
            datetime.strptime(item["date"], "%Y-%m-%d")
        except ValueError:
            continue
        if item["date"] in seen:
            continue
        row = deepcopy(item)
        try:
            number = float(row.get("value", "."))
            if not math.isfinite(number):
                row["value"] = "."
        except (TypeError, ValueError, OverflowError):
            row["value"] = "."
        seen.add(row["date"])
        rows.append(row)
    if value and not rows:
        raise ValueError("No valid observations")
    return sorted(rows, key=lambda row: row["date"], reverse=True)


def get_series_observations(series_id: str, api_key: str, limit: int = OBSERVATION_LIMIT) -> Optional[List[Dict[str, Any]]]:
    if not api_key:
        logging.error("FRED API key is missing.")
        return None
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return None
    series_id = series_id.upper()
    now = datetime.now(timezone.utc)
    with _cache_lock:
        entry = deepcopy(_series_cache.get(series_id))
    fallback = None
    if entry:
        timestamp, cached = entry
        fallback = cached[:limit]
        if (now - timestamp).total_seconds() < CACHE_DURATION_SECONDS and len(cached) >= limit:
            return fallback
    with _cache_lock:
        token = object()
        _cache_versions["observations", series_id] = token
    try:
        params: dict[str, Any] = dict(series_id=series_id, api_key=api_key, file_type="json", sort_order="desc", limit=limit)
        response = requests.get(f"{BASE_URL}/series/observations", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Response must be an object")
        rows = _observations(data.get("observations"))[:limit]
        with _cache_lock:
            if _cache_versions.get(("observations", series_id)) is token:
                _series_cache[series_id] = (now, deepcopy(rows))
        return rows
    except (requests.exceptions.RequestException, ValueError, TypeError, RecursionError):
        logging.error("Could not retrieve FRED observations for %s", series_id)
        return fallback


def detect_frequency(observations: List[Dict[str, Any]]) -> str:
    """
    Infer frequency from observation dates.

    Returns:
        'M' for monthly, 'Q' for quarterly, 'D' for daily, 'A' for annual
    """
    if len(observations) < 2:
        return "M"  # Default to monthly

    try:
        # Parse the first few dates to determine frequency
        dates = []
        for obs in observations[:10]:  # Look at first 10 observations
            date_obj = datetime.strptime(obs["date"], "%Y-%m-%d")
            dates.append(date_obj)

        if len(dates) < 2:
            return "M"

        # Calculate differences between consecutive dates
        diffs = []
        for i in range(1, len(dates)):
            diff = abs((dates[i] - dates[i - 1]).days)
            diffs.append(diff)

        # Calculate average difference
        avg_diff = sum(diffs) / len(diffs)

        # Classify based on average difference
        if avg_diff < 2:  # Less than 2 days - daily
            return "D"
        elif avg_diff < 15:  # Less than 15 days - weekly
            return "W"
        elif avg_diff < 45:  # Less than 45 days - monthly
            return "M"
        elif avg_diff < 135:  # Less than 135 days - quarterly
            return "Q"
        else:  # More than 135 days - annual
            return "A"
    except Exception:
        # Default to monthly for ambiguous cases
        return "M"


def compute_enhanced_metrics(
    observations: List[Dict[str, Any]],
    frequency: str = "M",
    short_months: int = 12,
    long_months: int = 24,
    z_lookback_years: int = 10,
) -> Dict[str, Any]:
    """
    Compute advanced metrics from observation data.

    Args:
        observations: List of observations in descending order (newest first)
        frequency: 'M' for monthly, 'Q' for quarterly
        short_months: Lookback for short rolling window (default 12)
        long_months: Lookback for long rolling window (default 24)
        z_lookback_years: Years of data for z-score calculation (default 10)

    Returns:
        Dict with: yoy_pct, roll_12, roll_24, z_10y, hist_min_10y, hist_max_10y, pct_of_range
    """
    metrics: Dict[str, Any] = {
        "yoy_pct": None,
        "roll_12": None,
        "roll_24": None,
        "z_10y": None,
        "hist_min_10y": None,
        "hist_max_10y": None,
        "pct_of_range": None,
    }

    if not observations:
        return metrics

    # Extract numeric values, converting '.' (FRED's N/A) to NaN
    values = []
    for obs in observations:
        val_str = obs.get("value") if isinstance(obs, dict) else None
        if val_str == ".":
            values.append(np.nan)
        else:
            try:
                val = float(val_str if val_str is not None else ".")
                values.append(val if math.isfinite(val) else np.nan)
            except (ValueError, TypeError, OverflowError):
                values.append(np.nan)

    # Check if we have valid data
    if not values or all(np.isnan(v) for v in values):
        return metrics

    current = values[0]
    values_arr = np.array(values)

    # Determine period counts based on frequency
    if frequency == "Q":
        short_periods = max(1, short_months // 3)  # 4 quarters for 12 months
        long_periods = max(2, long_months // 3)  # 8 quarters for 24 months
        z_periods = z_lookback_years * 4  # Quarters in lookback
    elif frequency == "A":
        short_periods = 1
        long_periods = 2
        z_periods = z_lookback_years
    elif frequency == "W":
        # Weekly data
        short_periods = 52  # 1 year
        long_periods = 104  # 2 years
        z_periods = z_lookback_years * 52
    elif frequency == "D":
        # Daily data (approx 260 trading days)
        short_periods = 260  # 1 year
        long_periods = 520  # 2 years
        z_periods = z_lookback_years * 260
    else:  # Monthly or default
        short_periods = short_months
        long_periods = long_months
        z_periods = z_lookback_years * 12

    # YoY percent change: (current - value_1y_ago) / value_1y_ago * 100
    if len(values_arr) > short_periods:
        yoy_val = values_arr[short_periods]
        if not np.isnan(yoy_val) and yoy_val != 0:
            metrics["yoy_pct"] = ((current - yoy_val) / abs(yoy_val)) * 100

    # Rolling 12 (short) average
    if len(values_arr) >= short_periods:
        valid_values = values_arr[:short_periods][~np.isnan(values_arr[:short_periods])]
        if len(valid_values) > 0:
            metrics["roll_12"] = float(np.mean(valid_values))

    # Rolling 24 (long) average
    if len(values_arr) >= long_periods:
        valid_values = values_arr[:long_periods][~np.isnan(values_arr[:long_periods])]
        if len(valid_values) > 0:
            metrics["roll_24"] = float(np.mean(valid_values))

    # Z-score using 10-year lookback mean and std
    lookback_end = min(len(values_arr), z_periods)
    if lookback_end >= 4:  # Need at least 4 observations for meaningful stats
        lookback_values = values_arr[:lookback_end]
        valid_lookback = lookback_values[~np.isnan(lookback_values)]
        if len(valid_lookback) >= 4:
            lookback_mean = np.mean(valid_lookback)
            lookback_std = np.std(valid_lookback)
            if lookback_std != 0:
                metrics["z_10y"] = (current - lookback_mean) / lookback_std

    # Historical min/max for 10-year range
    if lookback_end >= 4:
        valid_lookback = values_arr[:lookback_end][~np.isnan(values_arr[:lookback_end])]
        if len(valid_lookback) >= 4:
            metrics["hist_min_10y"] = float(np.min(valid_lookback))
            metrics["hist_max_10y"] = float(np.max(valid_lookback))

            # Calculate % of range: (current - min) / (max - min) * 100
            hist_range = metrics["hist_max_10y"] - metrics["hist_min_10y"]
            if hist_range != 0:
                metrics["pct_of_range"] = (
                    (current - metrics["hist_min_10y"]) / hist_range
                ) * 100

    return {key: (float(value) if value is not None and math.isfinite(value) else None) for key, value in metrics.items()}


def get_series_info(series_id: str, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Fetches metadata for a specific FRED series.
    Returns info dict with title, units, frequency, seasonal_adjustment, etc.
    """
    if not api_key:
        return None

    series_id = series_id.upper()
    with _cache_lock:
        cached = deepcopy(_info_cache.get(series_id))
    if cached is not None:
        return cached

    with _cache_lock:
        token = object()
        _cache_versions["info", series_id] = token
    try:
        url = f"{BASE_URL}/series"
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        series_list = data.get("seriess", []) if isinstance(data, dict) else []
        if isinstance(series_list, list) and series_list and isinstance(series_list[0], dict):
            with _cache_lock:
                if _cache_versions.get(("info", series_id)) is token:
                    _info_cache[series_id] = deepcopy(series_list[0])
            return deepcopy(series_list[0])
        return None
    except (requests.exceptions.RequestException, ValueError, TypeError, RecursionError):
        logging.error("Could not retrieve FRED metadata for %s", series_id)
        return None


def search_series(search_text: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Searches for FRED series by text.
    """
    if not api_key:
        logging.error("FRED API key is missing.")
        return []

    try:
        url = f"{BASE_URL}/series/search"
        params: dict[str, Any] = {
            "search_text": search_text,
            "api_key": api_key,
            "file_type": "json",
            "limit": 20,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        rows = data.get("seriess", []) if isinstance(data, dict) else []
        return [deepcopy(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    except (requests.exceptions.RequestException, ValueError, TypeError, RecursionError):
        logging.error("Could not search FRED series")
        return []


def get_series_summary(series_id: str, api_key: str) -> Dict[str, Any]:
    """
    Calculates comprehensive summary statistics for a FRED series.

    Returns dict with:
        - Basic info: id, title, current, date, units
        - Enhanced metrics: yoy_pct, roll_12, roll_24, z_10y, hist_min_10y, hist_max_10y, pct_of_range
        - Metadata: frequency, seasonal_adj
    """
    # Initialize with default structure
    summary: Dict[str, Any] = {
        "id": series_id,
        "title": series_id,
        "current": "N/A",
        "date": "N/A",
        "units": "",
        "units_short": "",
        "frequency": "M",
        "seasonal_adj": "",
        # Enhanced metrics
        "yoy_pct": None,
        "roll_12": None,
        "roll_24": None,
        "z_10y": None,
        "hist_min_10y": None,
        "hist_max_10y": None,
        "pct_of_range": None,
        # Legacy fields
        "change_1p": "N/A",  # 1 period change (vs prev)
        "change_1y": "N/A",
        "change_5y": "N/A",
    }

    info = get_series_info(series_id, api_key)

    # Calculate tailored limit based on frequency to optimize data fetching
    # We want ~10 years of data plus a small buffer (11 years)
    tailored_limit = 132  # Default fallback (Monthly)

    if info:
        summary["title"] = info.get("title", series_id)
        summary["units"] = info.get("units") or ""
        summary["units_short"] = info.get("units_short") or ""

        # Parse frequency from info (FRED uses codes like 'Monthly', 'Quarterly', etc.)
        freq_str = str(info.get("frequency") or "").lower()
        if "quarterly" in freq_str:
            summary["frequency"] = "Q"
            tailored_limit = 4 * 11
        elif "annual" in freq_str:
            summary["frequency"] = "A"
            tailored_limit = 15
        elif "daily" in freq_str:
            summary["frequency"] = "D"
            tailored_limit = 260 * 11  # ~2860
        elif "weekly" in freq_str:
            summary["frequency"] = "W"
            tailored_limit = 52 * 11  # ~572
        else:
            summary["frequency"] = "M"
            tailored_limit = 12 * 11  # 132

        # Seasonal adjustment status
        sa_str = (
            info.get("seasonal_adjustment_short")
            or info.get("seasonal_adjustment")
            or ""
        )
        if "seasonally adjusted" in sa_str.lower():
            summary["seasonal_adj"] = "SA"

    # Now fetch observations with optimized limit
    obs_list = get_series_observations(series_id, api_key, limit=tailored_limit)

    if not obs_list:
        return summary

    try:
        obs_list = _observations(obs_list)
        if not obs_list:
            return summary
        # Detect frequency from observations if not determined from metadata
        detected_freq = detect_frequency(obs_list)
        if summary["frequency"] == "M":  # Use detected if metadata wasn't definitive
            summary["frequency"] = detected_freq

        # Get current value and date (Obs List is desc, newest first)
        current_obs = obs_list[0]
        if current_obs["value"] != ".":
            summary["current"] = float(current_obs["value"])
            summary["date"] = current_obs["date"]
        else:
            summary["current"] = "N/A"
            summary["date"] = current_obs["date"]

        # Previous (1 period)
        # IMPORTANT: We must skip computation entirely if prev value is "." (FRED's N/A sentinel).
        # Falling back to 0 would make change_1p equal to the current absolute value, which is misleading.
        if len(obs_list) > 1 and summary["current"] != "N/A":
            prev_obs = obs_list[1]
            try:
                if prev_obs["value"] != ".":
                    prev_val = float(prev_obs["value"])
                    summary["change_1p"] = summary["current"] - prev_val
                # else: leave change_1p as "N/A" — no valid reference period
            except (ValueError, TypeError) as e:
                logging.debug(f"Could not parse previous value for {series_id}: {e}")

        # Pre-parse dates to enable fast binary search using bisect.
        # We parse the descending obs_list in reverse order to get an ascending list of dates.
        parsed_dates_asc = []
        valid_obs_asc = []
        for obs in reversed(obs_list):
            try:
                d = datetime.strptime(obs["date"], "%Y-%m-%d")
                parsed_dates_asc.append(d)
                valid_obs_asc.append(obs)
            except ValueError:
                continue

        # Find the nearest reference within 45 days; ties prefer the earlier date.
        # to avoid linear scans and redundant strptime parsing.
        def find_closest_reference(target_date):
            if not parsed_dates_asc:
                return None
            import bisect
            # bisect_left locates the insertion point to maintain sorted order
            idx = bisect.bisect_left(parsed_dates_asc, target_date)
            candidates = []
            if idx < len(parsed_dates_asc):
                candidates.append((abs((parsed_dates_asc[idx] - target_date).days), idx))
            if idx > 0:
                candidates.append((abs((parsed_dates_asc[idx - 1] - target_date).days), idx - 1))
            if not candidates:
                return None
            # Find candidate with minimal absolute difference in days
            min_diff, best_idx = min(candidates)
            if min_diff < 45:
                return valid_obs_asc[best_idx]
            return None

        # 1 Year Ago
        current_date_obj = datetime.strptime(current_obs["date"], "%Y-%m-%d")
        # Clamp Feb 29 to Feb 28 in a non-leap reference year.
        year_1y = current_date_obj.year - 1
        target_1y = current_date_obj.replace(year=year_1y, day=min(current_date_obj.day, monthrange(year_1y, current_date_obj.month)[1]))
        obs_1y = find_closest_reference(target_1y)
        if obs_1y and summary["current"] != "N/A":
            try:
                if obs_1y["value"] != ".":
                    val_1y = float(obs_1y["value"])
                    summary["change_1y"] = summary["current"] - val_1y
                # else: leave change_1y as "N/A" — no valid reference period
            except (ValueError, TypeError) as e:
                logging.debug(f"Could not parse 1Y ago value for {series_id}: {e}")

        # 5 Year Ago
        year_5y = current_date_obj.year - 5
        target_5y = current_date_obj.replace(year=year_5y, day=min(current_date_obj.day, monthrange(year_5y, current_date_obj.month)[1]))
        obs_5y = find_closest_reference(target_5y)
        if obs_5y and summary["current"] != "N/A":
            try:
                if obs_5y["value"] != ".":
                    val_5y = float(obs_5y["value"])
                    summary["change_5y"] = summary["current"] - val_5y
                # else: leave change_5y as "N/A" — no valid reference period
            except (ValueError, TypeError) as e:
                logging.debug(f"Could not parse 5Y ago value for {series_id}: {e}")

        # Compute enhanced metrics
        enhanced = compute_enhanced_metrics(
            obs_list,
            frequency=summary["frequency"],
            short_months=12,
            long_months=24,
            z_lookback_years=10,
        )
        summary.update(enhanced)

        for key, value in summary.items():
            if isinstance(value, (float, int)) and not math.isfinite(value):
                summary[key] = "N/A" if key in ("current", "change_1p", "change_1y", "change_5y") else None
        return summary
    except Exception as e:
        logging.error(f"Error calculating summary for {series_id}: {e}")
        return summary
