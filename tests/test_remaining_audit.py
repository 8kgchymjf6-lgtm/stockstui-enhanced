"""Close audit A7/B2/B3/C2 using real workers, widgets and provider boundaries."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
from textual.widgets import Select, Tabs, DataTable
from textual.worker import WorkerCancelled
from stockstui.common import OptionsDataUpdated, OptionsExpirationsUpdated
from stockstui.data_providers import fred_provider as fred, options_provider as options
from stockstui.main import StocksTUI
from stockstui.ui.views.options_view import OptionsView

DATES = ['2027-01-15', '2027-02-19']


def chain(value=10, underlying=None):
    frame = pd.DataFrame([dict(contractSymbol='C1',strike=100,lastPrice=value,
                              bid=value-1,ask=value+1,openInterest=10,volume=5)])
    return dict(calls=frame,puts=pd.DataFrame(),underlying=underlying)


class TestFredLeapYear(unittest.TestCase):
    def summary(self, observations):
        with patch.object(fred,'get_series_info',return_value={'frequency':'Daily'}), patch.object(
            fred,'get_series_observations',return_value=observations
        ):
            return fred.get_series_summary('TEST','isolated-test-key')

    def test_leap_day_retains_one_and_five_year_and_enhanced_metrics(self):
        result=self.summary([dict(date=d,value=v) for d,v in [
            ('2024-02-29','110'),('2024-02-28','105'),('2023-02-28','100'),('2019-02-28','80')]])
        self.assertEqual(result['change_1p'],5)
        self.assertEqual(result['change_1y'],10)
        self.assertEqual(result['change_5y'],30)
        self.assertEqual(result['hist_max_10y'],110)

    def test_ordinary_date_retains_existing_results(self):
        result=self.summary([dict(date=d,value=v) for d,v in [
            ('2024-02-28','110'),('2024-02-27','105'),('2023-02-28','100'),('2019-02-28','80')]])
        self.assertEqual((result['change_1p'],result['change_1y'],result['change_5y']),(5,10,30))

    def test_missing_one_year_does_not_remove_five_year_result(self):
        result=self.summary([dict(date=d,value=v) for d,v in [('2024-02-29','110'),('2024-02-28','108'),('2024-02-27','106'),('2019-02-28','80')]])
        self.assertEqual(result['change_1y'],'N/A')
        self.assertEqual(result['change_5y'],30)
        self.assertEqual(result['hist_max_10y'],110)

    def test_nearest_reference_policy_and_tie_prefer_earlier_observation(self):
        result=self.summary([dict(date=d,value=v) for d,v in [
            ('2024-02-29','110'),('2023-03-01','999'),('2023-02-27','100'),('2019-02-28','80')]])
        self.assertEqual(result['change_1y'],10)

    def test_missing_sentinel_for_one_period_does_not_remove_others(self):
        result=self.summary([dict(date=d,value=v) for d,v in [
            ('2024-02-29','110'),('2023-02-28','.'),('2019-02-28','80')]])
        self.assertEqual(result['change_1y'],'N/A')
        self.assertEqual(result['change_5y'],30)


class TestPartialOptionsProvider(unittest.TestCase):
    def setUp(self):
        options.clear_options_cache()
        self.addCleanup(options.clear_options_cache)

    def test_none_underlying_and_missing_puts_preserve_calls(self):
        raw=SimpleNamespace(calls=chain()['calls'],puts=None,underlying=None)
        with patch.object(options.yf,'Ticker',return_value=SimpleNamespace(option_chain=lambda **k:raw)):
            result=options.get_options_chain('AAPL',DATES[0],use_cache=False)
        self.assertEqual(result['underlying'],{})
        self.assertEqual(len(result['calls']),1)
        self.assertTrue(result['puts'].empty)

    def test_missing_numeric_fields_and_nullable_values_normalize_safely(self):
        raw=dict(calls=pd.DataFrame([dict(strike='100',contractSymbol='C1',lastPrice=None,volume=pd.NA)]),underlying=123)
        result=options.normalize_options_data(raw)
        self.assertEqual(len(result['calls']),1)
        self.assertTrue(pd.isna(result['calls'].iloc[0]['volume']))
        self.assertTrue(pd.isna(result['calls'].iloc[0]['lastPrice']))
        self.assertEqual(result['underlying'],{})
        self.assertNotIn('openInterest',raw['calls'])

    def test_unusable_rows_are_removed_without_discarding_good_rows(self):
        raw=chain();frame=raw['calls']
        raw['calls']=pd.concat([frame,pd.DataFrame([dict(strike='bad',contractSymbol='C2'),dict(strike=100,contractSymbol=None)]),frame],ignore_index=True)
        self.assertEqual(len(options.normalize_options_data(raw)['calls']),1)
        self.assertTrue(options.normalize_options_data(dict(calls=pd.DataFrame([{'foo':1}])))['calls'].empty)
        with self.assertRaises(ValueError):options.normalize_options_data(dict(calls=['invalid']))

    def test_older_chain_request_cannot_replace_newer_cache(self):
        entered,release=threading.Event(),threading.Event()
        def make_ticker(symbol):
            def get_chain(**kwargs):
                value=10
                if threading.current_thread().name.startswith('old-chain'):
                    entered.set()
                    if not release.wait(10):raise TimeoutError('Test did not release old call')
                else:value=99
                raw=chain(value)
                return SimpleNamespace(**raw)
            return SimpleNamespace(option_chain=get_chain)
        try:
            with patch.object(options.yf,'Ticker',side_effect=make_ticker), ThreadPoolExecutor(max_workers=1,thread_name_prefix='old-chain') as pool:
                old=pool.submit(options.get_options_chain,'AAPL',DATES[0],False)
                self.assertTrue(entered.wait(5))
                latest=options.get_options_chain('AAPL',DATES[0],False)
                release.set();old.result(timeout=5)
                cached=options.get_options_chain('AAPL',DATES[0])
                self.assertEqual(cached['calls'].iloc[0]['lastPrice'],99)
                latest['calls'].loc[0,'lastPrice']=1
                self.assertEqual(options.get_options_chain('AAPL',DATES[0])['calls'].iloc[0]['lastPrice'],99)
        finally:release.set()

    def test_older_expirations_request_cannot_replace_newer_cache(self):
        entered,release=threading.Event(),threading.Event()
        def ticker(symbol):
            if threading.current_thread().name.startswith('old-expiry'):
                entered.set()
                if not release.wait(10):raise TimeoutError('Test did not release old call')
                return SimpleNamespace(options=(DATES[0],))
            return SimpleNamespace(options=(DATES[1],))
        try:
            with patch.object(options.yf,'Ticker',side_effect=ticker),ThreadPoolExecutor(max_workers=1,thread_name_prefix='old-expiry') as pool:
                old=pool.submit(options.get_available_expirations,'AAPL',False)
                self.assertTrue(entered.wait(5))
                options.get_available_expirations('AAPL',False)
                release.set();old.result(timeout=5)
                self.assertEqual(options.get_available_expirations('AAPL'),(DATES[1],))
        finally:release.set()


class TestOptionsRequestStability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        for p in (patch('stockstui.config_manager.dirs',SimpleNamespace(user_config_dir=str(root/'config'),user_cache_dir=str(root/'cache'))),
                  patch('stockstui.main.market_provider.get_market_price_data',return_value=[]),
                  patch('stockstui.main.market_provider.get_market_status',return_value={}),
                  patch.object(options,'get_options_chain',side_effect=lambda *a,**k:chain()),
                  patch.object(options,'get_available_expirations',return_value=tuple(DATES))):
            p.start();self.addCleanup(p.stop)
        self.app=StocksTUI(cli_overrides={'tab':'options'})
        self.app.config.settings['auto_refresh']=False
        self.addCleanup(self.app.db_manager.close)

    async def settle(self,pilot):
        for _ in range(40):
            workers=list(self.app.workers)
            if workers:
                results=await asyncio.wait_for(asyncio.gather(*(w.wait() for w in workers),return_exceptions=True),15)
                for result in results:
                    if isinstance(result,BaseException) and not isinstance(result,WorkerCancelled):raise result
            await pilot.pause()
            if not list(self.app.workers):return
        raise TimeoutError('Workers did not settle')

    def request(self,ticker='AAPL',expiry=DATES[0]):
        view=self.app.query_one(OptionsView)
        select=view.query_one('#options-expiration-select',Select)
        with view.prevent(Select.Changed):
            select.set_options([(d,d) for d in DATES]);select.disabled=False;select.value=expiry
        self.app.options_ticker=ticker
        self.app.query_one('#options-display-container').loading=True
        return self.app.fetch_options_chain(ticker,expiry)

    def message(self,value=1,**changes):
        data=chain(value)
        args=dict(ticker=self.app.options_ticker,expiration=self.app._options_request_key[1],calls_data=data['calls'],puts_data=data['puts'],underlying=None,request_id=self.app._options_request_serial)
        args.update(changes);return OptionsDataUpdated(**args)

    async def test_none_exception_and_invalid_response_finish_loading_and_recover(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            for response in (None,TimeoutError('offline'),TimeoutError(),{'calls':['invalid']}):
                with patch.object(options,'get_options_chain',side_effect=response if isinstance(response,Exception) else None,return_value=response):
                    self.request();await self.settle(pilot)
                self.assertFalse(self.app.query_one('#options-display-container').loading)
                self.assertIn('error',self.app._last_options_data)
                self.assertTrue(self.app.query('#options-display-container > Static'))
            self.request();await self.settle(pilot)
            self.assertFalse(self.app.query_one('#options-display-container').loading)
            self.assertEqual(self.app.query_one('#options-calls-table',DataTable).row_count,1)

    async def test_partial_underlying_and_missing_fields_render_table_and_chart(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            data=dict(calls=pd.DataFrame([dict(contractSymbol='C1',strike=100,lastPrice=None,volume=pd.NA)]),puts=None,underlying=None)
            with patch.object(options,'get_options_chain',return_value=data):
                self.request();await self.settle(pilot)
            table=self.app.query_one('#options-calls-table',DataTable)
            self.assertEqual(table.row_count,1)
            self.assertIn('—',str(table.get_row_at(0)))
            header=self.app.query_one('.options-info-header')
            self.assertIn('Underlying: unavailable',str(header.renderable))
            self.app.query_one(OptionsView).action_toggle_chart();await pilot.pause()

    async def test_late_ticker_expiry_generation_and_unselected_expiry_do_not_change_state(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);self.request('MSFT',DATES[1]);await self.settle(pilot)
            latest=self.app._last_options_data;container=self.app.query_one('#options-display-container')
            for changes in (dict(ticker='AAPL'),dict(expiration=DATES[0]),dict(request_id=0)):
                container.loading=True
                await self.app.on_options_data_updated(self.message(**changes))
                self.assertIs(self.app._last_options_data,latest);self.assertTrue(container.loading)
            with self.app.query_one(OptionsView).prevent(Select.Changed):
                self.app.query_one('#options-expiration-select',Select).value=DATES[0]
            await self.app.on_options_data_updated(self.message())
            self.assertIs(self.app._last_options_data,latest)

    async def test_same_request_and_switch_away_back_reject_old_messages(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);self.request();await self.settle(pilot)
            old=self.message()
            for ticker,expiry in [('MSFT',DATES[0]),('AAPL',DATES[1]),('AAPL',DATES[0]),('AAPL',DATES[0])]:
                self.request(ticker,expiry);await self.settle(pilot)
            latest=self.app._last_options_data
            await self.app.on_options_data_updated(old)
            self.assertIs(self.app._last_options_data,latest)

    async def test_slow_cancelled_thread_cannot_replace_new_expiry(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            entered,release,finished=threading.Event(),threading.Event(),threading.Event()
            def provider(ticker,expiry):
                if expiry==DATES[0]:
                    entered.set()
                    try:
                        if not release.wait(10):raise TimeoutError('Test did not release worker')
                        return chain(1)
                    finally:finished.set()
                return chain(99)
            try:
                with patch.object(options,'get_options_chain',side_effect=provider):
                    old=self.request();self.assertTrue(await asyncio.to_thread(entered.wait,5))
                    current=self.request(expiry=DATES[1]);await current.wait();await pilot.pause()
                    release.set();self.assertTrue(await asyncio.to_thread(finished.wait,5));await pilot.pause()
                    self.assertTrue(old.is_cancelled)
                self.assertEqual(self.app._last_options_data['expiration'],DATES[1])
                self.assertEqual(self.app._last_options_data['calls'].iloc[0]['lastPrice'],99)
            finally:release.set()

    async def test_expiration_failure_and_empty_list_finish_loading_then_retry(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);view=self.app.query_one(OptionsView);self.app.options_ticker='AAPL'
            for error in (None,TimeoutError('offline')):
                with patch.object(options,'get_available_expirations',side_effect=error,return_value=None):
                    view._request_expirations();await self.settle(pilot)
                select=view.query_one(Select)
                self.assertTrue(select.disabled);self.assertEqual(select.value,'')
                self.assertFalse(self.app.query_one('#options-display-container').loading)
                self.assertIn('error',self.app._last_options_data)
            view._request_expirations();await self.settle(pilot)
            self.assertFalse(view.query_one(Select).disabled)
            self.assertEqual(self.app.query_one('#options-calls-table',DataTable).row_count,1)

    async def test_expiration_generation_protects_same_ticker_and_reset_selection(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);view=self.app.query_one(OptionsView)
            for ticker in ['AAPL','MSFT','AAPL']:
                self.app.options_ticker=ticker;view._request_expirations();await self.settle(pilot)
                if ticker=='AAPL' and self.app._options_expirations_serial==1:
                    old=OptionsExpirationsUpdated(ticker,(DATES[1],),1)
            await self.app.on_options_expirations_updated(old)
            self.assertEqual(view.expirations,DATES)
            with patch.object(self.app,'_fetch_options_expirations'):
                self.app.options_ticker='MSFT';view._request_expirations()
                self.assertIsNone(self.app._last_options_data)
                select=view.query_one(Select)
                self.assertTrue(select.disabled);self.assertEqual(select.value,'')
                with patch.object(self.app,'fetch_options_chain') as fetch:
                    view.on_expiration_changed(Select.Changed(select,DATES[0]))
                    fetch.assert_not_called()

    async def test_current_cancellation_clears_loading_and_allows_retry(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);entered,release=threading.Event(),threading.Event()
            def held(*args):
                entered.set();release.wait(10);return chain()
            try:
                with patch.object(options,'get_options_chain',side_effect=held):
                    worker=self.request();self.assertTrue(await asyncio.to_thread(entered.wait,5))
                    worker.cancel();await pilot.pause()
                    self.assertFalse(self.app.query_one('#options-display-container').loading)
                    release.set()
                self.request();await self.settle(pilot)
                self.assertEqual(self.app.query_one('#options-calls-table',DataTable).row_count,1)
            finally:release.set()

    async def test_expirations_and_chain_can_finish_while_another_tab_is_open(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);view=self.app.query_one(OptionsView)
            self.app.options_ticker='AAPL';view._request_expirations()
            index=next(i for i,t in enumerate(self.app.tab_map,1) if t['category']=='all')
            self.app.query_one(Tabs).active=f'tab-{index}';await self.settle(pilot)
            self.assertFalse(self.app.query_one('#options-display-container').loading)
            self.assertEqual(self.app.query_one('#options-calls-table',DataTable).row_count,1)

    async def test_closing_rejects_requests_and_results(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot);self.request();await self.settle(pilot)
            latest=self.app._last_options_data
            with patch.object(self.app,'_closing',True):
                await self.app.on_options_data_updated(self.message())
                self.assertIsNone(self.app.fetch_options_chain('MSFT',DATES[1]))
                self.assertIsNone(self.app.fetch_options_expirations('MSFT'))
            self.assertIs(self.app._last_options_data,latest)
