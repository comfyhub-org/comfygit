# Git Subdirectory Import Feature

## Executive Summary

**Goal:** Enable importing ComfyDock environments from subdirectories within git repositories.

**Use Case:** Custom node repositories with multiple example workflows stored in subdirectories:
```
github.com/user/my-custom-node
├── __init__.py              # Custom node code
├── requirements.txt
└── examples/                # Multiple workflow examples
    ├── example1/
    │   ├── pyproject.toml
    │   └── workflows/
    └── example2/
        ├── pyproject.toml
        └── workflows/
```

**Proposed Syntax:**
```bash
comfydock import https://github.com/user/repo#examples/example1
```

**Status:**
- ✅ Backend analysis complete
- ✅ Design decided (Option 3: `#subdirectory` syntax)
- ⏳ Implementation needed

## Current State Analysis

### How Git Import Works Today

**Entry Point:** `packages/cli/comfydock_cli/global_commands.py:262-277`
```python
if is_git:
    env = self.workspace.import_from_git(
        git_url=args.path,
        name=env_name,
        model_strategy=strategy,
        branch=getattr(args, 'branch', None),
        callbacks=CLIImportCallbacks()
    )
```

**Flow:**
1. **CLI** (`global_commands.py:262`) → Calls `workspace.import_from_git()`
2. **Workspace** (`core/workspace.py:382-441`) → Orchestrates import
3. **Factory** (`factories/environment_factory.py:221-288`) → Clones git repo
4. **Git Utils** (`utils/git.py:378-424`) → Executes `git clone`

### Current Limitations

**Problem 1: No URL Parsing for Subdirectories**
```python
# utils/git.py:110-119
def is_git_url(url: str) -> bool:
    return url.startswith(('https://', 'http://', 'git@', 'ssh://'))
```
- Doesn't extract subdirectory from URL
- Treats entire URL as git clone target

