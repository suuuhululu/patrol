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


class RosAdapterTests(unittest.TestCase):
    def robot_status(self, **changes):
        message = {
            "header": header(),
            "message_id": "123e4567-e89b-42d3-a456-426614174000",
            "robot_id": "robot1",
            "mission_state": 2,
            "battery_soc": 0.825,
            "pose_valid": True,
            "last_valid_pose_stamp": stamp(),
            "pose": ns(pose=ns(position=ns(x=12.4, y=8.7, z=0.0))),
        }
        message.update(changes)
        return ns(**message)

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

    def test_topic_registry_separates_active_and_pending_work(self):
        active = ros_adapter.active_subscriptions()
        self.assertEqual(len(active), 25)
        self.assertEqual(
            {spec.handler for spec in active},
            {
                "robot_status", "map", "camera_frame", "costmap",
                "detection_event", "evidence_chunk", "camera_state",
                "patrol_visit", "patrol_report", "keepout_status", "estop",
                "patrol_allowed",
            },
        )
        self.assertEqual(
            len([spec for spec in active if spec.handler == "costmap"]), 4
        )
        self.assertEqual(
            {spec.topic for spec in ros_adapter.SUBSCRIPTIONS if not spec.active}, set()
        )

    def test_dependency_check_reports_each_required_module(self):
        report = ros_adapter.dependency_report()
        self.assertEqual(
            set(report["dependencies"]),
            {"rclpy", "patrol_interfaces", "nav_msgs", "sensor_msgs", "std_msgs"},
        )
        self.assertEqual(report["ready"], all(report["dependencies"].values()))
        self.assertEqual(
            set(report["errors"]),
            {name for name, available in report["dependencies"].items() if not available},
        )

    def test_robot_status_maps_contract_id_soc_pose_and_mission(self):
        payload = ros_adapter.robot_status_payload(self.robot_status())
        self.assertEqual(payload["robot_id"], "AMR1")
        self.assertEqual(payload["battery"], 82.5)
        self.assertEqual(payload["mission_status"], "PATROLLING")
        self.assertEqual((payload["x"], payload["y"]), (12.4, 8.7))
        self.assertEqual(payload["connection_status"], "ONLINE")
        self.assertEqual(payload["observed_at"], "2023-11-14T22:13:20.250Z")

    def test_invalid_pose_keeps_battery_and_mission_without_coordinates(self):
        """위치를 잃어도 상태 자체는 받는다. 좌표만 비우고 마지막 유효 시각을 남긴다."""
        payload = ros_adapter.robot_status_payload(self.robot_status(
            pose_valid=False,
            pose=ns(pose=ns(position=ns(x=float("nan"), y=float("nan"), z=0.0))),
        ))
        self.assertFalse(payload["pose_valid"])
        self.assertIsNone(payload["x"])
        self.assertIsNone(payload["y"])
        self.assertEqual(payload["battery"], 82.5)
        self.assertEqual(payload["mission_status"], "PATROLLING")
        self.assertEqual(payload["last_valid_pose_at"], "2023-11-14T22:13:20.250Z")

    def test_robot_status_rejects_unknown_id_invalid_pose_and_soc(self):
        invalid_messages = [
            self.robot_status(robot_id="AMR1"),
            self.robot_status(pose_valid="yes"),
            self.robot_status(battery_soc=float("nan")),
            self.robot_status(mission_state=99),
            self.robot_status(header=header("odom")),
        ]
        for message in invalid_messages:
            with self.subTest(message=message), self.assertRaises(
                ros_adapter.RosMessageMappingError
            ):
                ros_adapter.robot_status_payload(message)

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

    def test_detection_event_maps_contract_enum_location_and_ids(self):
        message = ns(
            header=header(), message_id=str(uuid.uuid4()), event_id=str(uuid.uuid4()),
            robot_id="robot1", event_type=4, confidence=0.93, risk_level=2,
            pose=ns(pose=ns(position=ns(x=1.2, y=3.4, z=0.0))),
            location_valid=True, detected_at=stamp(), evidence_id=str(uuid.uuid4()),
        )
        payload = ros_adapter.detection_event_payload(
            "/robot1/detection/event", message
        )
        self.assertEqual(payload["robot_id"], "AMR1")
        self.assertEqual(payload["event_type"], "LIGHTING")
        self.assertEqual(payload["risk_level"], "MEDIUM")
        self.assertEqual((payload["x"], payload["y"]), (1.2, 3.4))

        message.location_valid = False
        message.pose.pose.position.x = float("nan")
        payload = ros_adapter.detection_event_payload(
            "/robot1/detection/event", message
        )
        self.assertEqual((payload["x"], payload["y"]), (None, None))

    def test_evidence_chunk_maps_bytes_and_rejects_namespace_mismatch(self):
        message = ns(
            header=header("camera"), message_id=str(uuid.uuid4()),
            evidence_id=str(uuid.uuid4()), event_id=str(uuid.uuid4()),
            robot_id="robot6", captured_at=stamp(), media_type="image/png",
            sha256="0" * 64, total_size=3, chunk_index=0, chunk_count=1,
            data=[1, 2, 3],
        )
        payload = ros_adapter.evidence_chunk_payload(
            "/robot6/detection/evidence", message
        )
        self.assertEqual(payload["robot_id"], "AMR2")
        self.assertEqual(payload["data"], b"\x01\x02\x03")
        with self.assertRaises(ros_adapter.RosMessageMappingError):
            ros_adapter.evidence_chunk_payload(
                "/robot1/detection/evidence", message
            )

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
