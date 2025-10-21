# Import/Export Architecture Refactoring Plan

## Executive Summary

This document outlines a refactoring of the import/export system to clarify responsibility boundaries and eliminate architectural inconsistencies. The current design has `ExportImportManager` performing both low-level I/O operations and high-level orchestration, creating confusion about ownership and dependencies.

**Goal:** Separate concerns into clear layers:
- **ExportImportManager** → Pure tarball I/O operations
- **ImportAnalyzer** → Preview and analysis service (new)
- **EnvironmentFactory** → Environment construction only
- **Environment** → Lifecycle and self-setup methods
- **Workspace** → High-level workflow orchestration

## Quick Reference - Files and Context

### Files to Create

**New service:**
- `packages/core/src/comfydock_core/services/import_analyzer.py`
  - Create from scratch (full implementation in Section 2)
  - Exports: `ImportAnalyzer`, `ImportAnalysis`, `ModelAnalysis`, `NodeAnalysis`, `WorkflowAnalysis`

### Files to Modify

**Core domain:**
- `packages/core/src/comfydock_core/core/environment.py`
  - Add: `finalize_import()` method after line 954
  - Reference: Logic from `ExportImportManager.import_bundle()` phases 1-6

- `packages/core/src/comfydock_core/core/workspace.py`
  - Add: `import_analyzer` cached property (around line 100)
  - Add: `preview_import()` method
  - Add: `preview_git_import()` method
  - Modify: `import_environment()` - two-step pattern (line 260)
  - Modify: `import_from_git()` - two-step pattern (line 315)

**Factory layer:**
- `packages/core/src/comfydock_core/factories/environment_factory.py`
  - Modify: `import_from_bundle()` - remove model_strategy/callbacks params
  - Modify: `import_from_git()` - remove model_strategy/callbacks params
  - Simplify both to just extract/clone and return Environment

**Manager layer:**
- `packages/core/src/comfydock_core/managers/export_import_manager.py`
  - Delete: `import_bundle()` method (lines 121-300)
  - Keep: `create_export()` and `extract_import()` unchanged

**CLI:**
- `packages/cli/comfydock_cli/global_commands.py`
  - Modify: `import_env()` method (line 150)
  - Add: Preview analysis before strategy prompt
  - Add: Display ImportAnalysis results
  - Modify: Conditional strategy prompt based on needs_model_downloads

### Key Context References

**Logic to be moved:**
- From: `packages/core/src/comfydock_core/managers/export_import_manager.py:121-300`
- To: `packages/core/src/comfydock_core/core/environment.py:finalize_import()`
- Changes: Replace `env.` with `self.`, keep phases 1-6 logic intact

**Protocols and types:**
- Import callbacks: `packages/core/src/comfydock_core/models/protocols.py`
  - `ImportCallbacks` protocol (for type hints)
  - Used in `finalize_import()` signature

**Dependencies for ImportAnalyzer:**
- `packages/core/src/comfydock_core/repositories/model_repository.py`
  - Method: `get_model(hash)` - check if model exists
- `packages/core/src/comfydock_core/repositories/node_mappings_repository.py`
  - Used for future node validation

**Existing utilities to reuse:**
- `packages/core/src/comfydock_core/utils/git.py`
  - `git_clone()` - for preview_git_import()
- `packages/core/src/comfydock_core/caching/comfyui_cache.py`
  - `ComfyUICacheManager`, `ComfyUISpec` - for finalize_import()
- `packages/core/src/comfydock_core/utils/comfyui_ops.py`
  - `clone_comfyui()` - for finalize_import()

### Line Number Guidance

**Environment.py additions:**
- Insert `finalize_import()` after line 954 (after `prepare_import_with_model_strategy()`)
- Estimated ~150 lines of new code

**Workspace.py additions:**
- Insert `import_analyzer` property around line 100 (after other cached properties)
- Insert `preview_import()` and `preview_git_import()` before `import_environment()` (before line 260)
- Modify `import_environment()` at line 260 - add env.finalize_import() call
- Modify `import_from_git()` at line 315 - add env.finalize_import() call

**ExportImportManager.py deletions:**
- Delete lines 121-300 (`import_bundle()` method)
- File should go from ~301 lines → ~120 lines

**EnvironmentFactory.py modifications:**
- `import_from_bundle()` - remove lines with `ExportImportManager.import_bundle()` call
- `import_from_git()` - remove lines with `ExportImportManager.import_bundle()` call
- Both methods should end by returning Environment instance (no finalization)

### Testing Files to Update

**Integration tests:**
- `packages/core/tests/integration/test_export_import.py`
  - Update to use two-step pattern
  - Add preview tests

**Unit tests to add:**
- `packages/core/tests/unit/services/test_import_analyzer.py` (new file)
  - Test model analysis
  - Test node analysis
  - Test workflow analysis

## Current Architecture Problems

### Problem 1: Asymmetric Ownership

**Export flow:**
```python
# Environment owns the export operation
env.export_environment(output_path)
    └─> ExportImportManager.create_export()  # Just creates tarball
```

**Import flow:**
```python
# Manager owns the import operation
Workspace.import_environment()
    └─> EnvironmentFactory.import_from_bundle()
        └─> ExportImportManager.import_bundle(env, ...)  # Does EVERYTHING
```

The export is a simple delegation, but import is full orchestration. This asymmetry is confusing.

