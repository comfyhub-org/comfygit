# Git-Based Import Implementation Plan

**Feature**: Enable `comfydock import <git-url>` to import environments directly from Git repositories

**Status**: Planning
**Priority**: High (MVP feature)
**Effort**: 1-2 days
**Created**: 2025-01-20

## Overview

Enable users to share ComfyUI environments via Git repositories instead of tarballs. Developers push their `.cec/` directory to GitHub, users run `comfydock import <url>` to create a new environment.

### User Flow

**Developer (sharing workflow):**
```bash
cd my-env/.cec
git init
git add .
git commit -m "My amazing workflow v1.0"
git remote add origin https://github.com/me/workflow.git
git push
```

**User (consuming workflow):**
```bash
comfydock import https://github.com/me/workflow.git

# Later, get updates as new environment
comfydock import https://github.com/me/workflow.git --name workflow-v2
```

### Key Design Decisions

1. **Each import creates a NEW environment** (no in-place updates/merging for MVP)
2. **manifest.json is OPTIONAL** (not required for git imports)
3. **Git history not preserved** (fresh git init in new environment)
4. **Shallow clones** (--depth 1 for speed)

## Current State Analysis

### Export Flow
@packages/core/src/comfydock_core/core/environment.py#L824-913

The export process:
1. Validates environment (L845-858): uncommitted changes, unresolved workflows
2. Gathers metadata (L874-908): workflows, models, nodes, python version
3. Creates ExportManifest in-memory (L897-908)
4. Calls ExportImportManager.create_export (L911-912)

**Issue**: manifest.json is created IN-MEMORY and added to tarball only
@packages/core/src/comfydock_core/managers/export_import_manager.py#L92-96

```python
manifest_data = json.dumps(manifest.to_dict(), indent=2).encode()
manifest_info = tarfile.TarInfo(name="manifest.json")  # Only in tarball!
tar.addfile(manifest_info, fileobj=io.BytesIO(manifest_data))
```

It's NEVER written to disk in .cec/ directory.

### Import Flow

**Entry point:**
@packages/core/src/comfydock_core/core/workspace.py#L260-313

Workspace.import_environment() → EnvironmentFactory.import_from_bundle()

**Factory method:**
@packages/core/src/comfydock_core/factories/environment_factory.py#L115-181

Flow:
1. Extract tarball to .cec (L155-157)
2. Create Environment object (L162-170)
3. Run import orchestration (L173-178)

**Import orchestration:**
@packages/core/src/comfydock_core/managers/export_import_manager.py#L189-341

The import_bundle() method has 6 phases:
- **Phase 0** (L217-221): Read manifest.json - **HARD REQUIREMENT** (raises ValueError if missing)
- **Phase 1** (L241-251): Clone ComfyUI (uses manifest.comfyui_version as fallback)
- **Phase 2** (L253-257): Install dependencies from pyproject.toml
- **Phase 3** (L259-263): Initialize NEW git repo (would conflict with cloned repo)
- **Phase 4** (L265-277): Copy workflows from .cec/workflows/ to ComfyUI/user/default/workflows/
- **Phase 5** (L279-293): Sync nodes from pyproject.toml
- **Phase 6** (L295-338): Resolve models with download strategy

**CLI:**
@packages/cli/comfydock_cli/global_commands.py#L149-272

The import_env() command:
1. Gets tarball path from args (L159)
2. Extracts manifest for preview (L236-246) - **Shows metadata before importing**
3. Calls workspace.import_environment() (L252-257)
4. Displays success message (L259-267)

### Manifest Usage Analysis

**ExportManifest structure:**
@packages/core/src/comfydock_core/managers/export_import_manager.py#L21-62

Fields:
- timestamp, comfydock_version, environment_name
- workflows, python_version, comfyui_version
- platform, total_models, total_nodes, dev_nodes

**Actual usage during import:**
- ✅ **comfyui_version** (L230, L236): Used as FALLBACK if not in pyproject.toml
- ✅ **Logging** (L243): For user feedback
- ❌ **Everything else**: NOT used during import (timestamp, environment_name, workflows, python_version, platform, counts, dev_nodes)

**Dev nodes issue:**
@packages/core/src/comfydock_core/managers/export_import_manager.py#L119-127

Dev nodes are bundled into tarball under `dev_nodes/`, but there's **NO CODE** to restore them during import. This is a bug/missing feature.

### Git Utilities Available

**Git clone:**
@packages/core/src/comfydock_core/utils/git.py#L1-75

Utilities available:
- `git_clone()` - Clone repository with optional depth, ref
- `git_init()` - Initialize repository
- `is_git_url()` - URL validation (need to check if this exists)

