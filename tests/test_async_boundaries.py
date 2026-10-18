"""Late results, cancelled workers and dialogs preserve their original context."""
import asyncio
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from textual.app import App, ComposeResult
from textual.worker import WorkerCancelled
from textual.widgets import DataTable, Markdown, Input
from stockstui.common import NewsDataUpdated, MarketStatusUpdated, ListName
from stockstui.main import main
from stockstui.parser import create_arg_parser
from stockstui.ui.views.news_view import NewsView
from stockstui.ui.views.fred_view import FredView
from stockstui.ui.views.config_views.lists_config_view import ListsConfigView
from tests import test_tab_status as tab_fixture
from tests import test_lists_config_view_extended as list_fixture


def article(title):
    return dict(title=title,link='https://example.org/'+title,publisher='Test',summary='Text',publish_time='Now')


class TestNewsLifecycle(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=tab_fixture.TestTabStatus.asyncSetUp
    fetch=tab_fixture.TestTabStatus.fetch
    settle=tab_fixture.TestTabStatus.settle
    select=tab_fixture.TestTabStatus.select

    async def test_older_same_symbol_reply_cannot_replace_newer_content(self):
        async with self.app.run_test() as pilot:
            await self.settle(pilot)
            self.app.news_ticker='AAPL'
            with patch.object(self.app,'_fetch_news',return_value=MagicMock()):
                self.app.fetch_news('AAPL');old=self.app._news_request_serial
                self.app.fetch_news('AAPL');current=self.app._news_request_serial
            await self.app.on_news_data_updated(NewsDataUpdated('AAPL',[article('new')],current))
            expected=self.app._last_news_content
            await self.app.on_news_data_updated(NewsDataUpdated('AAPL',[article('old')],old))
            self.assertEqual(self.app._last_news_content,expected)
            self.app.news_ticker='MSFT'
            await self.app.on_news_data_updated(NewsDataUpdated('AAPL',[article('wrong')],current))
            self.assertEqual(self.app._last_news_content,expected)

    async def test_empty_submission_invalidates_pending_news_and_clears_loading(self):
        async with self.app.run_test() as pilot:
            await self.settle(pilot);await self.select(pilot,'news')
            self.app.news_ticker='AAPL'
            with patch.object(self.app,'_fetch_news',return_value=MagicMock()):self.app.fetch_news('AAPL')
            old=self.app._news_request_serial
            view=self.app.query_one(NewsView);output=view.query_one(Markdown);output.loading=True
            view.on_news_ticker_submitted(Input.Submitted(view.query_one(Input),'   '))
            self.assertIsNone(self.app.news_ticker);self.assertFalse(output.loading)
            await self.app.on_news_data_updated(NewsDataUpdated('AAPL',[article('old')],old))
            self.assertIsNone(self.app._last_news_content)

    async def test_provider_failure_and_retry_end_loading(self):
        async with self.app.run_test() as pilot:
            await self.settle(pilot);await self.select(pilot,'news')
            self.app.news_ticker='AAPL';view=self.app.query_one(NewsView);output=view.query_one(Markdown)
            with patch('stockstui.main.market_provider.get_news_for_tickers',side_effect=OSError('offline')):
                output.loading=True;self.app.fetch_news('AAPL');await self.settle(pilot)
            self.assertFalse(output.loading)
            self.assertIn('Could not retrieve',str(self.app._last_news_content))
            with patch('stockstui.main.market_provider.get_news_for_tickers',return_value=[article('recovered')]):
                output.loading=True;self.app.fetch_news('AAPL');await self.settle(pilot)
            self.assertFalse(output.loading);self.assertIn('recovered',str(self.app._last_news_content))

    async def test_current_cancelled_worker_ends_loading(self):
        entered=threading.Event();release=threading.Event()
        def blocked(tickers, **kwargs):entered.set();release.wait(10);return [article('old')]
        async with self.app.run_test() as pilot:
            await self.settle(pilot);await self.select(pilot,'news')
            self.app.news_ticker='AAPL';output=self.app.query_one(NewsView).query_one(Markdown)
            with patch('stockstui.main.market_provider.get_news_for_tickers',side_effect=blocked):
                try:
                    output.loading=True;worker=self.app.fetch_news('AAPL')
                    self.assertTrue(await asyncio.to_thread(entered.wait,5));worker.cancel()
                    await self.settle(pilot);self.assertFalse(output.loading)
                finally:release.set()

    async def test_refresh_retries_each_data_view(self):
        from stockstui.ui.views.history_view import HistoryView
        from stockstui.ui.views.options_view import OptionsView
        async with self.app.run_test() as pilot:
            await self.settle(pilot)
            await self.select(pilot,'news');self.app.news_ticker='AAPL'
            with patch.object(self.app,'fetch_news') as fetch:
                self.app.action_refresh(force=True)
                fetch.assert_called_once_with('AAPL',force=True)
            await self.select(pilot,'history')
            with patch.object(self.app.query_one(HistoryView),'_request_historical_data') as fetch:
                self.app.action_refresh();fetch.assert_called_once_with()
            await self.select(pilot,'options');self.app.options_ticker='AAPL'
            view=self.app.query_one(OptionsView);view.expirations=['2027-01-15']
            with patch.object(view,'_request_options_chain') as fetch,patch('stockstui.main.options_provider.clear_options_cache') as clear:
                self.app.action_refresh(force=True);fetch.assert_called_once_with();clear.assert_called_once_with('AAPL')
            await self.select(pilot,'fred')
            with patch.object(self.app.query_one(FredView),'load_all_series') as fetch,patch('stockstui.main.fred_provider.clear_cache') as clear:
                self.app.action_refresh(force=True);fetch.assert_called_once_with();clear.assert_called_once()

    async def test_market_status_rejects_old_calendar_and_request(self):
        async with self.app.run_test() as pilot:
            await self.settle(pilot)
            with patch.object(self.app,'_fetch_market_status',return_value=MagicMock()):
                self.app.fetch_market_status('NYSE');old=self.app._market_status_serial
                self.app.fetch_market_status('NYSE');current=self.app._market_status_serial
            with patch.object(self.app,'_update_market_status_display') as display:
                await self.app.on_market_status_updated(MarketStatusUpdated({'status':'old'},'NYSE',old))
                self.app.config.settings['market_calendar']='LSE'
                await self.app.on_market_status_updated(MarketStatusUpdated({'status':'wrong'},'NYSE',current))
                display.assert_not_called()
                await self.app.on_market_status_updated(MarketStatusUpdated({'status':'new'},'LSE',current))
                display.assert_called_once_with({'status':'new'})

    async def test_literal_markup_list_name_survives_tab_rebuild(self):
        from textual.widgets import Tabs
        async with self.app.run_test() as pilot:
            await self.settle(pilot)
            self.app.config.lists['[/broken]']=[]
            await self.app._rebuild_app('[/broken]')
            await self.settle(pilot)
            active=self.app.query_one(Tabs).active_tab
            self.assertIn('[/broken]',active.label.plain)


class FredApp(App):
    def __init__(self):
        super().__init__();self.config=SimpleNamespace(settings={'fred_settings':{'api_key':'synthetic-key','series_list':['OLD']}})
        self.theme_variables={};self._closing=False
    def compose(self)->ComposeResult:yield FredView()


class TestFredLifecycle(unittest.IsolatedAsyncioTestCase):
    async def settle(self,app,pilot):
        for _ in range(20):
            results = await asyncio.gather(*(worker.wait() for worker in list(app.workers)), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException) and not isinstance(result, WorkerCancelled):
                    raise result
            await pilot.pause()
            if not list(app.workers):return
        raise TimeoutError('FRED worker did not finish')

    async def test_old_request_and_queued_callback_cannot_replace_new_series(self):
        entered=threading.Event();release=threading.Event()
        def summary(series,key):
            if series=='OLD':entered.set();release.wait(10)
            return dict(id=series,title=series,current=1)
        app=FredApp()
        with patch('stockstui.ui.views.fred_view.fred_provider.get_series_summary',side_effect=summary):
            async with app.run_test() as pilot:
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,5))
                    view=app.query_one(FredView);old=view._load_serial
                    app.config.settings['fred_settings']['series_list']=['NEW']
                    view.load_all_series();await self.settle(app,pilot)
                    view._apply_loaded_series(old,[dict(id='OLD',title='OLD',current=3)])
                    table=view.query_one(DataTable)
                    self.assertEqual([key.value for key in table.rows],['NEW'])
                finally:release.set()

    async def test_cancellation_and_invalid_summaries_are_controlled(self):
        app=FredApp();entered=threading.Event();release=threading.Event()
        def blocked(series,key):entered.set();release.wait(10);return dict(id=series)
        with patch('stockstui.ui.views.fred_view.fred_provider.get_series_summary',side_effect=blocked):
            async with app.run_test() as pilot:
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,5));view=app.query_one(FredView)
                    view._load_worker.cancel();await self.settle(app,pilot)
                    self.assertFalse(view.query_one(DataTable).loading)
                    view._populate_table([dict(id='GOOD',title=None,current=float('nan'),yoy_pct='bad',roll_12=float('inf'),frequency=None,date=None,units=None),dict(id='GOOD'),dict(id=None)])
                    self.assertEqual(view.query_one(DataTable).row_count,1)
                finally:release.set()


