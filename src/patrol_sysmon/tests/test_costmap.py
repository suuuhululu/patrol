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
        self.assertIn(b"data-costmap-select", page.data)
        self.assertIn(b"js/costmaps.js", page.data)


if __name__ == "__main__":
    unittest.main()
