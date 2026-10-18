"""Status belongs to the visible price list and never leaks into another tab."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from textual.widgets import Label, Tabs
from textual.worker import WorkerCancelled
from stockstui.common import PriceDataUpdated
from stockstui.data_providers import market_provider as provider
from stockstui.main import StocksTUI
from stockstui.ui.views.fred_view import FredView
from stockstui.ui.widgets.tag_filter import TagFilterChanged


class TestTabStatus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.rows = {symbol: dict(symbol=symbol, description=symbol, currency='USD',
                    price=100., previous_close=99., _fetched_at=f'2026-10-18T{hour}:00+00:00',
                    _stale=False) for symbol,hour in [('AAPL','10:01'),('^GSPC','11:02'),('BTC-USD','12:03')]}
        for p in (patch('stockstui.config_manager.dirs',SimpleNamespace(user_config_dir=str(root/'config'),user_cache_dir=str(root/'cache'))),
                  patch.object(provider,'_price_cache',{}),patch.object(provider,'_info_cache',{}),
                  patch.object(provider,'get_market_status',return_value={}),
                  patch.object(provider,'get_market_price_data',side_effect=self.fetch),
                  patch.object(FredView,'load_all_series')):
            p.start();self.addCleanup(p.stop)
        self.app=StocksTUI(cli_overrides={'tab':'aktier'})
        self.app.config.lists={name:[dict(ticker=symbol,alias=symbol,note='',tags='test')]
                               for name,symbol in [('aktier','AAPL'),('indeks','^GSPC'),('krypto','BTC-USD')]}
        self.app.config.lists.update(empty=[],cold=[dict(ticker='NEW',alias='NEW',note='',tags='')])
        self.app.config.settings.update(hidden_tabs=[],auto_refresh=False)
        self.app._refresh_hidden_tabs();self.app._setup_dynamic_tabs()
        self.addCleanup(self.app.db_manager.close)

    def fetch(self,symbols,**kwargs):
        rows=[deepcopy(self.rows[s]) for s in symbols if s in self.rows]
        provider.populate_price_cache({row['symbol']:dict(expiry=datetime.now(timezone.utc)+timedelta(hours=1),data=row) for row in rows})
        return rows

    async def settle(self,pilot):
        for _ in range(40):
            workers=list(self.app.workers)
            if workers:
                results=await asyncio.gather(*(w.wait() for w in workers),return_exceptions=True)
                for result in results:
                    if isinstance(result,BaseException) and not isinstance(result,WorkerCancelled):raise result
            await pilot.pause()
            if not list(self.app.workers):return
        raise TimeoutError('Workers did not settle')

    async def select(self,pilot,category):
        i=next(i for i,t in enumerate(self.app.tab_map,1) if t['category']==category)
        self.app.query_one(Tabs).active=f'tab-{i}'
        await self.settle(pilot)

    def status(self):
        content=self.app.query_one('#last-refresh-time',Label).renderable
        return getattr(content,'plain',str(content))

    def expected(self,symbol):
        stamp=datetime.fromisoformat(self.rows[symbol]['_fetched_at']).astimezone()
        return f'Last Refresh: {stamp:%H:%M:%S}'

    async def test_all_price_tabs_and_return_switches_have_their_own_time(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            for category,symbol in [('aktier','AAPL'),('indeks','^GSPC'),('krypto','BTC-USD'),('all','AAPL'),('indeks','^GSPC'),('aktier','AAPL')]:
                await self.select(pilot,category)
                self.assertEqual(self.status(),self.expected(symbol),category)

    async def test_special_tabs_clear_price_status_and_tooltip_and_ignore_price_results(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            for category in ['history','news','options','fred','debug','configs']:
                await self.select(pilot,'aktier')
                self.assertTrue(self.app.query_one('#last-refresh-time',Label).tooltip)
                await self.select(pilot,category)
                label=self.app.query_one('#last-refresh-time',Label)
                self.assertEqual(self.status(),'',category)
                self.assertIsNone(label.tooltip,category)
                for error in (None,'offline'):
                    await self.app.on_price_data_updated(PriceDataUpdated(list(self.rows.values()),'all',error=error))
                    self.assertEqual(self.status(),'',category)
                    self.assertIsNone(label.tooltip,category)
            await self.select(pilot,'krypto')
            self.assertEqual(self.status(),self.expected('BTC-USD'))

    async def test_empty_and_uncached_loading_tabs_do_not_borrow_previous_time(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            await self.select(pilot,'empty')
            self.assertEqual(self.status(),'Last Refresh: Unknown')
            self.assertNotIn('AAPL',str(self.app.query_one('#last-refresh-time',Label).tooltip))
            await self.select(pilot,'aktier')
            with patch.object(self.app,'fetch_prices'):
                await self.select(pilot,'cold')
                self.assertEqual(self.status(),'Last Refresh: Unknown')

    async def test_all_list_response_uses_only_current_list_rows(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            await self.select(pilot,'indeks')
            await self.app.on_price_data_updated(PriceDataUpdated(list(self.rows.values()),'all'))
            self.assertEqual(self.status(),self.expected('^GSPC'))
            tip=str(self.app.query_one('#last-refresh-time',Label).tooltip)
            self.assertIn('^GSPC',tip);self.assertNotIn('AAPL',tip);self.assertNotIn('BTC-USD',tip)

    async def test_empty_result_and_empty_filter_clear_time(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            await self.app.on_price_data_updated(PriceDataUpdated([],'aktier'))
            self.assertEqual(self.status(),'Last Refresh: Unknown')
            self.app.action_refresh();await self.settle(pilot)
            self.assertEqual(self.status(),self.expected('AAPL'))
            self.app.on_tag_filter_changed(TagFilterChanged(['no-matches']))
            await pilot.pause()
            self.assertEqual(self.status(),'Last Refresh: Unknown')
            self.app.on_tag_filter_changed(TagFilterChanged([]));await pilot.pause()
            self.assertEqual(self.status(),self.expected('AAPL'))

    async def test_other_list_result_does_not_change_status(self):
        async with self.app.run_test(size=(140,40)) as pilot:
            await self.settle(pilot)
            await self.select(pilot,'krypto')
            await self.app.on_price_data_updated(PriceDataUpdated([self.rows['AAPL']],'aktier'))
            self.assertEqual(self.status(),self.expected('BTC-USD'))