class TestDialogContext(unittest.IsolatedAsyncioTestCase):
    async def test_edit_and_delete_ticker_keep_original_list(self):
        app=list_fixture.ListsConfigViewTestApp()
        app.push_screen=MagicMock()
        async with app.run_test() as pilot:
            view=app.query_one(ListsConfigView);app.active_list_category='stocks'
            await view.on_edit_ticker_pressed();callback=app.push_screen.call_args.args[1]
            app.active_list_category='crypto';callback(('AAPL','New [/alias]','',''))
            self.assertEqual(app.config.lists['stocks'][0]['alias'],'New [/alias]')
            self.assertEqual(app.config.lists['crypto'][0]['ticker'],'BTC-USD')
            app.active_list_category='stocks';view._populate_ticker_table();await pilot.pause()
            await view.on_delete_ticker_pressed();callback=app.push_screen.call_args.args[1]
            app.active_list_category='crypto';callback(True)
            self.assertEqual([i['ticker'] for i in app.config.lists['stocks']],['GOOGL'])
            self.assertEqual(len(app.config.lists['crypto']),2)

    async def test_delete_list_confirmation_keeps_original_list(self):
        app=list_fixture.ListsConfigViewTestApp();app.push_screen=MagicMock()
        async with app.run_test():
            view=app.query_one(ListsConfigView);app.active_list_category='stocks'
            await view.on_delete_list_pressed();callback=app.push_screen.call_args.args[1]
            app.active_list_category='crypto';await callback(True)
            self.assertNotIn('stocks',app.config.lists);self.assertIn('crypto',app.config.lists)

    async def test_deleted_add_target_does_not_crash_or_report_success(self):
        app=list_fixture.ListsConfigViewTestApp();app.push_screen=MagicMock()
        async with app.run_test():
            view=app.query_one(ListsConfigView);app.active_list_category='stocks'
            await view.on_add_ticker_pressed();callback=app.push_screen.call_args.args[1]
            del app.config.lists['stocks'];app.config.save_lists.reset_mock()
            callback(('NEW','','',''));app.config.save_lists.assert_not_called()
            self.assertIn('no longer exists',app.notify.call_args.args[0])

    async def test_deleted_edit_and_delete_targets_do_not_report_success(self):
        for action,result in (('on_edit_ticker_pressed',('AAPL','Changed','','')),('on_delete_ticker_pressed',True)):
            app=list_fixture.ListsConfigViewTestApp();app.push_screen=MagicMock()
            async with app.run_test():
                view=app.query_one(ListsConfigView);app.active_list_category='stocks'
                await getattr(view,action)();callback=app.push_screen.call_args.args[1]
                app.config.lists['stocks'].clear();app.config.save_lists.reset_mock()
                callback(result);app.config.save_lists.assert_not_called()
                self.assertEqual(app.notify.call_args.kwargs.get('severity'),'warning')


