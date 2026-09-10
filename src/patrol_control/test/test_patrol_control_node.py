"""Unit tests for PatrolControlNode callbacks with local test doubles."""

from types import SimpleNamespace

from patrol_control.control_core import TaskState
from patrol_control.patrol_control_node import PatrolControlNode
from patrol_interfaces.action import Patrol
import pytest
import rclpy
from std_msgs.msg import Bool


class FakeFuture:
    """Small synchronous stand-in for an rclpy Future."""

    def __init__(self) -> None:
        self._callbacks = []
        self._result = None
        self._exception = None

    def add_done_callback(self, callback) -> None:
        self._callbacks.append(callback)

    def result(self):
        if self._exception is not None:
            raise self._exception
        return self._result

    def resolve(self, result) -> None:
        self._result = result
        for callback in tuple(self._callbacks):
            callback(self)


class FakeGoalHandle:
    """Accepted or rejected Patrol Goal handle."""

    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted
        self.result_future = FakeFuture()
        self.cancel_called = False

    def get_result_async(self):
        return self.result_future

    def cancel_goal_async(self):
        self.cancel_called = True
        return FakeFuture()


class FakeActionClient:
    """Capture Patrol Goals without contacting an Action server."""

    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.goal_future = FakeFuture()
        self.goals = []
        self.feedback_callback = None

    def server_is_ready(self) -> bool:
        return self.ready

    def send_goal_async(self, goal, *, feedback_callback):
        self.goals.append(goal)
        self.feedback_callback = feedback_callback
        return self.goal_future


class RecordingPublisher:
    """Collect published ROS messages for assertions."""

    def __init__(self) -> None:
        self.messages = []

    def publish(self, message) -> None:
        self.messages.append(message)


@pytest.fixture
def control_node():
    """Create a real Node without spinning an executor or ROS peers."""
    if rclpy.ok():
        rclpy.shutdown()
    rclpy.init()
    node = PatrolControlNode()
    try:
        yield node
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def install_recorders(node: PatrolControlNode):
    """Replace command and token outputs with recording publishers."""
    commands = {
        robot_id: RecordingPublisher() for robot_id in node._core.robot_ids
    }
    tokens = {
        robot_id: RecordingPublisher() for robot_id in node._core.robot_ids
    }
    node._command_publishers = commands
    node._token_publishers = tokens
    return commands, tokens


def start_and_accept(node: PatrolControlNode, robot_id: str = 'robot1'):
    """Start a permitted Goal and synchronously accept it."""
    client = FakeActionClient()
    node._action_clients[robot_id] = client
    node._core.observe_permit(True)
    assert node.start_patrol(robot_id) is True
    goal_handle = FakeGoalHandle()
    client.goal_future.resolve(goal_handle)
    return client, goal_handle


def feedback_message(*, state: int, event_type: int = 0, event_id: str = ''):
    """Build the Feedback wrapper passed by rclpy ActionClient."""
    feedback = Patrol.Feedback()
    feedback.task_state = state
    feedback.event_type = event_type
    feedback.event_id = event_id
    return SimpleNamespace(feedback=feedback)


def test_start_requires_permit_and_ready_server(control_node) -> None:
    client = FakeActionClient(ready=True)
    control_node._action_clients['robot1'] = client

    assert control_node.start_patrol('robot1') is False
    assert client.goals == []

    control_node._core.observe_permit(True)
    client.ready = False
    assert control_node.start_patrol('robot1') is False
    assert client.goals == []


def test_goal_contains_identity_and_acceptance_does_not_grant_token(
    control_node,
) -> None:
    _, tokens = install_recorders(control_node)
    client, _ = start_and_accept(control_node)

    assert len(client.goals) == 1
    assert client.goals[0].robot_id == 'robot1'
    assert client.goals[0].command_id.startswith('cmd-robot1-start-')

    control_node._publish_token_frames()
    assert tokens['robot1'].messages[-1].token == ''
    assert tokens['robot6'].messages[-1].token == ''


def test_waiting_feedback_grants_token_only_to_active_robot(control_node) -> None:
    _, tokens = install_recorders(control_node)
    start_and_accept(control_node)

    control_node._on_patrol_feedback(
        feedback_message(state=TaskState.WAITING_FOR_TOKEN),
        robot_id='robot1',
    )
    control_node._publish_token_frames()

    robot1 = tokens['robot1'].messages[-1]
    robot6 = tokens['robot6'].messages[-1]
    assert robot1.token != ''
    assert robot1.holder_robot_id == 'robot1'
    assert robot1.lease_duration.sec == 1
    assert robot1.lease_duration.nanosec == 0
    assert robot1.sequence == 1
    assert robot6.token == ''
    assert robot6.holder_robot_id == 'robot6'
    assert robot6.sequence == 1


def test_permit_edges_publish_one_command_each(control_node) -> None:
    commands, _ = install_recorders(control_node)
    start_and_accept(control_node)

    control_node._on_patrol_allowed(Bool(data=False))
    control_node._on_patrol_allowed(Bool(data=False))
    control_node._on_patrol_allowed(Bool(data=True))

    published = commands['robot1'].messages
    assert len(published) == 2
    assert published[0].command == published[0].MOVE_TO_SAFE_ZONE
    assert published[1].command == published[1].RESUME_PATROL
    assert published[0].robot_id == 'robot1'
    assert published[0].command_id != published[1].command_id
    assert commands['robot6'].messages == []


def test_rejected_goal_releases_active_slot(control_node) -> None:
    client = FakeActionClient()
    control_node._action_clients['robot1'] = client
    control_node._core.observe_permit(True)

    assert control_node.start_patrol('robot1') is True
    client.goal_future.resolve(FakeGoalHandle(accepted=False))

    assert control_node._core.active_robot_id is None
    assert control_node._core.drive_granted is False


def test_cancel_revokes_token_before_action_result(control_node) -> None:
    _, tokens = install_recorders(control_node)
    _, goal_handle = start_and_accept(control_node)
    control_node._on_patrol_feedback(
        feedback_message(state=TaskState.WAITING_FOR_TOKEN),
        robot_id='robot1',
    )

    assert control_node.cancel_active_patrol() is True
    assert goal_handle.cancel_called is True
    assert tokens['robot1'].messages[-1].token == ''
    assert control_node._core.active_robot_id == 'robot1'

    result = Patrol.Result()
    result.outcome = Patrol.Result.CANCELED
    result.reason_code = Patrol.Result.REASON_CONTROL_CANCELED
    goal_handle.result_future.resolve(SimpleNamespace(result=result))

    assert control_node._core.active_robot_id is None
    assert control_node._core.drive_granted is False


def test_auto_start_sends_only_one_goal(control_node) -> None:
    client = FakeActionClient()
    control_node._action_clients['robot1'] = client
    control_node._auto_start = True

    control_node._on_patrol_allowed(Bool(data=True))
    control_node._try_auto_start()

    assert len(client.goals) == 1
    assert control_node._auto_start_done is True
