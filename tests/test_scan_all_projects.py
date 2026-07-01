#!/usr/bin/env python3
"""Tests for the shared cross-project sweep (scan_all_projects, Slice 1 / ADR-0002).

External-behavior only: feed a fixture ~/.claude/projects/* tree and assert the
returned shortlist. Never touches internal call order or private helpers beyond
the documented seams. Prior art: tests/test_tool_errors.py.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib.reflect_utils import scan_all_projects


def _write_session(project_dir: Path, name: str, user_texts):
    """Write a session JSONL with the given user-message texts."""
    project_dir.mkdir(parents=True, exist_ok=True)
    session = project_dir / name
    with open(session, "w", encoding="utf-8") as f:
        for text in user_texts:
            entry = {
                "type": "user",
                "isMeta": False,
                "message": {"content": [{"type": "text", "text": text}]},
            }
            f.write(json.dumps(entry) + "\n")
    return session


class TestScanAllProjects(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = Path(self.tmp) / "projects"
        self.projects.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_projects_dir(self):
        result = scan_all_projects(projects_dir=self.projects, days=None)
        self.assertEqual(result["global_candidates"], [])
        self.assertEqual(result["project_specific"], {})
        self.assertEqual(result["projects_scanned"], 0)

    def test_nonexistent_projects_dir(self):
        result = scan_all_projects(projects_dir=self.projects / "nope", days=None)
        self.assertEqual(result["global_candidates"], [])
        self.assertEqual(result["project_specific"], {})

    def test_cross_project_dedup_and_frequency(self):
        """Same correction in two project folders -> one global candidate, seen in 2."""
        _write_session(self.projects / "-repo-a", "s1.jsonl",
                       ["no, use pnpm not npm"])
        _write_session(self.projects / "-repo-b", "s1.jsonl",
                       ["no, use pnpm not npm"])

        result = scan_all_projects(projects_dir=self.projects, days=None)

        self.assertEqual(len(result["global_candidates"]), 1)
        cand = result["global_candidates"][0]
        self.assertEqual(cand["seen_in_projects"], 2)
        self.assertEqual(sorted(cand["projects"]), ["-repo-a", "-repo-b"])
        # not also listed as project-specific
        self.assertEqual(result["project_specific"], {})

    def test_project_specific_grouped_not_dropped(self):
        """A correction in exactly one project is surfaced per-project with a count."""
        _write_session(self.projects / "-repo-a", "s1.jsonl",
                       ["no, use tabs not spaces in this repo"])

        result = scan_all_projects(projects_dir=self.projects, days=None)

        self.assertEqual(result["global_candidates"], [])
        self.assertIn("-repo-a", result["project_specific"])
        bucket = result["project_specific"]["-repo-a"]
        self.assertEqual(bucket["count"], 1)
        self.assertGreaterEqual(len(bucket["samples"]), 1)

    def test_project_specific_is_bounded_not_enumerated(self):
        """Many distinct single-project corrections -> count reflects all, samples capped."""
        texts = [f"no, use approach-{i} not the other one" for i in range(10)]
        _write_session(self.projects / "-repo-a", "s1.jsonl", texts)

        result = scan_all_projects(projects_dir=self.projects, days=None,
                                   samples_per_project=3)

        bucket = result["project_specific"]["-repo-a"]
        self.assertEqual(bucket["count"], 10)
        # token-bounded: samples capped, not a full enumeration
        self.assertLessEqual(len(bucket["samples"]), 3)

    def test_frequency_ranking(self):
        """Correction in more projects ranks above one in fewer."""
        for folder in ("-r1", "-r2", "-r3"):
            _write_session(self.projects / folder, "s.jsonl",
                           ["no, use ripgrep not grep"])
        for folder in ("-r1", "-r2"):
            _write_session(self.projects / folder, "s2.jsonl",
                           ["no, use fd not find"])

        result = scan_all_projects(projects_dir=self.projects, days=None)

        cands = result["global_candidates"]
        self.assertEqual(len(cands), 2)
        self.assertEqual(cands[0]["seen_in_projects"], 3)
        self.assertEqual(cands[1]["seen_in_projects"], 2)

    def test_dedup_within_project_counts_one_project(self):
        """Same correction 3x in one folder = 1 project, not 3 (still project-specific)."""
        _write_session(self.projects / "-repo-a", "s.jsonl",
                       ["no, use pnpm not npm"] * 3)

        result = scan_all_projects(projects_dir=self.projects, days=None)

        # only one project -> not global
        self.assertEqual(result["global_candidates"], [])
        self.assertEqual(result["project_specific"]["-repo-a"]["count"], 1)

    def test_days_filter_excludes_old_sessions(self):
        old = _write_session(self.projects / "-repo-a", "old.jsonl",
                             ["no, use pnpm not npm"])
        # backdate mtime ~200 days
        past = time.time() - 200 * 86400
        os.utime(old, (past, past))

        result = scan_all_projects(projects_dir=self.projects, days=90)

        self.assertEqual(result["projects_scanned"], 0)
        self.assertEqual(result["global_candidates"], [])

    def test_does_not_return_raw_sessions(self):
        """Output is a distilled shortlist, not raw session content (token bound)."""
        _write_session(self.projects / "-repo-a", "s.jsonl",
                       ["no, use pnpm not npm"])
        _write_session(self.projects / "-repo-b", "s.jsonl",
                       ["no, use pnpm not npm"])
        result = scan_all_projects(projects_dir=self.projects, days=None)
        # top-level keys are the distilled buckets only
        self.assertEqual(set(result.keys()),
                         {"global_candidates", "project_specific", "projects_scanned"})


if __name__ == "__main__":
    unittest.main()
