import json
from pathlib import Path
import tempfile
import unittest

from patrol_amr.mission_state import MissionStateSnapshot
from patrol_amr.mission_status_store import (
    MissionStatusStore, MissionStatusStoreError)


class MissionStatusStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / 'robot6' / 'mission.json'

    def test_snapshot_survives_process_boundary(self):
        snapshot = MissionStateSnapshot(
            mission='MISSION_PATROLLING',
            waypoint_index=2,
            last_waypoint_index=2,
            command_id='cmd-1',
            mission_id='msn-1',
            revision=7,
        )
        MissionStatusStore(self.path).write(snapshot)
        self.assertEqual(MissionStatusStore(self.path).read(), snapshot)

    def test_missing_file_is_no_status_yet(self):
        self.assertIsNone(MissionStatusStore(self.path).read())

    def test_damaged_or_unknown_schema_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        for payload in (
            '{bad',
            json.dumps({'schema_version': 99}),
            json.dumps('not-an-object'),
        ):
            with self.subTest(payload=payload):
                self.path.write_text(payload)
                with self.assertRaises(MissionStatusStoreError):
                    MissionStatusStore(self.path).read()


if __name__ == '__main__':
    unittest.main()
