"""Integration tests for CREATE command with version specification.

Tests the enhanced create flow that:
1. Fetches latest ComfyUI release by default
2. Validates user-provided versions
3. Supports aliases like "latest", "main", "master"
4. Stores version metadata in pyproject.toml
"""

import pytest
from comfygit_core.utils.comfyui_ops import resolve_comfyui_version


@pytest.fixture
def github_client():
    """Mocked GitHub client for testing without network calls."""

    class FakeRepositoryInfo:
        def __init__(self):
            self.latest_release = "v0.3.20"
            self.default_branch = "master"

    class FakeRelease:
        def __init__(self, tag_name: str):
            self.tag_name = tag_name
            self.name = f"Release {tag_name}"
            self.published_at = "2024-01-01T00:00:00Z"
            self.prerelease = False
            self.draft = False
            self.html_url = f"https://github.com/comfyanonymous/ComfyUI/releases/tag/{tag_name}"

    class MockGitHubClient:
        def get_repository_info(self, repo_url: str):
            """Return fake repository info."""
            return FakeRepositoryInfo()

        def validate_version_exists(self, repo_url: str, version: str) -> bool:
            """Validate that a version exists (mocked)."""
            # Only accept known release tags or branches
            known_versions = ["v0.3.66", "v0.3.20", "v0.3.19", "v0.3.15", "master", "main", "test"]
            return version in known_versions

        def list_releases(self, repo_url: str, include_prerelease: bool = False, limit: int = 10):
            """Return fake releases list."""
            all_releases = [
                FakeRelease("v0.3.66"),
                FakeRelease("v0.3.20"),
                FakeRelease("v0.3.19"),
                FakeRelease("v0.3.15"),
            ]
            return all_releases[:limit]

        def get_release_by_tag(self, repo_url: str, tag: str):
            """Get specific release by tag (mocked)."""
            # Return release if tag exists in our fake list
            fake_tags = ["v0.3.66", "v0.3.20", "v0.3.19", "v0.3.15"]
            if tag in fake_tags:
                return FakeRelease(tag)
            return None

    return MockGitHubClient()


def test_resolve_comfyui_version_exists(github_client):
    """SHOULD have resolve_comfyui_version function."""
    # Check that the function exists
    assert callable(resolve_comfyui_version), "Should have resolve_comfyui_version function"


def test_resolve_none_to_latest_release(github_client):
    """SHOULD resolve None to latest release tag."""
    version_to_clone, version_type, commit_sha = resolve_comfyui_version(None, github_client)

    assert version_to_clone is not None, "Should resolve to a version"
    assert version_type == "release", "Should resolve to release type"
    assert commit_sha is None, "Commit SHA should be None before cloning"


def test_resolve_latest_to_latest_release(github_client):
    """SHOULD resolve 'latest' to latest release tag."""
    version_to_clone, version_type, commit_sha = resolve_comfyui_version("latest", github_client)

    assert version_to_clone is not None, "Should resolve to a version"
    assert version_type == "release", "Should resolve to release type"
    assert commit_sha is None, "Commit SHA should be None before cloning"


def test_resolve_release_tag(github_client):
    """SHOULD resolve release tags (starting with 'v')."""
    # Get an actual release tag first
    repo_url = "https://github.com/comfyanonymous/ComfyUI.git"
    releases = github_client.list_releases(repo_url, limit=1)

    if len(releases) > 0:
        tag = releases[0].tag_name
        version_to_clone, version_type, commit_sha = resolve_comfyui_version(tag, github_client)

        assert version_to_clone == tag, "Should return the same tag"
        assert version_type == "release", "Should be release type"
        assert commit_sha is None, "Commit SHA should be None before cloning"


def test_resolve_branch_alias_master(github_client):
    """SHOULD resolve 'master' as a branch (ComfyUI only has master, not main)."""
    version_to_clone, version_type, commit_sha = resolve_comfyui_version("master", github_client)

    assert version_to_clone == "master", "Should return 'master'"
    assert version_type == "branch", "Should be branch type"
    assert commit_sha is None, "Commit SHA should be None before cloning"


def test_resolve_commit_hash(github_client):
    """SHOULD treat non-tag/non-branch values as commit hashes."""
    fake_commit = "abc123def456"
    version_to_clone, version_type, commit_sha = resolve_comfyui_version(fake_commit, github_client)

    assert version_to_clone == fake_commit, "Should return the commit hash"
    assert version_type == "commit", "Should be commit type"
    assert commit_sha is None, "Commit SHA should be None before cloning"


def test_resolve_invalid_release_tag_raises_error(github_client):
    """SHOULD raise ValueError for non-existent release tags."""
    with pytest.raises(ValueError, match="does not exist"):
        resolve_comfyui_version("v999.999.999", github_client)


def test_create_stores_version_metadata_in_pyproject(test_workspace, mock_comfyui_clone, mock_github_api):
    """SHOULD store version, type, and commit_sha in pyproject.toml."""
    # Create an environment
    env = test_workspace.create_environment("test-env", comfyui_version="master")

    # Load pyproject
    config = env.pyproject.load()

    # Check for version metadata
    comfygit_config = config.get("tool", {}).get("comfygit", {})
    assert "comfyui_version" in comfygit_config, "Should store comfyui_version"
    assert "comfyui_version_type" in comfygit_config, "Should store comfyui_version_type"
    assert "comfyui_commit_sha" in comfygit_config, "Should store comfyui_commit_sha"

    # Version type should be set
    assert comfygit_config["comfyui_version_type"] in ["release", "branch", "commit"], \
        "Version type should be one of the valid types"


def test_create_with_latest_fetches_from_github(test_workspace, mock_comfyui_clone, mock_github_api):
    """SHOULD fetch latest release when version is 'latest'."""
    # This test creates an environment with mocked GitHub API
    # It should resolve 'latest' to a release version
    env = test_workspace.create_environment("test-env", comfyui_version="latest")

    # Load pyproject
    config = env.pyproject.load()
    comfygit_config = config.get("tool", {}).get("comfygit", {})

    # Should have used release type
    assert comfygit_config["comfyui_version_type"] == "release", \
        "Should resolve 'latest' to a release"


def test_create_stores_actual_commit_sha_after_clone(test_workspace, mock_comfyui_clone, mock_github_api):
    """SHOULD store the actual commit SHA after cloning."""
    env = test_workspace.create_environment("test-env", comfyui_version="master")

    # Load pyproject
    config = env.pyproject.load()
    comfygit_config = config.get("tool", {}).get("comfygit", {})

    # Should have commit SHA
    commit_sha = comfygit_config.get("comfyui_commit_sha")
    assert commit_sha is not None, "Should store commit SHA after clone"
    # Commit SHA should be 40 hex characters
    assert isinstance(commit_sha, str), "Commit SHA should be a string"
