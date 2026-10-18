"""Undo journal for changes that must update settings and watchlists together.

Callers hold the shared configuration lock and both existing per-file locks.
An extant journal means the operation was not acknowledged as committed.
"""
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

JOURNAL = '.configuration-transaction.json'
FILES = frozenset({'settings.json', 'lists.json'})


def _sync_directory(directory: Path):
    if sys.platform == 'win32':
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_bytes(path: Path, data: bytes):
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError as error:
            logging.warning('Could not remove temporary configuration file: %s', error)


def _digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def recover_pending(directory: Path):
    journal = directory / JOURNAL
    if not journal.exists():
        return
    try:
        records = json.loads(journal.read_text(encoding='utf-8'))
        if not isinstance(records, dict) or not records or not set(records) <= FILES:
            raise ValueError('Invalid transaction file names')
        originals = {}
        # Validate every file before restoring any, preserving external manual edits.
        for name, record in records.items():
            if not isinstance(record, dict):
                raise ValueError('Invalid transaction record')
            original = base64.b64decode(record['before'], validate=True) if record['before'] is not None else None
            original_hash = _digest(original)
            path = directory / name
            current = path.read_bytes() if path.exists() else None
            if _digest(current) not in (original_hash, record['after_sha256']):
                raise ValueError('Configuration changed outside the interrupted transaction')
            originals[name] = original
        for name, data in originals.items():
            path = directory / name
            current = path.read_bytes() if path.exists() else None
            if current == data:
                continue
            if data is None:
                path.unlink(missing_ok=True)
            else:
                _replace_bytes(path, data)
        _sync_directory(directory)
        journal.unlink()
        _sync_directory(directory)
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise OSError(f'An interrupted configuration change needs recovery. Journal: {journal}. Original data and external manual edits are preserved.') from error


def commit_bundle(directory: Path, before: dict[str, bytes | None], after: dict[str, bytes]):
    if not after or not set(after) <= FILES or set(before) != set(after):
        raise ValueError('Unsupported configuration bundle')
    journal = directory / JOURNAL
    if journal.exists():
        raise OSError('An earlier configuration transaction needs recovery')
    originals = {name: base64.b64encode(data).decode('ascii') if data is not None else None for name, data in before.items()}
    records = {name: dict(before=originals[name], after_sha256=_digest(data)) for name, data in after.items()}
    payload = json.dumps(records).encode('utf-8')
    _replace_bytes(journal, payload)
    try:
        _sync_directory(directory)
        for name, data in after.items():
            _replace_bytes(directory / name, data)
        _sync_directory(directory)
        journal.unlink()
        _sync_directory(directory)
    except Exception:
        # Recreate the undo journal if acknowledging the commit failed after unlink.
        if not journal.exists():
            _replace_bytes(journal, payload)
        recover_pending(directory)
        raise
