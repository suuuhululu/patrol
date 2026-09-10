"""17단계 검증: 네 costmap의 최신 저장·보호된 조회·파일 교체를 확인한다."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.models.costmap import CostmapMessageConflictError, StaleCostmapError
from app.services import auth_service, costmap_service, map_service


class CostmapTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = create_app({
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/sysmon.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "costmap-tests-only-key",
            "MAP_MAX_CELLS": 100,
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user(
                "costmap-viewer", "Test-pass-123", "VIEWER"
            )

    def login_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def payload(self, message_id, seconds_ago=1, value=0, frame_id="map"):
        return {
            "message_id": message_id,
            "frame_id": frame_id,
            "resolution": 0.1,
            "width": 5,
            "height": 4,
            "origin": {"x": -1.0, "y": -2.0, "yaw": 0.0},
            "data": [value] * 20,
            "observed_at": (
                datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
            ).isoformat(),
        }

    def test_four_sources_are_stored_separately_and_listed_in_fixed_order(self):
        with self.app.app_context():
            for index, (robot_id, layer) in enumerate(costmap_service.COSTMAP_SOURCES):
                outcome, stored = costmap_service.receive_costmap(
                    robot_id, layer, self.payload(f"costmap-{index}", value=index)
                )
                self.assertEqual(outcome, "accepted")
                self.assertEqual((stored["robot_id"], stored["layer"]), (robot_id, layer))
            rows = get_db().execute(
                "SELECT robot_id, layer FROM costmap_latest ORDER BY robot_id, layer"
            ).fetchall()
            self.assertEqual([tuple(row) for row in rows], list(costmap_service.COSTMAP_SOURCES))
            self.assertEqual(len(list(Path(self.app.config["COSTMAP_DIR"]).glob("*.png"))), 4)

        self.login_session()
        response = self.client.get("/api/costmaps")
        self.assertEqual(response.status_code, 200)
        grids = response.get_json()["costmaps"]
        self.assertEqual(len(grids), 4)
        self.assertTrue(all(grid["available"] and grid["image_url"] for grid in grids))

    def test_latest_replacement_removes_previous_image_after_commit(self):
        with self.app.app_context():
            costmap_service.receive_costmap(
                "AMR1", "global", self.payload("first", seconds_ago=2)
            )
            first = next(Path(self.app.config["COSTMAP_DIR"]).glob("*.png"))
            costmap_service.receive_costmap(
                "AMR1", "global", self.payload("second", seconds_ago=1, value=100)
            )
            files = list(Path(self.app.config["COSTMAP_DIR"]).glob("*.png"))
            self.assertEqual(len(files), 1)
            self.assertNotEqual(files[0], first)
            self.assertFalse(first.exists())
            self.assertEqual(
                get_db().execute("SELECT message_id FROM costmap_latest").fetchone()[0],
                "second",
            )

    def test_duplicate_conflict_and_stale_inputs_preserve_latest(self):
        payload = self.payload("same", seconds_ago=2)
        with self.app.app_context():
            self.assertEqual(costmap_service.receive_costmap("AMR2", "local", payload)[0], "accepted")
            self.assertEqual(costmap_service.receive_costmap("AMR2", "local", payload)[0], "duplicate")
            with self.assertRaises(CostmapMessageConflictError):
                costmap_service.receive_costmap(
                    "AMR2", "local", {**payload, "data": [100] * 20}
                )
            with self.assertRaises(StaleCostmapError):
                costmap_service.receive_costmap(
                    "AMR2", "local", self.payload("older", seconds_ago=5)
                )
            self.assertEqual(get_db().execute("SELECT message_id FROM costmap_latest").fetchone()[0], "same")
            self.assertEqual(len(list(Path(self.app.config["COSTMAP_DIR"]).glob("*.png"))), 1)

    def test_invalid_source_frame_and_protected_image_do_not_leak_files(self):
        self.assertEqual(self.client.get("/api/costmaps").status_code, 302)
        self.assertEqual(self.client.get("/api/costmaps/AMR1/global/image").status_code, 302)
        with self.app.app_context():
            with self.assertRaises(costmap_service.CostmapValidationError):
                costmap_service.receive_costmap("robot1", "global", self.payload("bad-source"))
            with self.assertRaises(map_service.MapValidationError):
                costmap_service.receive_costmap(
                    "AMR1", "global", self.payload("bad-frame", frame_id="odom")
                )
            costmap_service.receive_costmap("AMR1", "global", self.payload("valid"))

        self.login_session()
        listing = self.client.get("/api/costmaps").get_json()["costmaps"]
        grid = next(item for item in listing if item["available"])
        image = self.client.get(grid["image_url"])
        self.assertEqual((image.status_code, image.mimetype), (200, "image/png"))
        image.close()
        page = self.client.get("/")
        self.assertIn(b'data-map-source="AMR1"', page.data)
        self.assertIn(b"/api/costmaps/AMR1/global/image", page.data)
        self.assertNotIn(b"js/costmaps.js", page.data)

    def send_robot(self, robot_id, x, y):
        return self.client.post("/api/robots/status", json={
            "message_id": f"{robot_id}-{x}-{y}", "robot_id": robot_id, "battery": 80,
            "x": x, "y": y, "frame_id": "map",
            "mission_status": "PATROLLING", "connection_status": "ONLINE",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }, headers={"X-Robot-Token": "costmap-device-test-key"})

    def test_nav_map_uses_selected_global_costmap_as_background(self):
        self.app.config["ROBOT_API_KEY"] = "costmap-device-test-key"
        self.login_session()
        self.assertEqual(self.client.get("/api/costmaps/nav").get_json()["available"], False)
        with self.app.app_context():
            # local은 NAV 지도 바탕 후보가 아니다.
            costmap_service.receive_costmap("AMR1", "local", self.payload("local-only"))
        empty = self.client.get("/api/costmaps/nav").get_json()
        self.assertFalse(empty["available"])
        self.assertEqual(empty["sources"], [
            {"robot_id": "AMR1", "available": False}, {"robot_id": "AMR2", "available": False},
        ])

        with self.app.app_context():
            costmap_service.receive_costmap("AMR1", "global", self.payload("amr1-global", seconds_ago=5))
            costmap_service.receive_costmap("AMR2", "global", self.payload("amr2-global", seconds_ago=5))
        self.assertEqual(self.send_robot("AMR1", -0.8, -1.9).status_code, 201)

        # 선택이 없으면 가장 최근에 받은 로봇(AMR2)을 고른다.
        auto = self.client.get("/api/costmaps/nav").get_json()
        self.assertEqual((auto["available"], auto["source_robot"]), (True, "AMR2"))
        self.assertIn("/api/costmaps/AMR2/global/image", auto["image_url"])

        chosen = self.client.get("/api/costmaps/nav?robot=AMR1").get_json()
        self.assertEqual(chosen["source_robot"], "AMR1")
        self.assertEqual(chosen["message_id"], "amr1-global")
        # origin (-1, -2), 0.1 m/cell, 높이 4칸: (-0.8, -1.9) -> 격자 (2, 4 - 1)
        marker = chosen["robots"][0]
        self.assertAlmostEqual(marker["x"], 2.0, places=3)
        self.assertAlmostEqual(marker["y"], 3.0, places=3)
        self.assertTrue(marker["inside_map"])
        image = self.client.get(chosen["image_url"])
        self.assertEqual(image.status_code, 200)
        image.close()

        self.assertEqual(self.client.get("/api/costmaps/nav?robot=AMR3").status_code, 400)

    def test_nav_map_reports_waiting_for_selected_robot_without_switching(self):
        self.login_session()
        with self.app.app_context():
            costmap_service.receive_costmap("AMR2", "global", self.payload("amr2-only"))
        waiting = self.client.get("/api/costmaps/nav?robot=AMR1").get_json()
        self.assertFalse(waiting["available"])
        self.assertEqual(waiting["source_robot"], "AMR1")
        self.assertIn("AMR1", waiting["state_label"])
        self.assertIsNone(waiting["image_url"])


if __name__ == "__main__":
    unittest.main()
