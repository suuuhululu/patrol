"""6단계 검증: 점유 지도 검증·파일/DB 저장·좌표 변환·보호된 조회를 확인한다."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import struct
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service


class MapTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "map-tests-only-key",
            "ROBOT_API_KEY": "map-device-test-key",
            "MAP_MAX_CELLS": 100,
            "ROBOT_OFFLINE_AFTER_SECONDS": 30,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")

    def login_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def map_payload(self, message_id="nav-map-001", seconds_ago=3, **changes):
        payload = {
            "message_id": message_id,
            "frame_id": "map",
            "resolution": 1.0,
            "width": 10,
            "height": 8,
            "origin": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            "data": [0] * 60 + [100] * 10 + [-1] * 10,
            "observed_at": (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat(),
        }
        payload.update(changes)
        return payload

    def robot_payload(self, message_id, x, y, seconds_ago, frame_id="map"):
        return {
            "message_id": message_id, "robot_id": "AMR1", "battery": 80,
            "x": x, "y": y, "frame_id": frame_id,
            "mission_status": "PATROLLING", "connection_status": "ONLINE",
            "observed_at": (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat(),
        }

    def send_map(self, payload, token="map-device-test-key"):
        headers = {"X-Robot-Token": token} if token is not None else {}
        return self.client.post("/api/maps/current", json=payload, headers=headers)

    def send_robot(self, payload):
        return self.client.post("/api/robots/status", json=payload,
                                headers={"X-Robot-Token": "map-device-test-key"})

    def test_map_api_requires_device_token_and_closes_without_configuration(self):
        self.assertEqual(self.send_map(self.map_payload(), token=None).status_code, 401)
        self.assertEqual(self.send_map(self.map_payload(), token="wrong").status_code, 401)
        disabled_config = {**self.config, "DATABASE": str(Path(self.folder.name) / "disabled/db.sqlite3"),
                           "ROBOT_API_KEY": None}
        disabled = create_app(disabled_config).test_client()
        self.assertEqual(disabled.post("/api/maps/current", json=self.map_payload()).status_code, 503)
        invalid_token_config = {
            **self.config,
            "DATABASE": str(Path(self.folder.name) / "invalid-token/db.sqlite3"),
            "ROBOT_API_KEY": "한글-토큰",
        }
        with self.assertRaisesRegex(RuntimeError, "ASCII"):
            create_app(invalid_token_config)

    def test_valid_occupancy_grid_creates_png_and_metadata_only_in_db(self):
        response = self.send_map(self.map_payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["result"], "accepted")
        map_dir = Path(self.app.config["MAP_DIR"])
        images = list(map_dir.glob("map-*.png"))
        self.assertEqual(len(images), 1)
        png = images[0].read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (10, 8))
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM maps").fetchone()
            self.assertEqual(row["image_path"], images[0].name)
            self.assertEqual(row["resolution"], 1.0)
            self.assertNotIn(bytes([100]) * 10, str(dict(row)).encode())

    def test_retry_conflict_and_stale_map_do_not_change_current_map(self):
        payload = self.map_payload(seconds_ago=2)
        self.assertEqual(self.send_map(payload).status_code, 201)
        self.assertEqual(self.send_map(payload).get_json()["result"], "duplicate")
        changed = {**payload, "data": [0] * 80}
        self.assertEqual(self.send_map(changed).status_code, 409)
        stale = self.map_payload(message_id="nav-map-old", seconds_ago=10, data=[50] * 80)
        self.assertEqual(self.send_map(stale).status_code, 409)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM maps").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT m.message_id FROM map_latest l JOIN maps m ON m.id=l.map_id").fetchone()[0],
                             "nav-map-001")
        self.assertEqual(len(list(Path(self.app.config["MAP_DIR"]).glob("map-*.png"))), 1)

    def test_invalid_map_inputs_leave_database_and_map_folder_empty(self):
        invalid = [
            self.map_payload(frame_id="odom"),
            self.map_payload(width=True),
            self.map_payload(width=11, height=10, data=[0] * 110),
            self.map_payload(resolution=0),
            self.map_payload(origin={"x": math.nan, "y": 0, "yaw": 0}),
            self.map_payload(data=[0] * 79),
            self.map_payload(data=[101] + [0] * 79),
            self.map_payload(observed_at="2026-09-06 11:00:00"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.send_map(payload).status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM maps").fetchone()[0], 0)
        self.assertEqual(list(Path(self.app.config["MAP_DIR"]).iterdir()), [])

    def test_large_grid_is_stored_and_only_the_image_is_downsampled(self):
        """실제 크기 지도를 거부하지 않고 화면용 이미지 픽셀만 줄인다."""
        from app.services import map_service
        from app.services.map_service import downsample_grid

        width, height = 40, 30
        payload = self.map_payload(
            message_id="nav-map-big", width=width, height=height,
            data=[0] * (width * height - 3) + [100, 100, -1],
        )
        app = create_app({**self.config, "MAP_MAX_CELLS": 10_000, "MAP_MAX_IMAGE_SIDE": 10})
        with app.app_context():
            outcome, stored = map_service.receive_map(payload)
            self.assertEqual(outcome, "accepted")
            # 좌표 변환에 쓰는 크기는 원본 그대로 저장한다.
            self.assertEqual((stored["width"], stored["height"]), (width, height))
            image = Path(app.config["MAP_DIR"]) / stored["image_path"]
            self.assertTrue(image.is_file())
            # PNG 헤더의 가로·세로는 솎은 크기다.
            header = image.read_bytes()[16:24]
            self.assertEqual(
                (int.from_bytes(header[:4], "big"), int.from_bytes(header[4:], "big")),
                (10, 8),
            )
        data, out_width, out_height = downsample_grid(list(range(12)), 4, 3, 2)
        self.assertEqual((out_width, out_height), (2, 2))
        self.assertEqual(data, [0, 2, 8, 10])
        # 제한보다 작은 격자는 그대로 둔다.
        self.assertEqual(downsample_grid([1, 2, 3, 4], 2, 2, 10), ([1, 2, 3, 4], 2, 2))

    def test_login_map_api_and_image_are_protected(self):
        self.assertEqual(self.client.get("/api/maps/current").location, "/login")
        self.assertEqual(self.client.get("/api/maps/current/image").location, "/login")
        self.send_map(self.map_payload())
        self.login_session()
        state = self.client.get("/api/maps/current")
        self.assertEqual(state.status_code, 200)
        self.assertTrue(state.get_json()["available"])
        image = self.client.get(state.get_json()["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.mimetype, "image/png")
        image.close()

    def test_robot_coordinates_and_recent_path_are_converted_to_map_pixels(self):
        self.send_map(self.map_payload())
        self.assertEqual(self.send_robot(self.robot_payload("amr1-map-001", 2, 2, 2)).status_code, 201)
        self.assertEqual(self.send_robot(self.robot_payload("amr1-map-002", 3, 4, 1)).status_code, 201)
        self.login_session()
        data = self.client.get("/api/maps/current").get_json()
        marker = data["robots"][0]
        self.assertEqual((marker["x"], marker["y"]), (3.0, 4.0))
        self.assertTrue(marker["inside_map"])
        self.assertEqual(data["paths"][0]["points"], [{"x": 2.0, "y": 6.0}, {"x": 3.0, "y": 4.0}])

    def test_frame_mismatch_is_not_drawn_and_outside_coordinate_is_reported(self):
        self.send_map(self.map_payload())
        self.send_robot(self.robot_payload("amr1-odom-001", 2, 2, 1, frame_id="odom"))
        self.login_session()
        frame_state = self.client.get("/api/maps/current").get_json()
        self.assertEqual(frame_state["robots"], [])
        self.assertIn("odom", frame_state["coordinate_warnings"][0])

        newer = self.robot_payload("amr1-map-outside", 20, 20, 0)
        self.assertEqual(self.send_robot(newer).status_code, 201)
        marker = self.client.get("/api/maps/current").get_json()["robots"][0]
        self.assertFalse(marker["inside_map"])

    def test_origin_yaw_is_applied_to_robot_marker(self):
        rotated = self.map_payload(origin={"x": 0, "y": 0, "yaw": math.pi / 2})
        self.send_map(rotated)
        self.send_robot(self.robot_payload("amr1-rotated", 0, 2, 1))
        self.login_session()
        marker = self.client.get("/api/maps/current").get_json()["robots"][0]
        self.assertAlmostEqual(marker["x"], 2.0, places=3)
        self.assertAlmostEqual(marker["y"], 8.0, places=3)


if __name__ == "__main__":
    unittest.main()
