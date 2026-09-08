"""Deterministic battery model tests; no robot or ROS graph required."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'src/patrol_amr_safety/'
          'patrol_amr_safety/battery_monitor.py')
SPEC = importlib.util.spec_from_file_location('battery_monitor', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
S = MODULE.BatteryStatus


class BatteryTests(unittest.TestCase):
    def test_soc_boundaries(self):
        cases = [
            (False, 0.0, S.CRITICAL),
            (False, 0.099999, S.CRITICAL),
            (False, 0.10, S.LOW),
            (False, 0.100001, S.LOW),
            (False, 0.199999, S.LOW),
            (False, 0.20, S.NORMAL),
            (False, 0.200001, S.NORMAL),
            (False, 1.0, S.NORMAL),
            (True, 0.0, S.CHARGING),
            (True, 0.499999, S.CHARGING),
            (True, 0.50, S.PATROL_READY),
            (True, 0.500001, S.PATROL_READY),
            (True, 0.799999, S.PATROL_READY),
            (True, 0.80, S.FULL),
            (True, 0.800001, S.FULL),
            (True, 1.0, S.FULL),
        ]
        for charging, soc, expected in cases:
            with self.subTest(charging=charging, soc=soc):
                self.assertEqual(MODULE.classify_battery(soc, charging), expected)

    def test_all_state_transitions(self):
        for initial in S:
            for target in S:
                with self.subTest(initial=initial, target=target):
                    model = MODULE.BatteryStateModel()
                    model.update(initial, 0.0)
                    self.assertEqual(model.update(initial, 3.0), initial)
                    immediate = target == S.CRITICAL or target == initial
                    self.assertEqual(model.update(target, 4.0),
                                     target if immediate else initial)
                    self.assertEqual(model.update(target, 6.999),
                                     target if immediate else initial)
                    self.assertEqual(model.update(target, 7.0), target)

    def test_interruption_restarts_hold(self):
        model = MODULE.BatteryStateModel()
        model.update(S.NORMAL, 0.0)
        model.update(S.LOW, 2.0)
        self.assertEqual(model.update(S.NORMAL, 3.0), S.UNKNOWN)
        self.assertEqual(model.update(S.NORMAL, 5.999), S.UNKNOWN)
        self.assertEqual(model.update(S.NORMAL, 6.0), S.NORMAL)
        model.update(S.LOW, 7.0)
        model.update(S.NORMAL, 8.0)
        self.assertIsNone(model.pending)
        self.assertEqual(model.update(S.LOW, 9.0), S.NORMAL)
        self.assertEqual(model.update(S.LOW, 12.0), S.LOW)

    def test_invalid_observation_breaks_pending(self):
        model = MODULE.BatteryStateModel()
        model.update(S.NORMAL, 0.0)
        model.invalidate(2.0)
        self.assertEqual(model.update(S.NORMAL, 3.0), S.UNKNOWN)
        self.assertEqual(model.update(S.NORMAL, 6.0), S.NORMAL)

    def test_battery_state_input_policy(self):
        classify = MODULE.classify_observation
        self.assertEqual(classify(0.81, True, 1), S.FULL)
        self.assertEqual(classify(0.60, True, 4), S.PATROL_READY)
        self.assertEqual(classify(0.15, True, 2), S.LOW)
        for args in [
            (0.5, False, 2),
            (float('nan'), True, 2),
            (-0.01, True, 2),
            (1.01, True, 2),
            (0.5, True, 0),
            (0.5, True, 3),
        ]:
            with self.subTest(args=args):
                self.assertEqual(classify(*args), S.UNKNOWN)

    def test_invalidation_is_immediate(self):
        model = MODULE.BatteryStateModel()
        model.update(S.NORMAL, 0.0)
        model.update(S.NORMAL, 3.0)
        self.assertEqual(model.state, S.NORMAL)
        self.assertEqual(model.invalidate(6.0), S.UNKNOWN)
        self.assertIsNone(model.pending)

    def test_invalid_caller_arguments(self):
        for soc in [float('nan'), float('inf'), -0.01, 1.01]:
            with self.assertRaises(ValueError):
                MODULE.classify_battery(soc, False)
        with self.assertRaises(ValueError):
            MODULE.classify_battery(0.5, None)
        model = MODULE.BatteryStateModel()
        model.update(S.LOW, 10.0)
        for now in [9.0, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                model.update(S.LOW, now)
        self.assertEqual(model.last_update, 10.0)


if __name__ == '__main__':
    unittest.main()
