"""Exercise the actual vision report methods without a camera or YOLO model."""

import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from rclpy.task import Future
from rclpy.time import Time
from patrol_interfaces.srv import ReportDetection
from std_msgs.msg import Bool
from std_srvs.srv import SetBool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Client:
    def __init__(self):
        self.calls = []
        self.ready = True

    def service_is_ready(self):
        return self.ready

    def call_async(self, request):
        future = Future()
        self.calls.append((request, future))
        return future


@pytest.fixture
def vision(monkeypatch):
    ultralytics = ModuleType('ultralytics')
    ultralytics.YOLO = lambda *_: pytest.fail('A model must not load in this test')
    monkeypatch.setitem(sys.modules, 'ultralytics', ultralytics)
    module = importlib.import_module('patrol_amr_safety.vision_node_v2')

    class Harness(module.DetectingNode):
        def __init__(self):
            self.class_name, self.confidence, self.bbox = 'fire', 0.9, (1, 1, 10, 10)
            self.event_type_map = {'fire': ReportDetection.Request.FIRE}
            self.submit_client, self.stop_client = Client(), Client()
            self._pending_futures = set()
            self._frames_received = self._frames_processed = 0
            self._last_image_at = self._last_odom_at = None
            self._last_detection = 'none'
            self._last_boxes_count = 0
            self.published, self.errors, self.recorded = [], [], []
            self.patrol_events = module.VisionPatrolLink(self, module.ROBOT_ID)

        def create_client(self, service_type, name):
            assert service_type is SetBool
            assert name == '/robot1/patrol_stop'
            return self.stop_client

        def create_publisher(self, message_type, name, depth):
            assert name == '/robot1/patrol_resume'
            assert depth == 2
            return SimpleNamespace(publish=lambda msg: self.published.append(msg.data))

        def get_logger(self):
            return SimpleNamespace(
                error=self.errors.append,
                info=lambda _, **kwargs: None,
                warning=lambda _, **kwargs: None,
            )

        def get_clock(self):
            return SimpleNamespace(now=lambda: Time(seconds=10))

        def get_current_position(self):
            return (1.0, 2.0)

        def compute_theta(self, *_):
            return 0.5

        def record_reported_event(self, *args):
            self.recorded.append(args)

    return Harness()