**Git operations:**
@packages/core/src/comfydock_core/managers/git_manager.py#L132-158

GitManager.initialize_environment_repo():
1. git_init()
2. ensure_git_identity()
3. create .gitignore
4. Initial commit

**Issue**: Will fail if .git already exists (from git clone)

## Required Changes

### 1. Make manifest.json Optional in Import

**File**: @packages/core/src/comfydock_core/managers/export_import_manager.py#L217-221

**Current code:**
```python
# Extract bundle (already done during env creation, but we need the manifest)
manifest_path = env.cec_path / "manifest.json"
if not manifest_path.exists():
    raise ValueError("Invalid import state: manifest.json not found in .cec")

manifest = ExportManifest.from_dict(json.loads(manifest_path.read_text()))
```

**Change to:**
```python
# Read manifest if it exists (tarballs have it, git imports may not)
manifest_path = env.cec_path / "manifest.json"
manifest = None

if manifest_path.exists():
    manifest = ExportManifest.from_dict(json.loads(manifest_path.read_text()))
    logger.debug("Using manifest.json for import metadata")
else:
    logger.info("No manifest.json found - proceeding with git-style import")
```

**Also update L230-236** to handle None manifest:
```python
# Determine ComfyUI version to clone
comfyui_version = None
try:
    pyproject_data = env.pyproject.load()
    comfydock_config = pyproject_data.get("tool", {}).get("comfydock", {})
    comfyui_version = comfydock_config.get("comfyui_commit_sha") or comfydock_config.get("comfyui_version")
except Exception as e:
    logger.warning(f"Could not read comfyui_version from pyproject.toml: {e}")

# Fallback to manifest only if it exists
if not comfyui_version and manifest:
    comfyui_version = manifest.comfyui_version
    logger.debug(f"Using comfyui_version from manifest: {comfyui_version}")
```

**And L263** (commit message):
```python
source_desc = tarball_path.name if tarball_path else "git repository"
env.git_manager.initialize_environment_repo(f"Imported from {source_desc}")
```

**And return statement L341** - manifest may be None, which is fine (return value is unused anyway).

### 2. Create Git Import Factory Method

**File**: @packages/core/src/comfydock_core/factories/environment_factory.py#L182 (after import_from_bundle)

**Add new method:**
```python
@staticmethod
def import_from_git(
    git_url: str,
    name: str,
    env_path: Path,
    workspace_paths: "WorkspacePaths",
    model_repository: "ModelRepository",
    node_mapping_repository: "NodeMappingsRepository",
    workspace_config_manager: "WorkspaceConfigRepository",
    model_downloader: "ModelDownloader",
    model_strategy: str = "all",
    branch: str | None = None,
    callbacks: "ImportCallbacks | None" = None
) -> Environment:
    """Import environment from git repository.

    Args:
        git_url: Git repository URL (https:// or git@)
        name: Name for imported environment
        env_path: Path where environment will be created
        workspace_paths: Workspace paths
        model_repository: Model repository
        node_mapping_repository: Node mapping repository
        workspace_config_manager: Workspace config manager
        model_downloader: Model downloader
        model_strategy: "all", "required", or "skip"
        branch: Optional branch/tag/commit to clone
        callbacks: Optional callbacks for progress updates

    Returns:
        Environment

    Raises:
        CDEnvironmentExistsError: If environment path exists
        ValueError: If repository is invalid or doesn't contain .cec structure
    """
    from ..utils.git import git_clone
    import tempfile
    import shutil

    if env_path.exists():
        raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

    # Clone repository to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        logger.info(f"Cloning repository: {git_url}")
        if callbacks:
            callbacks.on_phase("clone_repo", f"Cloning {git_url}...")

        try:
            git_clone(
                git_url,
                temp_path,
                depth=1,  # Shallow clone for speed
                ref=branch,
                timeout=300
            )
        except Exception as e:
            raise ValueError(f"Failed to clone repository: {e}")

        # Verify this is a ComfyDock environment repository
        # Check for essential files (manifest.json is optional now)
        pyproject_path = temp_path / "pyproject.toml"
        if not pyproject_path.exists():
            raise ValueError(
                f"Repository doesn't appear to be a ComfyDock environment.\n"
                f"Missing pyproject.toml. Expected a .cec directory structure."
            )

        # Create environment directory and copy files
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"

        logger.info(f"Copying repository contents to {cec_path}")
        shutil.copytree(temp_path, cec_path)

    # Create Environment object
    env = Environment(
        name=name,
        path=env_path,
        workspace_paths=workspace_paths,
        model_repository=model_repository,
        node_mapping_repository=node_mapping_repository,
        workspace_config_manager=workspace_config_manager,
        model_downloader=model_downloader,
    )

    # Run import orchestration (without tarball)
    from ..managers.export_import_manager import ExportImportManager
    manager = ExportImportManager(cec_path, env_path / "ComfyUI")
    manager.import_bundle(
        env=env,
        tarball_path=None,  # No tarball for git imports
        model_strategy=model_strategy,
        callbacks=callbacks
    )

    logger.info(f"Environment '{name}' imported from git successfully")
    return env
```

