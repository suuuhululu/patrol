"""9단계 검증: 네 영상의 인증·검증·최신 교체·로그인 표시를 확인한다."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.services import auth_service, camera_service
from app.services.map_service import occupancy_to_png


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.config = {
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "VIDEO_DIR": str(root / "live_frames"),
            "SECRET_KEY": "camera-tests-only-key",
            "ROBOT_API_KEY": "camera-device-test-key",
            "VIDEO_FRAME_MAX_BYTES": 1024,
            "CAMERA_OFFLINE_AFTER_SECONDS": 5,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.png = occupancy_to_png([0, 100, -1, 0], 2, 2)
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")

    def send_frame(self, camera_id="amr1", frame_id="amr1-frame-001", captured_at=None,
                   image=None, token="camera-device-test-key", content_type="image/png"):
        captured_at = captured_at or (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        headers = {"X-Frame-Id": frame_id, "X-Captured-At": captured_at}
        if token is not None:
            headers["X-Robot-Token"] = token
        return self.client.post(
            f"/api/cameras/{camera_id}/frame",
            data=self.png if image is None else image,
            headers=headers,
            content_type=content_type,
        )

    def login_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_device_token_content_type_and_disabled_api(self):
        self.assertEqual(self.send_frame(token=None).status_code, 401)
        self.assertEqual(self.send_frame(token="wrong").status_code, 401)
        self.assertEqual(self.send_frame(content_type="application/octet-stream").status_code, 415)
        disabled = create_app({
            **self.config,
            "DATABASE": str(Path(self.folder.name) / "disabled/db.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "disabled/evidence"),
            "VIDEO_DIR": str(Path(self.folder.name) / "disabled/live_frames"),
            "ROBOT_API_KEY": None,
        }).test_client()
        self.assertEqual(disabled.post("/api/cameras/amr1/frame").status_code, 503)

    def test_valid_frame_keeps_only_latest_file_and_metadata(self):
        response = self.send_frame()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["result"], "accepted")
        video_dir = Path(self.config["VIDEO_DIR"])
        self.assertEqual((video_dir / "amr1.frame").read_bytes(), self.png)
        self.assertTrue((video_dir / "amr1.json").is_file())
        newer_png = occupancy_to_png([100, 0, 0, -1], 2, 2)
        newer_time = datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.send_frame(frame_id="amr1-frame-002", captured_at=newer_time,
                                         image=newer_png).status_code, 201)
        self.assertEqual((video_dir / "amr1.frame").read_bytes(), newer_png)
        self.assertEqual(len(list(video_dir.glob("*.frame"))), 1)
        jpeg = b"\xff\xd8\xff\xe0demo-jpeg\xff\xd9"
        jpeg_response = self.send_frame(
            camera_id="webcam1", frame_id="webcam1-jpeg-001",
            captured_at=(datetime.now(timezone.utc) + timedelta(milliseconds=1)).isoformat(),
            image=jpeg, content_type="image/jpeg",
        )
        self.assertEqual(jpeg_response.status_code, 201)
        self.assertEqual((video_dir / "webcam1.frame").read_bytes(), jpeg)

    def test_retry_conflict_and_stale_frame(self):
        captured = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.assertEqual(self.send_frame(captured_at=captured).status_code, 201)
        duplicate = self.send_frame(captured_at=captured)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.get_json()["result"], "duplicate")
        changed = occupancy_to_png([100, 100, 0, 0], 2, 2)
        self.assertEqual(self.send_frame(captured_at=captured, image=changed).status_code, 409)
        older = (datetime.now(timezone.utc) - timedelta(seconds=3)).isoformat()
        stale = self.send_frame(frame_id="amr1-frame-old", captured_at=older)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()["error"], "stale_frame")

    def test_invalid_camera_time_image_and_size_are_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()
        invalid_responses = [
            self.send_frame(camera_id="camera3"),
            self.send_frame(frame_id="잘못된 ID"),
            self.send_frame(captured_at="2026-09-06 12:00:00"),
            self.send_frame(captured_at=future),
            self.send_frame(image=b"not-an-image"),
            self.send_frame(image=b"\x89PNG\r\n\x1a\n" + b"x" * 1100),
        ]
        self.assertTrue(all(response.status_code == 400 for response in invalid_responses))
        self.assertEqual(list(Path(self.config["VIDEO_DIR"]).glob("*.frame")), [])

    def test_list_and_frame_require_login_and_show_all_four_cameras(self):
        self.assertEqual(self.send_frame(camera_id="webcam2", frame_id="webcam2-frame").status_code, 201)
        self.assertEqual(self.client.get("/api/cameras").location, "/login")
        self.assertEqual(self.client.get("/api/cameras/webcam2/frame").location, "/login")
        self.login_session()
        cameras = self.client.get("/api/cameras").get_json()["cameras"]
        self.assertEqual([camera["id"] for camera in cameras], ["amr1", "amr2", "webcam1", "webcam2"])
        self.assertFalse(cameras[0]["available"])
        self.assertTrue(cameras[3]["available"])
        self.assertTrue(cameras[3]["frame_url"].startswith("/api/cameras/webcam2/frame"))
        image = self.client.get("/api/cameras/webcam2/frame")
        self.assertEqual((image.status_code, image.mimetype, image.data), (200, "image/png", self.png))
        image.close()
        self.assertEqual(self.client.get("/api/cameras/unknown/frame").status_code, 404)

    def test_live_becomes_offline_and_dashboard_contains_video_controls(self):
        now = datetime.now(timezone.utc)
        with self.app.app_context():
            camera_service.receive_frame(
                "amr2", "amr2-frame", now.isoformat(), BytesIO(self.png), now=now
            )
            live = camera_service.dashboard_cameras(now=now)[1]
            offline = camera_service.dashboard_cameras(now=now + timedelta(seconds=6))[1]
        self.assertTrue(live["live"])
        self.assertEqual(live["state_label"], "LIVE")
        self.assertFalse(offline["live"])
        self.assertEqual(offline["state_label"], "연결 끊김")
        self.login_session()
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-cameras-url="/api/cameras"', page)
        self.assertIn("/api/cameras/amr2/frame", page)
        self.assertIn("cameras.js", page)


if __name__ == "__main__":
    unittest.main()