### Problem 2: Manager Does Too Much

`ExportImportManager.import_bundle()` performs 6 phases of orchestration:
1. Clone/restore ComfyUI
2. Install dependencies
3. Initialize git
4. Copy workflows
5. Sync custom nodes
6. Resolve models

This violates Single Responsibility - a "manager" for tar operations shouldn't orchestrate environment lifecycle.

### Problem 3: Responsibility Misalignment

```python
# ExportImportManager depends on Environment methods
def import_bundle(self, env: Environment, ...):
    env.sync()  # Manager calling Environment
    env.prepare_import_with_model_strategy()  # Manager calling Environment
    env.resolve_workflow()  # Manager calling Environment
```

The dependency direction is backwards. Environment should use managers as utilities, not vice versa.

### Problem 4: Factory Confusion

`EnvironmentFactory` should create valid Environment instances. But does "valid" mean:
- **Structurally valid** (has .cec directory) but needs setup?
- **Fully initialized** (ready to use immediately)?

Currently it delegates to `ExportImportManager.import_bundle()` which makes it fully initialized, but this makes Factory do orchestration, which violates its purpose.

## Proposed Architecture

### Layer Responsibilities

```
┌─────────────────────────────────────────────────────────────────────┐
│ Workspace (Orchestration Layer)                                     │
│ - Coordinates multi-step workflows                                  │
│ - Provides preview_import() for pre-import analysis                 │
│ - Calls Factory + Environment methods                               │
│ - Manages environment collection                                    │
└─────────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────────┐  ┌─────────────┐  ┌─────────────────────────┐
│ Environment      │  │ Environment │  │ ImportAnalyzer          │
│ Factory          │  │             │  │ (Service Layer)         │
│ (Construction)   │  │ (Domain)    │  │ - Analyze .cec contents │
│ - Creates env    │  │ - Lifecycle │  │ - Preview downloads     │
│ - Validates      │  │ - Self-setup│  │ - Security analysis     │
└──────────────────┘  └─────────────┘  └─────────────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                ┌───────────────────────────┐
                │ ExportImportManager       │
                │ (I/O Layer)               │
                │ - create_export()         │
                │ - extract_import()        │
                │ - Pure tar operations     │
                └───────────────────────────┘
```

### Key Principles

1. **ExportImportManager** = Serialization utility (tar.gz operations only)
2. **ImportAnalyzer** = Analysis service (read-only preview of .cec contents)
3. **EnvironmentFactory** = Construction layer (creates valid instances)
4. **Environment** = Domain object (knows how to set itself up)
5. **Workspace** = Controller (orchestrates workflows using Environment methods)

## Detailed Component Refactoring

### 1. ExportImportManager → Pure I/O

**Before:**
```python
class ExportImportManager:
    def create_export(self, output_path, pyproject) -> Path:
        """Creates tarball"""

    def extract_import(self, tarball_path, target_cec_path) -> None:
        """Extracts tarball"""

    def import_bundle(self, env, tarball_path, model_strategy, callbacks):
        """Does 6 phases of orchestration"""  # ← THIS IS THE PROBLEM
```

**After:**
```python
class ExportImportManager:
    """Handles tarball serialization/deserialization only."""

    def __init__(self, cec_path: Path, comfyui_path: Path):
        self.cec_path = cec_path
        self.comfyui_path = comfyui_path

    def create_export(
        self,
        output_path: Path,
        pyproject_manager: PyprojectManager
    ) -> Path:
        """Create tarball from environment files.

        Packages:
        - pyproject.toml, uv.lock, .python-version
        - workflows/*.json
        - dev_nodes/* (filtered by .gitignore)

        Returns:
            Path to created tarball
        """
        # Current implementation stays exactly as-is (lines 26-77)

    def extract_import(self, tarball_path: Path, target_cec_path: Path) -> None:
        """Extract tarball to target .cec directory.

        Args:
            tarball_path: Source .tar.gz file
            target_cec_path: Target .cec directory (must not exist)

        Raises:
            ValueError: If target already exists
        """
        # Current implementation stays exactly as-is (lines 79-101)
```

**Changes:**
- **Remove** `import_bundle()` method entirely
- Keep `create_export()` and `extract_import()` unchanged
- This manager becomes a pure utility

### 2. ImportAnalyzer → New Analysis Service

**Create new service at `packages/core/src/comfydock_core/services/import_analyzer.py`:**

