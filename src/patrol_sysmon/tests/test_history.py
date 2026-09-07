"""10단계 검증: 통합 이력의 권한·종류·필터·페이지·화면 표시를 확인한다."""

from pathlib import Path
import tempfile
import unittest

from app import create_app
from app.database import get_db
from app.services import auth_service


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "instance"
        self.config = {
            "TESTING": True,
            "DATABASE": str(root / "sysmon.sqlite3"),
            "EVIDENCE_DIR": str(root / "evidence"),
            "VIDEO_DIR": str(root / "live_frames"),
            "SECRET_KEY": "history-tests-only-key",
            "ROBOT_API_KEY": "history-device-test-key",
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.app.app_context():
            self.user_id = auth_service.create_user("viewer", "Test-pass-123", "VIEWER")
            db = get_db()
            db.executemany(
                "INSERT INTO robots(robot_id, name) VALUES (?, ?)",
                (("AMR1", "로봇 1"), ("AMR2", "로봇 2")),
            )
            db.execute(
                """INSERT INTO robot_status_history
                   (robot_id,message_id,battery,x,y,frame_id,mission_status,connection_status,observed_at,received_at)
                   VALUES ('AMR1','status-001',82,12.5,8.0,'map','PATROLLING','ONLINE',
                           '2026-09-05T01:00:00.000Z','2026-09-05T01:00:01.000Z')"""
            )
            db.execute(
                """INSERT INTO events
                   (event_id,message_id,robot_id,event_type,occurred_at,x,y,frame_id,risk_level,status,received_at)
                   VALUES ('fire-001','fire-message-001','AMR1','FIRE','2026-09-05T02:00:00.000Z',
                           13.0,9.0,'map','HIGH','REVIEWING','2026-09-05T02:00:01.000Z')"""
            )
            evidence = root / "evidence" / "fire-001.png"
            evidence.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
            db.execute(
                "INSERT INTO event_evidence(event_id,image_path,captured_at) VALUES ('fire-001','fire-001.png','2026-09-05T02:00:00.100Z')"
            )
            db.execute(
                """INSERT INTO event_changes(event_id,user_id,previous_status,new_status,memo,changed_at)
                   VALUES ('fire-001',?,'NEW','REVIEWING','현장 영상 확인','2026-09-05T03:00:00.000Z')""",
                (self.user_id,),
            )
            db.execute(
                """INSERT INTO patrol_runs(patrol_id,report_id,message_id,robot_id,result,
                                             started_at,ended_at,planned_visit_count,
                                             completed_visit_count,received_at)
                   VALUES ('patrol-001','1f0b1f3c-7c1a-4c4e-8d6a-2f3f6a5c1101',
                           '1f0b1f3c-7c1a-4c4e-8d6a-2f3f6a5c1102','AMR1','SUCCEEDED',
                           '2026-09-05T04:00:00.000Z','2026-09-05T04:30:00.000Z',2,2,
                           '2026-09-05T04:30:01.000Z')"""
            )
            db.executemany(
                """INSERT INTO patrol_visits(visit_id,message_id,robot_id,patrol_id,waypoint_id,
                                            result,arrived_at,received_at)
                   VALUES (?,?,'AMR1','patrol-001',?,'SUCCEEDED',?,?)""",
                (
                    ("1f0b1f3c-7c1a-4c4e-8d6a-2f3f6a5c1201",
                     "1f0b1f3c-7c1a-4c4e-8d6a-2f3f6a5c1202", "P1",
                     "2026-09-05T04:10:00.000Z", "2026-09-05T04:10:01.000Z"),
                    ("1f0b1f3c-7c1a-4c4e-8d6a-2f3f6a5c1203",
                     "1f0b1f3c-7c1a-4c4e-8d6a-2f3f6a5c1204", "P2",
                     "2026-09-05T04:20:00.000Z", "2026-09-05T04:20:01.000Z"),
                ),
            )
            db.execute(
                """INSERT INTO handovers(handover_id,from_robot_id,to_robot_id,reason,status,requested_at,completed_at)
                   VALUES ('handover-001','AMR1','AMR2','배터리 교대','COMPLETED',
                           '2026-09-05T05:00:00.000Z','2026-09-05T05:05:00.000Z')"""
            )
            # [범위 경계] 예약된 commands 행이 있어도 통합 이력에는 포함하지 않는다.
            db.execute(
                """INSERT INTO commands(command_id,robot_id,requested_by,command_type,status,requested_at)
                   VALUES ('command-excluded','AMR1',?,'RETURN','COMPLETED','2026-09-05T06:00:00.000Z')""",
                (self.user_id,),
            )
            db.execute(
                """INSERT INTO vehicle_access_logs
                   (access_id,message_id,camera_id,direction,detected_at)
                   VALUES ('access-001','access-message-001','webcam1','ENTRY',
                           '2026-09-05T06:30:00.000Z')"""
            )
            db.commit()

    def login_session(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_history_page_and_api_require_login(self):
        self.assertEqual(self.client.get("/history").location, "/login")
        self.assertEqual(self.client.get("/api/history").location, "/login")

    def test_all_history_types_are_merged_in_time_order_without_commands(self):
        self.login_session()
        payload = self.client.get("/api/history").get_json()
        # [20단계] 관측점 방문 2건이 순찰 결과와 별도 기록으로 합쳐진다.
        self.assertEqual(payload["total"], 8)
        self.assertEqual(
            [row["record_type"] for row in payload["records"]],
            ["VEHICLE_ACCESS", "HANDOVER", "PATROL_VISIT", "PATROL_VISIT", "PATROL",
             "EVENT_CHANGE", "EVENT", "ROBOT_STATUS"],
        )
        self.assertNotIn("command-excluded", {row["record_id"] for row in payload["records"]})
        event = next(row for row in payload["records"] if row["record_type"] == "EVENT")
        self.assertEqual((event["risk_label"], event["status_label"]), ("상", "확인중"))
        self.assertEqual(event["evidence_url"], "/api/events/fire-001/evidence")

    def test_type_robot_event_and_keyword_filters(self):
        self.login_session()
        self.assertEqual(self.client.get("/api/history?type=EVENT").get_json()["total"], 1)
        self.assertEqual(self.client.get("/api/history?type=VEHICLE_ACCESS").get_json()["total"], 1)
        self.assertEqual(self.client.get("/api/history?keyword=webcam1").get_json()["total"], 1)
        self.assertEqual(self.client.get("/api/history?type=HANDOVER&robot=AMR2").get_json()["total"], 1)
        self.assertEqual(self.client.get("/api/history?risk=HIGH").get_json()["total"], 2)
        self.assertEqual(self.client.get("/api/history?status=REVIEWING").get_json()["total"], 2)
        memo = self.client.get("/api/history?keyword=%ED%98%84%EC%9E%A5").get_json()
        self.assertEqual((memo["total"], memo["records"][0]["record_type"]), (1, "EVENT_CHANGE"))
        # 관측점 이름으로 순찰 결과와 방문 기록을 함께 찾는다.
        point = self.client.get("/api/history?keyword=P2").get_json()
        self.assertEqual(point["total"], 2)
        self.assertEqual(
            {row["record_type"] for row in point["records"]}, {"PATROL", "PATROL_VISIT"}
        )
        visit = self.client.get("/api/history?type=PATROL_VISIT&robot=AMR1").get_json()
        self.assertEqual((visit["total"], visit["records"][0]["status_label"]), (2, "완료"))
        self.assertEqual(self.client.get("/api/history?keyword=%25").get_json()["total"], 0)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE events SET status='RESOLVED' WHERE event_id='fire-001'")
            db.commit()
        reviewing = self.client.get("/api/history?status=REVIEWING").get_json()
        self.assertEqual((reviewing["total"], reviewing["records"][0]["record_type"]),
                         (1, "EVENT_CHANGE"))

    def test_korean_date_range_is_converted_and_inclusive(self):
        self.login_session()
        self.assertEqual(
            self.client.get("/api/history?from=2026-09-05&to=2026-09-05").get_json()["total"], 8
        )
        self.assertEqual(
            self.client.get("/api/history?from=2026-09-06&to=2026-09-06").get_json()["total"], 0
        )

    def test_invalid_filters_return_400(self):
        self.login_session()
        invalid_urls = [
            "/api/history?type=COMMAND",
            "/api/history?robot=AMR3",
            "/api/history?from=2026-09-06&to=2026-09-05",
            "/api/history?from=not-a-date",
            "/api/history?page=0",
            "/api/history?keyword=" + "x" * 101,
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], "invalid_filter")
        self.assertEqual(
            self.client.get("/api/history?type=ROBOT_STATUS&risk=HIGH").get_json()["total"], 0
        )

    def test_pagination_and_html_navigation(self):
        with self.app.app_context():
            db = get_db()
            rows = []
            for index in range(51):
                rows.append((
                    "AMR2", f"status-extra-{index:03d}", 50, "map", "IDLE", "ONLINE",
                    f"2026-09-04T00:{index // 60:02d}:{index % 60:02d}.000Z",
                    f"2026-09-04T00:{index // 60:02d}:{index % 60:02d}.100Z",
                ))
            db.executemany(
                """INSERT INTO robot_status_history
                   (robot_id,message_id,battery,frame_id,mission_status,connection_status,observed_at,received_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                rows,
            )
            db.commit()
        self.login_session()
        first = self.client.get("/api/history").get_json()
        second = self.client.get("/api/history?page=2").get_json()
        self.assertEqual((first["total"], len(first["records"]), first["pages"]), (59, 50, 2))
        self.assertEqual((second["page"], len(second["records"])), (2, 9))
        page = self.client.get("/history?type=EVENT&risk=HIGH").get_data(as_text=True)
        self.assertIn("통합 이력 검색", page)
        self.assertIn("fire-001", page)
        self.assertIn("증거 이미지", page)
        dashboard = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/history"', dashboard)


if __name__ == "__main__":
    unittest.main()
