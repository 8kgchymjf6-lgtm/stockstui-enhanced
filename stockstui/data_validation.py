"""Normalize provider/cache numbers and historical frames without mutating input."""
import math
from numbers import Integral
from typing import Any
import numpy as np
import pandas as pd

PRICE_NUMBERS = frozenset({'price','previous_close','day_low','day_high','volume','open',
    'fifty_two_week_low','fifty_two_week_high','pe_ratio','shares','market_cap',
    'dividend_yield','eps','beta','all_time_high'})


def finite_number(value):
    if value is None or isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = value if isinstance(value, (int, float)) else int(value) if isinstance(value, Integral) else float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_price_row(value, symbol: str | None = None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    row = value.copy()
    if symbol is not None:
        row['symbol'] = symbol
    if 'symbol' in row and (not isinstance(row['symbol'], str) or not row['symbol'].strip()):
        return None
    for key in PRICE_NUMBERS & row.keys():
        row[key] = finite_number(row[key])
    if value.get('price') is not None and row.get('price') is None:
        row['_fetch_failed'] = True
        row['_stale'] = True
    if 'currency' in row and not isinstance(row['currency'], str):
        row['currency'] = None
    if 'description' in row and row['description'] is not None:
        row['description'] = str(row['description'])
    return row


def normalize_history_frame(value) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        return pd.DataFrame()
    frame = value.copy(deep=True)
    if isinstance(frame.columns, pd.MultiIndex):
        # Selecting an arbitrary ticker from a multi-symbol payload would mislabel data.
        empty = pd.DataFrame(index=pd.DatetimeIndex([]))
        empty.attrs = frame.attrs.copy()
        return empty
    frame = frame.loc[:, ~frame.columns.duplicated()]
    if not isinstance(frame.index, pd.DatetimeIndex):
        if pd.api.types.is_numeric_dtype(frame.index.dtype):
            return frame.iloc[:0]
        frame.index = pd.to_datetime(frame.index, errors='coerce', utc=True)
    frame = frame.loc[~frame.index.isna()].sort_index()
    for name in ('Open','High','Low','Close','Adj Close','Volume'):
        if name in frame:
            frame[name] = pd.to_numeric(frame[name].map(finite_number), errors='coerce')
            frame[name] = frame[name].where(np.isfinite(frame[name].to_numpy(dtype=float,na_value=np.nan)))
    return frame