```python
"""Import preview and analysis service."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from ..repositories.model_repository import ModelRepository
    from ..repositories.node_mappings_repository import NodeMappingsRepository

logger = get_logger(__name__)


@dataclass
class ModelAnalysis:
    """Analysis of a single model in the import."""
    filename: str
    hash: str | None
    sources: list[str]
    relative_path: str
    criticality: str  # "required" | "optional"
    locally_available: bool  # Checked against model_repository
    needs_download: bool  # True if not available and has sources
    workflows: list[str]  # Which workflows reference it


@dataclass
class NodeAnalysis:
    """Analysis of a custom node in the import."""
    name: str
    source: str  # "registry" | "development" | "git"
    install_spec: str | None  # Git URL or registry ID
    is_dev_node: bool  # Bundled in tarball's dev_nodes/


@dataclass
class WorkflowAnalysis:
    """Analysis of a workflow in the import."""
    name: str
    models_required: int
    models_optional: int
    nodes_required: list[str]


@dataclass
class ImportAnalysis:
    """Complete analysis of an import before finalization."""

    # ComfyUI version
    comfyui_version: str | None
    comfyui_version_type: str | None  # "release" | "branch" | "commit"

    # Models breakdown
    models: list[ModelAnalysis]
    total_models: int
    models_locally_available: int
    models_needing_download: int
    models_without_sources: int  # Can't be downloaded

    # Nodes breakdown
    nodes: list[NodeAnalysis]
    total_nodes: int
    registry_nodes: int
    dev_nodes: int
    git_nodes: int

    # Workflows
    workflows: list[WorkflowAnalysis]
    total_workflows: int

    # Summary flags
    needs_model_downloads: bool
    needs_node_installs: bool
    has_security_concerns: bool  # Future: flag untrusted sources

    def get_download_strategy_recommendation(self) -> str:
        """Recommend strategy based on analysis."""
        if not self.needs_model_downloads:
            return "skip"  # All models available
        if self.models_without_sources > 0:
            return "required"  # Some can't be downloaded
        return "all"  # Can download everything


class ImportAnalyzer:
    """Analyzes import requirements before finalization.

    Works on extracted .cec directory to provide preview of what
    will be downloaded, installed, and configured during import finalization.
    """

    def __init__(
        self,
        model_repository: ModelRepository,
        node_mapping_repository: NodeMappingsRepository
    ):
        self.model_repository = model_repository
        self.node_mapping_repository = node_mapping_repository

    def analyze_import(self, cec_path: Path) -> ImportAnalysis:
        """Analyze import requirements from extracted .cec directory.

        Args:
            cec_path: Path to extracted .cec directory

        Returns:
            ImportAnalysis with models, nodes, workflows breakdown
        """
        # Parse pyproject.toml
        pyproject_path = cec_path / "pyproject.toml"
        with open(pyproject_path) as f:
            pyproject_data = tomlkit.load(f)

        comfydock_config = pyproject_data.get("tool", {}).get("comfydock", {})

        # Analyze models
        models = self._analyze_models(pyproject_data)

        # Analyze nodes
        nodes = self._analyze_nodes(comfydock_config)

        # Analyze workflows
        workflows = self._analyze_workflows(cec_path / "workflows", pyproject_data)

        # Build summary
        return ImportAnalysis(
            comfyui_version=comfydock_config.get("comfyui_version"),
            comfyui_version_type=comfydock_config.get("comfyui_version_type"),
            models=models,
            total_models=len(models),
            models_locally_available=sum(1 for m in models if m.locally_available),
            models_needing_download=sum(1 for m in models if m.needs_download),
            models_without_sources=sum(
                1 for m in models if not m.sources and not m.locally_available
            ),
            nodes=nodes,
            total_nodes=len(nodes),
            registry_nodes=sum(1 for n in nodes if n.source == "registry"),
            dev_nodes=sum(1 for n in nodes if n.is_dev_node),
            git_nodes=sum(1 for n in nodes if n.source == "git"),
            workflows=workflows,
            total_workflows=len(workflows),
            needs_model_downloads=any(m.needs_download for m in models),
            needs_node_installs=any(n.source in ("registry", "git") for n in nodes),
            has_security_concerns=False  # Future
        )

    def _analyze_models(self, pyproject_data: dict) -> list[ModelAnalysis]:
        """Analyze all models from pyproject.toml."""
        models = []

        # Get global models table
        global_models = pyproject_data.get("tool", {}).get("comfydock", {}).get("models", {})

        # Get all workflows
        workflows_config = pyproject_data.get("tool", {}).get("comfydock", {}).get("workflows", {})

        # Build reverse index: hash -> workflows
        hash_to_workflows = {}
        for workflow_name, workflow_data in workflows_config.items():
            for model in workflow_data.get("models", []):
                model_hash = model.get("hash")
                if model_hash:
                    hash_to_workflows.setdefault(model_hash, []).append(workflow_name)

        # Analyze each model
        for model_hash, model_data in global_models.items():
            sources = model_data.get("sources", [])

            # Check local availability
            existing = self.model_repository.get_model(model_hash)
            locally_available = existing is not None

            models.append(ModelAnalysis(
                filename=model_data.get("filename", "unknown"),
                hash=model_hash,
                sources=sources,
                relative_path=model_data.get("relative_path", ""),
                criticality="unknown",  # Would need workflow context
                locally_available=locally_available,
                needs_download=not locally_available and bool(sources),
                workflows=hash_to_workflows.get(model_hash, [])
            ))

        return models

    def _analyze_nodes(self, comfydock_config: dict) -> list[NodeAnalysis]:
        """Analyze all custom nodes from pyproject.toml."""
        nodes = []
        nodes_config = comfydock_config.get("nodes", {})

        for node_name, node_data in nodes_config.items():
            source = node_data.get("source", "registry")

            nodes.append(NodeAnalysis(
                name=node_name,
                source=source,
                install_spec=node_data.get("install_spec"),
                is_dev_node=(source == "development")
            ))

        return nodes

    def _analyze_workflows(
        self,
        workflows_dir: Path,
        pyproject_data: dict
    ) -> list[WorkflowAnalysis]:
        """Analyze all workflows."""
        workflows = []

        if not workflows_dir.exists():
            return workflows

        workflows_config = pyproject_data.get("tool", {}).get("comfydock", {}).get("workflows", {})

        for workflow_name, workflow_data in workflows_config.items():
            models = workflow_data.get("models", [])

            workflows.append(WorkflowAnalysis(
                name=workflow_name,
                models_required=sum(1 for m in models if m.get("criticality") == "required"),
                models_optional=sum(1 for m in models if m.get("criticality") == "optional"),
                nodes_required=[]  # Would need to parse workflow JSON
            ))

        return workflows
```

