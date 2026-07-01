#!/usr/bin/env python3
"""Tests for hook scripts: git-commit detection (#3) and payload-cwd capture (#2)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_commit_reminder import detect_git_commit
from lib.reflect_utils import get_project_folder_name


class TestGitCommitDetection(unittest.TestCase):
    """#3 — tokenized git-commit detection (adjacent argv tokens)."""

    def test_real_commit_fires(self):
        is_commit, is_amend = detect_git_commit('git commit -m "fix bug"')
        self.assertTrue(is_commit)
        self.assertFalse(is_amend)

    def test_chained_commit_fires(self):
        is_commit, _ = detect_git_commit("npm test && git commit -m x")
        self.assertTrue(is_commit)

    def test_echo_does_not_fire(self):
        is_commit, _ = detect_git_commit('echo "remember to git commit now"')
        self.assertFalse(is_commit)

    def test_grep_does_not_fire(self):
        is_commit, _ = detect_git_commit('grep "git commit" changelog.txt')
        self.assertFalse(is_commit)

    def test_commit_graph_does_not_fire(self):
        is_commit, _ = detect_git_commit("git commit-graph write")
        self.assertFalse(is_commit)

    def test_amend_detected_as_standalone_token(self):
        is_commit, is_amend = detect_git_commit("git commit --amend --no-edit")
        self.assertTrue(is_commit)
        self.assertTrue(is_amend)

    def test_amend_inside_message_is_not_amend(self):
        # The false-negative fix: --amend in the commit *message* must not count.
        is_commit, is_amend = detect_git_commit('git commit -m "document the --amend flag"')
        self.assertTrue(is_commit)
        self.assertFalse(is_amend)

    def test_unbalanced_quotes_safe(self):
        is_commit, is_amend = detect_git_commit('git commit -m "unclosed')
        self.assertFalse(is_commit)
        self.assertFalse(is_amend)


class TestCapturePayloadCwd(unittest.TestCase):
    """#2 — capture is scoped to the hook payload cwd, not the process cwd."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.project = Path(self.home) / "myproject"
        (self.project / "sub").mkdir(parents=True)
        self.env = dict(os.environ, HOME=self.home)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def _queue_path(self, project_dir):
        folder = get_project_folder_name(str(project_dir))
        return Path(self.home) / ".claude" / "projects" / folder / "learnings-queue.json"

    def test_capture_lands_in_payload_cwd_queue(self):
        payload = json.dumps(
            {"prompt": "no, use pytest not unittest", "cwd": str(self.project)}
        )
        # Run the hook from a *subdirectory* to prove the payload cwd wins over
        # the process cwd.
        subprocess.run(
            [sys.executable, str(SCRIPTS / "capture_learning.py")],
            input=payload,
            text=True,
            env=self.env,
            cwd=str(self.project / "sub"),
            check=True,
        )

        # Capture must land in the project's queue (what /reflect scans)...
        project_queue = self._queue_path(self.project)
        self.assertTrue(project_queue.exists(), "capture did not land in project queue")
        items = json.loads(project_queue.read_text(encoding="utf-8"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["project"], str(self.project))

        # ...and NOT in a subdirectory-scoped queue that /reflect never scans.
        sub_queue = self._queue_path(self.project / "sub")
        self.assertFalse(sub_queue.exists(), "capture leaked into subdirectory queue")

    def test_concurrent_captures_across_processes_all_persist(self):
        # #1 acceptance: "two concurrent captures in the same project both
        # persist (concurrency test simulating two sessions)." Real sessions are
        # separate processes, so exercise the O_EXCL lock cross-process, not just
        # cross-thread.
        n = 6
        procs = []
        for i in range(n):
            payload = json.dumps(
                {"prompt": f"remember: fact number {i}", "cwd": str(self.project)}
            )
            procs.append(
                subprocess.Popen(
                    [sys.executable, str(SCRIPTS / "capture_learning.py")],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    text=True,
                    env=self.env,
                    cwd=str(self.project),
                )
            )
        for p, i in zip(procs, range(n)):
            payload = json.dumps(
                {"prompt": f"remember: fact number {i}", "cwd": str(self.project)}
            )
            p.communicate(input=payload)
        for p in procs:
            self.assertEqual(p.returncode, 0)

        items = json.loads(self._queue_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(len(items), n, "a concurrent capture was clobbered")


if __name__ == "__main__":
    unittest.main()
