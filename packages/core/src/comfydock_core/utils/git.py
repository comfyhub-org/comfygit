"""Low-level git utilities for repository operations."""

import re
import subprocess
from pathlib import Path

from comfydock_core.models.exceptions import CDProcessError

from ..logging.logging_config import get_logger
from .common import run_command

logger = get_logger(__name__)


# =============================================================================
# Error Handling Utilities
# =============================================================================

def _is_not_found_error(error: CDProcessError) -> bool:
    """Check if a git error indicates something doesn't exist.
    
    Args:
        error: The CDProcessError from a git command
        
    Returns:
        True if this is a "not found" type error
    """
    not_found_messages = [
        "does not exist",
        "invalid object",
        "bad revision",
        "path not in",
        "unknown revision",
        "not a valid object",
        "pathspec"
    ]
    error_text = ((error.stderr or "") + str(error)).lower()
    return any(msg in error_text for msg in not_found_messages)


def _git(cmd: list[str], repo_path: Path,
         check: bool = True,
         not_found_msg: str | None = None,
         capture_output: bool = True,
         text: bool = True) -> subprocess.CompletedProcess:
    """Run git command with consistent error handling.
    
    Args:
        cmd: Git command arguments (without 'git' prefix)
        repo_path: Path to git repository
        check: Whether to raise exception on non-zero exit
        not_found_msg: Custom message for "not found" errors
        capture_output: Whether to capture stdout/stderr
        text: Whether to return text output
        
    Returns:
        CompletedProcess result
        
    Raises:
        ValueError: For "not found" type errors
        OSError: For other git command failures
    """
    try:
        return run_command(
            ["git"] + cmd,
            cwd=repo_path,
            check=check,
            capture_output=capture_output,
            text=text
        )
    except CDProcessError as e:
        if _is_not_found_error(e):
            raise ValueError(not_found_msg or "Git object not found") from e
        raise OSError(f"Git command failed: {e}") from e

# =============================================================================
# Configuration Operations
# =============================================================================

def git_config_get(repo_path: Path, key: str) -> str | None:
    """Get a git config value.

    Args:
        repo_path: Path to git repository
        key: Config key (e.g., "user.name")

    Returns:
        Config value or None if not set
    """
    result = _git(["config", key], repo_path, check=False)
    return result.stdout.strip() if result.returncode == 0 else None

def git_config_set(repo_path: Path, key: str, value: str) -> None:
    """Set a git config value locally.

    Args:
        repo_path: Path to git repository
        key: Config key (e.g., "user.name")
        value: Value to set

    Raises:
        OSError: If git config command fails
    """
    _git(["config", key, value], repo_path)

# =============================================================================
# Repository Information
# =============================================================================

def parse_github_url(url: str) -> tuple[str, str, str | None] | None:
    """Parse GitHub URL to extract owner, repo name, and optional commit/ref.
    
    Args:
        url: GitHub repository URL
        
    Returns:
        Tuple of (owner, repo, commit) or None if invalid.
        commit will be None if no specific commit is specified.
    """
    # Handle URLs with commit/tree/blob paths like:
    # https://github.com/owner/repo/tree/commit-hash
    # https://github.com/owner/repo/commit/commit-hash
    github_match = re.match(
        r"(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/\.]+)(?:\.git)?(?:/(?:tree|commit|blob)/([^/]+))?",
        url,
    )
    if github_match:
        owner = github_match.group(1)
        repo = github_match.group(2)
        commit = github_match.group(3)  # Will be None if not present
        return (owner, repo, commit)
    return None

def git_rev_parse(repo_path: Path, ref: str = "HEAD", abbrev_ref: bool = False) -> str | None:
    """Parse a git reference to get its value.

    Args:
        repo_path: Path to git repository
        ref: Reference to parse (default: HEAD)
        abbrev_ref: If True, get abbreviated ref name

    Returns:
        Parsed reference value or None if command fails
    """
    cmd = ["rev-parse"]
    if abbrev_ref:
        cmd.append("--abbrev-ref")
    cmd.append(ref)

    result = _git(cmd, repo_path, check=False)
    return result.stdout.strip() if result.returncode == 0 else None

def git_describe_tags(repo_path: Path, exact_match: bool = False, abbrev: int | None = None) -> str | None:
    """Describe HEAD using tags.

    Args:
        repo_path: Path to git repository
        exact_match: If True, only exact tag match
        abbrev: If 0, only exact matches; if specified, abbreviate to N commits

    Returns:
        Tag description or None if no tags found
    """
    cmd = ["describe", "--tags"]
    if exact_match:
        cmd.append("--exact-match")
    if abbrev is not None:
        cmd.append(f"--abbrev={abbrev}")

    result = _git(cmd, repo_path, check=False)
    return result.stdout.strip() if result.returncode == 0 else None