**Purpose:**
- Provides read-only analysis of .cec directory before finalization
- Works for both tarball and git imports (both create .cec)
- Returns structured data for CLI to display as preview
- Foundation for future security/trust features

**Key Design:**
- Service class (stateless, reusable)
- Operates on extracted .cec (post-extraction, pre-finalization)
- No mutations - pure analysis
- Returns rich data structures for flexible presentation

### 3. Environment → Add Lifecycle Methods

**Add new method:**
```python
class Environment:
    def finalize_import(
        self,
        model_strategy: str = "all",
        callbacks: ImportCallbacks | None = None
    ) -> None:
        """Complete import setup after .cec extraction.

        Assumes .cec directory is already populated (from tarball or git).

        Phases:
            1. Clone/restore ComfyUI from cache
            2. Install dependencies (uv sync)
            3. Initialize git repository
            4. Copy workflows to ComfyUI user directory
            5. Sync custom nodes
            6. Prepare and resolve models based on strategy

        Args:
            model_strategy: "all", "required", or "skip"
            callbacks: Optional progress callbacks

        Raises:
            ValueError: If ComfyUI already exists or .cec not properly initialized
        """
        from ..caching.comfyui_cache import ComfyUICacheManager, ComfyUISpec
        from ..utils.comfyui_ops import clone_comfyui
        from ..utils.git import git_rev_parse
        from ..strategies.auto import AutoModelStrategy, AutoNodeStrategy

        logger.info(f"Finalizing import for environment: {self.name}")

        # Verify environment state
        if self.comfyui_path.exists():
            raise ValueError("Environment already has ComfyUI - cannot finalize import")

        # Phase 1: Clone or restore ComfyUI from cache
        comfyui_cache = ComfyUICacheManager(cache_base_path=self.workspace_paths.cache)

        # Read ComfyUI version from pyproject.toml
        comfyui_version = None
        comfyui_version_type = None
        try:
            pyproject_data = self.pyproject.load()
            comfydock_config = pyproject_data.get("tool", {}).get("comfydock", {})
            comfyui_version = comfydock_config.get("comfyui_version")
            comfyui_version_type = comfydock_config.get("comfyui_version_type")
        except Exception as e:
            logger.warning(f"Could not read comfyui_version from pyproject.toml: {e}")

        if comfyui_version:
            version_desc = f"{comfyui_version_type} {comfyui_version}" if comfyui_version_type else comfyui_version
            logger.debug(f"Using comfyui_version from pyproject: {version_desc}")

        # Auto-detect version type if not specified
        if not comfyui_version_type and comfyui_version:
            if comfyui_version.startswith('v'):
                comfyui_version_type = "release"
            elif comfyui_version in ("main", "master"):
                comfyui_version_type = "branch"
            else:
                comfyui_version_type = "commit"
            logger.debug(f"Auto-detected version type: {comfyui_version_type}")

        # Create version spec
        spec = ComfyUISpec(
            version=comfyui_version or "main",
            version_type=comfyui_version_type or "branch",
            commit_sha=None
        )

        # Check cache first
        cached_path = comfyui_cache.get_cached_comfyui(spec)

        if cached_path:
            if callbacks:
                callbacks.on_phase("restore_comfyui", f"Restoring ComfyUI {spec.version} from cache...")
            logger.info(f"Restoring ComfyUI {spec.version} from cache")
            shutil.copytree(cached_path, self.comfyui_path)
        else:
            if callbacks:
                callbacks.on_phase("clone_comfyui", f"Cloning ComfyUI {spec.version}...")
            logger.info(f"Cloning ComfyUI {spec.version}")
            clone_comfyui(self.comfyui_path, comfyui_version)

            # Cache the fresh clone
            commit_sha = git_rev_parse(self.comfyui_path, "HEAD")
            spec.commit_sha = commit_sha
            comfyui_cache.cache_comfyui(spec, self.comfyui_path)
            logger.info(f"Cached ComfyUI {spec.version} ({commit_sha[:7]})")

        # Remove ComfyUI's default models directory (will be replaced with symlink)
        models_dir = self.comfyui_path / "models"
        if models_dir.exists() and not models_dir.is_symlink():
            shutil.rmtree(models_dir)

        # Phase 2: Install dependencies
        if callbacks:
            callbacks.on_phase("install_deps", "Installing dependencies...")
        self.uv_manager.sync_project(verbose=False)

        # Phase 3: Initialize git
        if callbacks:
            callbacks.on_phase("init_git", "Initializing git repository...")
        self.git_manager.initialize_environment_repo("Imported environment")

        # Phase 4: Copy workflows
        if callbacks:
            callbacks.on_phase("copy_workflows", "Setting up workflows...")

        workflows_src = self.cec_path / "workflows"
        workflows_dst = self.comfyui_path / "user" / "default" / "workflows"
        workflows_dst.mkdir(parents=True, exist_ok=True)

        if workflows_src.exists():
            for workflow_file in workflows_src.glob("*.json"):
                shutil.copy2(workflow_file, workflows_dst / workflow_file.name)
                if callbacks:
                    callbacks.on_workflow_copied(workflow_file.name)

        # Phase 5: Sync custom nodes
        if callbacks:
            callbacks.on_phase("sync_nodes", "Syncing custom nodes...")

        try:
            sync_result = self.sync()
            if sync_result.success and sync_result.nodes_installed and callbacks:
                for node_name in sync_result.nodes_installed:
                    callbacks.on_node_installed(node_name)
            elif not sync_result.success and callbacks:
                for error in sync_result.errors:
                    callbacks.on_error(f"Node sync: {error}")
        except Exception as e:
            if callbacks:
                callbacks.on_error(f"Node sync failed: {e}")

        # Phase 6: Prepare and resolve models
        if callbacks:
            callbacks.on_phase("resolve_models", f"Resolving workflows ({model_strategy} strategy)...")

        workflows_to_resolve = []
        if model_strategy != "skip":
            workflows_to_resolve = self.prepare_import_with_model_strategy(model_strategy)

        # Resolve workflows with download intents
        download_failures = []

        for workflow_name in workflows_to_resolve:
            try:
                result = self.resolve_workflow(
                    name=workflow_name,
                    model_strategy=AutoModelStrategy(),
                    node_strategy=AutoNodeStrategy()
                )

                # Track successful vs failed downloads
                successful_downloads = sum(
                    1 for m in result.models_resolved
                    if m.match_type == 'download_intent' and m.resolved_model is not None
                )
                failed_downloads = [
                    (workflow_name, m.reference.widget_value)
                    for m in result.models_resolved
                    if m.match_type == 'download_intent' and m.resolved_model is None
                ]

                download_failures.extend(failed_downloads)

                if callbacks:
                    callbacks.on_workflow_resolved(workflow_name, successful_downloads)

            except Exception as e:
                if callbacks:
                    callbacks.on_error(f"Failed to resolve {workflow_name}: {e}")

        # Report download failures
        if download_failures and callbacks:
            callbacks.on_download_failures(download_failures)

        logger.info("Import finalization completed successfully")
```

