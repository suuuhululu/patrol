from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from patrol_amr.mission_command_store import CommandStore
from patrol_amr.mission_controller import ExecutionResult
from patrol_amr.mission_reporter import MissionReporter
from patrol_amr.mission_state import MissionStateTracker
from patrol_amr.mission_types import (
    MissionOutcome, MissionRequest, MissionType)
from patrol_amr.mission_worker import MissionWorker
from patrol_amr.patrol_report_outbox import PatrolReportOutbox


class Arbiter:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.disabled = []
        self.external_stop_triggered = False
        self.superseded = False

    def disable_motion(self, reason):
        self.disabled.append(reason)

    def was_superseded(self, request):
        return self.superseded


class Logger:
    def __init__(self):
        self.messages = []

    def __getattr__(self, level):
        return lambda message: self.messages.append((level, message))


class Controller:
    def __init__(
        self,
        state_callback,
        result,
        state='MISSION_PATROLLING',
        waypoint_index=6,
    ):
        self.state_callback = state_callback
        self.result = result
        self.state = state
        self.waypoint_index = waypoint_index

    def execute(self, request, cancel_event):
        self.state_callback(self.state, self.waypoint_index)
        return self.result


class MissionWorkerReportingTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_terminal_result_reaches_outbox_and_status_store_sink(self):
        store = CommandStore(self.root / 'commands.json')
        outbox = PatrolReportOutbox(self.root / 'reports.json')
        state = MissionStateTracker()
        arbiter = Arbiter()
        snapshots = []
        times = iter((100, 200))
        worker = MissionWorker(
            SimpleNamespace(robot_id='robot6'),
            '/robot6',
            store,
            arbiter,
            state,
            Logger(),
            lambda: False,
            reporter=MissionReporter(
                lambda result: outbox.enqueue(
                    result, 'robot6-20260908T100000')),
            state_sink=snapshots.append,
            now_ns=lambda: next(times),
        )
        worker._controller = Controller(
            worker._on_state_change, ExecutionResult('SUCCEEDED'))
        request = MissionRequest(
            command_id='cmd-1',
            mission_id='msn-1',
            robot_id='robot6',
            command=MissionType.START_PATROL,
        )

        worker._execute(request)

        pending = outbox.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].command_id, 'cmd-1')
        self.assertEqual(pending[0].final_waypoint_id, 'W7')
        self.assertEqual(pending[0].started_at_ns, 100)
        self.assertEqual(pending[0].finished_at_ns, 200)
        self.assertEqual(store.outcome('cmd-1'), 'SUCCEEDED')
        self.assertEqual(snapshots[-1].mission, 'MISSION_COMPLETED')
        self.assertEqual(arbiter.disabled, [])

    def test_rejected_command_is_not_added_to_patrol_report_outbox(self):
        store = CommandStore(self.root / 'commands.json')
        outbox = PatrolReportOutbox(self.root / 'reports.json')
        worker = MissionWorker(
            SimpleNamespace(robot_id='robot6'),
            '/robot6',
            store,
            Arbiter(),
            MissionStateTracker(),
            Logger(),
            lambda: False,
            reporter=MissionReporter(
                lambda result: outbox.enqueue(
                    result, 'robot6-20260908T100000')),
            now_ns=lambda: 100,
        )
        worker._controller = Controller(
            worker._on_state_change,
            ExecutionResult('REJECTED', 'SAFETY_PATH_NOT_READY'),
        )
        request = MissionRequest(
            command_id='cmd-2',
            mission_id='msn-2',
            robot_id='robot6',
            command=MissionType.START_PATROL,
        )

        worker._execute(request)

        self.assertEqual(outbox.pending(), ())
        self.assertEqual(store.outcome('cmd-2'), 'REJECTED')

    def test_safe_zone_success_preserves_waiting_state_without_report(self):
        store = CommandStore(self.root / 'commands.json')
        outbox = PatrolReportOutbox(self.root / 'reports.json')
        state = MissionStateTracker()
        snapshots = []
        worker = MissionWorker(
            SimpleNamespace(robot_id='robot6'),
            '/robot6',
            store,
            Arbiter(),
            state,
            Logger(),
            lambda: False,
            reporter=MissionReporter(
                lambda result: outbox.enqueue(
                    result, 'robot6-20260908T100000')),
            state_sink=snapshots.append,
            now_ns=lambda: 100,
        )
        worker._controller = Controller(
            worker._on_state_change,
            ExecutionResult('SUCCEEDED'),
            state='MISSION_WAITING_SAFE_ZONE',
            waypoint_index=-1,
        )
        request = MissionRequest(
            command_id='cmd-safe-1',
            mission_id='msn-1',
            robot_id='robot6',
            command=MissionType.MOVE_TO_SAFE_ZONE,
        )

        worker._execute(request)

        self.assertEqual(outbox.pending(), ())
        self.assertEqual(store.outcome('cmd-safe-1'), 'SUCCEEDED')
        self.assertEqual(
            snapshots[-1].mission, 'MISSION_WAITING_SAFE_ZONE')
        self.assertEqual(snapshots[-1].command_id, 'cmd-safe-1')
        self.assertEqual(snapshots[-1].mission_id, 'msn-1')
        self.assertEqual(worker._arbiter.disabled, [])

    def test_local_safety_cancel_uses_safety_reason_and_clears_checkpoint(self):
        store = CommandStore(self.root / 'commands.json')
        store.save_checkpoint('msn-1', 3)
        outbox = PatrolReportOutbox(self.root / 'reports.json')
        arbiter = Arbiter()
        arbiter.external_stop_triggered = True
        state = MissionStateTracker()
        worker = MissionWorker(
            SimpleNamespace(robot_id='robot6'),
            '/robot6',
            store,
            arbiter,
            state,
            Logger(),
            lambda: False,
            reporter=MissionReporter(
                lambda result: outbox.enqueue(
                    result, 'robot6-20260908T100000')),
            now_ns=lambda: 100,
        )
        worker._controller = Controller(
            worker._on_state_change,
            ExecutionResult('CANCELED', 'PATROL_NAVIGATION_CANCELED', 100),
        )
        request = MissionRequest(
            command_id='cmd-safety-1',
            mission_id='msn-1',
            robot_id='robot6',
            command=MissionType.START_PATROL,
        )

        worker._execute(request)

        pending = outbox.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].result, int(MissionOutcome.CANCELED))
        self.assertEqual(pending[0].reason_code, 102)
        self.assertEqual(pending[0].reason, 'LOCAL_SAFETY_REVOKED')
        self.assertIsNone(store.load_checkpoint('msn-1'))
        self.assertEqual(state.snapshot().mission, 'MISSION_CANCELED')

    def test_superseded_command_is_nonterminal_and_has_no_report(self):
        store = CommandStore(self.root / 'commands.json')
        store.save_checkpoint('msn-1', 2)
        outbox = PatrolReportOutbox(self.root / 'reports.json')
        arbiter = Arbiter()
        arbiter.superseded = True
        state = MissionStateTracker()
        snapshots = []
        worker = MissionWorker(
            SimpleNamespace(robot_id='robot6'),
            '/robot6',
            store,
            arbiter,
            state,
            Logger(),
            lambda: False,
            reporter=MissionReporter(
                lambda result: outbox.enqueue(
                    result, 'robot6-20260908T100000')),
            state_sink=snapshots.append,
            now_ns=lambda: 100,
        )
        worker._controller = Controller(
            worker._on_state_change,
            ExecutionResult('CANCELED', 'PATROL_NAVIGATION_CANCELED', 100),
        )
        request = MissionRequest(
            command_id='cmd-preempted-1',
            mission_id='msn-1',
            robot_id='robot6',
            command=MissionType.START_PATROL,
        )

        worker._execute(request)

        self.assertEqual(outbox.pending(), ())
        self.assertEqual(store.outcome(request.command_id), 'SUPERSEDED')
        self.assertEqual(store.load_checkpoint('msn-1'), 2)
        self.assertEqual(snapshots[-1].mission, 'MISSION_PATROLLING')


if __name__ == '__main__':
    unittest.main()