def test_real_node_initialization_connects_robot1_stop_and_resume(monkeypatch):
    ultralytics = ModuleType('ultralytics')
    ultralytics.YOLO = lambda *_: pytest.fail('A model must not load in this test')
    monkeypatch.setitem(sys.modules, 'ultralytics', ultralytics)
    module = importlib.import_module('patrol_amr_safety.vision_node_v2')
    clients, publishers, model_paths = {}, {}, []

    def fake_model(path):
        model_paths.append(path)
        return SimpleNamespace(names={})

    def create_client(_node, service_type, name):
        client = Client()
        clients[name] = (service_type, client)
        return client

    def create_publisher(_node, message_type, name, depth):
        publisher = SimpleNamespace(publish=lambda _: None)
        publishers[name] = (message_type, depth, publisher)
        return publisher

    monkeypatch.setattr(module, 'YOLO', fake_model)
    monkeypatch.setattr(module.Node, '__init__', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.DetectingNode, 'create_client', create_client)
    monkeypatch.setattr(module.DetectingNode, 'create_publisher', create_publisher)
    monkeypatch.setattr(module.DetectingNode, 'create_subscription',
                        lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(module.DetectingNode, 'create_timer',
                        lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(module.DetectingNode, 'get_logger', lambda _: SimpleNamespace(
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    ))

    node = module.DetectingNode()

    assert model_paths == [str(module.MODEL_PATH)]
    assert isinstance(node.patrol_events, module.VisionPatrolLink)
    assert clients['/robot1/patrol_stop'] == (SetBool, node.patrol_events.client)
    assert publishers['/robot1/patrol_resume'] == (
        Bool, 2, node.patrol_events.resume_pub)
    assert clients[module.SUBMIT_SERVICE] == (ReportDetection, node.submit_client)


def stop_confirmed(vision):
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    assert vision.patrol_events.request()
    request, pending = vision.stop_client.calls[-1]
    assert request.data is False
    assert vision.submit_client.calls == []
    assert vision.published == []
    pending.set_result(SetBool.Response(success=True, message='Stopped'))
    assert vision.patrol_events.stopped
    vision.submit_event(frame)
    return vision.submit_client.calls[-1]


def test_vision_resumes_only_after_monitor_stored_response(vision):
    request, report = stop_confirmed(vision)
    assert request.robot_id == 'robot1'
    assert vision.published == []
    assert vision.patrol_events.busy
    assert not vision.patrol_events.request()
    report.set_result(ReportDetection.Response(status=ReportDetection.Response.STORED))
    assert vision.published == [True]
    assert vision.recorded == [('fire', (1.0, 2.0), 0.5)]
    assert not vision.patrol_events.busy


def test_report_snapshot_survives_later_camera_updates(vision):
    request, report = stop_confirmed(vision)
    vision.class_name, vision.bbox, vision.confidence = 'leak', None, 0.0
    assert request.event_type == ReportDetection.Request.FIRE
    assert (request.position.x, request.position.y) == (1.0, 2.0)
    assert request.detected_at.sec == 10
    assert len(request.image) > 0
    report.set_result(ReportDetection.Response(status=ReportDetection.Response.STORED))
    assert vision.recorded == [('fire', (1.0, 2.0), 0.5)]


@pytest.mark.parametrize('transport_error', [False, True])
def test_failed_stop_never_reports_or_resumes(vision, transport_error):
    assert vision.patrol_events.request()
    pending = vision.stop_client.calls[-1][1]
    if transport_error:
        pending.set_exception(RuntimeError('Stop service failed'))
    else:
        pending.set_result(SetBool.Response(success=False, message='Not stopped'))
    assert not vision.submit_client.calls
    assert not vision.published
    assert vision.errors


@pytest.mark.parametrize('transport_error', [False, True])
def test_failed_report_does_not_resume(vision, transport_error):
    _, report = stop_confirmed(vision)
    if transport_error:
        report.set_exception(RuntimeError('Monitor unavailable'))
    else:
        report.set_result(ReportDetection.Response(
            status=(ReportDetection.Response.STORED + 1) % 256))
    assert not vision.published
    assert not vision.recorded


def test_unavailable_stop_service_does_not_start_report(vision):
    vision.stop_client.ready = False
    assert not vision.patrol_events.request()
    assert not vision.submit_client.calls
    assert not vision.published


def test_synchronous_stop_transport_error_allows_later_retry(vision):
    def failed_call(_):
        raise RuntimeError('Transport error')
    vision.stop_client.call_async = failed_call
    with pytest.raises(RuntimeError, match='Transport error'):
        vision.patrol_events.request()
    assert not vision.patrol_events.busy


@pytest.mark.parametrize('stop_reply_after_hold', [False, True])
def test_first_bbox_stops_immediately_but_report_waits_for_stop_and_hold(
        vision, monkeypatch, stop_reply_after_hold):
    module = sys.modules['patrol_amr_safety.vision_node_v2']
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    result = SimpleNamespace(plot=lambda: frame, boxes=[])
    vision.model = SimpleNamespace(predict=lambda **_: [result])
    vision.select_detection = lambda _: ('fire', 0.9, (1, 1, 10, 10))
    vision.is_known_event = lambda *_: False
    vision.class_name = vision.hold_start = vision.last_seen = None
    vision.reported = False
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock.now)
    monkeypatch.setattr(module.cv2, 'imdecode', lambda *_: frame)
    monkeypatch.setattr(module.cv2, 'imshow', lambda *_: None)
    monkeypatch.setattr(module.cv2, 'waitKey', lambda *_: -1)
    image = SimpleNamespace(data=b'')

    vision.image_callback(image)
    assert len(vision.stop_client.calls) == 1  # no one-second wait to request stop
    assert not vision.submit_client.calls
    clock.now = 11.1 if stop_reply_after_hold else 10.1
    vision.image_callback(image)
    assert not vision.submit_client.calls  # even elapsed hold cannot bypass stop reply
    vision.stop_client.calls[0][1].set_result(SetBool.Response(success=True))
    if not stop_reply_after_hold:
        vision.image_callback(image)
        assert not vision.submit_client.calls  # stop alone does not bypass report hold
    clock.now = 11.2
    vision.image_callback(image)
    assert len(vision.stop_client.calls) == 1
    assert len(vision.submit_client.calls) == 1
    assert not vision.published
    vision.submit_client.calls[0][1].set_result(
        ReportDetection.Response(status=ReportDetection.Response.STORED))
    assert vision.published == [True]
    assert not vision.errors