**Keep existing methods:**
- `export_environment()` - unchanged
- `prepare_import_with_model_strategy()` - unchanged

### 3. EnvironmentFactory → Construction Only

**Before:**
```python
@staticmethod
def import_from_bundle(tarball_path, name, env_path, workspace_paths, ...,
                       model_strategy, callbacks):
    # Creates environment structure
    # Extracts tarball
    # Calls ExportImportManager.import_bundle() for full orchestration
    # Returns ready-to-use environment
```

**After:**
```python
@staticmethod
def import_from_bundle(
    tarball_path: Path,
    name: str,
    env_path: Path,
    workspace_paths: WorkspacePaths,
    model_repository: ModelRepository,
    node_mapping_repository: NodeMappingsRepository,
    workspace_config_manager: WorkspaceConfigRepository,
    model_downloader: ModelDownloader
) -> Environment:
    """Create environment structure from tarball (extraction only).

    This creates the environment directory and extracts the .cec contents.
    The environment is NOT fully initialized - caller must call
    env.finalize_import() to complete setup.

    Args:
        tarball_path: Path to .tar.gz bundle
        name: Environment name
        env_path: Target environment directory
        workspace_paths: Workspace path configuration
        model_repository: Shared model repository
        node_mapping_repository: Shared node mappings
        workspace_config_manager: Workspace configuration
        model_downloader: Model download service

    Returns:
        Environment instance with .cec extracted but not fully initialized

    Raises:
        ValueError: If env_path already exists
    """
    if env_path.exists():
        raise ValueError(f"Environment path already exists: {env_path}")

    logger.info(f"Creating environment structure from bundle: {tarball_path}")

    # Create environment directory structure
    env_path.mkdir(parents=True, exist_ok=True)
    cec_path = env_path / ".cec"

    # Extract tarball to .cec
    manager = ExportImportManager(cec_path, env_path / "ComfyUI")
    manager.extract_import(tarball_path, cec_path)

    # Create and return Environment instance
    # NOTE: ComfyUI is not cloned yet, workflows not copied, models not resolved
    return Environment(
        name=name,
        path=env_path,
        workspace_paths=workspace_paths,
        model_repository=model_repository,
        node_mapping_repository=node_mapping_repository,
        workspace_config_manager=workspace_config_manager,
        model_downloader=model_downloader
    )
```

