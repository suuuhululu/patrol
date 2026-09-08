"""Read persisted mission progress into the RobotStatus state model."""

from __future__ import annotations

from patrol_amr_safety import robot_status_state as rss
from patrol_amr.mission_state import MissionStateSnapshot


class MissionStatusBridge:
    """Track the newest mission snapshot written by mission_supervisor."""

    def __init__(self, store) -> None:
        self._store = store
        self._last_revision = -1
        self._snapshot = MissionStateSnapshot()

    @property
    def snapshot(self) -> MissionStateSnapshot:
        return self._snapshot

    def refresh(self, state: rss.RobotStatusState) -> bool:
        snapshot = self._store.read()
        if snapshot is None or snapshot.revision == self._last_revision:
            return False
        try:
            mission_state = rss.MissionState[snapshot.mission]
        except KeyError as exc:
            raise ValueError(
                f'unsupported persisted mission state: {snapshot.mission}'
            ) from exc
        state.update_states(mission_state=mission_state)
        self._snapshot = snapshot
        self._last_revision = snapshot.revision
        return True
