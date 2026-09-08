from pathlib import Path
import tempfile
import threading
import unittest

from patrol_amr.mission_command_store import CommandStore
from patrol_amr.navigation_adapter import NavigationResult, Waypoint
from patrol_amr.scenarios.patrol import PatrolScenario


class FakeNavigation:
    def __init__(self, results):
        self.results = iter(results)
        self.visited = []

    def go_to(self, waypoint, cancel_event):
        self.visited.append(waypoint.name)
        return next(self.results)


class PatrolScenarioTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def make_scenario(self, results):
        navigation = FakeNavigation(results)
        store = CommandStore(self.root / 'commands.json')
        waypoints = [
            Waypoint('W1', 1.0, 2.0, 3.0),
            Waypoint('W2', 4.0, 5.0, 6.0),
        ]
        states = []
        scenario = PatrolScenario(
            navigation, store, waypoints, 0.0,
            lambda state, index: states.append((state, index)))
        return scenario, navigation, store, states

    def test_only_successful_goal_advances_checkpoint(self):
        scenario, navigation, store, states = self.make_scenario(
            [NavigationResult.SUCCEEDED, NavigationResult.FAILED])
        result = scenario.run('patrol-a', 0, threading.Event())
        self.assertIs(result, NavigationResult.FAILED)
        self.assertEqual(navigation.visited, ['W1', 'W2'])
        self.assertEqual(store.load_checkpoint('patrol-a'), 1)
        self.assertEqual(
            states, [('MISSION_PATROLLING', 0), ('MISSION_PATROLLING', 1)])

    def test_completed_patrol_clears_checkpoint(self):
        scenario, navigation, store, _ = self.make_scenario(
            [NavigationResult.SUCCEEDED, NavigationResult.SUCCEEDED])
        result = scenario.run('patrol-a', 0, threading.Event())
        self.assertIs(result, NavigationResult.SUCCEEDED)
        self.assertEqual(navigation.visited, ['W1', 'W2'])
        self.assertIsNone(store.load_checkpoint('patrol-a'))

    def test_preexisting_cancel_does_not_send_goal(self):
        scenario, navigation, store, _ = self.make_scenario([])
        cancel = threading.Event()
        cancel.set()
        self.assertIs(
            scenario.run('patrol-a', 0, cancel), NavigationResult.CANCELED)
        self.assertEqual(navigation.visited, [])
        self.assertIsNone(store.load_checkpoint('patrol-a'))

    def test_runs_all_seven_waypoints_in_order(self):
        navigation = FakeNavigation(
            [NavigationResult.SUCCEEDED] * 7)
        store = CommandStore(self.root / 'commands-seven.json')
        waypoints = [
            Waypoint(f'W{index}', float(index), 0.0, 0.0)
            for index in range(1, 8)
        ]
        scenario = PatrolScenario(
            navigation, store, waypoints, 0.0, lambda state, index: None)

        result = scenario.run('patrol-seven', 0, threading.Event())

        self.assertIs(result, NavigationResult.SUCCEEDED)
        self.assertEqual(
            navigation.visited,
            ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7'],
        )
        self.assertIsNone(store.load_checkpoint('patrol-seven'))
