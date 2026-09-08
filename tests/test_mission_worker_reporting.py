from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from patrol_amr.command_store import CommandStore
from patrol_amr.mission_controller import ExecutionResult
from patrol_amr.mission_reporter import MissionReporter
from patrol_amr.mission_state import MissionStateTracker
from patrol_amr.mission_types import MissionRequest, MissionType
from patrol_amr.mission_worker import MissionWorker
from patrol_amr.patrol_report_outbox import PatrolReportOutbox


class Arbiter:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.disabled = []

    def disable_motion(self, reason):
        self.disabled.append(reason)


class Logger:
    def __init__(self):
        self.messages = []

    def __getattr__(self, level):
        return lambda message: self.messages.append((level, message))


class Controller:
    def __init__(self, state_callback, result):
        self.state_callback = state_callback
        self.result = result

    def execute(self, request, cancel_event):
        self.state_callback('MISSION_PATROLLING', 6)
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
                    result, 'amr-20260908T100000')),
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
                    result, 'amr-20260908T100000')),
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


if __name__ == '__main__':
    unittest.main()
