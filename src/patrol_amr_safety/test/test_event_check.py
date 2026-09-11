from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest
import rclpy
from rclpy.task import Future
from rclpy.time import Time
from rclpy.clock import ClockType
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool
from std_srvs.srv import SetBool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patrol_amr_safety.event_check import EventCheck
from patrol_amr_safety.move_to_safetyzone import Evacuation
import patrol_amr_safety.move_to_safetyzone as safety


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init(args=[])
    yield
    rclpy.shutdown()


@pytest.fixture
def events():
    node = EventCheck(SimpleNamespace(
        namespace='event_check_test', stop_service='patrol_stop',
        resume_topic='patrol_resume', stop_timeout=10.0))
    node.set_active(True)
    yield node
    node.set_active(False)
    node.destroy_node()


def request_stop(events, value=False):
    coroutine = events.on_stop(SetBool.Request(data=value), SetBool.Response())
    return coroutine, coroutine.send(None)


def response_of(coroutine):
    with pytest.raises(StopIteration) as done:
        coroutine.send(None)
    return done.value.value


def test_response_waits_for_stop_and_early_resume_is_preserved(events):
    coroutine, completion = request_stop(events)
    events.on_resume(Bool(data=True))
    order = []

    def stop():
        assert not completion.done()
        order.append('stop_confirmed')

    def tick():
        response = response_of(coroutine)
        assert response.success
        assert 'index=4' in response.message
        order.append('response')

    evacuation = SimpleNamespace(stop=stop, tick=tick, evacuate=True)
    events.pause_and_wait(evacuation, 4)
    order.append('resume')
    assert order == ['stop_confirmed', 'response', 'resume']
    assert evacuation.saved_index == 4
    assert not evacuation.evacuate


def test_duplicate_stop_joins_one_cancellation(events):
    first, first_done = request_stop(events)
    requests = [first]
    stops = []

    def stop():
        stops.append(1)
        second, second_done = request_stop(events)
        requests.append(second)
        assert not second_done.done()
        events.on_resume(Bool(data=True))

    def tick():
        assert first_done.done()
        for coroutine in requests:
            assert response_of(coroutine).success

    events.pause_and_wait(SimpleNamespace(stop=stop, tick=tick), 3)
    assert len(stops) == 1


def test_false_topic_retracts_early_resume_and_history_keeps_two(events):
    coroutine, _ = request_stop(events)
    events.on_resume(Bool(data=True))
    events.on_resume(Bool(data=False))
    assert [entry[1] for entry in events.history] == [True, False]
    ticks = []

    def tick():
        if not ticks:
            assert response_of(coroutine).success
        else:
            events.on_resume(Bool(data=True))
        ticks.append(1)

    events.pause_and_wait(SimpleNamespace(stop=lambda: None, tick=tick), 0)
    assert len(ticks) == 2


def test_stop_failure_is_reported_and_resume_cannot_hide_it(events):
    coroutine, _ = request_stop(events)
    events.on_resume(Bool(data=True))

    def stop():
        raise RuntimeError('No fresh odometry')

    with pytest.raises(RuntimeError, match='No fresh odometry'):
        events.pause_and_wait(SimpleNamespace(stop=stop), 1)
    response = response_of(coroutine)
    assert not response.success
    assert 'No fresh odometry' in response.message


@pytest.mark.parametrize('active,value', [(False, False), (True, True)])
def test_invalid_or_inactive_request_is_rejected(events, active, value):
    events.set_active(active)
    coroutine = events.on_stop(SetBool.Request(data=value), SetBool.Response())
    response = response_of(coroutine)
    assert not response.success
    assert not events.stop_requested


def test_new_stop_while_paused_is_confirmed_again_without_resuming(events):
    first, _ = request_stop(events)
    requests = [first]
    stops, ticks = [], []

    def tick():
        assert response_of(requests[-1]).success
        if not ticks:
            second, _ = request_stop(events)
            requests.append(second)
        else:
            events.on_resume(Bool(data=True))
        ticks.append(1)

    events.pause_and_wait(
        SimpleNamespace(stop=lambda: stops.append(1), tick=tick), 2)
    assert len(stops) == 2


