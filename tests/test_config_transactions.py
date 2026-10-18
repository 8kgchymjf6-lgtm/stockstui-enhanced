"""Multi-file list edits either commit together or recover their original files."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stockstui import config_manager as config
from stockstui import config_transaction as transaction


class TestConfigTransactions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        patcher=patch.object(config,'dirs',SimpleNamespace(user_config_dir=str(root/'config'),user_cache_dir=str(root/'cache')))
        patcher.start();self.addCleanup(patcher.stop)
        self.app_root=Path(config.__file__).parent
        self.manager=config.ConfigManager(self.app_root)
        self.manager.lists={'first':[dict(ticker='AAPL',alias='',note='',tags='')],'second':[]}
        self.manager.settings.update(default_tab_category='first',hidden_tabs=['first'])
        self.manager.save_lists();self.manager.save_settings()
        self.directory=self.manager.user_config_dir
        self.before={name:(self.directory/name).read_bytes() for name in transaction.FILES}

    def change(self):
        self.manager.lists={'renamed':self.manager.lists['first'],'second':[]}
        self.manager.settings.update(default_tab_category='renamed',hidden_tabs=['renamed'])

    def assert_original(self):
        self.assertEqual({n:(self.directory/n).read_bytes() for n in transaction.FILES},self.before)
        self.assertFalse((self.directory/transaction.JOURNAL).exists())

    def test_success_updates_both_files_and_memory(self):
        self.change();self.manager.save_lists_and_settings()
        reopened=config.ConfigManager(self.app_root)
        self.assertIn('renamed',reopened.lists)
        self.assertEqual(reopened.settings['default_tab_category'],'renamed')
        self.assertEqual(reopened.settings['hidden_tabs'],['renamed'])
        self.assertFalse((self.directory/transaction.JOURNAL).exists())

    def test_reserved_saved_list_is_protected_without_overwriting_original(self):
        raw=b'{"history": [{"ticker": "AAPL"}], "first": []}'
        (self.directory/'lists.json').write_bytes(raw)
        reopened=config.ConfigManager(self.app_root)
        self.assertTrue(reopened.recovery_messages)
        self.assertNotIn('history',reopened.lists)
        self.assertEqual((self.directory/'lists.json').read_bytes(),raw)
        with self.assertRaises(config.ConfigSaveError):reopened.save_lists()
        self.assertEqual((self.directory/'lists.json.bak').read_bytes(),raw)

    def test_directory_sync_failure_after_single_file_commit_keeps_memory_consistent(self):
        self.manager.settings['extra_note']='committed'
        with patch.object(config,'_sync_directory',side_effect=OSError('unsupported')),self.assertLogs(level='WARNING'):
            self.manager.save_settings()
        self.assertEqual(self.manager.settings['extra_note'],'committed')
        self.assertEqual(json.loads((self.directory/'settings.json').read_text())['extra_note'],'committed')

    def test_deep_external_json_is_preserved_on_save_and_recovery(self):
        raw='['*2000+'0'+']'*2000
        (self.directory/'settings.json').write_text(raw)
        with self.assertRaises(config.ConfigSaveError):self.manager.save_settings()
        self.assertEqual((self.directory/'settings.json').read_text(),raw)
        (self.directory/transaction.JOURNAL).write_text(raw)
        reopened=config.ConfigManager(self.app_root)
        self.assertTrue(reopened.recovery_messages)
        self.assertEqual((self.directory/transaction.JOURNAL).read_text(),raw)

    def test_second_file_failure_restores_first_file_and_both_memories(self):
        self.change();replace=transaction.os.replace
        def fail(source,target):
            if Path(target).name=='settings.json':raise PermissionError('denied')
            return replace(source,target)
        with patch.object(transaction.os,'replace',side_effect=fail),self.assertRaises(config.ConfigSaveError):
            self.manager.save_lists_and_settings()
        self.assert_original()
        self.assertIn('first',self.manager.lists)
        self.assertEqual(self.manager.settings['default_tab_category'],'first')

    def test_failure_before_journal_does_not_modify_original_files(self):
        self.change()
        with patch.object(transaction.os,'fsync',side_effect=OSError('disk full')),self.assertRaises(config.ConfigSaveError):
            self.manager.save_lists_and_settings()
        self.assert_original()
        self.assertEqual(list(self.directory.glob('*.tmp')),[])

    def test_interruption_after_first_file_is_undone_at_startup(self):
        self.change();replace=transaction._replace_bytes
        def interrupt(path,data):
            if path.name=='settings.json':raise SystemExit('simulated interruption')
            return replace(path,data)
        with patch.object(transaction,'_replace_bytes',side_effect=interrupt),self.assertRaises(SystemExit):
            self.manager.save_lists_and_settings()
        self.assertTrue((self.directory/transaction.JOURNAL).exists())
        reopened=config.ConfigManager(self.app_root)
        self.assert_original();self.assertIn('first',reopened.lists)
        self.assertEqual(reopened.settings['default_tab_category'],'first')

    def test_interruption_after_both_writes_is_uncommitted_until_acknowledged(self):
        self.change();sync=transaction._sync_directory;calls=0
        def interrupt(directory):
            nonlocal calls
            calls+=1
            if calls==2:raise SystemExit('before commit acknowledgment')
            sync(directory)
        with patch.object(transaction,'_sync_directory',side_effect=interrupt),self.assertRaises(SystemExit):
            self.manager.save_lists_and_settings()
        config.ConfigManager(self.app_root)
        self.assert_original()

    def test_manual_edit_after_interruption_is_preserved_and_writes_protected(self):
        self.change();replace=transaction._replace_bytes
        def interrupt(path,data):
            if path.name=='settings.json':raise SystemExit()
            return replace(path,data)
        with patch.object(transaction,'_replace_bytes',side_effect=interrupt),self.assertRaises(SystemExit):
            self.manager.save_lists_and_settings()
        custom=json.loads(self.before['settings.json']);custom['manual_note']='keep this edit'
        edited=json.dumps(custom).encode();(self.directory/'settings.json').write_bytes(edited)
        lists=(self.directory/'lists.json').read_bytes()
        reopened=config.ConfigManager(self.app_root)
        self.assertEqual((self.directory/'settings.json').read_bytes(),edited)
        self.assertEqual((self.directory/'lists.json').read_bytes(),lists)
        self.assertTrue(reopened.recovery_messages)
        self.assertTrue((self.directory/transaction.JOURNAL).exists())
        with self.assertRaises(config.ConfigSaveError):reopened.save_lists()

    def test_independent_change_from_another_window_survives_bundle(self):
        other=config.ConfigManager(self.app_root)
        other.settings['auto_refresh']=not other.settings['auto_refresh'];other.save_settings()
        changed=other.settings['auto_refresh']
        self.change();self.manager.save_lists_and_settings()
        reopened=config.ConfigManager(self.app_root)
        self.assertEqual(reopened.settings['auto_refresh'],changed)
        self.assertEqual(reopened.settings['default_tab_category'],'renamed')

    def test_conflicting_list_edits_preserve_other_window_data(self):
        other=config.ConfigManager(self.app_root)
        other.lists['first'].append(dict(ticker='MSFT',alias='',note='',tags=''));other.save_lists()
        self.change()
        with self.assertRaises(config.ConfigSaveError):self.manager.save_lists_and_settings()
        self.assertEqual(self.manager.lists['first'],other.lists['first'])
        self.assertFalse((self.directory/transaction.JOURNAL).exists())

    def test_external_invalid_json_structure_is_never_imported_by_an_unchanged_save(self):
        (self.directory/'settings.json').write_text('[]')
        with self.assertRaises(config.ConfigSaveError):self.manager.save_settings()
        self.assertEqual((self.directory/'settings.json').read_text(),'[]')
        self.assertIsInstance(self.manager.settings,dict)

    def test_invalid_recovery_journal_cannot_write_outside_config_files(self):
        journal=self.directory/transaction.JOURNAL
        journal.write_text(json.dumps({'../outside.json':dict(before=None,after_sha256='bad')}))
        reopened=config.ConfigManager(self.app_root)
        self.assertTrue(journal.exists());self.assertTrue(reopened.recovery_messages)
        self.assertFalse((self.directory.parent/'outside.json').exists())
        for name,data in self.before.items():self.assertEqual((self.directory/name).read_bytes(),data)
