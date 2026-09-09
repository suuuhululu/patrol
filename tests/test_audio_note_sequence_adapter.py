"""Tests for audio goal construction without running a ROS graph."""

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(
    Path(__file__).resolve().parents[1] / 'src/patrol_amr'))

from patrol_amr.audio_note_sequence_adapter import (
    AudioNoteSequenceAdapter, AudioNoteSpec, build_infinite_audio_goal)


class FakeFuture:
    def __init__(self, result=None):
        self._result = result
        self._callbacks = []

    def add_done_callback(self, callback):
        self._callbacks.append(callback)

    def result(self):
        return self._result

    def complete(self):
        for callback in tuple(self._callbacks):
            callback(self)


class FakeGoalHandle:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.cancel_count = 0
        self.result_future = FakeFuture()

    def get_result_async(self):
        return self.result_future

    def cancel_goal_async(self):
        self.cancel_count += 1
        return FakeFuture()


class FakeActionClient:
    def __init__(self, available=True, accepted=True):
        self.available = available
        self.goal_handle = FakeGoalHandle(accepted)
        self.goal_future = FakeFuture(self.goal_handle)
        self.sent_goals = []

    def wait_for_server(self, timeout_sec):
        return self.available

    def send_goal_async(self, goal):
        self.sent_goals.append(goal)
        return self.goal_future


class AudioNoteSequenceGoalTest(unittest.TestCase):
    """Verify the known TurtleBot4 AudioNoteSequence wire format."""

    def test_builds_infinite_non_appending_sequence(self):
        goal = build_infinite_audio_goal([
            AudioNoteSpec(880, 1.0),
            AudioNoteSpec(660, 0.25),
        ])

        self.assertEqual(goal.iterations, -1)
        self.assertFalse(goal.note_sequence.append)
        self.assertEqual(
            [note.frequency for note in goal.note_sequence.notes],
            [880, 660],
        )
        self.assertEqual(goal.note_sequence.notes[0].max_runtime.sec, 1)
        self.assertEqual(
            goal.note_sequence.notes[1].max_runtime.nanosec, 250_000_000)

    def test_rejects_empty_or_invalid_notes(self):
        invalid_sequences = (
            [],
            [AudioNoteSpec(0, 1.0)],
            [AudioNoteSpec(440, 0.0)],
        )
        for sequence in invalid_sequences:
            with self.subTest(sequence=sequence):
                with self.assertRaises(ValueError):
                    build_infinite_audio_goal(sequence)


class AudioNoteSequenceAdapterTest(unittest.TestCase):
    """Verify idempotent asynchronous Action start and stop handling."""

    @staticmethod
    def adapter(fake_client):
        return AudioNoteSequenceAdapter(
            object(),
            server_timeout_s=0.5,
            action_client_factory=lambda node, action, name: fake_client,
        )

    def test_repeated_start_does_not_send_a_second_goal(self):
        client = FakeActionClient()
        adapter = self.adapter(client)

        first = adapter.start([AudioNoteSpec(880, 1.0)])
        duplicate = adapter.start([AudioNoteSpec(880, 1.0)])

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertEqual(len(client.sent_goals), 1)

    def test_stop_during_goal_acceptance_cancels_after_acceptance(self):
        client = FakeActionClient()
        adapter = self.adapter(client)
        adapter.start([AudioNoteSpec(880, 1.0)])

        self.assertTrue(adapter.stop())
        client.goal_future.complete()

        self.assertEqual(client.goal_handle.cancel_count, 1)

    def test_unavailable_action_fails_without_sending(self):
        client = FakeActionClient(available=False)
        adapter = self.adapter(client)

        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            adapter.start([AudioNoteSpec(880, 1.0)])
        self.assertEqual(client.sent_goals, [])


if __name__ == '__main__':
    unittest.main()