@pytest.mark.parametrize('interrupt_spin', [False, True])
def test_patrol_retries_interrupted_step_without_safe_zone_trip(events, interrupt_spin):
    from patrol_amr_safety import genius_patrol

    nav = SimpleNamespace(docked=True, interrupted=False, steps=[])
    nav.getDockedStatus = lambda: nav.docked
    nav.dock = lambda: setattr(nav, 'docked', True)
    nav.undock = lambda: setattr(nav, 'docked', False)
    nav.getPoseStamped = lambda position, yaw: tuple(position)
    nav.setInitialPose = lambda _: None
    nav.waitUntilNav2Active = lambda: None
    nav.info = lambda _: None

    def record(step, is_spin):
        nav.steps.append(step)
        if not nav.interrupted and is_spin == interrupt_spin:
            nav.interrupted = True
            nav.coroutine, _ = request_stop(events)
        return True

    nav.goToPose = lambda pose: record(pose, False)
    nav.spin = lambda **kwargs: record(('spin', kwargs['spin_dist']), True)
    helper = Evacuation.__new__(Evacuation)
    helper.event_check = events
    helper.evacuate = False
    helper.stop = lambda: None

    def tick():
        helper.check_events()
        if events._completion is not None and events._completion.done():
            assert response_of(nav.coroutine).success
            events.on_resume(Bool(data=True))

    def wait_for_task():
        helper.check_events()
        return not helper.evacuate

    helper.tick = tick
    helper.wait_for_task = wait_for_task
    helper.escape_and_wait = lambda *_: pytest.fail('Unexpected safe-zone movement')
    assert genius_patrol.run_patrol(nav, helper)
    expected_index = 1 if interrupt_spin else 0
    assert helper.saved_index == expected_index
    assert nav.steps[expected_index] == nav.steps[expected_index + 1]
    assert len(nav.steps) == 18  # unchanged 17-step route + interrupted step retry


def stop_harness(monkeypatch, *, moving=False, stale=False, cancel_done=True,
                 action_done=True, queued_before_stop=False):
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(safety.time, 'monotonic', lambda: clock.now)
    result, cancellation = Future(), Future()
    if action_done:
        result.set_result(None)
    if cancel_done:
        cancellation.set_result(SimpleNamespace(goals_canceling=[]))
    nav = SimpleNamespace(
        result_future=result,
        goal_handle=SimpleNamespace(cancel_goal_async=lambda: cancellation),
        isTaskComplete=lambda: result.done(),
        info=lambda _: None,
        get_clock=lambda: SimpleNamespace(
            now=lambda: Time(seconds=clock.now, clock_type=ClockType.ROS_TIME)))
    helper = Evacuation.__new__(Evacuation)
    helper.nav = nav
    helper.args = SimpleNamespace(stop_timeout=0.8, stop_hold=0.2,
                                  data_max_age=1.0, linear_epsilon=0.01,
                                  angular_epsilon=0.02)
    samples = []

    def tick():
        clock.now += 0.1
        msg = Odometry()
        stamp = 8.0 if stale else (9.99 if queued_before_stop else clock.now)
        msg.header.stamp = Time(seconds=stamp).to_msg()
        msg.twist.twist.linear.x = 0.1 if moving else 0.0
        helper.on_odom(msg)
        samples.append(msg)

    helper.tick = tick
    return helper, samples


def test_actual_stop_needs_multiple_fresh_stopped_odometry_samples(monkeypatch):
    helper, samples = stop_harness(monkeypatch)
    helper.stop()
    assert len(samples) >= 3


@pytest.mark.parametrize('options', [
    {'moving': True}, {'stale': True}, {'queued_before_stop': True},
    {'action_done': False}, {'action_done': False, 'cancel_done': False},
])
def test_stop_does_not_ack_movement_stale_data_or_unfinished_cancel(monkeypatch, options):
    helper, _ = stop_harness(monkeypatch, **options)
    with pytest.raises(RuntimeError, match='timeout|did not confirm'):
        helper.stop()


def test_service_and_resume_topic_on_real_executor(events):
    import threading
    from rclpy.executors import SingleThreadedExecutor

    client_node = rclpy.create_node('event_check_test_client')
    client = client_node.create_client(SetBool, '/event_check_test/patrol_stop')
    publisher = client_node.create_publisher(Bool, '/event_check_test/patrol_resume', 2)
    executor = SingleThreadedExecutor()
    executor.add_node(events)
    executor.add_node(client_node)
    thread = threading.Thread(target=executor.spin)
    thread.start()

    def until(predicate):
        deadline = time.monotonic() + 3.0
        while not predicate():
            assert time.monotonic() < deadline, 'ROS callback did not complete'
            time.sleep(0.005)

    try:
        assert client.wait_for_service(timeout_sec=3.0)
        response = client.call_async(SetBool.Request(data=False))
        until(lambda: events.stop_requested)
        assert not response.done()
        until(lambda: publisher.get_subscription_count() > 0)
        publisher.publish(Bool(data=True))
        until(lambda: events.latest_allowed is True)
        stopped = []

        def stop():
            assert not response.done()
            stopped.append(True)

        deadline = time.monotonic() + 3.0

        def tick():
            assert time.monotonic() < deadline, 'Service response blocked resume'
            time.sleep(0.005)

        events.pause_and_wait(SimpleNamespace(stop=stop, tick=tick), 6)
        until(response.done)
        assert stopped == [True]
        assert response.result().success
    finally:
        executor.shutdown(timeout_sec=3.0)
        thread.join(timeout=3.0)
        executor.remove_node(events)
        client_node.destroy_node()
