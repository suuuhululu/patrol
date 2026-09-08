"""Convert persistent mission completions to public PatrolReport messages."""

from __future__ import annotations


class PatrolReportPublishError(RuntimeError):
    """A pending result could not complete its ROS publish attempt."""


def nanoseconds_to_time(nanoseconds, message):
    if nanoseconds < 0:
        raise ValueError('time cannot be negative')
    message.sec = nanoseconds // 1_000_000_000
    message.nanosec = nanoseconds % 1_000_000_000
    return message


def fill_message(message, record, header_stamp) -> None:
    """Fill one generated PatrolReport without importing ROS in tests."""
    message.header.stamp = header_stamp
    message.report_id = record.report_id
    message.robot_id = record.robot_id
    message.source_session_id = record.source_session_id
    message.command_id = record.command_id
    message.mission_id = record.mission_id
    message.result = record.result
    message.reason_code = record.reason_code
    message.reason = record.reason
    nanoseconds_to_time(record.started_at_ns, message.started_at)
    nanoseconds_to_time(record.finished_at_ns, message.finished_at)
    message.final_waypoint_id = record.final_waypoint_id
    message.related_event_ids = list(record.related_event_ids)


class PatrolReportDrain:
    """Publish pending reports only when at least one receiver is matched."""

    def __init__(self, outbox, publisher, message_factory, now_message) -> None:
        self._outbox = outbox
        self._publisher = publisher
        self._message_factory = message_factory
        self._now_message = now_message

    def publish_pending(self) -> int:
        if self._publisher.get_subscription_count() < 1:
            return 0
        published = 0
        for record in self._outbox.pending():
            message = self._message_factory()
            fill_message(message, record, self._now_message())
            try:
                self._publisher.publish(message)
                removed = self._outbox.mark_published(record.report_id)
            except Exception as exc:
                raise PatrolReportPublishError(
                    f'cannot publish pending report {record.report_id}'
                ) from exc
            if not removed:
                raise PatrolReportPublishError(
                    f'pending report disappeared: {record.report_id}')
            published += 1
        return published
