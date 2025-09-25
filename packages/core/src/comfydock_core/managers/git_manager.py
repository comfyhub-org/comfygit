"""High-level Git workflow manager for ComfyDock environments.

This module provides higher-level git workflows that combine multiple git operations
with business logic. It builds on top of the low-level git utilities in git.py.
"""
from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..models.environment import GitStatus

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager

from ..utils.git import (
    get_uncommitted_changes,
    git_checkout,
    git_commit,
    git_config_get,
    git_config_set,
    git_describe_tags,
    git_diff,
    git_history,
    git_init,
    git_remote_get_url,
    git_rev_parse,
    git_show,
    git_status_porcelain,
)

logger = get_logger(__name__)


class GitManager:
    """Manages high-level git workflows for environment tracking."""

    def __init__(self, repo_path: Path):
        """Initialize GitManager for a specific repository.

        Args:
            repo_path: Path to the git repository (usually .cec directory)
        """
        self.repo_path = repo_path
        self.gitignore_content = """# Staging area
staging/

# Staging metadata
metadata/

# logs
logs/

# Python cache
__pycache__/
*.pyc

# Temporary files
*.tmp
*.bak
"""

    def ensure_git_identity(self) -> None:
        """Ensure git has a user identity configured for commits.

        Sets up local git config (not global) with sensible defaults.
        """
        # Check if identity is already configured
        existing_name = git_config_get(self.repo_path, "user.name")
        existing_email = git_config_get(self.repo_path, "user.email")

        # If both are set, we're good
        if existing_name and existing_email:
            return

        # Determine git identity using fallback chain
        git_name = self._get_git_identity()
        git_email = self._get_git_email()

        # Set identity locally for this repository only
        git_config_set(self.repo_path, "user.name", git_name)
        git_config_set(self.repo_path, "user.email", git_email)

        logger.info(f"Set local git identity: {git_name} <{git_email}>")

    def _get_git_identity(self) -> str:
        """Get a suitable git user name with smart fallbacks."""
        # Try environment variables first
        git_name = os.environ.get("GIT_AUTHOR_NAME")
        if git_name:
            return git_name

        # Try to get system username as fallback for name
        try:
            import pwd
            git_name = (
                pwd.getpwuid(os.getuid()).pw_gecos or pwd.getpwuid(os.getuid()).pw_name
            )
            if git_name:
                return git_name
        except Exception:
            pass

        try:
            git_name = os.getlogin()
            if git_name:
                return git_name
        except Exception:
            pass

        return "ComfyDock User"

    def _get_git_email(self) -> str:
        """Get a suitable git email with smart fallbacks."""
        # Try environment variables first
        git_email = os.environ.get("GIT_AUTHOR_EMAIL")
        if git_email:
            return git_email

        # Try to construct from username and hostname
        try:
            hostname = socket.gethostname()
            username = os.getlogin()
            return f"{username}@{hostname}"
        except Exception:
            pass

        return "user@comfydock.local"

    @staticmethod
    def get_custom_node_git_info(node_path: Path) -> dict | None:
        """Get git repository information for a custom node.

        Args:
            node_path: Path to the custom node directory

        Returns:
            Dict with git information or None if not a git repository
        """
        import re

        git_info = {}

        try:
            # Check if it's a git repository
            git_dir = node_path / ".git"
            if not git_dir.exists():
                return None

            # Get current commit hash
            commit = git_rev_parse(node_path, "HEAD")
            if commit:
                git_info["commit"] = commit

            # Get current branch
            branch = git_rev_parse(node_path, "HEAD", abbrev_ref=True)
            if branch and branch != "HEAD":
                git_info["branch"] = branch

            # Try to get current tag/version
            tag = git_describe_tags(node_path, exact_match=True)
            if tag:
                git_info["tag"] = tag
            else:
                # Try to get the most recent tag
                tag = git_describe_tags(node_path, abbrev=0)
                if tag:
                    git_info["tag"] = tag

            # Get remote URL
            remote_url = git_remote_get_url(node_path)
            if remote_url:
                git_info["remote_url"] = remote_url

                # Extract GitHub info if it's a GitHub URL
                github_match = re.match(
                    r"(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/\.]+)",
                    remote_url,
                )
                if github_match:
                    git_info["github_owner"] = github_match.group(1)
                    git_info["github_repo"] = github_match.group(2).replace(".git", "")

            # Check if there are uncommitted changes
            status_entries = git_status_porcelain(node_path)
            git_info["is_dirty"] = bool(status_entries)

            return git_info if git_info else None

        except Exception as e:
            from ..logging.logging_config import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Error getting git info for {node_path}: {e}")
            return None

    def initialize_environment_repo(
        self, initial_message: str = "Initial environment setup"
    ) -> None:
        """Initialize a new environment repository with proper setup.

        This combines:
        - Git init
        - Identity setup
        - Gitignore creation
        - Initial commit

        Args:
            initial_message: Message for the initial commit
        """
        # Initialize git repository
        git_init(self.repo_path)

        # Ensure git identity is configured
        self.ensure_git_identity()

        # Create standard .gitignore
        self._create_gitignore()

        # Initial commit (if there are files to commit)
        if any(self.repo_path.iterdir()):
            git_commit(self.repo_path, initial_message)
            logger.info(f"Created initial commit: {initial_message}")

    def commit_with_identity(self, message: str, add_all: bool = True) -> None:
        """Commit changes ensuring identity is set up.

        Args:
            message: Commit message
            add_all: Whether to stage all changes first
        """
        # Ensure identity before committing
        self.ensure_git_identity()

        # Perform the commit
        git_commit(self.repo_path, message, add_all)

    def apply_version(self, version: str, leave_unstaged: bool = True) -> None:
        """Apply files from a specific version to working directory.

        This is a high-level rollback operation that:
        - Resolves version identifiers (v1, v2, etc.) to commits
        - Applies files from that commit
        - Optionally leaves them unstaged for review

        Args:
            version: Version identifier (e.g., "v1", "v2") or commit hash
            leave_unstaged: If True, files are left as uncommitted changes

        Raises:
            ValueError: If version doesn't exist
        """
        # Resolve version to commit hash
        commit_hash = self.resolve_version(version)

        logger.info(f"Applying files from version {version} (commit {commit_hash[:8]})")

        # Apply all files from that commit
        git_checkout(self.repo_path, commit_hash, files=["."], unstage=leave_unstaged)

    def discard_uncommitted(self) -> None:
        """Discard all uncommitted changes in the repository."""
        logger.info("Discarding uncommitted changes")
        git_checkout(self.repo_path, "HEAD", files=["."])

    def get_version_history(self, limit: int = 10) -> list[dict]:
        """Get simplified version history with v1, v2 labels.

        Args:
            limit: Maximum number of versions to return

        Returns:
            List of version info dicts
        """
        return self._get_commit_versions(limit)

    def resolve_version(self, version: str) -> str:
        """Resolve a version identifier to a commit hash.

        Args:
            version: Version identifier (e.g., "v1", "v2") or commit hash

        Returns:
            Full commit hash

        Raises:
            ValueError: If version doesn't exist
        """
        return self._resolve_version_to_commit(version)

    def get_pyproject_diff(self) -> str:
        """Get the git diff specifically for pyproject.toml.

        Returns:
            Diff output or empty string
        """
        pyproject_path = Path("pyproject.toml")
        return git_diff(self.repo_path, pyproject_path) or ""

    def get_pyproject_from_version(self, version: str) -> str:
        """Get pyproject.toml content from a specific version.

        Args:
            version: Version identifier or commit hash

        Returns:
            File content as string

        Raises:
            ValueError: If version or file doesn't exist
        """
        commit_hash = self.resolve_version(version)
        return git_show(self.repo_path, commit_hash, Path("pyproject.toml"))

    def commit_all(self, message: str | None = None) -> None:
        """Commit all changes in the repository.

        Args:
            message: Commit message

        Raises:
            OSError: If git commands fail

        """
        if message is None:
            message = "Committing all changes"
        return git_commit(self.repo_path, message, add_all=True)

    def get_workflow_git_changes(self) -> dict[str, str]:
        """Get git status for workflow files specifically.

        Returns:
            Dict mapping workflow names to their git status:
            - 'modified' for modified files
            - 'added' for new/untracked files
            - 'deleted' for deleted files
        """
        status_entries = git_status_porcelain(self.repo_path)
        workflow_changes = {}

        for index_status, working_status, filename in status_entries:
            logger.debug(f"index status: {index_status}, working status: {working_status}, filename: {filename}")

            # Only process workflow files
            if filename.startswith('workflows/') and filename.endswith('.json'):
                # Extract workflow name from path (keep spaces as-is)
                workflow_name = Path(filename).stem
                logger.debug(f"Workflow name: {workflow_name}")

                # Determine status (prioritize working tree status)
                if working_status == 'M' or index_status == 'M':
                    workflow_changes[workflow_name] = 'modified'
                elif working_status == 'D' or index_status == 'D':
                    workflow_changes[workflow_name] = 'deleted'
                elif working_status == '?' or index_status == 'A':
                    workflow_changes[workflow_name] = 'added'

        logger.debug(f"Workflow changes: {str(workflow_changes)}")
        return workflow_changes

    def get_workflow_changes(self) -> dict[str, str]:
        """Get git status for workflow files.

        Returns:
            Dict mapping workflow names to their git status
        """
        return self.get_workflow_git_changes()

    def has_uncommitted_changes(self) -> bool:
        """Check if there are any uncommitted changes.

        Returns:
            True if there are uncommitted changes
        """
        return bool(get_uncommitted_changes(self.repo_path))

    def _create_gitignore(self) -> None:
        """Create standard .gitignore for environment tracking."""
        gitignore_path = self.repo_path / ".gitignore"
        gitignore_path.write_text(self.gitignore_content)

    def _get_commit_versions(self, limit: int = 10) -> list[dict]:
        """Get simplified version list from git history.

        Returns commits with simple identifiers instead of full hashes.

        Args:
            limit: Maximum number of commits to return

        Returns:
            List of commit info dicts with keys: version, hash, message, date

        Raises:
            OSError: If git command fails
        """
        result = git_history(self.repo_path, max_count=limit, pretty="format:%H|%s|%ai")

        commits = []
        for line in result.strip().split('\n'):
            if line:
                hash_val, message, date = line.split('|', 2)
                commits.append({
                    'hash': hash_val,
                    'message': message,
                    'date': date
                })

        # Reverse so oldest commit is first (chronological order)
        commits.reverse()

        # Now assign version numbers: oldest = v1, newest = v<highest>
        for i, commit in enumerate(commits):
            commit['version'] = f"v{i + 1}"

        return commits

    def _resolve_version_to_commit(self, version: str) -> str:
        """Resolve a simple version identifier to a git commit hash.
        
        Args:
            repo_path: Path to git repository
            version: Version identifier (e.g., "v1", "v2")
            
        Returns:
            Full commit hash
            
        Raises:
            ValueError: If version doesn't exist
            OSError: If git command fails
        """
        # If it's already a commit hash, return as-is
        if len(version) >= 7 and all(c in '0123456789abcdef' for c in version.lower()):
            return version

        commits = self._get_commit_versions(limit=100)

        for commit in commits:
            if commit['version'] == version:
                return commit['hash']

        raise ValueError(f"Version '{version}' not found")

    def get_status(self, pyproject_manager: PyprojectManager | None = None) -> GitStatus:
        """Get complete git status with optional change parsing.
        
        Args:
            pyproject_manager: Optional PyprojectManager for parsing changes
            
        Returns:
            GitStatus with all git information encapsulated
        """
        # Get basic git information
        diff = self.get_pyproject_diff()
        workflow_changes = self.get_workflow_changes()
        has_changes = bool(diff.strip()) or bool(workflow_changes)

        # Create status object
        status = GitStatus(
            has_changes=has_changes,
            diff=diff,
            workflow_changes=workflow_changes
        )

        # Parse changes if we have them and a pyproject manager
        if has_changes and pyproject_manager:
            from ..utils.git_change_parser import GitChangeParser
            parser = GitChangeParser(self.repo_path)
            current_config = pyproject_manager.load()

            # The parser updates the status object directly
            parser.update_git_status(status, current_config)

        return status
