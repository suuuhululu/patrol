"""Replay retained PatrolReport records after transport reconnection.

The public contract requires durable local storage and retransmission with the
same report ID, but it does not define an acknowledgement message.  This
module therefore does not delete or acknowledge records.  It detects only a
subscriber-count transition from disconnected to connected and lets the ROS
owner replay every retained terminal report once for that connection epoch.
"""

from patrol_amr import patrol_report


class SubscriberConnectionReplay:
    """Detect subscriber connection epochs without a wall-clock timeout."""

    def __init__(self):
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def observe(self, subscription_count: int) -> bool:
        """Return True once when the count changes from zero to positive."""
        if (
            isinstance(subscription_count, bool)
            or not isinstance(subscription_count, int)
            or subscription_count < 0
        ):
            raise ValueError('subscription_count must be a non-negative int')
        connected = subscription_count > 0
        replay_due = connected and not self._connected
        self._connected = connected
        return replay_due


def replay_completed_reports(
    store,
    publisher,
    message_type,
    published_at_factory,
):
    """Publish every retained completed report and return its report IDs.

    ``published_at_factory`` is called separately for every transmission so
    the transport owner supplies its current ROS clock without this module
    inventing a timestamp or freshness policy.
    """
    if not callable(published_at_factory):
        raise ValueError('published_at_factory must be callable')
    try:
        records = store.completed_reports()
    except AttributeError as error:
        raise ValueError('store must provide completed_reports()') from error

    report_ids = []
    for record in records:
        patrol_report.publish_record(
            publisher,
            message_type,
            record,
            published_at_factory(),
        )
        report_ids.append(record.report_id)
    return tuple(report_ids)