def git_remote_get_url(repo_path: Path, remote: str = "origin") -> str | None:
    """Get URL of a git remote.

    Args:
        repo_path: Path to git repository
        remote: Remote name (default: origin)

    Returns:
        Remote URL or None if not found
    """
    result = _git(["remote", "get-url", remote], repo_path, check=False)
    return result.stdout.strip() if result.returncode == 0 else None

# =============================================================================
# Basic Git Operations
# =============================================================================

def git_init(repo_path: Path) -> None:
    """Initialize a git repository.
    
    Args:
        repo_path: Path to initialize as git repository
        
    Raises:
        OSError: If git initialization fails
    """
    _git(["init"], repo_path)

def git_diff(repo_path: Path, file_path: Path) -> str:
    """Get git diff for a specific file.
    
    Args:
        repo_path: Path to git repository
        file_path: Path to file to diff
        
    Returns:
        Git diff output as string
        
    Raises:
        OSError: If git diff command fails
    """
    result = _git(["diff", str(file_path)], repo_path)
    return result.stdout

def git_commit(repo_path: Path, message: str, add_all: bool = True) -> None:
    """Commit changes with optional staging.
    
    Args:
        repo_path: Path to git repository
        message: Commit message
        add_all: Whether to stage all changes first
        
    Raises:
        OSError: If git commands fail
    """
    if add_all:
        _git(["add", "."], repo_path)
    _git(["commit", "-m", message], repo_path)

# =============================================================================
# Advanced Git Operations
# =============================================================================

def git_show(repo_path: Path, ref: str, file_path: Path, is_text: bool = True) -> str:
    """Show file content from a specific git ref.
    
    Args:
        repo_path: Path to git repository
        ref: Git reference (commit, branch, tag)
        file_path: Path to file to show
        is_text: Whether to treat file as text
        
    Returns:
        File content as string
        
    Raises:
        OSError: If git show command fails
        ValueError: If ref or file doesn't exist
    """
    cmd = ["show", f"{ref}:{file_path}"]
    if is_text:
        cmd.append("--text")
    result = _git(cmd, repo_path, not_found_msg=f"Git ref '{ref}' or file '{file_path}' does not exist")
    return result.stdout


def git_history(
    repo_path: Path,
    file_path: Path | None = None,
    pretty: str | None = None,
    max_count: int | None = None,
    follow: bool = False,
    oneline: bool = False,
) -> str:
    """Get git history for a specific file.

    Args:
        repo_path: Path to git repository
        file_path: Path to file to get history for
        oneline: Whether to show one-line format
        follow: Whether to follow renames
        max_count: Maximum number of commits to return
        pretty: Git pretty format

    Returns:
        Git log output as string

    Raises:
        OSError: If git log command fails
    """
    cmd = ["log"]
    if follow:
        cmd.append("--follow")
    if oneline:
        cmd.append("--oneline")
    if max_count:
        cmd.append(f"--max-count={max_count}")
    if pretty:
        cmd.append(f"--pretty={pretty}")
    if file_path:
        cmd.append("--")
        cmd.append(str(file_path))
    result = _git(cmd, repo_path)
    return result.stdout


def git_clone(
    url: str,
    target_path: Path,
    depth: int = 1,
    ref: str | None = None,
    timeout: int = 30,
) -> None:
    """Clone a git repository to a target path.

    Args:
        url: Git repository URL
        target_path: Directory to clone to
        depth: Clone depth (1 for shallow clone)
        ref: Optional specific ref (branch/tag/commit) to checkout
        timeout: Command timeout in seconds
        
    Raises:
        OSError: If git clone or checkout fails
        ValueError: If URL is invalid or ref doesn't exist
    """
    # Build clone command
    cmd = ["clone"]

    # For commit hashes, we need to clone without --depth and then checkout
    # For branches/tags, we can use --branch with depth
    is_commit_hash = ref and len(ref) == 40 and all(c in '0123456789abcdef' for c in ref.lower())

    if depth > 0 and not is_commit_hash:
        cmd.extend(["--depth", str(depth)])

    if ref and not is_commit_hash and not ref.startswith("refs/"):
        # If a specific branch/tag is requested, clone it directly
        cmd.extend(["--branch", ref])

    cmd.extend([url, str(target_path)])

    # Execute clone
    _git(cmd, Path.cwd(), not_found_msg=f"Git repository URL '{url}' does not exist")

    # If a specific commit hash was requested, checkout to it
    if is_commit_hash and ref:
        _git(["checkout", ref], target_path, not_found_msg=f"Commit '{ref}' does not exist")
    elif ref and ref.startswith("refs/"):
        # Handle refs/ style references
        _git(["checkout", ref], target_path, not_found_msg=f"Reference '{ref}' does not exist")

    logger.info(f"Successfully cloned {url} to {target_path}")