**Similarly for `import_from_git()`:**
```python
@staticmethod
def import_from_git(
    git_url: str,
    name: str,
    env_path: Path,
    workspace_paths: WorkspacePaths,
    model_repository: ModelRepository,
    node_mapping_repository: NodeMappingsRepository,
    workspace_config_manager: WorkspaceConfigRepository,
    model_downloader: ModelDownloader,
    branch: str | None = None
) -> Environment:
    """Create environment structure from git repository (clone only).

    This clones the git repository to .cec directory.
    The environment is NOT fully initialized - caller must call
    env.finalize_import() to complete setup.

    Args:
        git_url: Git repository URL
        name: Environment name
        env_path: Target environment directory
        workspace_paths: Workspace path configuration
        model_repository: Shared model repository
        node_mapping_repository: Shared node mappings
        workspace_config_manager: Workspace configuration
        model_downloader: Model download service
        branch: Optional branch/tag/commit to checkout

    Returns:
        Environment instance with .cec cloned but not fully initialized

    Raises:
        ValueError: If env_path already exists or git clone fails
    """
    if env_path.exists():
        raise ValueError(f"Environment path already exists: {env_path}")

    logger.info(f"Creating environment structure from git: {git_url}")

    # Create environment directory structure
    env_path.mkdir(parents=True, exist_ok=True)
    cec_path = env_path / ".cec"

    # Clone repository to .cec
    from ..utils.git import git_clone

    git_clone(git_url, cec_path, branch=branch)
    logger.info(f"Cloned {git_url} to {cec_path}")

    # Validate it's a ComfyDock environment
    pyproject_path = cec_path / "pyproject.toml"
    if not pyproject_path.exists():
        raise ValueError(
            f"Repository does not contain pyproject.toml - not a valid ComfyDock environment"
        )

    # Create and return Environment instance
    # NOTE: ComfyUI is not cloned yet, workflows not copied, models not resolved
    return Environment(
        name=name,
        path=env_path,
        workspace_paths=workspace_paths,
        model_repository=model_repository,
        node_mapping_repository=node_mapping_repository,
        workspace_config_manager=workspace_config_manager,
        model_downloader=model_downloader
    )
```

### 4. Workspace → Orchestrates Workflow + Provides Preview

**Add ImportAnalyzer as cached property:**
```python
class Workspace:
    @cached_property
    def import_analyzer(self) -> ImportAnalyzer:
        """Get import analysis service."""
        from ..services.import_analyzer import ImportAnalyzer
        return ImportAnalyzer(
            model_repository=self.model_index_manager,
            node_mapping_repository=self.node_mapping_repository
        )
```

**Add preview methods:**
```python
def preview_import(self, tarball_path: Path) -> ImportAnalysis:
    """Preview import requirements without creating environment.

    Extracts to temp directory, analyzes, then cleans up.

    Args:
        tarball_path: Path to .tar.gz bundle

    Returns:
        ImportAnalysis with full breakdown
    """
    import tempfile
    from ..managers.export_import_manager import ExportImportManager

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cec = Path(temp_dir) / ".cec"

        # Extract to temp location
        manager = ExportImportManager(temp_cec, Path(temp_dir) / "ComfyUI")
        manager.extract_import(tarball_path, temp_cec)

        # Analyze
        return self.import_analyzer.analyze_import(temp_cec)

def preview_git_import(
    self,
    git_url: str,
    branch: str | None = None
) -> ImportAnalysis:
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
        git_clone(git_url, temp_cec, branch=branch)

        # Analyze
        return self.import_analyzer.analyze_import(temp_cec)
```

**Before:**
```python
def import_environment(self, tarball_path, name, model_strategy, callbacks):
    # Delegates everything to Factory
    environment = EnvironmentFactory.import_from_bundle(
        # ... lots of params including model_strategy and callbacks
    )
    return environment  # Fully initialized
```

**After:**
```python
def import_environment(
    self,
    tarball_path: Path,
    name: str,
    model_strategy: str = "all",
    callbacks: ImportCallbacks | None = None
) -> Environment:
    """Import environment from tarball bundle.

    Complete workflow:
    1. Create environment structure and extract tarball
    2. Finalize import (clone ComfyUI, install deps, sync nodes, resolve models)

    Args:
        tarball_path: Path to .tar.gz bundle
        name: Name for imported environment
        model_strategy: "all", "required", or "skip"
        callbacks: Optional callbacks for progress updates

    Returns:
        Fully initialized Environment

    Raises:
        CDEnvironmentExistsError: If environment already exists
        ComfyDockError: If import fails
        RuntimeError: If import fails
    """
    env_path = self.paths.environments / name

    if env_path.exists():
        raise CDEnvironmentExistsError(f"Environment '{name}' already exists")

    try:
        # Step 1: Create environment structure (extract .cec)
        environment = EnvironmentFactory.import_from_bundle(
            tarball_path=tarball_path,
            name=name,
            env_path=env_path,
            workspace_paths=self.paths,
            model_repository=self.model_index_manager,
            node_mapping_repository=self.node_mapping_repository,
            workspace_config_manager=self.workspace_config_manager,
            model_downloader=self.model_downloader
        )

        # Step 2: Let environment complete its setup
        environment.finalize_import(model_strategy, callbacks)

        return environment

    except Exception as e:
        logger.error(f"Failed to import environment: {e}")
        if env_path.exists():
            logger.debug(f"Cleaning up partial environment at {env_path}")
            shutil.rmtree(env_path, ignore_errors=True)

        if isinstance(e, ComfyDockError):
            raise
        else:
            raise RuntimeError(f"Failed to import environment '{name}': {e}") from e
```

