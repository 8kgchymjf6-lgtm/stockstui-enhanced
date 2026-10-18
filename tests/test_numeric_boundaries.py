"""External price/history values cannot crash tables or poison valid cached numbers."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pandas as pd
from hypothesis import given, settings, strategies as st
from textual.app import App
from textual.widgets import DataTable
from stockstui import data_validation as validation
from stockstui.data_providers import market_provider as market
from stockstui.database.db_manager import DbManager
from stockstui.presentation import formatter
from stockstui.ui.widgets.history_chart import HistoryChart
from stockstui.utils import merge_price_data


class TestPriceNumbers(unittest.TestCase):
    def test_invalid_optional_fields_and_old_prices_are_controlled(self):
        data=dict(symbol='TEST',price='12.5',previous_close='10',day_low='bad',day_high=float('inf'),eps='not numeric',beta=float('nan'),volume=float('inf'),currency={},all_time_high='20')
        result=formatter.format_price_data_for_table([None,[],data],{'TEST':'bad'}, {})
        self.assertEqual(len(result),1);row=result[0]
        self.assertEqual(row['Price'],12.5);self.assertEqual(row['Change'],2.5)
        self.assertEqual(row["Day's Range"],'N/A');self.assertEqual(row['EPS'],'N/A')
        self.assertEqual(row['Volume'],'N/A');self.assertEqual(row['Beta'],'N/A')
        self.assertIsNone(row['_change_direction']);self.assertEqual(data['price'],'12.5')

    def test_zero_eps_and_beta_are_valid_numbers(self):
        row=formatter.format_price_data_for_table([dict(symbol='TEST',eps=0,beta=0)],{}, {})[0]
        self.assertEqual(row['EPS'],'0.00');self.assertEqual(row['Beta'],'0.00')

    def test_invalid_new_values_do_not_replace_cached_valid_numbers(self):
        old=dict(symbol='TEST',price=10,all_time_high=20)
        merged=merge_price_data(old,dict(price=float('inf'),all_time_high=float('nan')))
        self.assertEqual(merged['price'],10);self.assertEqual(merged['all_time_high'],20)
        self.assertTrue(merged['_fetch_failed']);self.assertTrue(merged['_stale'])
        self.assertEqual(old['price'],10)

    def test_derived_overflow_is_unavailable(self):
        row=formatter.format_price_data_for_table([dict(symbol='TEST',price=1e308,previous_close=-1e308,all_time_high=1e-308,dividend_yield=1e308)],{}, {})[0]
        self.assertIsNone(row['Change']);self.assertIsNone(row['% Change']);self.assertIsNone(row['% Off ATH'])
        self.assertEqual(formatter.format_market_cap(float('inf')),'N/A')
        self.assertEqual(row['Div Yield'],'N/A')

    def test_bad_live_price_keeps_old_fetch_time_and_marks_stale(self):
        now=datetime.now(timezone.utc);old_time='2026-10-17T10:00:00+00:00'
        entry=dict(expiry=now,data=dict(symbol='TEST',price=10,previous_close=9,_fetched_at=old_time))
        with patch.object(market,'_price_cache',{'TEST':entry}),patch.object(market,'_info_cache',{'TEST':{'quoteType':'CRYPTOCURRENCY','exchange':'NYSE'}}),patch.object(market,'_fetch_and_cache_slow_data'),patch.object(market,'_fetch_fast_data',return_value={'TEST':{'price':float('inf')}}):
            rows=market.get_market_price_data(['TEST'])
        self.assertEqual(rows[0]['price'],10);self.assertEqual(rows[0]['_fetched_at'],old_time);self.assertTrue(rows[0]['_stale'])

    @given(st.one_of(st.none(),st.booleans(),st.floats(),st.integers(),st.text(max_size=20)))
    @settings(max_examples=150,deadline=None)
    def test_numeric_input_is_finite_or_unavailable(self,value):
        normalized=validation.finite_number(value)
        self.assertTrue(normalized is None or math.isfinite(normalized))
        rows=formatter.format_price_data_for_table([dict(symbol='TEST',price=value,previous_close=1,eps=value,beta=value,day_low=value,day_high=value)],{}, {})
        self.assertEqual(len(rows),1)


class TestHistoryNumbers(unittest.IsolatedAsyncioTestCase):
    async def test_partial_history_and_invalid_volume_render_as_unavailable(self):
        original=pd.DataFrame({'Close':['12.5',float('inf'),13], 'Volume':[None,float('inf'),'bad']},index=['2026-01-01','bad','2026-01-03'])
        original.attrs['currency']='DKK'
        app=App()
        async with app.run_test():
            table=formatter.format_historical_data_as_table(original)
            await app.mount(table)
            self.assertEqual(table.row_count,2)
            self.assertEqual(table.get_row_at(0),['2026-01-01','N/A','N/A','N/A','DKK12.50','N/A'])
            self.assertEqual(len(original),3)

    async def test_empty_columns_and_numeric_indexes_do_not_crash_table(self):
        app=App()
        async with app.run_test():
            for frame in (pd.DataFrame({'Close':[1]}),pd.DataFrame(index=pd.to_datetime(['2026-01-01'])),pd.DataFrame({'Volume':[float('nan')]},index=pd.to_datetime(['2026-01-01']))):
                table=formatter.format_historical_data_as_table(frame);await app.mount(table)
                self.assertLessEqual(table.row_count,1);await table.remove()

    def test_chart_ticks_accept_finite_extreme_ranges(self):
        chart=HistoryChart(pd.DataFrame(),'1d')
        values=[-np.finfo(float).max,-1e308,-1e-300,0,1e-300,1e308,np.finfo(float).max]
        for low in values:
            for high in values:
                if low<=high:
                    with self.subTest(low=low,high=high):
                        ticks=chart._get_nice_y_ticks(float(low),float(high))
                        self.assertLessEqual(len(ticks),256);self.assertTrue(all(math.isfinite(tick) for tick in ticks))
        chart=HistoryChart(pd.DataFrame({'Close':[5e-324,1e-323]},index=pd.to_datetime(['2026-01-01','2026-01-02'])),'1mo')
        chart._y_scale=1e-323;plot=MagicMock()
        with patch.object(HistoryChart,'plt',new_callable=PropertyMock,return_value=plot):
            chart._set_price_ticks()
        low,high=plot.ylim.call_args.args
        self.assertLessEqual(low,0.5);self.assertGreaterEqual(high,1.0)
        chart._y_scale=1.0
        self.assertEqual(chart._price_label(0.00001),'1.00e-05')
        self.assertEqual(chart._price_label(1e50),'1.00e+50')
        self.assertEqual(chart._price_label(10),'10.00')


class TestCachePayloads(unittest.TestCase):
    def test_invalid_cached_shapes_and_timestamps_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            db=DbManager(Path(root)/'cache.db')
            self.addCleanup(db.close)
            now=datetime.now(timezone.utc).timestamp()+60
            for symbol,value,stamp in [('GOOD',{'price':'12.5'},now),('LIST',[],now),('NULL',None,now),('OVERFLOW',{},float('inf'))]:
                db.conn.execute('INSERT INTO price_cache VALUES (?,?,?)',(symbol,json.dumps(value),stamp))
            db.conn.commit()
            rows=db.load_price_cache_from_db()
            self.assertEqual(set(rows),{'GOOD'});self.assertEqual(rows['GOOD']['data']['price'],12.5)


class TestSplitUnits(unittest.TestCase):
    def test_split_does_not_keep_highs_from_old_share_units(self):
        now=datetime.now(timezone.utc)
        before=datetime(2026,1,1,tzinfo=timezone.utc)
        split=datetime(2026,1,2,tzinfo=timezone.utc).timestamp()
        old=dict(expiry=now,data=dict(symbol='TEST',price=100,previous_close=99,all_time_high=150,eps=4,_fetched_at=before.isoformat()))
        ticker=type('Ticker',(),{'info':dict(currency='USD',exchange='NYSE',regularMarketPrice=50,allTimeHigh=75,lastSplitDate=split,regularMarketTime=split,sharesOutstanding=200),'fast_info':{}})()
        with patch.object(market,'_price_cache',{'TEST':old}),patch.object(market,'_info_cache',{}),patch.object(market.yf,'Ticker',return_value=ticker),patch.object(market,'_calculate_info_expiry',return_value=now):
            market._fetch_and_cache_slow_data(['TEST'])
            row=market._price_cache['TEST']['data']
        self.assertEqual(row['price'],50);self.assertEqual(row['all_time_high'],75)
        self.assertIsNone(row.get('eps'));self.assertEqual(row['_last_split_at'],split)


class TestExtremeChart(unittest.IsolatedAsyncioTestCase):
    async def test_extreme_finite_prices_do_not_crash_plot_rendering(self):
        class ChartApp(App):
            def __init__(self,chart):super().__init__();self.chart=chart
            def compose(self):yield self.chart
        for values in ([1e308,-1e308],[1e308,1e308],[1e-300,2e-300],
                       [5e-324,1e-323],[-1e-323,-5e-324],[1e50,2e50],[.00001,.00002]):
            with self.subTest(values=values):
                chart=HistoryChart(pd.DataFrame({'Close':values},index=pd.to_datetime(['2026-01-01','2026-01-02'])),'1mo')
                async with ChartApp(chart).run_test() as pilot:await pilot.pause()