def git_checkout(repo_path: Path,
                target: str = "HEAD",
                files: list[str] | None = None,
                unstage: bool = False) -> None:
    """Universal checkout function for commits, branches, or specific files.
    
    Args:
        repo_path: Path to git repository
        target: What to checkout (commit, branch, tag)
        files: Specific files to checkout (None for all)
        unstage: Whether to unstage files after checkout
        
    Raises:
        OSError: If git command fails
        ValueError: If target doesn't exist
    """
    cmd = ["checkout", target]
    if files:
        cmd.extend(["--"] + files)

    _git(cmd, repo_path, not_found_msg=f"Git target '{target}' does not exist")

    # Optionally unstage files to leave them as uncommitted changes
    if unstage and files:
        _git(["reset", "HEAD"] + files, repo_path)
    elif unstage and not files:
        _git(["reset", "HEAD", "."], repo_path)

# =============================================================================
# Status & Change Tracking
# =============================================================================

def git_status_porcelain(repo_path: Path) -> list[tuple[str, str, str]]:
    """Get git status in porcelain format, parsed.

    Args:
        repo_path: Path to git repository

    Returns:
        List of tuples: (index_status, working_status, filename)
        Status characters follow git's convention:
        - 'M' = modified, 'A' = added, 'D' = deleted
        - '?' = untracked, ' ' = unmodified
    """
    result = _git(["status", "--porcelain"], repo_path)
    entries = []

    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            if line and len(line) >= 3:
                index_status = line[0]
                working_status = line[1]
                filename = line[2:].lstrip()

                # Handle quoted filenames (spaces/special chars)
                if filename.startswith('"') and filename.endswith('"'):
                    filename = filename[1:-1].encode().decode('unicode_escape')

                entries.append((index_status, working_status, filename))

    return entries

def get_staged_changes(repo_path: Path) -> list[str]:
    """Get list of files that are staged (git added) but not committed.
    
    Args:
        repo_path: Path to the git repository
        
    Returns:
        List of file paths that are staged
        
    Raises:
        OSError: If git command fails
    """
    result = _git(["diff", "--cached", "--name-only"], repo_path)

    if result.stdout:
        return result.stdout.strip().split('\n')

    return []


def get_uncommitted_changes(repo_path: Path) -> list[str]:
    """Get list of files that have uncommitted changes (staged or unstaged).

    Args:
        repo_path: Path to the git repository

    Returns:
        List of file paths with uncommitted changes

    Raises:
        OSError: If git command fails
    """
    result = _git(["status", "--porcelain"], repo_path)

    if result.stdout:
        changes = []
        for line in result.stdout.strip().split('\n'):
            if line and len(line) >= 3:
                # Git status --porcelain format: "XY filename"
                # X = index status, Y = working tree status
                # But the spacing varies based on content:
                # "M  filename" = staged (M + space + space + filename)
                # " M filename" = unstaged (space + M + space + filename)
                # "MM filename" = both staged and unstaged

                # The first 2 characters are always status flags
                # Everything after position 2 contains spaces + filename
                remaining = line[2:]    # Everything after status characters

                # Skip any leading whitespace to get to filename
                filename = remaining.lstrip()
                if filename:  # Make sure filename is not empty
                    changes.append(filename)
        return changes

    return []

def git_ls_tree(repo_path: Path, ref: str, recursive: bool = False) -> str:
    """List files in a git tree object.

    Args:
        repo_path: Path to git repository
        ref: Git reference (commit, branch, tag)
        recursive: If True, recursively list all files

    Returns:
        Output with file paths, one per line

    Raises:
        OSError: If git command fails
        ValueError: If ref doesn't exist
    """
    cmd = ["ls-tree"]
    if recursive:
        cmd.append("-r")
    cmd.extend(["--name-only", ref])

    result = _git(cmd, repo_path, not_found_msg=f"Git ref '{ref}' does not exist")
    return result.stdout

def git_ls_files(repo_path: Path) -> str:
    """List all files tracked by git in the current working tree.

    Args:
        repo_path: Path to git repository

    Returns:
        Output with file paths, one per line

    Raises:
        OSError: If git command fails
    """
    result = _git(["ls-files"], repo_path)
    return result.stdout
