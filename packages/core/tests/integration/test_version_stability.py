"""Test that version numbers remain stable and all commits are shown.

This addresses the bug where:
1. Version numbers change after rollbacks (v1 has different message)
2. Only last N commits are shown (some versions are hidden)
3. Version numbers are recalculated on each log call (unstable)
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestVersionStability:
    """Test that version numbers assigned to commits remain stable."""

    def test_version_numbers_stable_across_log_calls(self, test_env):
        """Version numbers should not change between log calls."""
        # ARRANGE: Create 5 commits with actual changes
        pyproject_path = test_env.cec_path / "pyproject.toml"

        for i in range(1, 6):
            # Make a change
            with open(pyproject_path, 'a') as f:
                f.write(f"\n# Change {i}")
            test_env.git_manager.commit_with_identity(f"Commit {i}")

        # ACT: Get version history twice
        first_log = test_env.git_manager.get_version_history(limit=100)
        second_log = test_env.git_manager.get_version_history(limit=100)

        # ASSERT: Version numbers should be identical
        assert len(first_log) == len(second_log), "Should have same number of versions"

        for first, second in zip(first_log, second_log):
            assert first['version'] == second['version'], \
                f"Version number changed: {first['version']} != {second['version']}"
            assert first['message'] == second['message'], \
                f"Version {first['version']} has different message"
            assert first['hash'] == second['hash'], \
                f"Version {first['version']} has different hash"

    def test_version_numbers_stable_after_rollback(self, test_env):
        """Version numbers should not change after a rollback creates a new commit."""
        # ARRANGE: Create commits and record their version->message mapping
        pyproject_path = test_env.cec_path / "pyproject.toml"

        for i, msg in enumerate(["Initial commit", "Second commit", "Third commit"], 1):
            with open(pyproject_path, 'a') as f:
                f.write(f"\n# Rollback test {i}")
            test_env.git_manager.commit_with_identity(msg)

        # Get initial mapping
        before_rollback = test_env.git_manager.get_version_history(limit=100)
        version_to_message_before = {v['version']: v['message'] for v in before_rollback}

        # ACT: Rollback to v2 (this creates a new commit)
        test_env.rollback("v2", force=True)

        # Get mapping after rollback
        after_rollback = test_env.git_manager.get_version_history(limit=100)
        version_to_message_after = {v['version']: v['message'] for v in after_rollback}

        # ASSERT: Old version numbers should still map to same messages
        # (v1 should still be "Initial commit", v2 should still be "Second commit", etc.)
        for version, message in version_to_message_before.items():
            assert version in version_to_message_after, \
                f"Version {version} disappeared after rollback"
            assert version_to_message_after[version] == message, \
                f"Version {version} changed: was '{message}', now '{version_to_message_after[version]}'"

        # The new rollback commit should be v5 (next sequential after v4)
        # Before rollback there were 4 commits (including "Initial test environment")
        # After rollback there should be 5 commits
        expected_new_version = f"v{len(before_rollback) + 1}"
        assert expected_new_version in version_to_message_after, \
            f"Should have {expected_new_version} after rollback"
        assert "Rollback to v2" in version_to_message_after[expected_new_version], \
            f"New commit should be labeled as {expected_new_version}"

    def test_all_commits_shown_in_history(self, test_env):
        """All commits should be shown, not just the last N."""
        # ARRANGE: Create 25 commits (more than typical limit of 10)
        pyproject_path = test_env.cec_path / "pyproject.toml"

        for i in range(1, 26):
            with open(pyproject_path, 'a') as f:
                f.write(f"\n# All commits test {i}")
            test_env.git_manager.commit_with_identity(f"Commit {i}")

        # ACT: Get version history (should show ALL commits)
        history = test_env.git_manager.get_version_history(limit=100)

        # ASSERT: Should show all 25 commits plus initial commit
        assert len(history) >= 25, \
            f"Should show all commits, got {len(history)}, expected at least 25"

        # Version numbers should go from v1 to v26 (or higher with initial commits)
        versions = [v['version'] for v in history]
        assert 'v1' in versions, "Should include v1"
        assert f'v{len(history)}' in versions, f"Should include v{len(history)}"

    def test_version_numbers_are_chronological(self, test_env):
        """Version numbers should be assigned chronologically (v1 = oldest)."""
        # ARRANGE: Create commits with distinctive messages
        pyproject_path = test_env.cec_path / "pyproject.toml"
        messages = [
            "First commit",
            "Second commit",
            "Third commit",
            "Fourth commit",
            "Fifth commit"
        ]

        for i, msg in enumerate(messages, 1):
            with open(pyproject_path, 'a') as f:
                f.write(f"\n# Chronological {i}")
            test_env.git_manager.commit_with_identity(msg)

        # ACT: Get history
        history = test_env.git_manager.get_version_history(limit=100)

        # Find our commits in the history
        our_commits = [v for v in history if v['message'] in messages]

        # ASSERT: They should be in chronological order with sequential version numbers
        assert len(our_commits) == 5, "Should find all 5 commits"

        for i, commit in enumerate(our_commits):
            assert commit['message'] == messages[i], \
                f"Commit order wrong: expected '{messages[i]}', got '{commit['message']}'"

    def test_limit_parameter_deprecated_shows_all(self, test_env):
        """The limit parameter should effectively be ignored (show all commits)."""
        # ARRANGE: Create 15 commits
        pyproject_path = test_env.cec_path / "pyproject.toml"

        for i in range(1, 16):
            with open(pyproject_path, 'a') as f:
                f.write(f"\n# Limit test {i}")
            test_env.git_manager.commit_with_identity(f"Commit {i}")

        # ACT: Call with small limit (old behavior would truncate)
        history_with_limit = test_env.git_manager.get_version_history(limit=5)

        # ASSERT: Should still show all commits (limit should be ignored or set very high)
        # We have at least 15 commits we just created, plus any initial commits
        assert len(history_with_limit) >= 15, \
            f"Should show all commits despite limit=5, got {len(history_with_limit)}"


class TestVersionNumberFormat:
    """Test that version numbers follow the correct format."""

    def test_version_numbers_are_sequential(self, test_env):
        """Version numbers should be v1, v2, v3, ... with no gaps."""
        # ARRANGE: Create some commits
        pyproject_path = test_env.cec_path / "pyproject.toml"

        for i in range(5):
            with open(pyproject_path, 'a') as f:
                f.write(f"\n# Sequential {i}")
            test_env.git_manager.commit_with_identity(f"Commit {i}")

        # ACT
        history = test_env.git_manager.get_version_history(limit=100)

        # ASSERT: Extract version numbers and check they're sequential
        version_numbers = [int(v['version'][1:]) for v in history]  # Strip 'v' prefix

        for i in range(len(version_numbers)):
            assert version_numbers[i] == i + 1, \
                f"Version gap detected: expected v{i+1}, got v{version_numbers[i]}"
