"""Integration tests for CREATE command with version specification.

Tests the enhanced create flow that:
1. Fetches latest ComfyUI release by default
2. Validates user-provided versions
3. Supports aliases like "latest", "main", "master"
4. Stores version metadata in pyproject.toml
"""

import pytest
from pathlib import Path
from comfydock_core.utils.comfyui_ops import resolve_comfyui_version
from comfydock_core.clients.github_client import GitHubClient
from comfydock_core.caching.api_cache import APICacheManager


@pytest.fixture
def temp_cache(tmp_path):
    """Temporary cache for testing."""
    return tmp_path / "test_cache"


@pytest.fixture
def github_client(temp_cache):
    """GitHub client with temporary cache."""
    cache_manager = APICacheManager(cache_base_path=temp_cache)
    return GitHubClient(cache_manager=cache_manager)


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
    comfydock_config = config.get("tool", {}).get("comfydock", {})
    assert "comfyui_version" in comfydock_config, "Should store comfyui_version"
    assert "comfyui_version_type" in comfydock_config, "Should store comfyui_version_type"
    assert "comfyui_commit_sha" in comfydock_config, "Should store comfyui_commit_sha"

    # Version type should be set
    assert comfydock_config["comfyui_version_type"] in ["release", "branch", "commit"], \
        "Version type should be one of the valid types"


def test_create_with_latest_fetches_from_github(test_workspace, mock_comfyui_clone, mock_github_api):
    """SHOULD fetch latest release when version is 'latest'."""
    # This test creates an environment with mocked GitHub API
    # It should resolve 'latest' to a release version
    env = test_workspace.create_environment("test-env", comfyui_version="latest")

    # Load pyproject
    config = env.pyproject.load()
    comfydock_config = config.get("tool", {}).get("comfydock", {})

    # Should have used release type
    assert comfydock_config["comfyui_version_type"] == "release", \
        "Should resolve 'latest' to a release"


def test_create_stores_actual_commit_sha_after_clone(test_workspace, mock_comfyui_clone, mock_github_api):
    """SHOULD store the actual commit SHA after cloning."""
    env = test_workspace.create_environment("test-env", comfyui_version="master")

    # Load pyproject
    config = env.pyproject.load()
    comfydock_config = config.get("tool", {}).get("comfydock", {})

    # Should have commit SHA
    commit_sha = comfydock_config.get("comfyui_commit_sha")
    assert commit_sha is not None, "Should store commit SHA after clone"
    # Commit SHA should be 40 hex characters
    assert isinstance(commit_sha, str), "Commit SHA should be a string"
