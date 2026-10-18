"""Regression coverage for the second review of failure and stale-result paths."""
import asyncio
from datetime import datetime, timezone
import logging
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pandas as pd
from textual.app import App

from stockstui.data_providers import market_provider as market, fred_provider as fred
from stockstui.log_handler import TextualHandler
from stockstui.presentation.formatter import format_news_for_display
from stockstui.ui.widgets.history_chart import HistoryChart


class TestNewsBoundaries(unittest.TestCase):
    def setUp(self):
        self.old = market._news_cache
        market._news_cache = {}
        self.addCleanup(setattr, market, '_news_cache', self.old)

    def test_empty_success_is_not_a_network_failure(self):
        with patch.object(market, 'get_news_data', return_value=[]):
            self.assertEqual(market.get_news_for_tickers(['AAPL']), [])

    def test_failure_of_one_ticker_keeps_valid_other_tickers(self):
        valid = dict(link='https://example.org/a', title='A', publish_datetime_utc=datetime.now(timezone.utc))
        def fetch(ticker):
            if ticker == 'BAD': raise OSError('offline')
            return [valid]
        with patch.object(market, 'get_news_data', side_effect=fetch):
            self.assertEqual(market.get_news_for_tickers(['BAD','AAPL']), [valid])

    def test_missing_and_naive_dates_sort_without_losing_valid_articles(self):
        rows=[dict(link=f'https://example.org/{n}', title=n, publish_datetime_utc=date) for n,date in
              [('unknown',None),('naive',datetime(2026,1,2)),('aware',datetime(2026,1,3,tzinfo=timezone.utc))]]
        with patch.object(market, 'get_news_data', return_value=rows):
            result=market.get_news_for_tickers(['AAPL'])
        self.assertEqual([r['title'] for r in result], ['aware','naive','unknown'])

    def test_null_nested_fields_and_bad_rows_do_not_abort_other_articles(self):
        raw=[None, {'content':None}, {'content':{'title':None,'provider':None,'canonicalUrl':None}},
             {'content':{'title':'Good','provider':{'displayName':'Publisher'},'canonicalUrl':{'url':'https://example.org/good'},'pubDate':42}}]
        with patch.object(market, 'get_ticker_info', return_value={'symbol':'AAPL'}), patch.object(market.yf, 'Ticker') as ticker:
            ticker.return_value.news=raw
            rows=market.get_news_data('AAPL')
        self.assertTrue(any(r['title']=='Good' for r in rows))
        text,urls=format_news_for_display(rows)
        self.assertIn('Good',str(text))

    def test_cache_is_not_mutated_by_callers(self):
        now=datetime.now(timezone.utc)
        market._news_cache['AAPL']=(now,[{'title':'Original'}])
        rows=market.get_news_data('AAPL');rows[0]['title']='Changed'
        self.assertEqual(market.get_news_data('AAPL')[0]['title'],'Original')

    def test_news_formatter_accepts_null_optional_text(self):
        text,urls=format_news_for_display([dict(title=None,publisher=None,summary=None,publish_time=None,link=None)])
        self.assertEqual(urls,[])
        self.assertIsInstance(str(text),str)

    def test_article_without_url_is_shown_once_as_plain_text(self):
        row=dict(title='Article without link',link=None,publisher='Test')
        with patch.object(market,'get_news_data',return_value=[row]):
            rows=market.get_news_for_tickers(['AAPL','MSFT'])
        self.assertEqual(rows,[row])
        text,urls=format_news_for_display(rows)
        self.assertIn(row['title'],str(text));self.assertEqual(urls,[])


class TestFredBoundaries(unittest.TestCase):
    def setUp(self):
        self.series=fred._series_cache;self.info=fred._info_cache
        fred._series_cache={};fred._info_cache={}
        self.addCleanup(setattr,fred,'_series_cache',self.series)
        self.addCleanup(setattr,fred,'_info_cache',self.info)

    def test_cached_observations_honor_limit_and_are_copies(self):
        rows=[dict(date=f'2026-01-0{n}',value=str(n)) for n in range(5,0,-1)]
        fred._series_cache['TEST']=(datetime.now(timezone.utc),rows)
        result=fred.get_series_observations('TEST','test-key',limit=2)
        self.assertEqual(len(result),2)
        result[0]['value']='changed'
        self.assertEqual(rows[0]['value'],'5')

    def test_malformed_response_shapes_are_controlled(self):
        for data in ([],None,{'observations':None},{'observations':[None,{'value':'1'}]}):
            with self.subTest(data=data), patch.object(fred.requests,'get') as get:
                get.return_value.json.return_value=data
                self.assertIsNone(fred.get_series_observations('TEST','test-key'))

    def test_request_errors_do_not_log_secret_api_keys(self):
        error=fred.requests.RequestException('https://api.example.org?api_key=SECRET-VALUE')
        with patch.object(fred.requests,'get',side_effect=error), self.assertLogs(level='ERROR') as logs:
            self.assertIsNone(fred.get_series_observations('TEST','SECRET-VALUE'))
        self.assertNotIn('SECRET-VALUE',' '.join(logs.output))

    def test_metadata_cache_is_a_copy(self):
        fred._info_cache['TEST']={'title':'Original'}
        result=fred.get_series_info('TEST','test-key');result['title']='Changed'
        self.assertEqual(fred.get_series_info('TEST','test-key')['title'],'Original')
        fred.clear_cache(['test'])
        self.assertNotIn('TEST',fred._info_cache)