### 3. Add Workspace Git Import Method

**File**: @packages/core/src/comfydock_core/core/workspace.py#L313 (after import_environment)

**Add new method:**
```python
def import_from_git(
    self,
    git_url: str,
    name: str,
    model_strategy: str = "all",
    branch: str | None = None,
    callbacks: "ImportCallbacks | None" = None
) -> Environment:
    """Import environment from git repository.

    Args:
        git_url: Git repository URL
        name: Name for imported environment
        model_strategy: "all", "required", or "skip"
        branch: Optional branch/tag/commit
        callbacks: Optional callbacks for progress updates

    Returns:
        Environment

    Raises:
        CDEnvironmentExistsError: If environment already exists
        ValueError: If repository is invalid
    """
    env_path = self.paths.environments / name

    if env_path.exists():
        raise CDEnvironmentExistsError(f"Environment '{name}' already exists")

    try:
        environment = EnvironmentFactory.import_from_git(
            git_url=git_url,
            name=name,
            env_path=env_path,
            workspace_paths=self.paths,
            model_repository=self.model_index_manager,
            node_mapping_repository=self.node_mapping_repository,
            workspace_config_manager=self.workspace_config_manager,
            model_downloader=self.model_downloader,
            model_strategy=model_strategy,
            branch=branch,
            callbacks=callbacks
        )

        return environment

    except Exception as e:
        logger.error(f"Failed to import from git: {e}")
        if env_path.exists():
            logger.debug(f"Cleaning up partial environment at {env_path}")
            shutil.rmtree(env_path, ignore_errors=True)

        if isinstance(e, ComfyDockError):
            raise
        else:
            raise RuntimeError(f"Failed to import environment '{name}': {e}") from e
```

### 4. Update CLI to Handle Git URLs

**File**: @packages/cli/comfydock_cli/global_commands.py#L149-272

**Modify import_env method:**

Add URL detection at the beginning (after L163):
```python
from pathlib import Path

# Detect if this is a git URL or local tarball
is_git = args.path.startswith(('https://', 'git@', 'git://'))

if is_git:
    git_url = args.path
    tarball_path = None
else:
    tarball_path = Path(args.path)
    if not tarball_path.exists():
        print(f"✗ File not found: {tarball_path}")
        return 1
    git_url = None
```

**Modify preview section (L235-250):**

```python
if git_url:
    # Git import - show URL, skip preview (no manifest yet)
    print(f"📦 Importing from git repository")
    print(f"   URL: {git_url}")
    if hasattr(args, 'branch') and args.branch:
        print(f"   Branch/Tag: {args.branch}")
else:
    # Tarball import - extract and show manifest
    import json
    import tarfile

    with tarfile.open(tarball_path, "r:gz") as tar:
        manifest_member = tar.getmember("manifest.json")
        manifest_file = tar.extractfile(manifest_member)
        if not manifest_file:
            raise ValueError("Invalid tarball: manifest.json is empty")
        manifest_data = json.loads(manifest_file.read())

    print(f"✅ Extracted environment: {manifest_data['environment_name']}")
    print(f"   • {len(manifest_data['workflows'])} workflows")
    print(f"   • {manifest_data['total_nodes']} nodes")
    print(f"   • {manifest_data['total_models']} models")
```

**Modify import call (L252-257):**

```python
if git_url:
    env = self.workspace.import_from_git(
        git_url=git_url,
        name=env_name,
        model_strategy=strategy,
        branch=getattr(args, 'branch', None),
        callbacks=CLIImportCallbacks()
    )
else:
    env = self.workspace.import_environment(
        tarball_path=tarball_path,
        name=env_name,
        model_strategy=strategy,
        callbacks=CLIImportCallbacks()
    )
```

**Add CLI argument for branch** (in the argparser setup, not shown in context but needed):
```python
parser.add_argument('--branch', '-b', help='Git branch, tag, or commit to import')
```

### 5. Verify Git Utilities Exist

**Check if these exist:**
@packages/core/src/comfydock_core/utils/git.py