**Problem 2: Direct Clone to .cec/**
```python
# factories/environment_factory.py:268
git_clone(git_url, cec_path, ref=branch)
```
- Clones entire repo directly to `.cec/` directory
- No intermediate extraction step

**Problem 3: Root-Level Validation**
```python
# factories/environment_factory.py:272-276
pyproject_path = cec_path / "pyproject.toml"
if not pyproject_path.exists():
    raise ValueError(
        "Repository does not contain pyproject.toml - not a valid ComfyDock environment"
    )
```
- Expects `pyproject.toml` at repository root
- Fails if environment is in subdirectory

## Proposed Solution

### URL Syntax Convention

Use `#` to separate base repository URL from subdirectory path:

```bash
# Format: <git_url>#<subdirectory_path>

# Examples
comfydock import https://github.com/user/repo#examples/example1
comfydock import https://github.com/user/repo#examples/example1 --branch main
comfydock import git@github.com:user/repo.git#workflows/production
comfydock import --preview https://github.com/user/repo#examples/test
```

**Why `#` separator?**
- ✅ Valid URL fragment syntax
- ✅ Not used by git protocols
- ✅ Works with all git providers (GitHub, GitLab, Bitbucket)
- ✅ Easy to parse: `url.rsplit('#', 1)`
- ✅ Backward compatible (URLs without `#` work unchanged)

### Implementation Strategy

**Clone + Extract Pattern:**
1. Parse URL to separate base repo from subdirectory path
2. Clone entire repository to temporary directory
3. Validate subdirectory exists and contains `pyproject.toml`
4. Copy subdirectory contents to target `.cec/` directory
5. Clean up temporary clone

**Why not sparse checkout?**
- Sparse checkout is complex (requires multiple git commands)
- Not all git providers support it properly
- Clone-and-extract is simpler and more reliable for MVP
- Performance impact is acceptable (most repos are < 100MB)

## Implementation Plan

### Step 1: Add URL Parsing Utility

**File:** `packages/core/src/comfydock_core/utils/git.py`

**Location:** After `parse_github_url()` function (around line 205)

**Add new function:**
```python
def parse_git_url_with_subdir(url: str) -> tuple[str, str | None]:
    """Parse git URL with optional subdirectory specification.

    Supports syntax: <git_url>#<subdirectory_path>

    Examples:
        "https://github.com/user/repo"
        → ("https://github.com/user/repo", None)

        "https://github.com/user/repo#examples/example1"
        → ("https://github.com/user/repo", "examples/example1")

        "git@github.com:user/repo.git#workflows/prod"
        → ("git@github.com:user/repo.git", "workflows/prod")

    Args:
        url: Git URL with optional #subdirectory suffix

    Returns:
        Tuple of (base_git_url, subdirectory_path or None)
    """
    if '#' not in url:
        return url, None

    # Split on last # to handle edge cases like:
    # https://example.com/#anchor/path#subdir → keep base URL intact
    base_url, subdir = url.rsplit('#', 1)

    # Normalize subdirectory path
    subdir = subdir.strip('/')

    if not subdir:
        # URL ended with # but no path
        return base_url, None

    return base_url, subdir
```

**Add tests:** `packages/core/tests/unit/utils/test_git.py`

```python
def test_parse_git_url_with_subdir_no_subdir():
    url, subdir = parse_git_url_with_subdir("https://github.com/user/repo")
    assert url == "https://github.com/user/repo"
    assert subdir is None

def test_parse_git_url_with_subdir_with_subdir():
    url, subdir = parse_git_url_with_subdir("https://github.com/user/repo#examples/example1")
    assert url == "https://github.com/user/repo"
    assert subdir == "examples/example1"

def test_parse_git_url_with_subdir_ssh():
    url, subdir = parse_git_url_with_subdir("git@github.com:user/repo.git#workflows/prod")
    assert url == "git@github.com:user/repo.git"
    assert subdir == "workflows/prod"

def test_parse_git_url_with_subdir_normalizes_slashes():
    url, subdir = parse_git_url_with_subdir("https://github.com/user/repo#/examples/example1/")
    assert url == "https://github.com/user/repo"
    assert subdir == "examples/example1"

def test_parse_git_url_with_subdir_empty_after_hash():
    url, subdir = parse_git_url_with_subdir("https://github.com/user/repo#")
    assert url == "https://github.com/user/repo"
    assert subdir is None
```

### Step 2: Add Subdirectory Clone Helper

**File:** `packages/core/src/comfydock_core/utils/git.py`

**Location:** After `git_clone()` function (around line 425)

**Add new function:**
```python
def git_clone_subdirectory(
    url: str,
    target_path: Path,
    subdir: str,
    depth: int = 1,
    ref: str | None = None,
    timeout: int = 30,
) -> None:
    """Clone a git repository and extract a specific subdirectory.

    Clones the entire repository to a temporary location, validates
    the subdirectory exists, then copies only that subdirectory to
    the target path.

    Args:
        url: Git repository URL (without #subdir)
        target_path: Directory to extract subdirectory contents to
        subdir: Subdirectory path within repository (e.g., "examples/example1")
        depth: Clone depth (1 for shallow clone)
        ref: Optional specific ref (branch/tag/commit) to checkout
        timeout: Command timeout in seconds

    Raises:
        OSError: If git clone fails
        ValueError: If subdirectory doesn't exist in repository
    """
    import tempfile
    import shutil

    # Clone to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_repo = Path(temp_dir) / "repo"

        logger.info(f"Cloning {url} to temporary location for subdirectory extraction")
        git_clone(url, temp_repo, depth=depth, ref=ref, timeout=timeout)

        # Validate subdirectory exists
        subdir_path = temp_repo / subdir
        if not subdir_path.exists():
            raise ValueError(
                f"Subdirectory '{subdir}' does not exist in repository. "
                f"Available top-level directories: {', '.join(d.name for d in temp_repo.iterdir() if d.is_dir())}"
            )

        if not subdir_path.is_dir():
            raise ValueError(f"Path '{subdir}' exists but is not a directory")

        # Validate it's a ComfyDock environment
        pyproject_path = subdir_path / "pyproject.toml"
        if not pyproject_path.exists():
            raise ValueError(
                f"Subdirectory '{subdir}' does not contain pyproject.toml - "
                f"not a valid ComfyDock environment"
            )

        # Copy subdirectory contents to target
        logger.info(f"Extracting subdirectory '{subdir}' to {target_path}")
        shutil.copytree(subdir_path, target_path, dirs_exist_ok=True)

        logger.info(f"Successfully extracted {url}#{subdir} to {target_path}")
```

**Add tests:** `packages/core/tests/unit/utils/test_git.py`

```python
def test_git_clone_subdirectory_success(tmp_path, mock_git_repo_with_subdirs):
    """Test successful subdirectory clone."""
    target = tmp_path / "target"

    # Mock repo structure:
    # repo/
    #   examples/
    #     example1/
    #       pyproject.toml

    git_clone_subdirectory(
        url=mock_git_repo_with_subdirs,
        target_path=target,
        subdir="examples/example1"
    )

    assert (target / "pyproject.toml").exists()

def test_git_clone_subdirectory_not_found(tmp_path, mock_git_repo):
    """Test error when subdirectory doesn't exist."""
    target = tmp_path / "target"

    with pytest.raises(ValueError, match="Subdirectory 'nonexistent' does not exist"):
        git_clone_subdirectory(
            url=mock_git_repo,
            target_path=target,
            subdir="nonexistent"
        )

def test_git_clone_subdirectory_missing_pyproject(tmp_path, mock_git_repo_with_subdirs):
    """Test error when subdirectory lacks pyproject.toml."""
    target = tmp_path / "target"

    # Mock repo has subdirectory but no pyproject.toml
    with pytest.raises(ValueError, match="does not contain pyproject.toml"):
        git_clone_subdirectory(
            url=mock_git_repo_with_subdirs,
            target_path=target,
            subdir="examples/invalid"
        )
```

### Step 3: Update EnvironmentFactory.import_from_git()

**File:** `packages/core/src/comfydock_core/factories/environment_factory.py`

**Current code (lines 264-276):**
```python
# Clone repository to .cec
from ..utils.git import git_clone

git_clone(git_url, cec_path, ref=branch)
logger.info(f"Cloned {git_url} to {cec_path}")

# Validate it's a ComfyDock environment
pyproject_path = cec_path / "pyproject.toml"
if not pyproject_path.exists():
    raise ValueError(
        "Repository does not contain pyproject.toml - not a valid ComfyDock environment"
    )
```

**Replace with:**
```python
# Parse URL for subdirectory specification
from ..utils.git import git_clone, git_clone_subdirectory, parse_git_url_with_subdir

base_url, subdir = parse_git_url_with_subdir(git_url)

# Clone repository to .cec (with subdirectory extraction if specified)
if subdir:
    logger.info(f"Cloning {base_url} and extracting subdirectory '{subdir}' to {cec_path}")
    git_clone_subdirectory(base_url, cec_path, subdir, ref=branch)
    # Note: git_clone_subdirectory validates pyproject.toml internally
else:
    logger.info(f"Cloning {base_url} to {cec_path}")
    git_clone(base_url, cec_path, ref=branch)

    # Validate it's a ComfyDock environment (only for non-subdir imports)
    pyproject_path = cec_path / "pyproject.toml"
    if not pyproject_path.exists():
        raise ValueError(
            "Repository does not contain pyproject.toml - not a valid ComfyDock environment"
        )

logger.info(f"Successfully prepared environment from git")
```

**Changes:**
- Lines 266-268: Import new functions
- Lines 270-271: Parse URL to extract subdirectory
- Lines 273-284: Conditional clone logic based on subdirectory presence
- Line 286: Update success message

### Step 4: Update Workspace.preview_git_import()

**File:** `packages/core/src/comfydock_core/core/workspace.py`

**Current code (lines 293-319):**
```python
def preview_git_import(
    self,
    git_url: str,
    branch: str | None = None
):
    """Preview git import requirements without creating environment.

    Clones to temp directory, analyzes, then cleans up.

    Args:
        git_url: Git repository URL
        branch: Optional branch/tag/commit

    Returns:
        ImportAnalysis with full breakdown
    """
    import tempfile
    from ..utils.git import git_clone

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cec = Path(temp_dir) / ".cec"

        # Clone to temp location
        git_clone(git_url, temp_cec, ref=branch)

        # Analyze
        return self.import_analyzer.analyze_import(temp_cec)
```

**Replace with:**
```python
def preview_git_import(
    self,
    git_url: str,
    branch: str | None = None
):
    """Preview git import requirements without creating environment.

    Clones to temp directory, analyzes, then cleans up.
    Supports subdirectory syntax: <git_url>#<subdirectory>

    Args:
        git_url: Git repository URL (with optional #subdirectory)
        branch: Optional branch/tag/commit

    Returns:
        ImportAnalysis with full breakdown
    """
    import tempfile
    from ..utils.git import git_clone, git_clone_subdirectory, parse_git_url_with_subdir

    # Parse URL for subdirectory
    base_url, subdir = parse_git_url_with_subdir(git_url)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cec = Path(temp_dir) / ".cec"

        # Clone to temp location (with subdirectory extraction if specified)
        if subdir:
            git_clone_subdirectory(base_url, temp_cec, subdir, ref=branch)
        else:
            git_clone(base_url, temp_cec, ref=branch)

        # Analyze
        return self.import_analyzer.analyze_import(temp_cec)
```

**Changes:**
- Lines 306-308: Import new functions
- Lines 310-311: Parse URL
- Lines 316-319: Conditional clone based on subdirectory

### Step 5: Update CLI Help Text

**File:** `packages/cli/comfydock_cli/cli.py`

**Current code (line 97):**
```python
import_parser.add_argument("path", type=str, nargs="?", help="Path to .tar.gz file or git repository URL")
```

**Replace with:**
```python
import_parser.add_argument(
    "path",
    type=str,
    nargs="?",
    help="Path to .tar.gz file or git repository URL (use #subdirectory for subdirectory imports)"
)
```

**Add examples in help text:**

Consider adding a longer help description or examples section. This could be done by updating the import parser setup around line 96:

```python
# import - Import ComfyDock environment
import_parser = subparsers.add_parser(
    "import",
    help="Import ComfyDock environment from tarball or git repository",
    epilog="""
Examples:
  Import from tarball:
    comfydock import bundle.tar.gz

  Import from git repository:
    comfydock import https://github.com/user/repo

  Import from subdirectory:
    comfydock import https://github.com/user/repo#examples/example1

  Import with branch:
    comfydock import https://github.com/user/repo#examples/example1 --branch main

  Preview before importing:
    comfydock import --preview https://github.com/user/repo#examples/example1
    """,
    formatter_class=argparse.RawDescriptionHelpFormatter
)
```

### Step 6: Add Integration Test

**File:** `packages/core/tests/integration/test_git_subdirectory_import.py` (new file)

**Create comprehensive test:**
```python
"""Integration tests for git subdirectory import functionality."""
import tempfile
from pathlib import Path
import subprocess

import pytest

from comfydock_core.factories.workspace_factory import WorkspaceFactory


@pytest.fixture
def git_repo_with_subdirs(tmp_path):
    """Create a mock git repository with subdirectory structure."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

    # Create subdirectory structure
    examples = repo_path / "examples"
    examples.mkdir()

    example1 = examples / "example1"
    example1.mkdir()

    # Create pyproject.toml in example1
    pyproject = example1 / "pyproject.toml"
    pyproject.write_text("""
[tool.comfydock]
comfyui_version = "v0.2.7"
comfyui_version_type = "release"
    """)

    # Create workflows directory
    workflows = example1 / "workflows"
    workflows.mkdir()

    # Create example2 without pyproject.toml (for negative testing)
    example2 = examples / "example2"
    example2.mkdir()
    (example2 / "README.md").write_text("No pyproject here")

    # Commit everything
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

    return repo_path


def test_import_from_subdirectory(git_repo_with_subdirs, tmp_path):
    """Test importing from a subdirectory using # syntax."""
    workspace_path = tmp_path / "workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Create minimal registry data
    cache_dir = workspace_path / "comfydock_cache" / "custom_nodes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(cache_dir / "node_mappings.json", "w") as f:
        json.dump({"mappings": []}, f)

    # Import with subdirectory syntax
    git_url = f"{git_repo_with_subdirs}#examples/example1"
    env = workspace.import_from_git(
        git_url=git_url,
        name="test_env",
        model_strategy="skip"
    )

    # Verify environment was created
    assert env.path.exists()
    assert (env.path / ".cec" / "pyproject.toml").exists()
    assert (env.path / ".cec" / "workflows").exists()


def test_preview_subdirectory_import(git_repo_with_subdirs, tmp_path):
    """Test preview functionality with subdirectory syntax."""
    workspace_path = tmp_path / "workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Create minimal registry data
    cache_dir = workspace_path / "comfydock_cache" / "custom_nodes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(cache_dir / "node_mappings.json", "w") as f:
        json.dump({"mappings": []}, f)

    # Preview with subdirectory syntax
    git_url = f"{git_repo_with_subdirs}#examples/example1"
    analysis = workspace.preview_git_import(git_url)

    # Verify analysis returned
    assert analysis is not None
    assert analysis.comfyui_version == "v0.2.7"
    assert analysis.comfyui_version_type == "release"

    # Verify no environment was created
    envs = workspace.list_environments()
    assert len(envs) == 0


def test_import_subdirectory_not_found(git_repo_with_subdirs, tmp_path):
    """Test error when subdirectory doesn't exist."""
    workspace_path = tmp_path / "workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Create minimal registry data
    cache_dir = workspace_path / "comfydock_cache" / "custom_nodes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(cache_dir / "node_mappings.json", "w") as f:
        json.dump({"mappings": []}, f)

    # Try to import non-existent subdirectory
    git_url = f"{git_repo_with_subdirs}#nonexistent/path"

    with pytest.raises(ValueError, match="Subdirectory 'nonexistent/path' does not exist"):
        workspace.import_from_git(
            git_url=git_url,
            name="test_env",
            model_strategy="skip"
        )


def test_import_subdirectory_missing_pyproject(git_repo_with_subdirs, tmp_path):
    """Test error when subdirectory lacks pyproject.toml."""
    workspace_path = tmp_path / "workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Create minimal registry data
    cache_dir = workspace_path / "comfydock_cache" / "custom_nodes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(cache_dir / "node_mappings.json", "w") as f:
        json.dump({"mappings": []}, f)

    # Try to import subdirectory without pyproject.toml
    git_url = f"{git_repo_with_subdirs}#examples/example2"

    with pytest.raises(ValueError, match="does not contain pyproject.toml"):
        workspace.import_from_git(
            git_url=git_url,
            name="test_env",
            model_strategy="skip"
        )


def test_import_without_subdirectory_still_works(git_repo_with_subdirs, tmp_path):
    """Test that existing behavior (no subdirectory) still works."""
    workspace_path = tmp_path / "workspace"
    workspace = WorkspaceFactory.create(workspace_path)

    # Create minimal registry data
    cache_dir = workspace_path / "comfydock_cache" / "custom_nodes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import json
    with open(cache_dir / "node_mappings.json", "w") as f:
        json.dump({"mappings": []}, f)

    # Add pyproject.toml at root for backward compatibility test
    (git_repo_with_subdirs / "pyproject.toml").write_text("""
[tool.comfydock]
comfyui_version = "v0.3.0"
comfyui_version_type = "release"
    """)
    subprocess.run(["git", "add", "."], cwd=git_repo_with_subdirs, check=True)
    subprocess.run(["git", "commit", "-m", "Add root pyproject"], cwd=git_repo_with_subdirs, check=True)

    # Import without subdirectory (existing behavior)
    env = workspace.import_from_git(
        git_url=str(git_repo_with_subdirs),
        name="test_env",
        model_strategy="skip"
    )

    # Should import from root
    assert env.path.exists()
    assert (env.path / ".cec" / "pyproject.toml").exists()
```

## Edge Cases & Error Handling

### 1. Invalid Subdirectory Path

**Scenario:** User specifies subdirectory that doesn't exist
```bash
comfydock import https://github.com/user/repo#nonexistent/path
```

**Handling:**
```python
# In git_clone_subdirectory()
if not subdir_path.exists():
    raise ValueError(
        f"Subdirectory '{subdir}' does not exist in repository. "
        f"Available top-level directories: {', '.join(d.name for d in temp_repo.iterdir() if d.is_dir())}"
    )
```

**Error message:**
```
✗ Subdirectory 'nonexistent/path' does not exist in repository.
  Available top-level directories: examples, docs, tests
```

### 2. Subdirectory is a File

**Scenario:** Path exists but is a file, not a directory
```bash
comfydock import https://github.com/user/repo#README.md
```

**Handling:**
```python
if not subdir_path.is_dir():
    raise ValueError(f"Path '{subdir}' exists but is not a directory")
```

### 3. Subdirectory Without pyproject.toml

**Scenario:** Subdirectory exists but isn't a valid environment
```bash
comfydock import https://github.com/user/repo#examples/invalid
```

**Handling:**
```python
pyproject_path = subdir_path / "pyproject.toml"
if not pyproject_path.exists():
    raise ValueError(
        f"Subdirectory '{subdir}' does not contain pyproject.toml - "
        f"not a valid ComfyDock environment"
    )
```

### 4. Multiple # in URL

**Scenario:** URL contains multiple # characters
```bash
comfydock import https://example.com/#page#examples/example1
```

**Handling:**
```python
# Use rsplit('#', 1) to split on last # only
base_url, subdir = url.rsplit('#', 1)
# This preserves any # in the base URL
```

### 5. Empty Subdirectory After #

**Scenario:** URL ends with # but no path
```bash
comfydock import https://github.com/user/repo#
```

**Handling:**
```python
if not subdir:
    # Treat as no subdirectory specified
    return base_url, None
```

### 6. Trailing/Leading Slashes

**Scenario:** Subdirectory has inconsistent slashes
```bash
comfydock import https://github.com/user/repo#/examples/example1/
```

**Handling:**
```python
# Normalize subdirectory path
subdir = subdir.strip('/')
```

### 7. Nested Subdirectories

**Scenario:** Deep nesting
```bash
comfydock import https://github.com/user/repo#examples/workflows/production/version1
```

**Handling:** Should work naturally since we use `Path(repo) / subdir`

### 8. Preview with Subdirectory

**Scenario:** Preview mode with subdirectory
```bash
comfydock import --preview https://github.com/user/repo#examples/example1
```

**Handling:** Already implemented via `workspace.preview_git_import()` changes

### 9. Subdirectory with Branch

**Scenario:** Both subdirectory and branch specified
```bash
comfydock import https://github.com/user/repo#examples/example1 --branch v1.0
```

**Handling:** Should work - branch is passed separately to `git_clone_subdirectory()`

### 10. Large Repository Performance

**Scenario:** Repository is very large (>500MB)

**Mitigation:**
- Shallow clone (depth=1) helps
- Future optimization: Add sparse checkout option
- For now: Document that subdirectory imports clone full repo

## Usage Examples

### Basic Subdirectory Import

```bash
# Import from examples/basic subdirectory
comfydock import https://github.com/user/comfyui-workflows#examples/basic

# Output:
# 📦 Importing environment from git repository
#    URL: https://github.com/user/comfyui-workflows#examples/basic
#
# Environment name: basic-workflow
#
# 📋 Analyzing import...
#
# 📋 Import Preview
#
# ComfyUI: v0.2.7 (release)
# Workflows: 1 workflow(s)
# Custom Nodes: 2 node(s) (2 registry)
#
# Models:
#   • 3 total model(s)
#   • 1 already available ✓
#   • 2 need downloading
#
# Model download strategy:
#   [1] all      - Download 2 model(s)
#   [2] required - Download required models only
#   [3] skip     - Skip downloads (resolve later)
#
# Choice [1]/2/3: 1
#
# ✅ Import complete: basic-workflow
```

### Preview Subdirectory

```bash
comfydock import --preview https://github.com/user/custom-node#examples/advanced

# Output:
# 📋 Analyzing import...
#
# 📋 Import Preview
#
# ComfyUI: v0.3.0 (release)
# Workflows: 3 workflow(s)
# Custom Nodes: 5 node(s) (3 registry, 2 git)
#
# Models:
#   • 8 total model(s)
#   • 0 already available
#   • 6 need downloading
#   • 2 missing source ⚠️
#
# Preview complete - no import performed
```

### Subdirectory with Branch

```bash
comfydock import https://github.com/user/workflows#production/stable --branch v2.0 --name prod

# Imports from production/stable subdirectory on v2.0 branch
```

### Fast Path (No Preview)

```bash
comfydock import https://github.com/user/workflows#examples/test --name test --strategy skip

# Skips preview, uses 'skip' strategy directly
```

### SSH URLs

```bash
comfydock import git@github.com:user/workflows.git#examples/demo

# Works with SSH URLs too
```

## File Reference Summary

### Files to Modify

1. **`packages/core/src/comfydock_core/utils/git.py`**
   - Add `parse_git_url_with_subdir()` after line 205
   - Add `git_clone_subdirectory()` after line 425
   - ~100 new lines

2. **`packages/core/src/comfydock_core/factories/environment_factory.py`**
   - Modify `import_from_git()` method lines 264-276
   - Add subdirectory handling logic
   - ~15 lines changed

3. **`packages/core/src/comfydock_core/core/workspace.py`**
   - Modify `preview_git_import()` method lines 293-319
   - Add subdirectory handling
   - ~10 lines changed

4. **`packages/cli/comfydock_cli/cli.py`**
   - Update help text line 97
   - Optional: Add examples section
   - ~5-20 lines changed

### Files to Create

5. **`packages/core/tests/integration/test_git_subdirectory_import.py`** (new)
   - Comprehensive integration tests
   - ~200 lines

### Files to Update (Tests)

6. **`packages/core/tests/unit/utils/test_git.py`**
   - Add tests for `parse_git_url_with_subdir()`
   - Add tests for `git_clone_subdirectory()`
   - ~100 new lines

## Testing Plan

### Unit Tests

**File:** `packages/core/tests/unit/utils/test_git.py`

- ✅ `test_parse_git_url_with_subdir_no_subdir()`
- ✅ `test_parse_git_url_with_subdir_with_subdir()`
- ✅ `test_parse_git_url_with_subdir_ssh()`
- ✅ `test_parse_git_url_with_subdir_normalizes_slashes()`
- ✅ `test_parse_git_url_with_subdir_empty_after_hash()`
- ✅ `test_git_clone_subdirectory_success()`
- ✅ `test_git_clone_subdirectory_not_found()`
- ✅ `test_git_clone_subdirectory_missing_pyproject()`

### Integration Tests

**File:** `packages/core/tests/integration/test_git_subdirectory_import.py`

- ✅ `test_import_from_subdirectory()`
- ✅ `test_preview_subdirectory_import()`
- ✅ `test_import_subdirectory_not_found()`
- ✅ `test_import_subdirectory_missing_pyproject()`
- ✅ `test_import_without_subdirectory_still_works()` (backward compatibility)

### Manual Testing

```bash
# 1. Create test repository with subdirectories
mkdir test-repo && cd test-repo
git init
mkdir -p examples/example1 examples/example2
echo "[tool.comfydock]" > examples/example1/pyproject.toml
echo "comfyui_version = 'v0.2.7'" >> examples/example1/pyproject.toml
git add . && git commit -m "Initial"

# 2. Test local import
comfydock import $(pwd)#examples/example1 --name test1

# 3. Test preview
comfydock import --preview $(pwd)#examples/example1

# 4. Test error cases
comfydock import $(pwd)#nonexistent  # Should error

# 5. Test backward compatibility
echo "[tool.comfydock]" > pyproject.toml
echo "comfyui_version = 'v0.3.0'" >> pyproject.toml
git add . && git commit -m "Add root"
comfydock import $(pwd) --name test2  # Should work
```

## Success Criteria

### Functional Requirements

- [ ] Parse URLs with `#subdirectory` syntax correctly
- [ ] Clone repository and extract subdirectory to `.cec/`
- [ ] Validate subdirectory contains `pyproject.toml`
- [ ] Preview works with subdirectory syntax
- [ ] Error messages are helpful (show available directories)
- [ ] Backward compatibility: imports without `#` work unchanged
- [ ] Works with branches: `url#subdir --branch main`
- [ ] Works with SSH URLs: `git@github.com:user/repo.git#subdir`
- [ ] Temp directories are cleaned up properly

### UX Requirements

- [ ] Clear error messages for missing subdirectories
- [ ] Help text documents `#subdirectory` syntax
- [ ] Preview shows correct environment from subdirectory
- [ ] CLI output indicates subdirectory being imported
- [ ] Path normalization handles trailing slashes gracefully

### Code Quality

- [ ] No breaking changes to existing import flow
- [ ] Unit tests cover URL parsing and edge cases
- [ ] Integration tests cover end-to-end subdirectory imports
- [ ] All existing tests still pass (514 passed baseline)
- [ ] Code follows existing patterns in git.py and factories

## Timeline Estimate

- **Step 1** (URL parsing): 30 minutes
- **Step 2** (Clone helper): 45 minutes
- **Step 3** (Factory update): 20 minutes
- **Step 4** (Workspace preview): 15 minutes
- **Step 5** (CLI help): 10 minutes
- **Step 6** (Integration tests): 60 minutes
- **Unit tests**: 30 minutes
- **Manual testing**: 30 minutes
- **Edge cases & polish**: 30 minutes

**Total: ~4 hours**

## Future Enhancements

After initial implementation, consider:

### 1. Sparse Checkout Optimization

For very large repositories (>1GB), implement sparse checkout:

```python
def git_clone_subdirectory_sparse(url, target_path, subdir, ref):
    """Optimized sparse checkout for large repos."""
    # git clone --no-checkout --depth 1
    # git sparse-checkout init --cone
    # git sparse-checkout set <subdir>
    # git checkout <ref>
```

### 2. GitHub Tree URL Support

Parse GitHub-style URLs directly:
```bash
comfydock import https://github.com/user/repo/tree/main/examples/example1
```

### 3. Multiple Subdirectory Support

Allow importing multiple subdirectories:
```bash
comfydock import https://github.com/user/repo#examples/example1,examples/example2
```

### 4. List Available Subdirectories

Add discovery command:
```bash
comfydock import --list-subdirs https://github.com/user/repo
# Output:
# Available ComfyDock environments:
#   examples/example1
#   examples/example2
#   workflows/production
```

### 5. Subdirectory Caching

Cache cloned repositories to avoid re-downloading:
```bash
# First time: full clone
comfydock import https://github.com/user/repo#examples/example1

# Second time: use cached clone
comfydock import https://github.com/user/repo#examples/example2
```

## Alternative Approaches Considered

### Approach 1: Sparse Checkout (Rejected for MVP)

**Why rejected:**
- More complex implementation (5-6 git commands)
- Not all git providers support it properly
- Minimal performance benefit for typical repos (<100MB)
- Can be added later as optimization

### Approach 2: GitHub Tree URL Parsing (Rejected)

**Why rejected:**
- GitHub-specific (doesn't work for GitLab, Bitbucket)
- Conflicts with `--branch` flag semantics
- More complex regex parsing
- Less explicit than `#subdirectory` syntax

### Approach 3: Dedicated `--subdir` Flag (Rejected)

```bash
comfydock import https://github.com/user/repo --subdir examples/example1
```

**Why rejected:**
- More verbose than `#subdirectory`
- Separates path from URL (less intuitive)
- Doesn't work well with shell completion
- URL with `#` is self-contained and copyable

## References

- **Current Import Implementation:** `packages/core/src/comfydock_core/core/workspace.py:382-441`
- **Environment Factory:** `packages/core/src/comfydock_core/factories/environment_factory.py:221-288`
- **Git Utils:** `packages/core/src/comfydock_core/utils/git.py`
- **CLI Import Command:** `packages/cli/comfydock_cli/global_commands.py:149-292`
- **Existing Git Tests:** `packages/core/tests/integration/test_git_import.py`
- **Import Preview Design:** `packages/core/docs/plan/import-preview-cli-integration.md`
