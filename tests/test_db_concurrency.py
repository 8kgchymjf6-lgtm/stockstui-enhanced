"""Exercise real SQLite connections under overlapping reads and writes."""
import logging
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stockstui.database.db_manager import DbManager


class TestDbConcurrency(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'cache.sqlite'
        self.messages = []
        messages = self.messages

        class Capture(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    messages.append(record.getMessage())

        handler = Capture()
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)

    def manager(self):
        manager = DbManager(self.path)
        self.addCleanup(manager.close)
        return manager

    def exercise_writers(self, managers):
        barrier = threading.Barrier(4)
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        def writer(worker):
            manager = managers[worker]
            barrier.wait(timeout=10)
            for batch in range(20):
                start = worker * 1000 + batch * 50
                symbols = [f'T{i:05d}' for i in range(start, start + 50)]
                prices = {
                    symbol: {'expiry': expiry, 'data': {'symbol': symbol, 'price': 123.0}}
                    for symbol in symbols
                }
                manager.save_price_cache_to_db(prices)
                manager.save_info_cache_to_db({
                    symbol: {'shortName': symbol, 'exchange': 'TEST', 'currency': 'USD'}
                    for symbol in symbols
                })
                manager.save_option_position(f'TEST-{worker}-{batch}', 'TEST', 1.0, 2.0)
                manager.load_price_cache_from_db()
                manager.load_info_cache_from_db()
                manager.get_all_option_positions()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(writer, worker) for worker in range(4)]
            for future in futures:
                future.result(timeout=30)

        expected = {f'T{i:05d}' for i in range(4000)}
        self.assertEqual(set(managers[0].load_price_cache_from_db()), expected)
        self.assertEqual(set(managers[0].load_info_cache_from_db()), expected)
        self.assertEqual(len(managers[0].get_all_option_positions()), 80)
        self.assertEqual(managers[0].conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.messages[:3], [])

    def test_overlapping_operations_on_shared_connection_preserve_all_rows(self):
        manager = self.manager()
        self.exercise_writers([manager] * 4)

    def test_overlapping_operations_on_separate_connections_preserve_all_rows(self):
        self.exercise_writers([self.manager() for _ in range(4)])

    def test_close_waits_for_in_flight_write_and_is_idempotent(self):
        manager = self.manager()
        entered = threading.Event()
        release = threading.Event()

        def trace(statement):
            if statement.startswith('BEGIN'):
                entered.set()
                release.wait(timeout=10)

        manager.conn.set_trace_callback(trace)
        payload = {'AAPL': {
            'expiry': datetime.now(timezone.utc) + timedelta(hours=1),
            'data': {'price': 123.0},
        }}
        with ThreadPoolExecutor(max_workers=2) as executor:
            saving = executor.submit(manager.save_price_cache_to_db, payload)
            try:
                self.assertTrue(entered.wait(timeout=5))
                closing = executor.submit(manager.close)
                self.assertFalse(closing.done(), 'Close must wait for the active write')
            finally:
                release.set()
            saving.result(timeout=10)
            closing.result(timeout=10)
        manager.close()
        self.assertEqual(manager.load_price_cache_from_db(), {})
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM price_cache').fetchone()[0], 1)
        self.assertEqual(self.messages[:3], [])


if __name__ == '__main__':
    unittest.main()
