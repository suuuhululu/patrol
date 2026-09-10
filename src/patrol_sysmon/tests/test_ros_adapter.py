"""ROS adapter 등록표와 메시지 변환을 확인한다."""

from math import sin, cos
from types import SimpleNamespace
import unittest
import uuid

from app import ros_adapter


def ns(**values):
    return SimpleNamespace(**values)


def stamp(sec=1_700_000_000, nanosec=250_000_000):
    return ns(sec=sec, nanosec=nanosec)


def header(frame_id="map"):
    return ns(stamp=stamp(), frame_id=frame_id)


GOAL = uuid.UUID("123e4567-e89b-42d3-a456-426614174000")


class RosAdapterTests(unittest.TestCase):
    def patrol_feedback(self, task_state=4, waypoint="wp1", frame_id="map", x=12.4, y=8.7):
        return ns(
            goal_id=ns(uuid=list(GOAL.bytes)),
            feedback=ns(
                task_state=task_state, current_waypoint_id=waypoint, token_valid=True,
                current_pose=ns(header=header(frame_id), pose=ns(position=ns(x=x, y=y, z=0.0))),
            ),
        )

    def occupancy_grid(self):
        angle = 0.5
        return ns(
            header=header(),
            info=ns(
                resolution=0.5,
                width=3,
                height=2,
                origin=ns(
                    position=ns(x=-1.0, y=2.0, z=0.0),
                    orientation=ns(
                        x=0.0, y=0.0, z=sin(angle / 2), w=cos(angle / 2)
                    ),
                ),
            ),
            data=[0, 0, 100, -1, 50, 0],
        )

    def test_estop_payload_uses_contract_fields_only(self):
        message = ns(
            header=header(""), target_robot_id="all", active=True, reason=2,
            sequence=12,
        )
        payload = ros_adapter.estop_payload(message)
        self.assertEqual(payload["target_robot_id"], "all")
        self.assertTrue(payload["active"])
        self.assertEqual(payload["reason"], 2)
        self.assertEqual(payload["sequence"], 12)
        self.assertEqual(
            set(payload),
            {"target_robot_id", "active", "reason", "sequence", "observed_at"},
        )
        with self.assertRaises(ros_adapter.RosMessageMappingError):
            ros_adapter.estop_payload(ns(header=header(""), target_robot_id="AMR1", active=True, reason=0, sequence=1))

    def test_topic_registry_separates_active_and_pending_work(self):
        active = ros_adapter.active_subscriptions()
        self.assertEqual(len(active), 17)
        self.assertEqual(
            {spec.handler for spec in active},
            {
                "patrol_feedback", "patrol_goal_status", "battery_state",
                "map", "camera_frame", "costmap", "camera_state", "estop", "patrol_allowed",
            },
        )
        self.assertEqual(
            len([spec for spec in active if spec.handler == "costmap"]), 2
        )
        self.assertEqual(
            {spec.topic for spec in ros_adapter.SUBSCRIPTIONS if not spec.active}, set()
        )

    def test_dependency_check_reports_each_required_module(self):
        report = ros_adapter.dependency_report()
        self.assertEqual(
            set(report["dependencies"]),
            {
                "rclpy", "patrol_interfaces", "patrol_interfaces.action", "action_msgs",
                "nav_msgs", "sensor_msgs", "std_msgs",
            },
        )
        self.assertEqual(report["ready"], all(report["dependencies"].values()))
        self.assertEqual(
            set(report["errors"]),
            {name for name, available in report["dependencies"].items() if not available},
        )

    def test_patrol_feedback_maps_namespace_goal_state_and_map_pose(self):
        payload = ros_adapter.patrol_feedback_payload(
            "/robot6/patrol_action/_action/feedback", self.patrol_feedback(task_state=11)
        )
        self.assertEqual(payload["robot_id"], "AMR2")
        self.assertEqual(payload["goal_id"], str(GOAL))
        self.assertEqual(payload["task_state"], "WAYPOINT_REACHED")
        self.assertEqual(payload["waypoint_id"], "wp1")
        self.assertTrue(payload["pose_valid"])
        self.assertEqual((payload["x"], payload["y"]), (12.4, 8.7))

    def test_patrol_feedback_without_map_pose_keeps_state_without_coordinates(self):
        """위치를 모르면 좌표만 비우고 임무 상태는 받는다."""
        for message in (
            self.patrol_feedback(frame_id=""),
            self.patrol_feedback(frame_id="odom"),
            self.patrol_feedback(x=float("nan")),
        ):
            with self.subTest(message=message):
                payload = ros_adapter.patrol_feedback_payload(
                    "/robot1/patrol_action/_action/feedback", message
                )
                self.assertFalse(payload["pose_valid"])
                self.assertIsNone(payload["x"])
                self.assertEqual(payload["task_state"], "PATROLLING")

    def test_patrol_feedback_rejects_unknown_topic_state_and_goal_id(self):
        invalid = [
            ("/robot2/patrol_action/_action/feedback", self.patrol_feedback()),
            ("/robot1/patrol_action/_action/feedback", self.patrol_feedback(task_state=99)),
            ("/robot1/patrol_action/_action/feedback", ns(
                goal_id=ns(uuid=[1, 2, 3]), feedback=self.patrol_feedback().feedback,
            )),
        ]
        for topic, message in invalid:
            with self.subTest(topic=topic), self.assertRaises(ros_adapter.RosMessageMappingError):
                ros_adapter.patrol_feedback_payload(topic, message)

    def test_goal_status_keeps_known_states_and_marks_finished(self):
        message = ns(status_list=[
            ns(goal_info=ns(goal_id=ns(uuid=list(GOAL.bytes)), stamp=stamp()), status=2),
            ns(goal_info=ns(goal_id=ns(uuid=list(uuid.uuid4().bytes)), stamp=stamp()), status=6),
            ns(goal_info=ns(goal_id=ns(uuid=list(uuid.uuid4().bytes)), stamp=stamp()), status=0),
        ])
        payload = ros_adapter.patrol_goal_status_payload(
            "/robot1/patrol_action/_action/status", message
        )
        self.assertEqual(payload["robot_id"], "AMR1")
        # UNKNOWN(0)은 판단 근거가 없어 뺀다. ABORTED(6)는 순찰 결과 FAILED로 옮긴다.
        self.assertEqual(
            [(goal["status"], goal["finished"]) for goal in payload["goals"]],
            [("EXECUTING", False), ("FAILED", True)],
        )
        self.assertEqual(payload["goals"][0]["goal_id"], str(GOAL))
        self.assertEqual(payload["goals"][0]["accepted_at"], "2023-11-14T22:13:20.250Z")

    def test_battery_state_maps_percentage_and_leaves_unknown_empty(self):
        payload = ros_adapter.battery_state_payload("/robot1/battery_state", ns(percentage=0.825))
        self.assertEqual((payload["robot_id"], payload["battery"]), ("AMR1", 82.5))
        for value in (float("nan"), 1.5, -0.1, None):
            with self.subTest(value=value):
                self.assertIsNone(ros_adapter.battery_state_payload(
                    "/robot6/battery_state", ns(percentage=value)
                )["battery"])
        with self.assertRaises(ros_adapter.RosMessageMappingError):
            ros_adapter.battery_state_payload("/robot2/battery_state", ns(percentage=0.5))

    def test_occupancy_grid_maps_origin_data_and_stable_message_id(self):
        payload = ros_adapter.occupancy_grid_payload(self.occupancy_grid())
        self.assertEqual(payload["message_id"], "ros-map-1700000000-250000000")
        self.assertEqual((payload["width"], payload["height"]), (3, 2))
        self.assertEqual(payload["origin"]["x"], -1.0)
        self.assertAlmostEqual(payload["origin"]["yaw"], 0.5)
        self.assertEqual(payload["data"], [0, 0, 100, -1, 50, 0])

    def test_compressed_image_maps_topic_and_keeps_bytes(self):
        message = ns(header=header("camera_optical"), data=b"test-image")
        camera_id, frame_id, captured_at, stream = ros_adapter.compressed_image_input(
            "/vision/cctv/gate/image/compressed", message
        )
        self.assertEqual(camera_id, "webcam1")
        self.assertEqual(frame_id, "ros-webcam1-1700000000-250000000")
        self.assertEqual(captured_at, "2023-11-14T22:13:20.250Z")
        self.assertEqual(stream.read(), b"test-image")

    def test_camera_state_maps_topic_enum_and_confidence(self):
        message = ns(
            header=header("gate_cam"), event_id=str(uuid.uuid4()),
            camera_id="gate_cam", state=1, confidence=0.91,
        )
        payload = ros_adapter.camera_state_payload(
            "/vision/cctv/gate_event", message
        )
        self.assertEqual(
            (payload["camera_id"], payload["state"], payload["confidence"]),
            ("gate_cam", "ENTERING", 0.91),
        )
        # [v2 enum] EXITED는 2다. 메시지 상수가 없을 때 쓰는 대비 표도 v2 숫자를 따른다.
        message.state = 2
        self.assertEqual(
            ros_adapter.camera_state_payload("/vision/cctv/gate_event", message)["state"],
            "EXITED",
        )
        message.camera_id = "center_cam"
        with self.assertRaises(ros_adapter.RosMessageMappingError):
            ros_adapter.camera_state_payload("/vision/cctv/gate_event", message)

    def test_patrol_allowed_requires_actual_bool(self):
        self.assertIs(ros_adapter.patrol_allowed_payload(ns(data=False)), False)
        for value in (0, 1, "false", None):
            with self.subTest(value=value), self.assertRaises(
                ros_adapter.RosMessageMappingError
            ):
                ros_adapter.patrol_allowed_payload(ns(data=value))


if __name__ == "__main__":
    unittest.main()
