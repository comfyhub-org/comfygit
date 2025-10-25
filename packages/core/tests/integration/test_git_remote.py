"""Tests for git remote operations."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


class TestGitRemote:
    """Test git remote management operations."""

    def test_add_remote(self, test_env, tmp_path):
        """Add remote should configure origin."""
        # Create bare remote repo
        remote_repo = tmp_path / "remote-repo"
        remote_repo.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_repo, check=True, capture_output=True)

        # Use test environment
        env = test_env

        # Add remote
        env.git_manager.add_remote("origin", str(remote_repo))

        # Verify remote exists with correct URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=env.cec_path,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert str(remote_repo) in result.stdout

    def test_list_remotes(self, test_env, tmp_path):
        """List remotes should return all configured remotes."""
        # Create two bare remotes
        origin_repo = tmp_path / "origin-repo"
        origin_repo.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=origin_repo, check=True, capture_output=True)

        upstream_repo = tmp_path / "upstream-repo"
        upstream_repo.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=upstream_repo, check=True, capture_output=True)

        # Use test environment
        env = test_env

        # Add remotes
        env.git_manager.add_remote("origin", str(origin_repo))
        env.git_manager.add_remote("upstream", str(upstream_repo))

        # List remotes
        remotes = env.git_manager.list_remotes()

        # Should return list of tuples: [(name, url, type), ...]
        assert len(remotes) >= 2

        remote_dict = {name: url for name, url, _ in remotes}
        assert "origin" in remote_dict
        assert "upstream" in remote_dict
        assert str(origin_repo) in remote_dict["origin"]
        assert str(upstream_repo) in remote_dict["upstream"]

    def test_remove_remote(self, test_env, tmp_path):
        """Remove remote should delete configuration."""
        # Create bare remote
        remote_repo = tmp_path / "remote-repo"
        remote_repo.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_repo, check=True, capture_output=True)

        # Use test environment
        env = test_env

        # Add remote
        env.git_manager.add_remote("origin", str(remote_repo))

        # Verify it exists
        assert env.git_manager.has_remote("origin")

        # Remove remote
        env.git_manager.remove_remote("origin")

        # Verify it's gone
        assert not env.git_manager.has_remote("origin")

    def test_add_remote_rejects_duplicate(self, test_env, tmp_path):
        """Add remote should fail if remote already exists."""
        # Create bare remote
        remote_repo = tmp_path / "remote-repo"
        remote_repo.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_repo, check=True, capture_output=True)

        # Use test environment
        env = test_env

        # Add remote
        env.git_manager.add_remote("origin", str(remote_repo))

        # Try to add again - should fail
        with pytest.raises(OSError, match="already exists"):
            env.git_manager.add_remote("origin", str(remote_repo))

    def test_remove_nonexistent_remote_fails(self, test_env):
        """Remove remote should fail with helpful error if remote doesn't exist."""
        # Use test environment (has no remotes by default)
        env = test_env

        # Try to remove non-existent remote
        with pytest.raises(ValueError, match="not found"):
            env.git_manager.remove_remote("origin")

    def test_has_remote(self, test_env, tmp_path):
        """has_remote should correctly detect remote existence."""
        # Create bare remote
        remote_repo = tmp_path / "remote-repo"
        remote_repo.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_repo, check=True, capture_output=True)

        # Use test environment
        env = test_env

        # Initially no remote
        assert not env.git_manager.has_remote("origin")

        # Add remote
        env.git_manager.add_remote("origin", str(remote_repo))

        # Now has remote
        assert env.git_manager.has_remote("origin")

        # Still no upstream
        assert not env.git_manager.has_remote("upstream")