class TestCommandAndNames(unittest.TestCase):
    def test_builtin_list_names_are_rejected_in_dialog_and_cli(self):
        validator=ListName();parser=create_arg_parser()
        for name in ('all','History','news','options','fred','debug','configs',''):
            with self.subTest(name=name):
                self.assertFalse(validator.validate(name).is_valid)
                with self.assertRaises(SystemExit):parser.parse_args(['--session-list',name+'=AAPL'])
        self.assertTrue(validator.validate('Danish stocks').is_valid)
        self.assertEqual(parser.parse_args(['--session-list','custom=AAPL']).session_list,{'custom':['AAPL']})

    def test_help_version_and_manual_preserve_existing_log(self):
        with tempfile.TemporaryDirectory() as root:
            cache=Path(root)/'stockstui';cache.mkdir();log=cache/'stockstui.log';log.write_text('existing diagnostic log')
            for flag in ('--version','--help','--man'):
                result=subprocess.run([sys.executable,'-m','stockstui.main',flag],env={**os.environ,'XDG_CACHE_HOME':root},text=True,capture_output=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(log.read_text(),'existing diagnostic log')

    def test_app_notification_handler_is_removed_even_when_app_fails(self):
        with tempfile.TemporaryDirectory() as root,patch('stockstui.main.create_arg_parser') as parser,patch('stockstui.main.PlatformDirs',return_value=SimpleNamespace(user_cache_dir=root)),patch('stockstui.main.logging.basicConfig'),patch('stockstui.main.StocksTUI') as app:
            parser.return_value.parse_args.return_value=SimpleNamespace(man=False,output=None)
            app.return_value.run.side_effect=RuntimeError('run failed')
            before=list(logging.getLogger().handlers)
            with self.assertRaises(RuntimeError):main()
            self.assertEqual(logging.getLogger().handlers,before)
