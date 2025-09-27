"""Tests for GlobalNodeResolver utilities."""

from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver


class TestGitHubUrlNormalization:
    """Test GitHub URL normalization functionality."""

    def test_https_url_no_changes_needed(self):
        resolver = GlobalNodeResolver()
        url = "https://github.com/owner/repo"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_https_url_with_git_suffix(self):
        resolver = GlobalNodeResolver()
        url = "https://github.com/owner/repo.git"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_ssh_url_git_at_format(self):
        resolver = GlobalNodeResolver()
        url = "git@github.com:owner/repo.git"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_ssh_url_git_at_format_no_git_suffix(self):
        resolver = GlobalNodeResolver()
        url = "git@github.com:owner/repo"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_ssh_url_full_format(self):
        resolver = GlobalNodeResolver()
        url = "ssh://git@github.com/owner/repo.git"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_ssh_url_full_format_no_git_suffix(self):
        resolver = GlobalNodeResolver()
        url = "ssh://git@github.com/owner/repo"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_www_github_url(self):
        resolver = GlobalNodeResolver()
        url = "https://www.github.com/owner/repo"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_complex_github_url_with_extra_path_parts(self):
        resolver = GlobalNodeResolver()
        url = "https://github.com/owner/repo/tree/main"
        result = resolver._normalize_github_url(url)
        assert result == "https://github.com/owner/repo"

    def test_empty_url(self):
        resolver = GlobalNodeResolver()
        result = resolver._normalize_github_url("")
        assert result == ""

    def test_none_url(self):
        resolver = GlobalNodeResolver()
        result = resolver._normalize_github_url(None)
        assert result == ""

    def test_non_github_url(self):
        resolver = GlobalNodeResolver()
        url = "https://gitlab.com/owner/repo.git"
        result = resolver._normalize_github_url(url)
        # Non-GitHub URLs still get .git removed
        assert result == "https://gitlab.com/owner/repo"

    def test_invalid_github_url_format(self):
        resolver = GlobalNodeResolver()
        url = "https://github.com/owner"  # Missing repo
        result = resolver._normalize_github_url(url)
        # Should return original URL since it doesn't have enough path parts
        assert result == "https://github.com/owner"


class TestGitHubToRegistryMapping:
    """Test GitHub URL to Registry ID mapping functionality."""

    def test_build_github_to_registry_map_empty_packages(self):
        resolver = GlobalNodeResolver()
        resolver.packages = {}
        resolver._build_github_to_registry_map()
        assert resolver.github_to_registry == {}

    def test_build_github_to_registry_map_with_packages(self):
        resolver = GlobalNodeResolver()
        resolver.packages = {
            "test-package": {
                "repository": "https://github.com/owner/repo",
                "display_name": "Test Package"
            },
            "another-package": {
                "repository": "git@github.com:owner2/repo2.git",
                "display_name": "Another Package"
            },
            "no-repo-package": {
                "display_name": "No Repo Package"
                # No repository field
            }
        }
        resolver._build_github_to_registry_map()

        expected = {
            "https://github.com/owner/repo": {
                "package_id": "test-package",
                "data": resolver.packages["test-package"]
            },
            "https://github.com/owner2/repo2": {
                "package_id": "another-package",
                "data": resolver.packages["another-package"]
            }
        }

        assert resolver.github_to_registry == expected

    def test_resolve_github_url_existing_mapping(self):
        resolver = GlobalNodeResolver()
        resolver.loaded = True  # Mark as loaded to avoid loading mappings
        resolver.github_to_registry = {
            "https://github.com/owner/repo": {
                "package_id": "test-package",
                "data": {"display_name": "Test Package"}
            }
        }

        result = resolver.resolve_github_url("https://github.com/owner/repo.git")
        assert result == ("test-package", {"display_name": "Test Package"})

    def test_resolve_github_url_no_mapping(self):
        resolver = GlobalNodeResolver()
        resolver.github_to_registry = {}
        resolver.loaded = True

        result = resolver.resolve_github_url("https://github.com/unknown/repo")
        assert result is None

    def test_get_github_url_for_package_existing(self):
        resolver = GlobalNodeResolver()
        resolver.packages = {
            "test-package": {
                "repository": "https://github.com/owner/repo",
                "display_name": "Test Package"
            }
        }
        resolver.loaded = True

        result = resolver.get_github_url_for_package("test-package")
        assert result == "https://github.com/owner/repo"

    def test_get_github_url_for_package_not_found(self):
        resolver = GlobalNodeResolver()
        resolver.packages = {}
        resolver.loaded = True

        result = resolver.get_github_url_for_package("unknown-package")
        assert result is None