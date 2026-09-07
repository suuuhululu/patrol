"""13단계 검증: 부하 도구가 임시 저장소만 사용하고 측정 보고서를 만드는지 확인한다."""

import unittest

from testkit.load_test import LoadTestConfig, run_load_test


class LoadTestToolTests(unittest.TestCase):
    def test_invalid_config_is_rejected(self):
        invalid = (
            LoadTestConfig(duration_seconds=0),
            LoadTestConfig(readers=-1),
            LoadTestConfig(readers=1.5),
            LoadTestConfig(status_hz=-1),
            LoadTestConfig(seed_history=-1),
            LoadTestConfig(seed_history=1.5),
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                config.validate()

    def test_short_mixed_load_measures_every_operation_in_temp_storage(self):
        report = run_load_test(LoadTestConfig(
            duration_seconds=0.25,
            readers=7,
            read_hz_per_reader=20,
            status_hz=20,
            map_hz=10,
            camera_hz=20,
            event_hz=10,
            vehicle_hz=10,
            seed_history=20,
        ))
        self.assertEqual(report["measurement_status"], "MEASURED")
        self.assertEqual(report["pass_threshold_status"], "TBD-MON-001·003")
        self.assertTrue(report["integrity_ok"])
        self.assertTrue(report["temporary_storage_removed"])
        self.assertEqual(report["unexpected_exceptions"], 0)
        self.assertEqual(report["unexpected_http_errors"], 0)
        for operation in (
            "write_robot_status",
            "write_map",
            "write_camera_frame",
            "write_event",
            "write_vehicle_access",
            "read_dashboard",
            "read_api_robots_status",
            "read_api_maps_current",
            "read_api_cameras",
            "read_api_events",
            "read_api_vehicle_access",
            "read_api_history",
        ):
            with self.subTest(operation=operation):
                self.assertGreaterEqual(
                    report["operations"][operation]["requests"], 1
                )
        self.assertGreaterEqual(
            report["storage"]["table_counts"]["robot_status_history"], 20
        )
        self.assertEqual(report["storage"]["integrity_check"], "ok")
        self.assertEqual(report["storage"]["foreign_key_errors"], 0)
        self.assertEqual(report["storage"]["temporary_files"], [])

    def test_short_lock_is_released_and_storage_recovers(self):
        report = run_load_test(LoadTestConfig(
            duration_seconds=0.2,
            readers=0,
            status_hz=10,
            map_hz=0,
            camera_hz=0,
            event_hz=0,
            vehicle_hz=0,
            seed_history=0,
            lock_seconds=0.05,
        ))
        self.assertTrue(report["lock_scenario"]["acquired"])
        self.assertTrue(report["lock_scenario"]["released"])
        self.assertEqual(report["unexpected_http_errors"], 0)
        self.assertEqual(
            report["operations"]["post_lock_robot_status"]["status_codes"],
            {"201": 1},
        )
        self.assertTrue(report["integrity_ok"])


if __name__ == "__main__":
    unittest.main()
