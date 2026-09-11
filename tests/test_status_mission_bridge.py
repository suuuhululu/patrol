from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for package_root in ('src/patrol_amr_safety', 'src/patrol_amr'):
    sys.path.insert(0, str(REPOSITORY_ROOT / package_root))

from patrol_amr.mission_state import MissionStateSnapshot
from patrol_amr_safety.robot_status_state import MissionState, RobotStatusState
from patrol_amr_safety.status_mission_bridge import MissionStatusBridge


class Store:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def read(self):
        return self.snapshot


class MissionStatusBridgeTest(unittest.TestCase):
    def test_new_revision_updates_public_mission_axis_and_fields(self):
        persisted = MissionStateSnapshot(
            mission='MISSION_PATROLLING',
            waypoint_index=3,
            command_id='cmd-1',
            mission_id='msn-1',
            revision=2,
        )
        state = RobotStatusState('robot6')
        bridge = MissionStatusBridge(Store(persisted))
        self.assertTrue(bridge.refresh(state))
        self.assertEqual(
            state.snapshot(0.0).mission_state,
            MissionState.MISSION_PATROLLING,
        )
        self.assertEqual(bridge.snapshot.command_id, 'cmd-1')
        self.assertFalse(bridge.refresh(state))

    def test_unknown_mission_name_is_rejected(self):
        bridge = MissionStatusBridge(Store(
            MissionStateSnapshot(mission='INVENTED', revision=1)))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            bridge.refresh(RobotStatusState('robot1'))

    def test_older_revision_is_rejected_without_rolling_state_back(self):
        store = Store(MissionStateSnapshot(
            mission='MISSION_PATROLLING', revision=5))
        state = RobotStatusState('robot1')
        bridge = MissionStatusBridge(store)
        self.assertTrue(bridge.refresh(state))

        store.snapshot = MissionStateSnapshot(
            mission='MISSION_PAUSED', revision=4)
        with self.assertRaisesRegex(ValueError, 'moved backward'):
            bridge.refresh(state)
        self.assertEqual(
            state.snapshot(0.0).mission_state,
            MissionState.MISSION_PATROLLING,
        )


if __name__ == '__main__':
    unittest.main()