Needed functions:
- `git_clone(url, target, depth, ref, timeout)` - Should exist
- `is_git_url(url)` - May need to add

**If is_git_url doesn't exist, add:**
```python
def is_git_url(url: str) -> bool:
    """Check if a string is a git URL.

    Args:
        url: String to check

    Returns:
        True if this looks like a git URL
    """
    return url.startswith(('https://', 'git@', 'git://'))
```

## Implementation Order

1. **Phase 1: Make manifest.json optional** (lowest risk)
   - Modify import_bundle to handle None manifest
   - Test with existing tarball imports (should work unchanged)
   - Test by manually removing manifest.json from extracted tarball

2. **Phase 2: Add git import factory method**
   - Implement EnvironmentFactory.import_from_git
   - Add Workspace.import_from_git wrapper
   - Test with manual git clone + import

3. **Phase 3: Update CLI**
   - Add git URL detection
   - Add branch argument
   - Route to appropriate import method
   - Update help text

4. **Phase 4: Testing & polish**
   - Integration tests
   - Error handling
   - Documentation

## Testing Strategy

### Unit Tests

**Test manifest.json optional:**
@packages/core/tests/integration/test_export_import.py#L67-114

Add test case:
```python
def test_import_without_manifest(self, tmp_path):
    """Test that import works without manifest.json (git import scenario)."""
    # Create .cec structure without manifest.json
    source_cec = tmp_path / "source"
    source_cec.mkdir()

    # Create required files
    (source_cec / "pyproject.toml").write_text('''
[project]
name = "test-env"
version = "0.1.0"

[tool.comfydock]
comfyui_version = "v0.2.0"
''')

    (source_cec / ".python-version").write_text("3.12\n")

    workflows = source_cec / "workflows"
    workflows.mkdir()
    (workflows / "test.json").write_text('{"nodes": []}')

    # Copy to target and import (simulating git clone result)
    target_cec = tmp_path / "target" / ".cec"
    shutil.copytree(source_cec, target_cec)

    # Import should work without manifest.json
    env = Environment(...)
    manager = ExportImportManager(target_cec, tmp_path / "target" / "ComfyUI")

    # Should NOT raise ValueError about missing manifest
    result = manager.import_bundle(env, tarball_path=None, model_strategy="skip")

    assert result is not None  # Returns None manifest, which is ok
```

**Test git import:**
```python
def test_import_from_git(test_workspace, tmp_path):
    """Test importing from a git repository."""
    # Create a mock git repo with .cec structure
    git_repo = tmp_path / "mock-repo"
    git_repo.mkdir()

    # Create .cec structure
    (git_repo / "pyproject.toml").write_text('[project]\nname = "git-test"')
    (git_repo / ".python-version").write_text("3.12\n")
    workflows = git_repo / "workflows"
    workflows.mkdir()
    (workflows / "test.json").write_text('{}')

    # Initialize as git repo
    subprocess.run(["git", "init"], cwd=git_repo)
    subprocess.run(["git", "add", "."], cwd=git_repo)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=git_repo)

    # Import from local git path
    env = test_workspace.import_from_git(
        git_url=str(git_repo),
        name="test-git-import",
        model_strategy="skip"
    )

    assert env.name == "test-git-import"
    assert env.cec_path.exists()
    assert (env.cec_path / "pyproject.toml").exists()
    assert (env.cec_path / "workflows" / "test.json").exists()
```

### Manual Testing

1. **Tarball import** (verify no regression):
   ```bash
   comfydock export
   comfydock import my-env_export_20250120.tar.gz --name test-tarball
   ```

2. **Git import** (happy path):
   ```bash
   comfydock import https://github.com/user/workflow.git --name test-git
   ```

3. **Git import with branch**:
   ```bash
   comfydock import https://github.com/user/workflow.git --branch v1.0 --name test-v1
   ```

4. **Git import with private repo** (SSH):
   ```bash
   comfydock import git@github.com:user/private-workflow.git --name test-private
   ```

5. **Error cases**:
   - Invalid git URL
   - Repository without pyproject.toml
   - Network error during clone
   - Duplicate environment name

## Edge Cases & Considerations

### 1. Git Already Initialized in .cec

**Current behavior:**
@packages/core/src/comfydock_core/managers/git_manager.py#L146-148

```python
# Initialize git repository
git_init(self.repo_path)
```

This will fail if .git already exists.

**Solution:**
Since we're cloning to temp and copying files (not the .git directory), this shouldn't be an issue. The shutil.copytree in import_from_git should copy files but not .git metadata.

**Verify**: Test that .git directory is NOT copied during shutil.copytree.

