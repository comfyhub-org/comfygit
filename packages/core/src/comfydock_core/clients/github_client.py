"""GitHub API client for repository operations and metadata retrieval."""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from comfydock_core.caching.api_cache import APICacheManager
from comfydock_core.constants import DEFAULT_GITHUB_URL
from comfydock_core.logging.logging_config import get_logger
from comfydock_core.utils.git import parse_github_url
from comfydock_core.utils.retry import RateLimitManager, RetryConfig

logger = get_logger(__name__)


@dataclass
class GitHubRepoInfo:
    """Information about a GitHub repository."""
    owner: str
    name: str
    default_branch: str
    description: str | None = None
    latest_release: str | None = None
    clone_url: str | None = None
    latest_commit: str | None = None


class GitHubClient:
    """Client for interacting with GitHub repositories.
    
    Provides repository cloning, metadata retrieval, and release management.
    Designed for custom nodes hosted on GitHub.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_GITHUB_URL,
        cache_manager: APICacheManager | None = None,
    ):
        self.base_url = base_url
        self.cache_manager = cache_manager or APICacheManager()
        self.rate_limiter = RateLimitManager(min_interval=0.05)
        self.retry_config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True,
        )

    def parse_github_url(self, url: str) -> GitHubRepoInfo | None:
        """Parse a GitHub URL to extract repository information.
        
        Args:
            url: GitHub repository URL
            
        Returns:
            GitHubRepoInfo or None if invalid URL
        """
        parsed = parse_github_url(url)
        if not parsed:
            return None

        owner, name, _ = parsed  # Ignore commit for basic parsing
        return GitHubRepoInfo(
            owner=owner,
            name=name,
            default_branch="main",  # Will be updated by get_repository_info
            clone_url=f"https://github.com/{owner}/{name}.git"
        )

    def clone_repository(self, repo_url: str, target_path: Path,
                        ref: str | None = None) -> bool:
        """Clone a GitHub repository to a target path.
        
        Args:
            repo_url: GitHub repository URL
            target_path: Where to clone the repository
            ref: Optional git ref (branch/tag/commit) to checkout
            
        Returns:
            True if successful, False otherwise
        """
        # TODO: Use git to clone repository
        # TODO: Checkout specific ref if provided
        # TODO: Handle authentication if needed
        return False

    def get_repository_info(self, repo_url: str) -> GitHubRepoInfo | None:
        """Get information about a GitHub repository.
        
        Args:
            repo_url: GitHub repository URL
            
        Returns:
            Repository information or None if not found
        """
        parsed = parse_github_url(repo_url)
        if not parsed:
            return None

        owner, name, specified_commit = parsed
        cache_key = f"{owner}/{name}" + (f"@{specified_commit}" if specified_commit else "")

        # Try cache first
        cached = self.cache_manager.get("github", cache_key)
        if cached:
            return GitHubRepoInfo(**cached)

        try:
            # Rate limit API calls
            self.rate_limiter.wait_if_needed("github_api")

            # Get repo metadata
            api_url = f"https://api.github.com/repos/{owner}/{name}"
            with urllib.request.urlopen(api_url) as response:
                repo_data = json.loads(response.read())

            default_branch = repo_data.get("default_branch", "main")

            # Use specified commit if provided, otherwise get latest commit on default branch
            latest_commit = specified_commit
            if not specified_commit:
                try:
                    commits_url = f"https://api.github.com/repos/{owner}/{name}/commits/{default_branch}"
                    with urllib.request.urlopen(commits_url) as response:
                        commit_data = json.loads(response.read())
                        latest_commit = commit_data.get("sha")
                except urllib.error.HTTPError:
                    # Could not get latest commit, that's okay
                    pass

            # Get latest release
            latest_release = None
            try:
                releases_url = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
                with urllib.request.urlopen(releases_url) as response:
                    release_data = json.loads(response.read())
                    latest_release = release_data.get("tag_name")
            except urllib.error.HTTPError:
                # No releases found, that's okay
                pass

            repo_info = GitHubRepoInfo(
                owner=owner,
                name=name,
                default_branch=default_branch,
                description=repo_data.get("description"),
                latest_release=latest_release,
                clone_url=repo_data.get("clone_url"),
                latest_commit=latest_commit
            )

            # Cache the result
            self.cache_manager.set("github", cache_key, repo_info.__dict__)

            return repo_info

        except (urllib.error.URLError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to get repository info for {repo_url}: {e}")
            return None

    def download_release_asset(self, repo_url: str, asset_name: str,
                              target_path: Path) -> bool:
        """Download a specific release asset from a repository.
        
        Args:
            repo_url: GitHub repository URL
            asset_name: Name of the asset to download
            target_path: Where to save the downloaded asset
            
        Returns:
            True if successful, False otherwise
        """
        # TODO: Find release with the asset
        # TODO: Download the asset
        # TODO: Save to target path
        return False