class TestLogDispatch(unittest.IsolatedAsyncioTestCase):
    async def test_ui_thread_warnings_are_displayed(self):
        app=App();app.config=SimpleNamespace(get_setting=lambda *args:False)
        async with app.run_test():
            handler=TextualHandler(app)
            with patch.object(app,'notify') as notify:
                handler.emit(logging.makeLogRecord(dict(msg='Warning from UI',levelno=logging.WARNING,levelname='WARNING')))
                notify.assert_called_once()

    async def test_worker_thread_warnings_are_displayed(self):
        app=App();app.config=SimpleNamespace(get_setting=lambda *args:False)
        async with app.run_test():
            handler=TextualHandler(app)
            with patch.object(app,'notify') as notify:
                await asyncio.to_thread(handler.emit,logging.makeLogRecord(dict(msg='Worker',levelno=logging.WARNING,levelname='WARNING')))
                notify.assert_called_once()


class TestChartBoundaries(unittest.TestCase):
    def test_nonfinite_ticks_are_rejected_without_numpy_errors(self):
        chart=HistoryChart(pd.DataFrame(),'1d')
        for low,high in ((0,float('inf')),(float('nan'),2),(-float('inf'),float('inf'))):
            with self.subTest(low=low,high=high):self.assertEqual(chart._get_nice_y_ticks(low,high),[])

    def test_bad_history_rows_are_removed_without_mutating_provider_data(self):
        original=pd.DataFrame({'Close':[10,float('inf'),'invalid',12]},index=['2026-01-01','2026-01-02','bad','2026-01-04'])
        original.attrs['currency']='DKK'
        chart=HistoryChart(original,'1mo')
        self.assertEqual(len(chart._data),2)
        self.assertTrue(isinstance(chart._data.index,pd.DatetimeIndex))
        self.assertEqual(chart._data['Close'].tolist(),[10,12])
        self.assertEqual(len(original),4)
        self.assertEqual(chart._data.attrs['currency'],'DKK')


class TestCacheGeneration(unittest.TestCase):
    def test_slow_fred_metadata_cannot_replace_newer_or_repopulate_after_clear(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        for clear in (False,True):
            with self.subTest(clear=clear):
                fred.clear_cache();entered=threading.Event();release=threading.Event()
                def old_json():entered.set();release.wait(5);return {'seriess':[{'title':'old'}]}
                old_reply=MagicMock();old_reply.json.side_effect=old_json
                new_reply=MagicMock();new_reply.json.return_value={'seriess':[{'title':'new'}]}
                with patch.object(fred.requests,'get',side_effect=[old_reply,new_reply]),ThreadPoolExecutor(max_workers=2) as pool:
                    old=pool.submit(fred.get_series_info,'test','key')
                    try:
                        self.assertTrue(entered.wait(5))
                        if clear:fred.clear_cache()
                        else:self.assertEqual(fred.get_series_info('TEST','key')['title'],'new')
                    finally:release.set()
                    old.result(5)
                if clear:self.assertNotIn('TEST',fred._info_cache)
                else:self.assertEqual(fred._info_cache['TEST']['title'],'new')
        fred.clear_cache()

    def test_slow_news_cannot_replace_newer_result_or_repopulate_cleared_cache(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        entered=threading.Event();release=threading.Event()
        class Reply:
            def __init__(self,title,blocked=False):self.title=title;self.blocked=blocked
            @property
            def news(self):
                if self.blocked:entered.set();release.wait(5)
                return [{'content':{'title':self.title,'canonicalUrl':{'url':'https://example.org/'+self.title}}}]
        market.clear_news_cache()
        with patch.object(market,'get_ticker_info',return_value={'symbol':'AAPL'}),patch.object(market.yf,'Ticker',side_effect=[Reply('old',True),Reply('new')]),ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(market.get_news_data,'AAPL',True)
            try:
                self.assertTrue(entered.wait(5));self.assertEqual(market.get_news_data('AAPL',True)[0]['title'],'new')
            finally:release.set()
            old.result(5)
        self.assertEqual(market.get_news_data('AAPL')[0]['title'],'new')
        market.clear_news_cache()

    def test_slow_fred_observations_cannot_replace_newer_or_repopulate_after_clear(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        for clear in (False,True):
            with self.subTest(clear=clear):
                fred.clear_cache();entered=threading.Event();release=threading.Event()
                def old_json():entered.set();release.wait(5);return {'observations':[{'date':'2026-01-01','value':'1'}]}
                old_response=MagicMock();old_response.json.side_effect=old_json
                new_response=MagicMock();new_response.json.return_value={'observations':[{'date':'2026-01-01','value':'2'}]}
                with patch.object(fred.requests,'get',side_effect=[old_response,new_response]),ThreadPoolExecutor(max_workers=2) as pool:
                    old=pool.submit(fred.get_series_observations,'TEST','key',2)
                    try:
                        self.assertTrue(entered.wait(5))
                        if clear:fred.clear_cache()
                        else:self.assertEqual(fred.get_series_observations('TEST','key',2)[0]['value'],'2')
                    finally:release.set()
                    old.result(5)
                if clear:self.assertNotIn('TEST',fred._series_cache)
                else:self.assertEqual(fred._series_cache['TEST'][1][0]['value'],'2')
        fred.clear_cache()

    def test_cancelled_news_batch_does_not_start_more_requests(self):
        calls=[]
        def fetch(ticker):calls.append(ticker);return []
        with patch.object(market,'get_news_data',side_effect=fetch):
            market.get_news_for_tickers(['AAPL','MSFT','GOOG'],cancelled=lambda:bool(calls))
        self.assertEqual(calls,['AAPL'])


class TestFiniteGreeks(unittest.TestCase):
    def test_nonfinite_model_inputs_do_not_produce_nan_numbers(self):
        from stockstui.utils.black_scholes import calculate_greeks
        for index in range(6):
            values=[100.,100.,1.,.05,.2,0.]
            values[index]=float('nan')
            self.assertEqual(calculate_greeks('c',*values),{})