**Similarly for `import_from_git()`:**
```python
def import_from_git(
    self,
    git_url: str,
    name: str,
    model_strategy: str = "all",
    branch: str | None = None,
    callbacks: ImportCallbacks | None = None
) -> Environment:
    """Import environment from git repository.

    Complete workflow:
    1. Create environment structure and clone repository
    2. Finalize import (clone ComfyUI, install deps, sync nodes, resolve models)

    Args:
        git_url: Git repository URL (https://, git@, or local path)
        name: Name for imported environment
        model_strategy: "all", "required", or "skip"
        branch: Optional branch/tag/commit
        callbacks: Optional callbacks for progress updates

    Returns:
        Fully initialized Environment

    Raises:
        CDEnvironmentExistsError: If environment already exists
        ValueError: If repository is invalid
        ComfyDockError: If import fails
        RuntimeError: If import fails
    """
    env_path = self.paths.environments / name

    if env_path.exists():
        raise CDEnvironmentExistsError(f"Environment '{name}' already exists")

    try:
        # Step 1: Create environment structure (clone git repo to .cec)
        environment = EnvironmentFactory.import_from_git(
            git_url=git_url,
            name=name,
            env_path=env_path,
            workspace_paths=self.paths,
            model_repository=self.model_index_manager,
            node_mapping_repository=self.node_mapping_repository,
            workspace_config_manager=self.workspace_config_manager,
            model_downloader=self.model_downloader,
            branch=branch
        )

        # Step 2: Let environment complete its setup
        environment.finalize_import(model_strategy, callbacks)

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

## Migration Guide

### Step 1: Create ImportAnalyzer Service

1. Create new file `packages/core/src/comfydock_core/services/import_analyzer.py`
2. Copy the complete ImportAnalyzer implementation from section 2 above
3. Includes:
   - Data classes: `ModelAnalysis`, `NodeAnalysis`, `WorkflowAnalysis`, `ImportAnalysis`
   - Service class: `ImportAnalyzer`
   - All analysis methods

### Step 2: Add Workspace Preview Methods

1. Open `packages/core/src/comfydock_core/core/workspace.py`
2. Add `import_analyzer` cached property
3. Add `preview_import()` method for tarball analysis
4. Add `preview_git_import()` method for git URL analysis
5. Add necessary imports (`tempfile`, `ImportAnalyzer`, `ImportAnalysis`)

### Step 3: Add `Environment.finalize_import()`

1. Open `packages/core/src/comfydock_core/core/environment.py`
2. Add the new `finalize_import()` method after `prepare_import_with_model_strategy()` (around line 955)
3. Copy implementation from `ExportImportManager.import_bundle()` phases 1-6
4. Update to use `self` instead of `env` parameter
5. Add necessary imports at top of file

### Step 4: Simplify EnvironmentFactory

1. Open `packages/core/src/comfydock_core/factories/environment_factory.py`
2. Modify `import_from_bundle()`:
   - Remove `model_strategy` and `callbacks` parameters
   - Remove call to `ExportImportManager.import_bundle()`
   - Just extract tarball and return Environment instance
3. Modify `import_from_git()`:
   - Remove `model_strategy` and `callbacks` parameters
   - Just clone repo and return Environment instance

### Step 5: Update Workspace Orchestration

1. Open `packages/core/src/comfydock_core/core/workspace.py`
2. Update `import_environment()`:
   - Call `EnvironmentFactory.import_from_bundle()` without model_strategy/callbacks
   - Call `environment.finalize_import(model_strategy, callbacks)`
3. Update `import_from_git()`:
   - Call `EnvironmentFactory.import_from_git()` without model_strategy/callbacks
   - Call `environment.finalize_import(model_strategy, callbacks)`

### Step 6: Simplify ExportImportManager

1. Open `packages/core/src/comfydock_core/managers/export_import_manager.py`
2. Delete `import_bundle()` method entirely (lines 121-300)
3. Keep `create_export()` and `extract_import()` unchanged

### Step 7: Update CLI to Use Preview

1. Open `packages/cli/comfydock_cli/global_commands.py`
2. Update `import_env()` method:
   - Call `workspace.preview_import()` or `workspace.preview_git_import()` before prompting
   - Display `ImportAnalysis` results to user
   - Use `analysis.get_download_strategy_recommendation()` as default
   - Only show strategy prompt if `analysis.needs_model_downloads` is True

Example CLI update:
```python
# Before prompting for strategy
if is_git:
    analysis = self.workspace.preview_git_import(args.path, getattr(args, 'branch', None))
else:
    analysis = self.workspace.preview_import(Path(args.path))

# Display preview
print(f"\n📋 Import Preview:")
print(f"   ComfyUI: {analysis.comfyui_version or 'main'}")
print(f"   Workflows: {analysis.total_workflows}")
print(f"   Custom Nodes: {analysis.total_nodes}")
print(f"   Models: {analysis.total_models}")

if analysis.needs_model_downloads:
    print(f"\n📥 Model Downloads:")
    print(f"   • {analysis.models_locally_available} already available")
    print(f"   • {analysis.models_needing_download} need downloading")
    if analysis.models_without_sources > 0:
        print(f"   ⚠️  {analysis.models_without_sources} have no source")

    # Show strategy prompt
    recommended = analysis.get_download_strategy_recommendation()
    # ... prompt user ...
else:
    print(f"   ✓ All models available locally")
    strategy = "skip"  # No downloads needed
