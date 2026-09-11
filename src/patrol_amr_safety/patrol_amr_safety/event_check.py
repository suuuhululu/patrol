#!/usr/bin/env python3
"""Stop the current patrol in place, acknowledge completion, resume by topic.

genius_patrol owns motion. This node only receives events; pause_and_wait is
called by that patrol worker and reuses move_to_safetyzone.Evacuation.stop.
"""

from collections import deque
import threading
import time

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.task import Future
from std_msgs.msg import Bool
from std_srvs.srv import SetBool


class EventCheck(Node):
    def __init__(self, args):
        super().__init__('event_check', namespace=args.namespace)
        self._lock = threading.RLock()
        self.history = deque(maxlen=2)  # (source, value, monotonic receive time)
        self.latest_allowed = None
        self._active = False
        self._completion = self._responded = None
        self._group = ReentrantCallbackGroup()
        self.stop_service = self.create_service(
            SetBool, args.stop_service, self.on_stop, callback_group=self._group)
        self.resume_sub = self.create_subscription(
            Bool, args.resume_topic, self.on_resume, 2, callback_group=self._group)
        self.get_logger().info(
            f'Stop service: {args.stop_service} (false); '
            f'resume topic: {args.resume_topic} (true)')

    @property
    def stop_requested(self):
        with self._lock:
            return self._completion is not None and not self._completion.done()

    def set_active(self, active):
        with self._lock:
            self._active = active
            if not active:
                self.fail('Patrol is not active')
                self._completion = self._responded = None
                self.latest_allowed = None

    async def on_stop(self, request, response):
        self.get_logger().info(f'Patrol stop request received: data={request.data}')
        if request.data:
            response.success = False
            response.message = 'Use data=false to stop; resume with the Bool topic'
            self.get_logger().warning(f'Patrol stop request rejected: {response.message}')
            return response
        with self._lock:
            self.history.append(('stop_service', False, time.monotonic()))
            if not self._active:
                response.success = False
                response.message = 'Patrol is not active'
                self.get_logger().warning(f'Patrol stop request rejected: {response.message}')
                return response
            self.latest_allowed = False
            # Concurrent requests share one stop and its completion result.
            if self._completion is None or self._completion.done():
                self._completion = Future(executor=self.executor)
                self.get_logger().info('Patrol stop accepted; waiting for patrol worker to stop')
            else:
                self.get_logger().info('Patrol stop already pending; sharing its completion')
            completion = self._completion
        response.success, response.message = await completion
        self.get_logger().info(
            f'Patrol stop response: success={response.success}; {response.message}')
        with self._lock:
            if self._completion is completion:
                self._responded = completion
        return response

    def on_resume(self, message):
        with self._lock:
            self.history.append(('resume_topic', bool(message.data), time.monotonic()))
            # false does not initiate a stop: it only retracts a pending resume.
            previous_allowed = self.latest_allowed
            self.latest_allowed = bool(message.data)
            if previous_allowed is not self.latest_allowed:
                self.get_logger().info(
                    f'Patrol resume topic received: data={self.latest_allowed}; '
                    f'active={self._active}')

    def fail(self, reason):
        with self._lock:
            if self.stop_requested:
                self.get_logger().error(f'Patrol stop could not complete: {reason}')
                self._completion.set_result((False, str(reason)))

    def pause_and_wait(self, evacuation, index):
        """Called only by the patrol worker; never from a ROS callback."""
        evacuation.saved_index = index
        while True:
            with self._lock:
                if not self._active or self._completion is None:
                    raise RuntimeError('Patrol is not active')
                completion = self._completion
            if not completion.done():
                evacuation.evacuate = False
                self.get_logger().info(f'Patrol worker starting stop: patrol index={index}')
                try:
                    evacuation.stop()
                except Exception as exc:
                    self.fail(f'Stop failed: {exc}')
                    raise
                with self._lock:
                    if not completion.done():
                        completion.set_result((True, f'Stopped in place; patrol index={index}'))
                        self.get_logger().info(
                            f'Patrol stop completed; waiting for response delivery and resume: '
                            f'patrol index={index}')
            if not completion.result()[0]:
                raise RuntimeError(completion.result()[1])
            with self._lock:
                if (self._completion is completion and self._responded is completion
                        and self.latest_allowed is True):
                    self._completion = self._responded = None
                    evacuation.evacuate = False
                    self.get_logger().info(f'Patrol worker resuming: patrol index={index}')
                    return
            evacuation.tick()


class VisionPatrolLink:
    """One vision event: stop, report, then resume after report success."""

    def __init__(self, node, robot_id):
        self.node = node
        self.stop_service_name = f'/{robot_id}/patrol_stop'
        self.resume_topic_name = f'/{robot_id}/patrol_resume'
        self.client = node.create_client(SetBool, self.stop_service_name)
        self.resume_pub = node.create_publisher(Bool, self.resume_topic_name, 2)
        self.pending = None
        self.busy = False
        self.stopped = False
        self._last_wait_log = {}
        self.node.get_logger().info(
            f'Vision patrol link ready: stop service={self.stop_service_name}; '
            f'resume topic={self.resume_topic_name}')

    def _log_wait(self, reason, message):
        now = time.monotonic()
        last_logged = self._last_wait_log.get(reason)
        if last_logged is None or now - last_logged >= 5.0:
            self._last_wait_log[reason] = now
            self.node.get_logger().warning(message)

    def request(self):
        if self.busy:
            self._log_wait(
                'busy', f'Patrol stop request skipped: previous event still in progress; '
                f'stop confirmed={self.stopped}; service={self.stop_service_name}')
            return False
        if not self.client.service_is_ready():
            self._log_wait(
                'unavailable', f'Patrol stop service unavailable: {self.stop_service_name}; '
                'stop request was not sent')
            return False
        self.busy = True
        self.node.get_logger().info(
            f'Sending patrol stop request: service={self.stop_service_name}; data=false')
        try:
            self.pending = self.client.call_async(SetBool.Request(data=False))
        except Exception as exc:
            self.busy = False
            self.node.get_logger().error(f'Patrol stop request dispatch failed: {exc}')
            raise
        self.pending.add_done_callback(self._done)
        return True

    def _done(self, future):
        try:
            response = future.result()
            self.node.get_logger().info(
                f'Patrol stop response received: service={self.stop_service_name}; '
                f'success={response.success}; message={response.message}')
            if not response.success:
                raise RuntimeError(response.message)
        except Exception as exc:
            self.busy = False
            self.node.get_logger().error(f'Patrol stop failed; report deferred: {exc}')
            return
        self.stopped = True

    def resume(self):
        self.resume_pub.publish(Bool(data=True))
        self.node.get_logger().info(
            f'Patrol resume published: topic={self.resume_topic_name}; data=true')
        self.busy = False
        self.stopped = False


def main():
    if __package__:
        from .genius_patrol import main as patrol_main
    else:
        from genius_patrol import main as patrol_main
    patrol_main()


if __name__ == '__main__':
    main()
