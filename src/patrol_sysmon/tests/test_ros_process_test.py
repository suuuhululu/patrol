"""16단계 별도 프로세스 가상 ROS publisher 종단시험."""

import json
import time
import unittest

from app.ros_adapter import dependency_report
from testkit.ros_process_test import run_separate_process_ros_test
from testkit.ros_topic_test import RosTopicTestConfig


def _summary(report):
    """판정 실패 원인을 바로 볼 수 있게 보고서 핵심만 문자열로 만든다."""
    matched = report["matched_subscriptions"]
    return json.dumps({
        "exit": report["process_exit_codes"],
        "child_errors": report["child_errors"],
        "matched": len(matched),
        "zero_matched": [name for name, count in matched.items() if count < 1],
        "processed": report["processed"],
        "storage": report["storage"],
        "dashboard": sorted(set(report["dashboard_http"].values())),
        "processing_failures": report["processing_failures"],
    }, ensure_ascii=False)[:1500]


@unittest.skipUnless(dependency_report()["ready"], "ROS workspace source 필요")
class RosSeparateProcessTests(unittest.TestCase):
    def tearDown(self):
        # [DDS 정리 대기] 앞 시험의 participant가 완전히 사라지기 전에 다음 도메인을
        # 열면 발견이 늦어져 수신량이 들쭉날쭉해진다. 짧게 쉬고 다음 시험으로 넘어간다.
        time.sleep(1.5)

    def test_publisher_and_adapter_processes_exchange_all_active_topics(self):
        report = run_separate_process_ros_test(RosTopicTestConfig(
            duration_seconds=2.5,
            domain_id=81,
            status_hz=10,
            map_hz=5,
            image_hz=10,
        ))
        self.assertTrue(report["process_pass"], _summary(report))
        self.assertTrue(report["temporary_storage_removed"])
        self.assertEqual(report["external_publishers"], "NOT_RUN")
        self.assertEqual(report["process_exit_codes"], {"adapter": 0, "publisher": 0})
        self.assertEqual(len(report["matched_subscriptions"]), 7)
        self.assertTrue(all(
            count >= 1 for count in report["matched_subscriptions"].values()
        ))
        self.assertEqual(report["processing_failures"], 0)

    def test_display_images_are_processed_at_most_five_hz(self):
        """계약 2.5절대로 표시용 영상은 5 Hz까지만 처리한다.

        다른 토픽 부하가 크면 BEST_EFFORT 영상이 DDS 단계에서 먼저 밀리므로,
        adapter가 따라올 수 있는 조건에서 처리 상한만 확인한다.
        """
        report = run_separate_process_ros_test(RosTopicTestConfig(
            duration_seconds=3.0,
            domain_id=82,
            status_hz=2,
            map_hz=1,
            image_hz=12,
        ))
        self.assertTrue(report["process_pass"], _summary(report))
        processed = report["processed"]
        self.assertGreaterEqual(processed.get("camera_frame_throttled", 0), 1)
        # 카메라 4개 × 5 Hz × 시험 시간에 여유를 둔 상한이다.
        self.assertLessEqual(processed.get("camera_frame_accepted", 0), 4 * 5 * 4)

    def test_stage17_costmaps_exchange_all_nine_active_topics(self):
        report = run_separate_process_ros_test(RosTopicTestConfig(
            duration_seconds=2.5,
            domain_id=83,
            status_hz=10,
            map_hz=5,
            image_hz=10,
            costmap_hz=8,
        ))
        self.assertTrue(report["process_pass"], _summary(report))
        self.assertTrue(report["temporary_storage_removed"])
        self.assertEqual(report["stage"], 17)
        self.assertEqual(len(report["matched_subscriptions"]), 9)
        self.assertEqual(set(report["storage"]["costmap_sources"]), {
            "AMR1:global", "AMR2:global",
        })
        self.assertGreater(report["processed"].get("costmap_accepted", 0), 0)
        self.assertEqual(report["processing_failures"], 0)

    def test_stage20_patrol_and_safety_cross_process_boundary(self):
        report = run_separate_process_ros_test(RosTopicTestConfig(
            duration_seconds=3.0,
            domain_id=86,
            status_hz=8,
            map_hz=3,
            image_hz=8,
            costmap_hz=5,
            cctv_hz=4,
            patrol_hz=4,
            safety_hz=4,
        ))
        self.assertTrue(report["process_pass"], _summary(report))
        self.assertTrue(report["temporary_storage_removed"])
        self.assertEqual(report["stage"], 20)
        self.assertEqual(len(report["matched_subscriptions"]), 19)
        self.assertGreaterEqual(report["storage"]["patrol_visits"], 2)
        self.assertGreaterEqual(report["storage"]["patrol_reports"], 1)
        self.assertTrue(report["storage"]["keepout_states"])
        self.assertIsNotNone(report["storage"]["estop_latest"])
        self.assertGreaterEqual(report["storage"]["estop_changes"], 2)
        self.assertEqual(report["processing_failures"], 0)

    def test_stage19_cctv_state_and_permit_cross_process_boundary(self):
        report = run_separate_process_ros_test(RosTopicTestConfig(
            # permit 변경 관측은 표본이 적으면 흔들려 관측 창을 넉넉히 둔다.
            duration_seconds=4.0,
            domain_id=85,
            status_hz=8,
            map_hz=3,
            image_hz=8,
            costmap_hz=5,
            cctv_hz=4,
        ))
        self.assertTrue(report["process_pass"], _summary(report))
        self.assertTrue(report["temporary_storage_removed"])
        self.assertEqual(report["stage"], 19)
        self.assertEqual(len(report["matched_subscriptions"]), 12)
        self.assertEqual(
            set(report["storage"]["cctv_camera_ids"]),
            {"gate_cam", "center_cam"},
        )
        self.assertGreaterEqual(report["storage"]["cctv_state_events"], 2)
        self.assertIsNotNone(report["storage"]["patrol_permit_latest"])
        self.assertGreaterEqual(report["storage"]["patrol_permit_history"], 2)
        self.assertEqual(report["dashboard_http"]["/api/cctv/status"], 200)
        self.assertGreater(report["processed"].get("camera_state_accepted", 0), 0)
        self.assertEqual(report["processing_failures"], 0)


if __name__ == "__main__":
    unittest.main()
