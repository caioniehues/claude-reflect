#!/usr/bin/env python3
"""Tests for tool-call sequence extraction (extract_tool_sequences, Slice 3 / ADR-0003).

External-behavior only: feed fixture assistant-`tool_use` JSONL and assert the
distilled sequences, counts, tool-sets, and — critically — that bulky tool inputs
never leak into the output. Prior art: tests/test_tool_errors.py.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib.reflect_utils import extract_tool_sequences, aggregate_tool_sequences


def _user(text):
    return {"type": "user", "isMeta": False,
            "message": {"content": [{"type": "text", "text": text}]}}


def _tool_result(payload):
    """A user-role tool_result carrier (must NOT split a task)."""
    return {"type": "user",
            "message": {"content": [{"type": "tool_result", "is_error": False,
                                     "content": payload}]}}


def _assistant(*tool_calls):
    """assistant turn with (name, input_dict) tool_use blocks."""
    content = [{"type": "tool_use", "name": name, "input": inp}
               for name, inp in tool_calls]
    return {"type": "assistant", "message": {"content": content}}


class TestExtractToolSequences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _session(self, entries, name="s.jsonl"):
        session = Path(self.tmp) / name
        with open(session, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return session

    def test_empty_and_nonexistent(self):
        self.assertEqual(extract_tool_sequences(Path(self.tmp) / "nope.jsonl"), [])
        empty = self._session([])
        self.assertEqual(extract_tool_sequences(empty), [])

    def test_single_task_sequence_in_order(self):
        session = self._session([
            _user("go find where auth is handled"),
            _assistant(("Grep", {"pattern": "auth"})),
            _tool_result("...matches..."),
            _assistant(("Read", {"file_path": "/a.py"})),
            _tool_result("...file..."),
            _assistant(("Grep", {"pattern": "login"})),
        ])
        records = extract_tool_sequences(session)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["sequence"], ["Grep", "Read", "Grep"])
        self.assertEqual(records[0]["tools"], ["Grep", "Read"])

    def test_task_boundaries_split_on_user_turns(self):
        session = self._session([
            _user("find X"),
            _assistant(("Grep", {"pattern": "x"})),
            _user("now review the diff"),
            _assistant(("Bash", {"command": "git diff"})),
            _assistant(("Read", {"file_path": "/b.py"})),
        ])
        records = extract_tool_sequences(session)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["sequence"], ["Grep"])
        self.assertEqual(records[1]["sequence"], ["Bash", "Read"])

    def test_tool_results_do_not_split_tasks(self):
        """user-role tool_result carriers must not start a new task."""
        session = self._session([
            _user("find X"),
            _assistant(("Grep", {"pattern": "x"})),
            _tool_result("big matches blob"),
            _assistant(("Read", {"file_path": "/a.py"})),
        ])
        records = extract_tool_sequences(session)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["sequence"], ["Grep", "Read"])

    def test_bulky_inputs_are_stripped(self):
        """No tool inputs (file contents, diffs, command bodies) leak to output."""
        secret = "SECRET_DIFF_BODY_THAT_MUST_NOT_LEAK"
        session = self._session([
            _user("review"),
            _assistant(("Bash", {"command": f"git diff # {secret}"}),
                       ("Write", {"content": secret, "file_path": "/x"})),
        ])
        records = extract_tool_sequences(session)
        blob = json.dumps(records)
        self.assertNotIn(secret, blob)
        self.assertEqual(records[0]["sequence"], ["Bash", "Write"])

    def test_text_only_assistant_turn_yields_no_task(self):
        session = self._session([
            _user("hello"),
            {"type": "assistant",
             "message": {"content": [{"type": "text", "text": "hi there"}]}},
        ])
        self.assertEqual(extract_tool_sequences(session), [])


class TestAggregateToolSequences(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(aggregate_tool_sequences([]), [])

    def test_clusters_identical_sequences_with_counts(self):
        records = [
            {"sequence": ["Grep", "Read", "Grep"], "tools": ["Grep", "Read"]},
            {"sequence": ["Grep", "Read", "Grep"], "tools": ["Grep", "Read"]},
            {"sequence": ["Bash", "Read"], "tools": ["Bash", "Read"]},
        ]
        clusters = aggregate_tool_sequences(records, min_occurrences=2)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["sequence"], ["Grep", "Read", "Grep"])
        self.assertEqual(clusters[0]["count"], 2)
        self.assertEqual(clusters[0]["tools"], ["Grep", "Read"])

    def test_cross_project_reach_attribution(self):
        """Clusters carry projects / seen_in_projects for global-vs-local routing (US18)."""
        records = [
            {"sequence": ["Grep", "Read"], "tools": ["Grep", "Read"], "project": "-a"},
            {"sequence": ["Grep", "Read"], "tools": ["Grep", "Read"], "project": "-b"},
            {"sequence": ["Grep", "Read"], "tools": ["Grep", "Read"], "project": "-a"},
        ]
        clusters = aggregate_tool_sequences(records, min_occurrences=2)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["count"], 3)
        self.assertEqual(clusters[0]["projects"], ["-a", "-b"])
        self.assertEqual(clusters[0]["seen_in_projects"], 2)

    def test_reach_zero_when_records_lack_project(self):
        """Records without a project field contribute no reach (graceful)."""
        records = [
            {"sequence": ["A"], "tools": ["A"]},
            {"sequence": ["A"], "tools": ["A"]},
        ]
        clusters = aggregate_tool_sequences(records, min_occurrences=2)
        self.assertEqual(clusters[0]["seen_in_projects"], 0)
        self.assertEqual(clusters[0]["projects"], [])

    def test_below_threshold_filtered(self):
        records = [{"sequence": ["Grep"], "tools": ["Grep"]}]
        self.assertEqual(aggregate_tool_sequences(records, min_occurrences=2), [])

    def test_sorted_by_count_desc(self):
        records = (
            [{"sequence": ["A"], "tools": ["A"]}] * 2
            + [{"sequence": ["B", "C"], "tools": ["B", "C"]}] * 3
        )
        clusters = aggregate_tool_sequences(records, min_occurrences=2)
        self.assertEqual(clusters[0]["sequence"], ["B", "C"])
        self.assertEqual(clusters[0]["count"], 3)
        self.assertEqual(clusters[1]["count"], 2)


if __name__ == "__main__":
    unittest.main()
