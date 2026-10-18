"""Adversarial ordering of network results and persistent cache snapshots."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import sqlite3
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
from stockstui.data_providers import market_provider as market
from stockstui.data_providers import portfolio as portfolios
from stockstui import config_manager as config
from stockstui.database.db_manager import DbManager


class TestPriceIntegrity(unittest.TestCase):
    def setUp(self):
        for name in ('_price_cache','_info_cache','_price_versions','_info_versions'):
            patcher=patch.object(market,name,{},create=True)
            patcher.start();self.addCleanup(patcher.stop)
        self.expiry=datetime.now(timezone.utc)+timedelta(hours=1)

    def seed(self):
        market._price_cache['TEST']=dict(expiry=self.expiry,data=dict(symbol='TEST',price=5,currency='USD',_fetched_at='2026-10-18T10:00:00+00:00'))
        market._info_cache['TEST']=dict(quoteType='CRYPTOCURRENCY',exchange='NYSE',currency='USD')

    def test_late_fast_success_cannot_replace_newer_price(self):
        self.fast_race({'TEST':{'price':10}})

    def test_late_fast_failure_cannot_mark_newer_price_as_failed(self):
        self.fast_race({})

    def test_pending_newer_refresh_does_not_starve_completed_prices(self):
        self.seed();entered=[threading.Event(),threading.Event()];release=[threading.Event(),threading.Event()];calls=[]
        def fetch(*args,**kwargs):
            index=len(calls);calls.append(index);entered[index].set();release[index].wait(5)
            return {'TEST':{'price':10 if index==0 else 20}}
        with patch.object(market,'_fetch_fast_data',side_effect=fetch),ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(market.get_market_price_data,['TEST'])
            self.assertTrue(entered[0].wait(5));new=pool.submit(market.get_market_price_data,['TEST'])
            try:
                self.assertTrue(entered[1].wait(5));release[0].set();old.result(5)
                self.assertEqual(market.get_price_cache_state()['TEST']['data']['price'],10)
            finally:
                for event in release:event.set()
                new.result(5)
        self.assertEqual(market.get_price_cache_state()['TEST']['data']['price'],20)

    def test_overlapping_lists_preserve_independent_symbol_updates(self):
        self.seed()
        market._price_cache['OTHER']=dict(expiry=self.expiry,data=dict(symbol='OTHER',price=5))
        market._info_cache['OTHER']=dict(quoteType='CRYPTOCURRENCY')
        entered=threading.Event();release=threading.Event()
        def fetch(tickers,**kwargs):
            if len(tickers)==2:
                entered.set();release.wait(5);return {'TEST':{'price':10},'OTHER':{'price':30}}
            return {'TEST':{'price':20}}
        with patch.object(market,'_fetch_fast_data',side_effect=fetch),ThreadPoolExecutor(max_workers=1) as pool:
            old=pool.submit(market.get_market_price_data,['TEST','OTHER'])
            try:
                self.assertTrue(entered.wait(5));market.get_market_price_data(['TEST'])
            finally:release.set()
            old.result(5)
        state=market.get_price_cache_state()
        self.assertEqual(state['TEST']['data']['price'],20)
        self.assertEqual(state['OTHER']['data']['price'],30)

    def fast_race(self,old_result):
        self.seed();entered=threading.Event();release=threading.Event();calls=[]
        def fetch(*args,**kwargs):
            calls.append(True)
            if len(calls)==1:
                entered.set();release.wait(5);return old_result
            return {'TEST':{'price':20}}
        with patch.object(market,'_fetch_fast_data',side_effect=fetch),ThreadPoolExecutor(max_workers=1) as pool:
            old=pool.submit(market.get_market_price_data,['TEST'])
            try:
                self.assertTrue(entered.wait(5))
                newer=market.get_market_price_data(['TEST'])
                self.assertEqual(newer[0]['price'],20)
            finally:release.set()
            older=old.result(5)
        row=market.get_price_cache_state()['TEST']['data']
        self.assertEqual(row['price'],20)
        self.assertFalse(row.get('_fetch_failed'))
        self.assertEqual(older[0]['price'],20)
        self.assertFalse(older[0]['_stale'])

    def test_late_slow_success_cannot_replace_newer_price_or_metadata(self):
        self.slow_race(dict(currency='USD',regularMarketPrice=10,longName='Old',shortName='Old'))

    def test_late_slow_failure_cannot_poison_newer_cache(self):
        self.slow_race(None)

    def slow_race(self,old_info):
        entered=threading.Event();release=threading.Event()
        class Old:
            fast_info={}
            @property
            def info(self):entered.set();release.wait(5);return old_info
        new=SimpleNamespace(info=dict(currency='USD',regularMarketPrice=20,longName='New',shortName='New'),fast_info={})
        with patch.object(market.yf,'Ticker',side_effect=[Old(),new]),patch.object(market,'_calculate_info_expiry',return_value=self.expiry),ThreadPoolExecutor(max_workers=1) as pool:
            old=pool.submit(market._fetch_and_cache_slow_data,['TEST'])
            try:
                self.assertTrue(entered.wait(5));market._fetch_and_cache_slow_data(['TEST'])
            finally:release.set()
            old.result(5)
        row=market.get_price_cache_state()['TEST']['data']
        self.assertEqual(row['price'],20);self.assertEqual(row['description'],'New')
        self.assertEqual(market.get_info_cache_state()['TEST']['shortName'],'New')
        self.assertFalse(row.get('_fetch_failed'))

    def test_info_failure_does_not_permanently_block_retry(self):
        good=SimpleNamespace(info=dict(currency='USD',shortName='Recovered'))
        with patch.object(market.yf,'Ticker',side_effect=[OSError('offline'),good]) as factory:
            self.assertIsNone(market.get_ticker_info('TEST'))
            info=market.get_ticker_info('TEST')
        self.assertEqual(info['shortName'],'Recovered');self.assertEqual(factory.call_count,2)
        market._info_cache['OTHER']={'currency':None,'shortName':None}
        with patch.object(market.yf,'Ticker',return_value=good):
            self.assertEqual(market.get_ticker_info('other')['shortName'],'Recovered')

    def test_late_info_failure_does_not_erase_newer_success(self):
        entered=threading.Event();release=threading.Event()
        class Old:
            @property
            def info(self):entered.set();release.wait(5);raise OSError('offline')
        good=SimpleNamespace(info=dict(currency='USD',shortName='New'))
        with patch.object(market.yf,'Ticker',side_effect=[Old(),good]),ThreadPoolExecutor(max_workers=1) as pool:
            old=pool.submit(market.get_ticker_info,'TEST')
            try:
                self.assertTrue(entered.wait(5));self.assertEqual(market.get_ticker_info('TEST')['shortName'],'New')
            finally:release.set()
            old.result(5)
        self.assertEqual(market.get_info_cache_state()['TEST']['shortName'],'New')

    def test_zero_eps_and_beta_do_not_select_fallback_values(self):
        reply=SimpleNamespace(info=dict(currency='USD',regularMarketPrice=10,trailingEps=0,forwardEps=5,beta=0,beta3Year=2,sharesOutstanding=10),fast_info={'shares':0})
        with patch.object(market.yf,'Ticker',return_value=reply),patch.object(market,'_calculate_info_expiry',return_value=self.expiry):
            market._fetch_and_cache_slow_data(['TEST'])
        row=market.get_price_cache_state()['TEST']['data']
        self.assertEqual(row['eps'],0);self.assertEqual(row['beta'],0)
        self.assertEqual(row['shares'],10);self.assertEqual(row['market_cap'],100)

    def test_outdated_split_response_keeps_matching_price_and_fetch_time(self):
        split=datetime(2026,1,2,tzinfo=timezone.utc).timestamp()
        old=dict(symbol='TEST',price=50,all_time_high=75,_last_split_at=split,
                 _fetched_at='2026-01-03T12:00:00+00:00',_quote_at='2026-01-03T11:59:00+00:00',_quote_time_kind='quote')
        market._price_cache['TEST']=dict(expiry=self.expiry,data=old.copy())
        reply=SimpleNamespace(info=dict(currency='USD',regularMarketPrice=100,lastSplitDate=split-86400),fast_info={})
        with patch.object(market.yf,'Ticker',return_value=reply),patch.object(market,'_calculate_info_expiry',return_value=self.expiry):
            market._fetch_and_cache_slow_data(['TEST'])
        row=market.get_price_cache_state()['TEST']['data']
        self.assertEqual(row['price'],50);self.assertEqual(row['_fetched_at'],old['_fetched_at'])
        self.assertEqual(row['_quote_at'],old['_quote_at']);self.assertTrue(row['_fetch_failed'])

    def test_valid_slow_price_survives_unavailable_fast_info(self):
        class Reply:
            info=dict(currency='USD',regularMarketPrice=10)
            @property
            def fast_info(self):raise OSError('optional fast info failed')
        with patch.object(market.yf,'Ticker',return_value=Reply()),patch.object(market,'_calculate_info_expiry',return_value=self.expiry):
            market._fetch_and_cache_slow_data(['TEST'])
        self.assertEqual(market.get_price_cache_state()['TEST']['data']['price'],10)

    def test_fast_close_survives_missing_optional_ohlcv_fields(self):
        frame=pd.DataFrame({('Close','TEST'):[10.]},index=pd.to_datetime(['2026-10-18T10:00:00Z']))
        with patch.object(market.yf,'download',return_value=frame):rows=market._fetch_fast_data(['TEST'])
        self.assertEqual(rows['TEST']['price'],10)

    def test_fresh_price_without_metadata_still_refreshes(self):
        self.seed();market._info_cache.clear()
        reply=SimpleNamespace(info=dict(currency='USD',regularMarketPrice=10),fast_info={})
        with patch.object(market.yf,'Ticker',return_value=reply) as factory,patch.object(market,'_calculate_info_expiry',return_value=self.expiry),patch.object(market,'get_market_status',return_value={'is_open':False}):
            rows=market.get_market_price_data(['TEST'])
        factory.assert_called_once_with('TEST');self.assertEqual(rows[0]['price'],10)

    def test_legacy_metadata_reloads_before_prepost_update(self):
        self.seed();market._info_cache['TEST']={'currency':'USD','exchange':'NYSE'}
        reply=SimpleNamespace(info=dict(currency='USD',regularMarketPrice=10,hasPrePostMarketData=True),fast_info={})
        with patch.object(market.yf,'Ticker',return_value=reply),patch.object(market,'_calculate_info_expiry',return_value=self.expiry),patch.object(market,'get_market_status',return_value={'is_open':False,'status':'pre'}),patch.object(market,'_fetch_fast_data',return_value={'TEST':{'price':12}}) as fast:
            rows=market.get_market_price_data(['TEST'],enable_pre_post_market=True)
        fast.assert_called_once_with(['TEST'],prepost=True);self.assertEqual(rows[0]['price'],12)


class TestPersistentOrdering(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=DbManager(Path(self.temp.name)/'cache.db');self.addCleanup(self.db.close)
        self.expiry=datetime.now(timezone.utc)+timedelta(hours=1)

    def save(self,row):self.db.save_price_cache_to_db({'TEST':dict(expiry=self.expiry,data=dict(symbol='TEST',**row))})
    def read(self):return self.db.load_price_cache_from_db()['TEST']['data']

    def test_split_units_survive_save_and_restart(self):
        split=datetime(2026,1,2,tzinfo=timezone.utc).timestamp()
        self.save(dict(price=100,all_time_high=150,eps=4,day_high=140,_fetched_at='2026-01-01T12:00:00+00:00'))
        self.save(dict(price=50,all_time_high=75,_last_split_at=split,_fetched_at='2026-01-03T12:00:00+00:00'))
        row=self.read()
        self.assertEqual(row['all_time_high'],75);self.assertIsNone(row.get('eps'));self.assertIsNone(row.get('day_high'))

    def test_late_old_snapshot_cannot_roll_back_newer_data(self):
        self.save(dict(price=20,description='New',_fetched_at='2026-10-18T11:00:00+00:00'))
        self.save(dict(price=10,description='Old',_fetched_at='2026-10-18T10:00:00+00:00'))
        row=self.read();self.assertEqual(row['price'],20);self.assertEqual(row['description'],'New')

    def test_late_old_snapshot_cannot_reduce_newer_cache_expiry(self):
        newer_expiry=self.expiry+timedelta(hours=2)
        self.db.save_price_cache_to_db({'TEST':dict(expiry=newer_expiry,data=dict(price=20,_fetched_at='2026-10-18T11:00:00+00:00'))})
        self.save(dict(price=10,_fetched_at='2026-10-18T10:00:00+00:00'))
        entry=self.db.load_price_cache_from_db()['TEST']
        self.assertEqual(entry['expiry'],newer_expiry)

    def test_old_snapshot_cannot_restore_pre_split_units(self):
        split=datetime(2026,1,2,tzinfo=timezone.utc).timestamp()
        self.save(dict(price=50,all_time_high=75,_last_split_at=split,_fetched_at='2026-01-03T12:00:00+00:00'))
        self.save(dict(price=100,all_time_high=150,_fetched_at='2026-01-01T12:00:00+00:00'))
        row=self.read();self.assertEqual(row['price'],50);self.assertEqual(row['all_time_high'],75)

    def test_market_flags_survive_database_restart(self):
        self.db.save_info_cache_to_db({'TEST':dict(currency='USD',quoteType='CRYPTOCURRENCY',hasPrePostMarketData=True)})
        self.db.close();reopened=DbManager(self.db.db_path);self.addCleanup(reopened.close)
        info=reopened.load_info_cache_from_db()['TEST']
        self.assertEqual(info['quoteType'],'CRYPTOCURRENCY');self.assertIs(info['hasPrePostMarketData'],True)
        old_path=Path(self.temp.name)/'legacy.db'
        with sqlite3.connect(old_path) as connection:
            connection.execute('CREATE TABLE ticker_info (ticker TEXT PRIMARY KEY, exchange TEXT, short_name TEXT, long_name TEXT, currency TEXT, timestamp REAL NOT NULL)')
            connection.execute('INSERT INTO ticker_info VALUES (?,?,?,?,?,?)',('LEGACY','NYSE','Original','Original company','USD',datetime.now(timezone.utc).timestamp()))
        legacy=DbManager(old_path);self.addCleanup(legacy.close)
        saved=legacy.load_info_cache_from_db()['LEGACY']
        self.assertEqual(saved['shortName'],'Original');self.assertEqual(saved['currency'],'USD')
        self.assertNotIn('hasPrePostMarketData',saved)


class TestPortfolioIntegrity(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        directories=SimpleNamespace(user_config_dir=str(root/'config'),user_cache_dir=str(root/'cache'))
        with patch.object(config,'dirs',directories):self.config=config.ConfigManager(Path(config.__file__).parent)
        self.manager=portfolios.PortfolioManager(self.config)
        self.manager.create_portfolio('Second');self.manager.create_portfolio('Third')

    def test_add_all_is_indivisible_if_a_later_write_would_fail(self):
        path=self.config.user_config_dir/'portfolios.json';before=path.read_bytes()
        save=self.config._atomic_save;calls=[]
        def fail_second(name,data):
            calls.append(name)
            if len(calls)==2:raise config.ConfigSaveError('second write failed')
            return save(name,data)
        with patch.object(self.config,'_atomic_save',side_effect=fail_second):
            try:self.manager.add_ticker_to_all_portfolios('NEW')
            except config.ConfigSaveError:self.assertEqual(path.read_bytes(),before)
            else:
                self.assertEqual(len(calls),1)
                self.assertTrue(all('NEW' in item['tickers'] for item in self.manager.get_all_portfolios().values()))

    def test_bulk_write_failure_preserves_all_portfolios(self):
        path=self.config.user_config_dir/'portfolios.json';before=path.read_bytes()
        with patch.object(config.os,'replace',side_effect=OSError('disk full')),self.assertRaises(config.ConfigSaveError):
            self.manager.add_ticker_to_all_portfolios('NEW')
        self.assertEqual(path.read_bytes(),before)
        self.assertTrue(all('NEW' not in item['tickers'] for item in self.manager.get_all_portfolios().values()))

    def test_portfolio_timestamps_represent_utc(self):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):
                if tz is None:return cls(2026,1,1,14)
                return cls(2026,1,1,12,tzinfo=timezone.utc).astimezone(tz)
        with patch.object(portfolios.datetime,'datetime',Clock):
            key=self.manager.create_portfolio('UTC')
        stamp=datetime.fromisoformat(self.manager.get_portfolio(key)['created'].replace('Z', '+00:00'))
        self.assertEqual(stamp,datetime(2026,1,1,12,tzinfo=timezone.utc))
