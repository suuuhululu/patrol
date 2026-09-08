"""Tests for active fire aggregation and duplicate handling."""

import unittest

from patrol_amr.fire_event_registry import FireEventRegistry


class FireEventRegistryTest(unittest.TestCase):
    """Verify Q-12's multiple-active-fire buzzer decision."""

    def test_duplicate_active_event_has_no_second_effect(self):
        registry = FireEventRegistry()

        first = registry.activate('det-robot6-fire-0001')
        duplicate = registry.activate('det-robot6-fire-0001')

        self.assertTrue(first.changed)
        self.assertTrue(first.buzzer_should_be_on)
        self.assertFalse(duplicate.changed)
        self.assertEqual(duplicate.active_event_count, 1)

    def test_buzzer_stays_on_until_last_active_fire_resolves(self):
        registry = FireEventRegistry()
        registry.activate('det-robot6-fire-0001')
        registry.activate('det-robot6-fire-0002')

        first = registry.resolve('det-robot6-fire-0001')
        last = registry.resolve('det-robot6-fire-0002')

        self.assertTrue(first.buzzer_should_be_on)
        self.assertEqual(first.active_event_count, 1)
        self.assertFalse(last.buzzer_should_be_on)
        self.assertEqual(last.active_event_count, 0)

    def test_unknown_resolution_does_not_change_state(self):
        registry = FireEventRegistry()

        update = registry.resolve('det-robot6-fire-missing')

        self.assertFalse(update.changed)
        self.assertFalse(update.buzzer_should_be_on)

    def test_blank_event_id_is_rejected(self):
        registry = FireEventRegistry()

        with self.assertRaisesRegex(ValueError, 'event_id'):
            registry.activate('  ')


if __name__ == '__main__':
    unittest.main()