```

### Step 8: Update Tests

1. Update any tests that call `ExportImportManager.import_bundle()` directly
2. Update tests to use new two-step pattern:
   ```python
   env = EnvironmentFactory.import_from_bundle(...)
   env.finalize_import(model_strategy, callbacks)
   ```
3. Add tests for `ImportAnalyzer`:
   - Test model analysis with locally available models
   - Test model analysis with missing models
   - Test node analysis
   - Test workflow analysis
4. Add tests for Workspace preview methods:
   - Test `preview_import()` with tarball
   - Test `preview_git_import()` with git URL

## Benefits of This Refactoring

1. **Clear Separation of Concerns**
   - ExportImportManager = I/O only
   - ImportAnalyzer = Analysis/preview service
   - EnvironmentFactory = Construction only
   - Environment = Domain logic and lifecycle
   - Workspace = Orchestration + preview API

2. **Import Preview Capability** (NEW)
   - `workspace.preview_import(tarball)` - Analyze before importing
   - `workspace.preview_git_import(url)` - Works for both tarball and git imports
   - Rich structured data for CLI to display
   - Foundation for security features (trust levels, source validation)

3. **Better Reusability**
   - Can import .cec without full setup: `env = Factory.import_from_bundle()`
   - Can finalize later: `env.finalize_import(strategy, callbacks)`
   - Can customize the flow between steps
   - Can analyze without importing: `workspace.preview_import()`

4. **Symmetric Export/Import**
   - Export: `env.export_environment()`
   - Import: `env.finalize_import()`
   - Both are Environment methods now

5. **Eliminates Circular Dependency Concerns**
   - Environment creates managers as needed
   - Managers don't call back into Environment
   - Clean dependency direction: Workspace → Environment → Managers/Services

6. **More Testable**
   - Can test extraction separately from setup
   - Can test analysis separately from import
   - Can mock callbacks more easily
   - Can test each phase independently
   - ImportAnalyzer is pure logic (no side effects)

## Risk Assessment

**Low Risk:**
- Core logic is moving, not changing
- Interface to CLI remains the same
- Only internal refactoring

**Potential Issues:**
- Need to ensure all imports are correctly added
- Git operations might need careful testing
- Callback timing might differ slightly

**Mitigation:**
- Keep existing tests passing
- Test both tarball and git import flows
- Verify callback ordering matches current behavior

## Timeline Estimate

- Step 1 (Create ImportAnalyzer): 45 min
- Step 2 (Workspace preview methods): 20 min
- Step 3 (Environment.finalize_import): 30 min
- Step 4 (Factory simplification): 15 min
- Step 5 (Workspace orchestration): 15 min
- Step 6 (Manager cleanup): 5 min
- Step 7 (CLI preview integration): 20 min
- Step 8 (Test updates): 45 min
- Verification and integration testing: 30 min

**Total: ~3.5 hours**

## Success Criteria

### Core Functionality
- [ ] All existing tests pass
- [ ] Import from tarball works (CLI: `comfydock import <file>`)
- [ ] Import from git works (CLI: `comfydock import <url>`)
- [ ] Export works (CLI: `comfydock export`)
- [ ] Callbacks fire in correct order
- [ ] No circular dependencies in imports
- [ ] All 3 model strategies work (all, required, skip)
- [ ] Error handling and cleanup on failure works

### New Preview Functionality
- [ ] `workspace.preview_import(tarball)` returns complete ImportAnalysis
- [ ] `workspace.preview_git_import(url)` returns complete ImportAnalysis
- [ ] Preview correctly identifies locally available models
- [ ] Preview correctly identifies models needing download
- [ ] Preview correctly identifies models without sources
- [ ] Preview correctly counts nodes by source type
- [ ] Preview correctly analyzes workflows
- [ ] CLI displays preview before prompting for strategy
- [ ] CLI skips strategy prompt when all models are available
- [ ] Preview uses temp directory and cleans up properly

## Future Enhancements

After this refactoring, we could:

1. **Add partial import support**
   ```python
   env = Factory.import_from_bundle(tarball)
   # Do custom setup here
   env.finalize_import(strategy)
   ```

2. **Add import resumption**
   ```python
   env = workspace.get_environment("partially-imported")
   env.finalize_import(strategy)  # Resume from failure
   ```

3. **Add dry-run mode**
   ```python
   env.finalize_import(strategy, dry_run=True)  # Preview what would happen
   ```

4. **Add security/trust analysis** (enabled by ImportAnalyzer)
   ```python
   analysis = workspace.preview_import(tarball)

   # Flag untrusted sources
   for model in analysis.models:
       if any(is_untrusted(url) for url in model.sources):
           model.security_flag = "untrusted"

   for node in analysis.nodes:
       if node.source == "git" and is_untrusted(node.install_spec):
           node.security_flag = "untrusted"

   # Security slider in CLI
   if analysis.has_security_concerns:
       print("⚠️  This environment contains untrusted sources")
       choice = input("Continue? (y/n): ")
   ```

5. **Add detailed model inspection**
   ```python
   analysis = workspace.preview_import(tarball)

   # Show each model with sources
   for model in analysis.models:
       print(f"{model.filename}:")
       print(f"  Hash: {model.hash}")
       print(f"  Sources: {', '.join(model.sources)}")
       print(f"  Workflows: {', '.join(model.workflows)}")

       if model.needs_download:
           choice = input("  Download? (y/n/s=skip all): ")
           # User can skip specific models
   ```

6. **Add node source validation**
   ```python
   # In ImportAnalyzer._analyze_nodes()
   for node in nodes:
       if node.source == "git":
           # Check if git URL is in trusted registry
           node.is_trusted = check_registry(node.install_spec)
       elif node.source == "registry":
           # Always trusted (official registry)
           node.is_trusted = True
   ```

These are all enabled by:
- Separating construction from initialization
- ImportAnalyzer providing rich analysis data
- Two-step import allowing inspection between extraction and finalization
