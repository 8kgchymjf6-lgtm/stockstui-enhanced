import json
from pathlib import Path
import logging
import os
import copy
import time
import errno
from contextlib import contextmanager

if os.name == "nt":
    import msvcrt
else:
    import fcntl
import tempfile
from threading import RLock
from platformdirs import PlatformDirs

# Use platformdirs to determine the correct user directories.
# This ensures we respect OS conventions (e.g., ~/.config vs ~/Library/Application Support)
# The "appauthor" argument is optional but good practice.
APP_NAME = "stockstui"
APP_AUTHOR = "andriy-git"
dirs = PlatformDirs(APP_NAME, APP_AUTHOR)


@contextmanager
def _configuration_lock(path, timeout=2.0):
    with open(path, "a+b") as lock:
        if os.name == "nt":
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise ConfigSaveError(
                        "Another window is saving configuration. Please retry."
                    ) from error
                time.sleep(0.01)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class ConfigSaveError(OSError):
    """A configuration change was not saved; callers must not report success."""


_MISSING = object()


def _same_data(left, right):
    # Watchlist order is user data: ordinary dict equality ignores it.
    if isinstance(left, dict) and isinstance(right, dict):
        return list(left) == list(right) and all(
            _same_data(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same_data(a, b) for a, b in zip(left, right)
        )
    return left == right


def _merge_changes(base, ours, theirs):
    """Merge independent dictionary keys; reject conflicting list edits."""
    if _same_data(ours, base):
        return theirs if theirs is _MISSING else copy.deepcopy(theirs)
    if _same_data(theirs, base) or _same_data(ours, theirs):
        return ours if ours is _MISSING else copy.deepcopy(ours)
    if all(isinstance(value, dict) for value in (base, ours, theirs)):
        merged = {}
        common = base.keys() & ours.keys() & theirs.keys()
        base_order = [key for key in base if key in common]
        our_order = [key for key in ours if key in common]
        their_order = [key for key in theirs if key in common]
        if our_order == base_order:
            preferred, other = theirs, ours
        elif their_order == base_order or our_order == their_order:
            preferred, other = ours, theirs
        else:
            raise ConfigSaveError(
                "List order changed in another window. Reopen the app before retrying."
            )
        for key in dict.fromkeys([*preferred, *other]):
            value = _merge_changes(
                base.get(key, _MISSING),
                ours.get(key, _MISSING),
                theirs.get(key, _MISSING),
            )
            if value is not _MISSING:
                merged[key] = value
        return merged
    raise ConfigSaveError(
        "Configuration changed in another window. Reopen the app before retrying; your change was not saved."
    )


class ConfigManager:
    """
    Manages loading, saving, and accessing application configuration files.
    It uses platformdirs to store files in OS-appropriate locations.
    - Config files (`.json`) go in the user_config_dir.
    - Cache files (`.db`) go in the user_cache_dir.
    """

    def __init__(self, app_root: Path):
        """
        Initializes the ConfigManager.
        Args:
            app_root: The root path of the application package.
        """
        self._save_lock = RLock()
        self._snapshots: dict[str, dict] = {}
        # Define user-specific and default configuration directories
        self.user_config_dir = Path(dirs.user_config_dir)
        self.user_cache_dir = Path(dirs.user_cache_dir)
        self.default_dir = app_root / "default_configs"

        # Ensure directories exist
        self.user_config_dir.mkdir(parents=True, exist_ok=True)
        self.user_cache_dir.mkdir(parents=True, exist_ok=True)

        # The database path now correctly uses the cache directory.
        self.db_path = self.user_cache_dir / "app_cache.db"

        self.settings: dict = self._load_or_create("settings.json")

        # Merge defaults for new keys to ensure backward compatibility
        try:
            default_settings_path = self.default_dir / "settings.json"
            if default_settings_path.exists():
                with open(default_settings_path, "r") as f:
                    default_settings = json.load(f)
                    updated = False
                    for k, v in default_settings.items():
                        if k not in self.settings:
                            self.settings[k] = v
                            updated = True
                        elif (
                            k == "column_settings"
                            and isinstance(v, list)
                            and isinstance(self.settings[k], list)
                        ):
                            # Special handling for column_settings to merge new columns
                            existing_keys = {
                                col.get("key")
                                for col in self.settings[k]
                                if isinstance(col, dict)
                            }
                            for default_col in v:
                                if (
                                    isinstance(default_col, dict)
                                    and default_col.get("key") not in existing_keys
                                ):
                                    self.settings[k].append(default_col)
                                    updated = True
                    if updated:
                        self.save_settings()
        except Exception as e:
            logging.error(f"Failed to merge default settings: {e}")

        self.lists: dict = self._load_or_create("lists.json")
        self.themes: dict = self._load_or_create("themes.json")
        self.portfolios: dict = self._load_or_create("portfolios.json")

        # Migrate existing stocks to default portfolio on first run
        try:
            self._migrate_stocks_to_default_portfolio()
        except ConfigSaveError as error:
            logging.error("Could not save portfolio migration: %s", error)

    def _load_or_create(self, filename: str) -> dict:
        """
        Loads a JSON configuration file from the user's config directory.
        If the file is missing or corrupted, it's restored from the default config.
        """
        user_path = self.user_config_dir / filename
        default_path = self.default_dir / filename

        data = None
        if user_path.exists():
            try:
                with open(user_path, "r") as f:
                    if os.fstat(f.fileno()).st_size == 0:
                        raise json.JSONDecodeError("File is empty.", "", 0)
                    data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logging.warning(
                    f"User config '{user_path}' is corrupted: {e}. Restoring from default."
                )
                try:
                    backup_path = user_path.with_suffix(user_path.suffix + ".bak")
                    os.replace(user_path, backup_path)
                    logging.info(f"Corrupted file backed up to '{backup_path.name}'.")
                except OSError as backup_err:
                    logging.error(
                        f"Could not back up corrupted file '{user_path}': {backup_err}"
                    )
                data = None

        if data is None:
            if not default_path.exists():
                logging.critical(
                    f"Default config '{default_path}' is missing! Cannot create user config."
                )
                return {}
            try:
                with open(default_path, "r") as f_default:
                    default_data = json.load(f_default)
                self._atomic_save(filename, default_data)
                logging.info(
                    f"Created/Restored user config '{user_path}' from default."
                )
                return default_data
            except (IOError, json.JSONDecodeError) as e:
                logging.error(
                    f"Failed to create user config from '{default_path}': {e}"
                )
                return {}

        self._snapshots[filename] = copy.deepcopy(data)
        return data

    def _atomic_save(self, filename: str, data: dict):
        """Serialize writers and atomically replace using a unique, durable temp file."""
        user_path = self.user_config_dir / filename
        temp_path = None
        with self._save_lock:
            try:
                with _configuration_lock(
                    self.user_config_dir / ("." + filename + ".lock")
                ):
                    candidate = copy.deepcopy(data)
                    baseline = self._snapshots.get(filename, _MISSING)
                    if baseline is not _MISSING:
                        if not user_path.exists():
                            raise ConfigSaveError(
                                "Configuration was removed in another window; reopen the app before saving."
                            )
                        with open(user_path, encoding="utf-8") as existing:
                            current = json.load(existing)
                        candidate = _merge_changes(baseline, candidate, current)
                    fd, name = tempfile.mkstemp(
                        prefix="." + filename + ".",
                        suffix=".tmp",
                        dir=self.user_config_dir,
                    )
                    temp_path = Path(name)
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        json.dump(candidate, stream, indent=2, allow_nan=False)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp_path, user_path)
                    temp_path = None
                    self._snapshots[filename] = copy.deepcopy(candidate)
                    return candidate
            except (OSError, ValueError, TypeError) as error:
                raise ConfigSaveError(f"Could not save {filename}: {error}") from error
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError as cleanup_error:
                        logging.warning(
                            "Could not remove temporary config file: %s", cleanup_error
                        )

    def _save(self, name: str):
        """Restore the last committed in-memory state when saving fails."""
        filename = name + ".json"
        try:
            saved = self._atomic_save(filename, getattr(self, name))
        except ConfigSaveError:
            if filename in self._snapshots:
                setattr(self, name, copy.deepcopy(self._snapshots[filename]))
            raise
        if saved is not None:
            setattr(self, name, saved)

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def save_settings(self):
        self._save("settings")

    def save_lists(self):
        self._save("lists")

    def save_portfolios(self):
        self._save("portfolios")

    def _migrate_stocks_to_default_portfolio(self):
        """Migrate existing stocks from lists to default portfolio if needed."""
        if "portfolios" not in self.portfolios:
            return

        # Check if migration was already done by looking for a migration flag
        if self.portfolios.get("settings", {}).get("migration_completed"):
            return

        default_portfolio = self.portfolios["portfolios"].get("default", {})

        # Only migrate if default portfolio is empty
        if not default_portfolio.get("tickers"):
            # Get all tickers from the 'stocks' list
            stocks_list = self.lists.get("stocks", [])
            if stocks_list:
                tickers = [item["ticker"] for item in stocks_list if "ticker" in item]
                if tickers:
                    import datetime

                    now = datetime.datetime.now().isoformat() + "Z"
                    default_portfolio["tickers"] = tickers
                    default_portfolio["created"] = now
                    default_portfolio["modified"] = now
                    self.portfolios["portfolios"]["default"] = default_portfolio
                    logging.info(f"Migrated {len(tickers)} stocks to default portfolio")

        # Set migration flag to prevent future migrations
        if "settings" not in self.portfolios:
            self.portfolios["settings"] = {}
        self.portfolios["settings"]["migration_completed"] = True
        self.save_portfolios()
