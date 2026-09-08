import json
from pathlib import Path
import tempfile
import unittest

from patrol_amr.mission_command_store import (
    ClaimResult, CommandStore, StoreError)


class CommandStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_claim_survives_reload_and_detects_content_conflict(self):
        path = self.root / 'robot1.json'
        store = CommandStore(path)
        self.assertIs(store.claim('cmd-1', 'hash-a').result, ClaimResult.NEW)
        store.finish('cmd-1', 'SUCCEEDED')

        reloaded = CommandStore(path)
        self.assertIs(
            reloaded.claim('cmd-1', 'hash-a').result, ClaimResult.DUPLICATE)
        self.assertIs(
            reloaded.claim('cmd-1', 'hash-b').result, ClaimResult.CONFLICT)
        self.assertEqual(reloaded.outcome('cmd-1'), 'SUCCEEDED')

    def test_checkpoint_is_persistent_and_clearable(self):
        path = self.root / 'robot6.json'
        store = CommandStore(path)
        store.save_checkpoint('patrol-a', 3)
        self.assertEqual(CommandStore(path).load_checkpoint('patrol-a'), 3)
        store.clear_checkpoint('patrol-a')
        self.assertIsNone(CommandStore(path).load_checkpoint('patrol-a'))

    def test_superseded_is_a_durable_nonterminal_command_outcome(self):
        path = self.root / 'robot1.json'
        store = CommandStore(path)
        store.claim('cmd-preempted', 'hash-a')
        store.finish(
            'cmd-preempted',
            'SUPERSEDED',
            'SUPERSEDED_BY_HIGHER_PRIORITY',
        )
        self.assertEqual(
            CommandStore(path).outcome('cmd-preempted'),
            'SUPERSEDED',
        )

    def test_damaged_store_fails_closed(self):
        path = self.root / 'damaged.json'
        path.write_text('{not-json')
        with self.assertRaises(StoreError):
            CommandStore(path)

    def test_keeps_all_commands_claimed_within_24_hours(self):
        path = self.root / 'commands.json'
        now = 2_000_000.0
        store = CommandStore(path, clock=lambda: now)
        for index in range(1005):
            store.claim(f'cmd-{index}', f'hash-{index}')
        persisted = json.loads(path.read_text())
        self.assertEqual(len(persisted['commands']), 1005)

    def test_keeps_only_latest_1000_commands_older_than_24_hours(self):
        path = self.root / 'commands.json'
        old_entries = {
            f'old-{index:04d}': {
                'fingerprint': f'hash-{index}',
                'claimed_unix_s': float(index),
                'outcome': 'SUCCEEDED',
                'reason': '',
            }
            for index in range(1005)
        }
        path.write_text(json.dumps({
            'schema_version': 1,
            'commands': old_entries,
            'checkpoints': {},
        }))
        now = 200_000.0

        store = CommandStore(path, clock=lambda: now)
        store.claim('recent', 'recent-hash')

        persisted = json.loads(path.read_text())['commands']
        self.assertEqual(len(persisted), 1001)
        self.assertNotIn('old-0000', persisted)
        self.assertNotIn('old-0004', persisted)
        self.assertIn('old-0005', persisted)
        self.assertIn('old-1004', persisted)
        self.assertIn('recent', persisted)
