"""ROS 2 battery monitor and Q-11 battery-state transition model."""

from enum import IntEnum
import math
import time


BATTERY_STATUS_UNKNOWN = 0
BATTERY_STATUS_CHARGING = 1
BATTERY_STATUS_DISCHARGING = 2
BATTERY_STATUS_FULL = 4


class BatteryStatus(IntEnum):
    UNKNOWN = 0
    CRITICAL = 1
    LOW = 2
    NORMAL = 3
    CHARGING = 4
    PATROL_READY = 5
    FULL = 6


def classify_battery(soc: float, charging: bool) -> BatteryStatus:
    """Classify an already validated SOC and explicitly known direction.

    Invalid arguments indicate a caller error. Sensor-invalid observations
    must instead be supplied as UNKNOWN to BatteryStateModel.update().
    """
    if not math.isfinite(soc) or not 0.0 <= soc <= 1.0:
        raise ValueError('soc must be finite and between 0 and 1')
    if not isinstance(charging, bool):
        raise ValueError('charging must be an explicitly known bool')
    if charging:
        if soc < 0.50:
            return BatteryStatus.CHARGING
        if soc < 0.80:
            return BatteryStatus.PATROL_READY
        return BatteryStatus.FULL
    if soc < 0.10:
        return BatteryStatus.CRITICAL
    if soc < 0.20:
        return BatteryStatus.LOW
    return BatteryStatus.NORMAL


def classify_observation(
    soc: float, present: bool, power_supply_status: int
) -> BatteryStatus:
    """Validate a BatteryState observation and classify it.

    Invalid input becomes UNKNOWN. Charging/FULL and DISCHARGING are the
    only statuses whose direction is considered explicit (TBD-AMR-003
    decision, 2026-09-07).
    """
    if not present or not math.isfinite(soc) or not 0.0 <= soc <= 1.0:
        return BatteryStatus.UNKNOWN
    if power_supply_status in (BATTERY_STATUS_CHARGING, BATTERY_STATUS_FULL):
        return classify_battery(soc, True)
    if power_supply_status == BATTERY_STATUS_DISCHARGING:
        return classify_battery(soc, False)
    return BatteryStatus.UNKNOWN


class BatteryStateModel:
    """Apply Q-11 to observations at caller-supplied monotonic times.

    Call update on every valid observation. Invalid or stale input uses
    invalidate(), because the 2026-09-07 decision requires immediate UNKNOWN.
    """

    HOLD_SECONDS = 3.0

    def __init__(self):
        self.state = BatteryStatus.UNKNOWN
        self.pending = None
        self.pending_since = None
        self.last_update = None

    def update(self, observed: BatteryStatus, now: float) -> BatteryStatus:
        """Return current state; CRITICAL is immediate, others require Q-11."""
        observed = BatteryStatus(observed)
        if not math.isfinite(now):
            raise ValueError('now must be finite')
        if self.last_update is not None and now < self.last_update:
            raise ValueError('now must not move backwards')
        self.last_update = now

        if observed == BatteryStatus.CRITICAL or observed == self.state:
            self.state = observed
            self.pending = None
            self.pending_since = None
        elif observed != self.pending:
            self.pending = observed
            self.pending_since = now
        elif now - self.pending_since >= self.HOLD_SECONDS:
            self.state = observed
            self.pending = None
            self.pending_since = None
        return self.state

    def invalidate(self, now: float) -> BatteryStatus:
        """Immediately set UNKNOWN for invalid input or a three-second gap."""
        if not math.isfinite(now):
            raise ValueError('now must be finite')
        if self.last_update is not None and now < self.last_update:
            raise ValueError('now must not move backwards')
        self.last_update = now
        self.state = BatteryStatus.UNKNOWN
        self.pending = None
        self.pending_since = None
        return self.state


def create_node_class():
    """Import ROS dependencies lazily so pure model tests need no ROS setup."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import (
        DurabilityPolicy,
        HistoryPolicy,
        QoSProfile,
        ReliabilityPolicy,
        qos_profile_sensor_data,
    )
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import UInt8

    class BatteryMonitor(Node):
        """Convert relative battery_state input to relative battery_status."""

        STALE_AFTER_SECONDS = 3.0

        def __init__(self):
            super().__init__('battery_monitor')
            self._model = BatteryStateModel()
            self._last_received_at = None
            self._last_published = None
            output_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            self._publisher = self.create_publisher(
                UInt8, 'battery_status', output_qos
            )
            self.create_subscription(
                BatteryState,
                'battery_state',
                self._on_battery_state,
                qos_profile_sensor_data,
            )
            self.create_timer(0.1, self._check_freshness)
            self._publish_if_changed()

        def _on_battery_state(self, message) -> None:
            now = time.monotonic()
            self._last_received_at = now
            observed = classify_observation(
                message.percentage,
                message.present,
                message.power_supply_status,
            )
            if observed == BatteryStatus.UNKNOWN:
                self._model.invalidate(now)
            else:
                self._model.update(observed, now)
            self._publish_if_changed()

        def _check_freshness(self) -> None:
            now = time.monotonic()
            if self._last_received_at is None:
                return
            if now - self._last_received_at >= self.STALE_AFTER_SECONDS:
                self._model.invalidate(now)
                self._last_received_at = None
                self._publish_if_changed()

        def _publish_if_changed(self) -> None:
            if self._model.state == self._last_published:
                return
            self._last_published = self._model.state
            self._publisher.publish(UInt8(data=int(self._model.state)))
            self.get_logger().info(
                f'battery status: {self._model.state.name}'
            )

    return BatteryMonitor, rclpy


def main(args=None):
    """Run the battery monitor ROS node."""
    BatteryMonitor, rclpy = create_node_class()
    rclpy.init(args=args)
    node = BatteryMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
