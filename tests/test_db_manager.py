import unittest
import sqlite3
from unittest.mock import Mock, patch
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from stockstui.database.db_manager import (
    DbManager,
    CACHE_LOAD_DURATION_SECONDS,
    CACHE_PRUNE_EXPIRY_SECONDS,
)


class TestDbManager(unittest.TestCase):
    """
    Unit tests for the DbManager class.
    Uses a temporary file for the SQLite database to ensure tests are isolated.
    """

    def setUp(self):
        """Set up a temporary database for each test."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_cache.db"
        self.dbm = DbManager(self.db_path)

    def tearDown(self):
        """Close the connection and clean up the temporary directory."""
        self.dbm.close()
        self.tmpdir.cleanup()

    def test_table_creation(self):
        """Verify that the necessary tables are created on initialization."""
        cursor = self.dbm.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        self.assertIn("price_cache", tables)
        self.assertIn("ticker_info", tables)

    def test_save_and_load_price_cache(self):
        """Test the full cycle of saving and loading the price cache."""
        now = datetime.now(timezone.utc)
        sample_data = {
            "AAPL": {"expiry": now, "data": {"price": 150.0}},
            "GOOG": {"expiry": now, "data": {"price": 2800.0}},
        }

        self.dbm.save_price_cache_to_db(sample_data)
        loaded_data = self.dbm.load_price_cache_from_db()

        self.assertEqual(len(loaded_data), 2)
        self.assertIn("AAPL", loaded_data)
        self.assertEqual(loaded_data["AAPL"]["data"]["price"], 150.0)
        # Compare timestamps with a small tolerance for float precision
        self.assertAlmostEqual(
            loaded_data["AAPL"]["expiry"].timestamp(), now.timestamp(), places=5
        )

    def test_load_price_cache_filters_stale_data(self):
        """Test that load_price_cache_from_db filters out entries older than CACHE_LOAD_DURATION."""
        stale_ts = (
            datetime.now(timezone.utc)
            - timedelta(seconds=CACHE_LOAD_DURATION_SECONDS + 60)
        ).timestamp()
        fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).timestamp()

        # Manually insert data with different timestamps
        cursor = self.dbm.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO price_cache (ticker, data, timestamp) VALUES (?, ?, ?)",
            ("STALE", json.dumps({"price": 10}), stale_ts),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO price_cache (ticker, data, timestamp) VALUES (?, ?, ?)",
            ("FRESH", json.dumps({"price": 20}), fresh_ts),
        )

        loaded_data = self.dbm.load_price_cache_from_db()

        self.assertEqual(len(loaded_data), 1)
        self.assertIn("FRESH", loaded_data)
        self.assertNotIn("STALE", loaded_data)

    def test_prune_expired_entries(self):
        """Test that _prune_expired_entries removes data older than CACHE_PRUNE_EXPIRY."""
        very_old_ts = (
            datetime.now(timezone.utc)
            - timedelta(seconds=CACHE_PRUNE_EXPIRY_SECONDS + 60)
        ).timestamp()
        not_so_old_ts = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()

        cursor = self.dbm.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO price_cache (ticker, data, timestamp) VALUES (?, ?, ?)",
            ("OLD", json.dumps({}), very_old_ts),
        )
        cursor.execute(
            "INSERT OR REPLACE INTO price_cache (ticker, data, timestamp) VALUES (?, ?, ?)",
            ("NEW", json.dumps({}), not_so_old_ts),
        )
        self.dbm.conn.commit()

        # Pruning happens at initialization, so we create a new instance
        new_dbm = DbManager(self.db_path)

        # Check the database content directly
        cursor = new_dbm.conn.cursor()
        cursor.execute("SELECT ticker FROM price_cache")
        remaining_tickers = {row[0] for row in cursor.fetchall()}

        self.assertEqual(len(remaining_tickers), 1)
        self.assertIn("NEW", remaining_tickers)
        self.assertNotIn("OLD", remaining_tickers)
        new_dbm.close()

    def test_save_and_load_info_cache(self):
        """Test the full cycle of saving and loading the ticker info cache."""
        sample_data = {
            "TSLA": {
                "exchange": "NMS",
                "shortName": "Tesla",
                "longName": "Tesla, Inc.",
                "currency": "USD",
            },
            "NVDA": {
                "exchange": "NMS",
                "shortName": "NVIDIA",
                "longName": "NVIDIA Corporation",
                "currency": None,
            },
        }

        self.dbm.save_info_cache_to_db(sample_data)
        loaded_data = self.dbm.load_info_cache_from_db()

        self.assertEqual(loaded_data, sample_data)

    def test_save_price_cache_merges_fields(self):
        """Test that save_price_cache_to_db performs a field-level merge with existing DB data."""
        now = datetime.now(timezone.utc)
        
        # 1. Save initial entry
        initial_data = {
            "AAPL": {
                "expiry": now,
                "data": {
                    "symbol": "AAPL",
                    "price": 150.0,
                    "all_time_high": 200.0,
                    "description": "Apple Inc."
                }
            }
        }
        self.dbm.save_price_cache_to_db(initial_data)
        
        # 2. Save partial update with None/missing fields
        update_data = {
            "AAPL": {
                "expiry": now,
                "data": {
                    "symbol": "AAPL",
                    "price": 155.0,
                    "all_time_high": None,
                    "pe_ratio": 30.0
                }
            }
        }
        self.dbm.save_price_cache_to_db(update_data)
        
        # 3. Load from DB and verify fields are merged
        loaded = self.dbm.load_price_cache_from_db()
        aapl_data = loaded["AAPL"]["data"]
        
        self.assertEqual(aapl_data["price"], 155.0, "Price should be updated")
        self.assertEqual(aapl_data["all_time_high"], 200.0, "ATH should be retained")
        self.assertEqual(aapl_data["pe_ratio"], 30.0, "PE ratio should be added")
        self.assertEqual(aapl_data["description"], "Apple Inc.", "Description should be retained")


    def test_option_positions_table_creation(self):
        """Verify that the option_positions table is created."""
        cursor = self.dbm.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='option_positions'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_save_and_get_option_position(self):
        """Test saving and retrieving one option position."""
        self.dbm.save_option_position(
            symbol="AAPL260116C00200000",
            ticker="AAPL",
            quantity=2.0,
            avg_cost=12.50,
        )

        position = self.dbm.get_option_position("AAPL260116C00200000")

        self.assertEqual(
            position,
            {
                "symbol": "AAPL260116C00200000",
                "ticker": "AAPL",
                "quantity": 2.0,
                "avg_cost": 12.50,
            },
        )

    def test_save_option_position_updates_existing_position(self):
        """Saving the same symbol again should replace its values."""
        symbol = "MSFT260116P00300000"

        self.dbm.save_option_position(symbol, "MSFT", 1.0, 8.0)
        self.dbm.save_option_position(symbol, "MSFT", 3.0, 7.25)

        position = self.dbm.get_option_position(symbol)

        self.assertIsNotNone(position)
        self.assertEqual(position["quantity"], 3.0)
        self.assertEqual(position["avg_cost"], 7.25)

    def test_get_missing_option_position_returns_none(self):
        """A symbol that does not exist should return None."""
        self.assertIsNone(self.dbm.get_option_position("DOES_NOT_EXIST"))

    def test_get_all_and_delete_option_positions(self):
        """Test listing all positions and deleting one position."""
        first_symbol = "AAPL260116C00200000"
        second_symbol = "NVDA260116P00100000"

        self.dbm.save_option_position(first_symbol, "AAPL", 2.0, 12.50)
        self.dbm.save_option_position(second_symbol, "NVDA", -1.0, 6.75)

        positions = self.dbm.get_all_option_positions()

        self.assertEqual(set(positions), {first_symbol, second_symbol})
        self.assertEqual(positions[first_symbol]["ticker"], "AAPL")
        self.assertEqual(positions[second_symbol]["quantity"], -1.0)

        self.dbm.delete_option_position(first_symbol)

        self.assertIsNone(self.dbm.get_option_position(first_symbol))
        remaining = self.dbm.get_all_option_positions()
        self.assertEqual(set(remaining), {second_symbol})

    def test_delete_missing_option_position_is_safe(self):
        """Deleting an unknown symbol should not raise an exception."""
        self.dbm.delete_option_position("DOES_NOT_EXIST")
        self.assertEqual(self.dbm.get_all_option_positions(), {})


    def test_load_price_cache_skips_invalid_json(self):
        """Invalid cached JSON should be ignored without breaking the load."""
        fresh_ts = datetime.now(timezone.utc).timestamp()

        cursor = self.dbm.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO price_cache "
            "(ticker, data, timestamp) VALUES (?, ?, ?)",
            ("BROKEN", "{invalid json", fresh_ts),
        )
        self.dbm.conn.commit()

        loaded = self.dbm.load_price_cache_from_db()

        self.assertNotIn("BROKEN", loaded)
        self.assertEqual(loaded, {})

    def test_save_price_cache_skips_incomplete_entries(self):
        """Entries without usable data or expiry should not be saved."""
        cache_data = {
            "NO_DATA": {
                "expiry": datetime.now(timezone.utc),
                "data": {},
            },
            "NO_EXPIRY": {
                "data": {"price": 100.0},
            },
        }

        self.dbm.save_price_cache_to_db(cache_data)

        cursor = self.dbm.conn.cursor()
        cursor.execute("SELECT ticker FROM price_cache")
        self.assertEqual(cursor.fetchall(), [])

    def test_save_price_cache_replaces_corrupt_existing_json(self):
        """Valid new data should replace an existing corrupt cache record."""
        now = datetime.now(timezone.utc)

        cursor = self.dbm.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO price_cache "
            "(ticker, data, timestamp) VALUES (?, ?, ?)",
            ("AAPL", "{broken json", now.timestamp()),
        )
        self.dbm.conn.commit()

        self.dbm.save_price_cache_to_db(
            {
                "AAPL": {
                    "expiry": now,
                    "data": {
                        "symbol": "AAPL",
                        "price": 175.0,
                    },
                }
            }
        )

        loaded = self.dbm.load_price_cache_from_db()

        self.assertEqual(
            loaded["AAPL"]["data"],
            {
                "symbol": "AAPL",
                "price": 175.0,
            },
        )

    def test_load_info_cache_filters_stale_entries(self):
        """Only fresh ticker metadata should be loaded."""
        stale_ts = (
            datetime.now(timezone.utc)
            - timedelta(seconds=CACHE_LOAD_DURATION_SECONDS + 60)
        ).timestamp()
        fresh_ts = datetime.now(timezone.utc).timestamp()

        cursor = self.dbm.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO ticker_info
            (ticker, exchange, short_name, long_name, currency, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("STALE", "NMS", "Stale", "Stale Company", "USD", stale_ts),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO ticker_info
            (ticker, exchange, short_name, long_name, currency, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("FRESH", "NMS", "Fresh", "Fresh Company", "USD", fresh_ts),
        )
        self.dbm.conn.commit()

        loaded = self.dbm.load_info_cache_from_db()

        self.assertIn("FRESH", loaded)
        self.assertNotIn("STALE", loaded)
        self.assertEqual(loaded["FRESH"]["currency"], "USD")

    def test_methods_are_safe_without_database_connection(self):
        """Database methods should return safely when no connection exists."""
        self.dbm.close()
        self.dbm.conn = None

        self.assertEqual(self.dbm.load_price_cache_from_db(), {})
        self.assertEqual(self.dbm.load_info_cache_from_db(), {})
        self.assertIsNone(self.dbm.get_option_position("AAPL"))
        self.assertEqual(self.dbm.get_all_option_positions(), {})

        self.dbm.save_price_cache_to_db({})
        self.dbm.save_info_cache_to_db({})
        self.dbm.save_option_position("AAPL", "AAPL", 1.0, 10.0)
        self.dbm.delete_option_position("AAPL")
        self.dbm.close()


    def test_initialization_handles_connection_error(self):
        """A failed SQLite connection should leave the manager usable."""
        failed_path = Path(self.tmpdir.name) / "failed.db"

        with patch(
            "stockstui.database.db_manager.sqlite3.connect",
            side_effect=sqlite3.Error("connection failed"),
        ):
            manager = DbManager(failed_path)

        self.assertIsNone(manager.conn)
        manager.close()

    def test_private_setup_methods_are_safe_without_connection(self):
        """Table creation and pruning should return safely without a connection."""
        self.dbm.close()
        self.dbm.conn = None

        self.dbm._create_tables()
        self.dbm._prune_expired_entries()

    def test_load_methods_handle_sqlite_errors(self):
        """Cache load methods should return empty dictionaries on SQLite errors."""
        bad_connection = Mock()
        bad_connection.cursor.side_effect = sqlite3.Error("read failed")
        self.dbm.conn = bad_connection

        self.assertEqual(self.dbm.load_price_cache_from_db(), {})
        self.assertEqual(self.dbm.load_info_cache_from_db(), {})

    def test_save_price_cache_rolls_back_on_sqlite_error(self):
        """A failed price-cache transaction should be rolled back."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = sqlite3.Error("write failed")
        self.dbm.conn = connection

        self.dbm.save_price_cache_to_db(
            {
                "AAPL": {
                    "expiry": datetime.now(timezone.utc),
                    "data": {"price": 175.0},
                }
            }
        )

        connection.rollback.assert_called_once()

    def test_save_info_cache_rolls_back_on_sqlite_error(self):
        """A failed info-cache transaction should be rolled back."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = sqlite3.Error("write failed")
        self.dbm.conn = connection

        self.dbm.save_info_cache_to_db(
            {
                "AAPL": {
                    "exchange": "NMS",
                    "shortName": "Apple",
                    "longName": "Apple Inc.",
                    "currency": "USD",
                }
            }
        )

        connection.rollback.assert_called_once()

    def test_save_option_position_rolls_back_on_sqlite_error(self):
        """A failed option save should be rolled back."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = sqlite3.Error("write failed")
        self.dbm.conn = connection

        self.dbm.save_option_position("AAPL-CALL", "AAPL", 1.0, 10.0)

        connection.rollback.assert_called_once()

    def test_get_option_methods_handle_sqlite_errors(self):
        """Option reads should return safe values when SQLite fails."""
        connection = Mock()
        connection.cursor.side_effect = sqlite3.Error("read failed")
        self.dbm.conn = connection

        self.assertIsNone(self.dbm.get_option_position("AAPL-CALL"))
        self.assertEqual(self.dbm.get_all_option_positions(), {})

    def test_delete_option_position_rolls_back_on_sqlite_error(self):
        """A failed option deletion should be rolled back."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = sqlite3.Error("delete failed")
        self.dbm.conn = connection

        self.dbm.delete_option_position("AAPL-CALL")

        connection.rollback.assert_called_once()


    def test_create_tables_rolls_back_on_sqlite_error(self):
        """Table creation should roll back when SQLite fails."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = sqlite3.Error("table creation failed")
        self.dbm.conn = connection

        self.dbm._create_tables()

        connection.rollback.assert_called_once()

    def test_prune_logs_deleted_price_and_info_entries(self):
        """Successful pruning should report deleted cache records."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.rowcount = 2
        self.dbm.conn = connection

        with patch("stockstui.database.db_manager.logging.info") as log_info:
            self.dbm._prune_expired_entries()

        self.assertEqual(log_info.call_count, 2)
        connection.commit.assert_called_once()

    def test_prune_rolls_back_on_sqlite_error(self):
        """Failed pruning should roll back its transaction."""
        connection = Mock()
        cursor = Mock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = sqlite3.Error("prune failed")
        self.dbm.conn = connection

        self.dbm._prune_expired_entries()

        connection.rollback.assert_called_once()

    def test_bad_price_entry_does_not_block_valid_entry(self):
        """One malformed cache entry should not block later valid entries."""
        now = datetime.now(timezone.utc)

        cache_data = {
            "BROKEN": {
                "expiry": "not-a-datetime",
                "data": {"price": 1.0},
            },
            "AAPL": {
                "expiry": now,
                "data": {"price": 175.0},
            },
        }

        self.dbm.save_price_cache_to_db(cache_data)

        loaded = self.dbm.load_price_cache_from_db()

        self.assertNotIn("BROKEN", loaded)
        self.assertEqual(loaded["AAPL"]["data"]["price"], 175.0)


if __name__ == "__main__":
    unittest.main()

