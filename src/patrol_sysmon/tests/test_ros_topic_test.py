"""15단계 가상 ROS 토픽 종단시험의 설정과 격리 저장을 검증한다."""

import os
import unittest

from app.ros_adapter import dependency_report
from testkit.ros_topic_test import RosTopicTestConfig, run_local_ros_topic_test


class RosTopicTestConfigTests(unittest.TestCase):
    def test_invalid_or_operational_domain_config_is_rejected(self):
        invalid = (
            RosTopicTestConfig(duration_seconds=0),
            RosTopicTestConfig(domain_id=-1),
            RosTopicTestConfig(domain_id=6),
            RosTopicTestConfig(domain_id=233),
            RosTopicTestConfig(status_hz=0),
            RosTopicTestConfig(map_hz=float("nan")),
            RosTopicTestConfig(image_hz=-1),
            RosTopicTestConfig(costmap_hz=-1),
            RosTopicTestConfig(costmap_hz=float("nan")),
            RosTopicTestConfig(cctv_hz=-1),
            RosTopicTestConfig(cctv_hz=float("nan")),
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                config.validate()


@unittest.skipUnless(dependency_report()["ready"], "ROS workspace source 필요")
class RosTopicLiveTests(unittest.TestCase):
    def test_virtual_topics_reach_only_temporary_storage(self):
        previous_domain = os.environ.get("ROS_DOMAIN_ID")
        report = run_local_ros_topic_test(RosTopicTestConfig(
            duration_seconds=1.5,
            domain_id=78,
            status_hz=10,
            map_hz=5,
            image_hz=10,
        ))
        self.assertTrue(report["local_pass"])
        self.assertTrue(report["temporary_storage_removed"])
        self.assertEqual(report["external_publishers"], "NOT_RUN")
        self.assertEqual(report["processing_failures"], 0)
        self.assertEqual(
            set(report["storage"]["robot_latest_ids"]), {"AMR1", "AMR2"}
        )
        self.assertEqual(
            set(report["storage"]["camera_ids"]),
            {"amr1", "amr2", "webcam1", "webcam2"},
        )
        self.assertEqual(report["storage"]["integrity_check"], "ok")
        self.assertEqual(os.environ.get("ROS_DOMAIN_ID"), previous_domain)


if __name__ == "__main__":
    unittest.main()