If it is copied, explicitly exclude it:
```python
def ignore_git(dir, files):
    return ['.git'] if '.git' in files else []

shutil.copytree(temp_path, cec_path, ignore=ignore_git)
```

### 2. Large Repositories

**Issue**: Some workflows might have large dev_nodes directories

**Solution**:
- Use shallow clone (--depth 1)
- Consider adding progress callback for clone operation
- Document recommended .gitignore patterns

### 3. Dev Nodes Restoration

**Current bug**: Dev nodes bundled but not restored
@packages/core/src/comfydock_core/managers/export_import_manager.py#L119-127

**For MVP**: Document this limitation
**Future**: Add dev_nodes restoration logic before Phase 5

### 4. Private Repositories

**SSH vs HTTPS authentication**:
- SSH: Use user's configured keys
- HTTPS: Git credential manager
- No special handling needed (git clone handles it)

**Document**: Users need git credentials configured

### 5. Submodules

**Issue**: If .cec repo has submodules

**Solution for MVP**: Don't support (fail with clear error)
**Future**: Add `--recursive` flag support

## Documentation Updates

### README.md

Add section:
```markdown
## Sharing Environments via Git

ComfyDock environments can be shared through Git repositories:

### As a Developer

1. Prepare your environment:
   ```bash
   # Ensure workflows are committed
   comfydock commit -m "Finalize workflow v1.0"
   ```

2. Share the .cec directory:
   ```bash
   cd my-env/.cec
   git init
   git add .
   git commit -m "Release v1.0"
   git remote add origin https://github.com/you/workflow.git
   git push -u origin main
   ```

3. Share the URL with users!

### As a User

Import any shared environment:
```bash
comfydock import https://github.com/user/amazing-workflow.git
```

Get updates (creates new environment):
```bash
comfydock import https://github.com/user/amazing-workflow.git --name workflow-v2
```

Specify branch or tag:
```bash
comfydock import https://github.com/user/workflow.git --branch v1.0.0
```
```

### CLI Help Text

Update `comfydock import --help`:
```
usage: comfydock import <path-or-url> [options]

Import a ComfyDock environment from a tarball or git repository.

positional arguments:
  path                  Path to .tar.gz file OR git repository URL

optional arguments:
  -h, --help           show this help message and exit
  --name NAME          Name for the imported environment
  -b, --branch BRANCH  Git branch, tag, or commit to import (git imports only)
  --use               Set as active environment after import

examples:
  comfydock import my-env_export_20250120.tar.gz
  comfydock import https://github.com/user/workflow.git
  comfydock import https://github.com/user/workflow.git --branch v1.0
  comfydock import git@github.com:user/private.git --name my-private-env
```

## Success Metrics

- ✅ Tarball imports still work (no regression)
- ✅ Git imports work with public repos (HTTPS)
- ✅ Git imports work with private repos (SSH)
- ✅ Branch/tag selection works
- ✅ Error messages are clear
- ✅ Performance acceptable (< 30s for typical import)

## Future Enhancements (Out of Scope for MVP)

1. **Update existing environments** (git pull + merge)
2. **Version tracking** (list available tags, show what's new)
3. **Submodule support** (for complex workflows)
4. **Partial imports** (workflows only, no models)
5. **Import from local git repos** (file:// URLs)
6. **Watch for updates** (notify when upstream changes)
7. **Fork workflows** (create derivative with attribution)

## References

Key files to understand:
- @packages/core/src/comfydock_core/managers/export_import_manager.py - Core import/export logic
- @packages/core/src/comfydock_core/factories/environment_factory.py - Environment creation patterns
- @packages/core/src/comfydock_core/core/workspace.py - Workspace-level operations
- @packages/cli/comfydock_cli/global_commands.py - CLI interface
- @packages/core/src/comfydock_core/utils/git.py - Git utilities
- @packages/core/src/comfydock_core/managers/git_manager.py - Git repository management
- @packages/core/tests/integration/test_export_import.py - Existing import/export tests

## Implementation Checklist

- [ ] Make manifest.json optional in import_bundle
- [ ] Add EnvironmentFactory.import_from_git
- [ ] Add Workspace.import_from_git
- [ ] Update CLI to detect and route git URLs
- [ ] Add --branch argument to CLI
- [ ] Verify git utilities exist (is_git_url)
- [ ] Add unit test for import without manifest
- [ ] Add integration test for git import
- [ ] Test tarball import (regression)
- [ ] Test git import (HTTPS public)
- [ ] Test git import (SSH private)
- [ ] Test branch/tag selection
- [ ] Update README documentation
- [ ] Update CLI help text
- [ ] Manual smoke test end-to-end flow
