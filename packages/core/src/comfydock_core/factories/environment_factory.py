"""Factory for creating new environments."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from comfydock_core.core.environment import Environment

from ..logging.logging_config import get_logger
from ..managers.git_manager import GitManager
from ..models.exceptions import (
    CDEnvironmentExistsError,
)
from ..utils.comfyui_ops import clone_comfyui

if TYPE_CHECKING:
    from comfydock_core.core.workspace import Workspace

logger = get_logger(__name__)

class EnvironmentFactory:

    @staticmethod
    def create(
        name: str,
        env_path: Path,
        workspace: Workspace,
        python_version: str = "3.12",
        comfyui_version: str | None = None,
    ) -> Environment:
        """Create a new environment."""
        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

        # Create structure
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"
        cec_path.mkdir()

        # Pin Python version for uv
        python_version_file = cec_path / ".python-version"
        python_version_file.write_text(python_version + "\n")
        logger.debug(f"Created .python-version: {python_version}")

        # Initialize environment
        env = Environment(
            name=name,
            path=env_path,
            workspace=workspace
        )

        # Resolve ComfyUI version
        from ..caching.api_cache import APICacheManager
        from ..caching.comfyui_cache import ComfyUICacheManager, ComfyUISpec
        from ..clients.github_client import GitHubClient
        from ..utils.comfyui_ops import resolve_comfyui_version
        from ..utils.git import git_rev_parse

        api_cache = APICacheManager(cache_base_path=workspace.paths.cache)
        github_client = GitHubClient(cache_manager=api_cache)

        version_to_clone, version_type, _ = resolve_comfyui_version(
            comfyui_version,
            github_client
        )

        # Check ComfyUI cache first
        comfyui_cache = ComfyUICacheManager(cache_base_path=workspace.paths.cache)
        spec = ComfyUISpec(
            version=version_to_clone,
            version_type=version_type,
            commit_sha=None  # Will be set after cloning
        )

        cached_path = comfyui_cache.get_cached_comfyui(spec)

        if cached_path:
            # Restore from cache
            logger.info(f"Restoring ComfyUI {version_type} {version_to_clone} from cache...")
            shutil.copytree(cached_path, env.comfyui_path)
            commit_sha = git_rev_parse(env.comfyui_path, "HEAD")
            sha_display = f" ({commit_sha[:7]})" if commit_sha else ""
            logger.info(f"Restored ComfyUI from cache{sha_display}")
        else:
            # Clone fresh
            logger.info(f"Cloning ComfyUI {version_type} {version_to_clone}...")
            try:
                comfyui_version_output = clone_comfyui(env.comfyui_path, version_to_clone)
                if comfyui_version_output:
                    logger.info(f"Successfully cloned ComfyUI version: {comfyui_version_output}")
                else:
                    logger.warning("ComfyUI clone failed")
                    raise RuntimeError("ComfyUI clone failed")
            except Exception as e:
                logger.warning(f"ComfyUI clone failed: {e}")
                raise e

            # Get actual commit SHA and cache it
            commit_sha = git_rev_parse(env.comfyui_path, "HEAD")
            if commit_sha:
                spec.commit_sha = commit_sha
                comfyui_cache.cache_comfyui(spec, env.comfyui_path)
                logger.info(f"Cached ComfyUI {version_type} {version_to_clone} ({commit_sha[:7]})")
            else:
                logger.warning(f"Could not determine commit SHA for ComfyUI {version_type} {version_to_clone}")

        # Remove ComfyUI's default models directory (will be replaced with symlink)
        models_dir = env.comfyui_path / "models"
        if models_dir.exists() and not models_dir.is_symlink():
            shutil.rmtree(models_dir)
            logger.debug("Removed ComfyUI's default models directory")

        # Create initial pyproject.toml with full version metadata
        config = EnvironmentFactory._create_initial_pyproject(
            name,
            python_version,
            version_to_clone,
            version_type,
            commit_sha
        )
        env.pyproject.save(config)

        # Get requirements from ComfyUI and add them
        comfyui_reqs = env.comfyui_path / "requirements.txt"
        if comfyui_reqs.exists():
            logger.info("Adding ComfyUI requirements...")
            env.uv_manager.add_requirements_with_sources(comfyui_reqs, frozen=True)

        # Initial UV sync to create venv (verbose to show progress)
        logger.info("Creating virtual environment...")
        env.uv_manager.sync_project(verbose=True)

        # Use GitManager for repository initialization
        git_mgr = GitManager(cec_path)
        git_mgr.initialize_environment_repo("Initial environment setup")

        # Create model symlink (should succeed now that models/ is removed)
        try:
            env.model_symlink_manager.create_symlink()
            logger.info("Model directory linked successfully")
        except Exception as e:
            logger.error(f"Failed to create model symlink: {e}")
            raise  # FATAL - environment won't work without models

        logger.info(f"Environment '{name}' created successfully")
        return env

    @staticmethod
    def import_from_bundle(
        tarball_path: Path,
        name: str,
        env_path: Path,
        workspace: Workspace
    ) -> Environment:
        """Create environment structure from tarball (extraction only).

        This creates the environment directory and extracts the .cec contents.
        The environment is NOT fully initialized - caller must call
        env.finalize_import() to complete setup.

        Args:
            tarball_path: Path to .tar.gz bundle
            name: Environment name
            env_path: Target environment directory
            workspace: Workspace instance

        Returns:
            Environment instance with .cec extracted but not fully initialized

        Raises:
            CDEnvironmentExistsError: If env_path already exists
        """
        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

        logger.info(f"Creating environment structure from bundle: {tarball_path}")

        # Create environment directory structure
        env_path.mkdir(parents=True, exist_ok=True)
        cec_path = env_path / ".cec"

        # Extract tarball to .cec
        from ..managers.export_import_manager import ExportImportManager
        manager = ExportImportManager(cec_path, env_path / "ComfyUI")
        manager.extract_import(tarball_path, cec_path)

        # Create and return Environment instance
        # NOTE: ComfyUI is not cloned yet, workflows not copied, models not resolved
        return Environment(
            name=name,
            path=env_path,
            workspace=workspace
        )

    @staticmethod
    def import_from_git(
        git_url: str,
        name: str,
        env_path: Path,
        workspace: Workspace,
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
            workspace: Workspace instance
            branch: Optional branch/tag/commit to checkout

        Returns:
            Environment instance with .cec cloned but not fully initialized

        Raises:
            CDEnvironmentExistsError: If env_path already exists
            ValueError: If git clone fails
        """
        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

        logger.info(f"Creating environment structure from git: {git_url}")

        # Create environment directory structure
        env_path.mkdir(parents=True, exist_ok=True)
        cec_path = env_path / ".cec"

        # Parse URL for subdirectory specification
        from ..utils.git import git_clone, git_clone_subdirectory, parse_git_url_with_subdir

        base_url, subdir = parse_git_url_with_subdir(git_url)

        # Clone repository to .cec (with subdirectory extraction if specified)
        if subdir:
            logger.info(f"Cloning {base_url} and extracting subdirectory '{subdir}' to {cec_path}")
            git_clone_subdirectory(base_url, cec_path, subdir, ref=branch)
            # Note: git_clone_subdirectory validates pyproject.toml internally

            # Subdirectory imports lose git history, need to init new repo
            from ..utils.git import git_init, git_remote_get_url
            if not (cec_path / ".git").exists():
                logger.info("Initializing git repository for subdirectory import")
                git_init(cec_path)

                # WARNING: Do NOT auto-add remote for subdirectory imports!
                # The base_url points to the parent repo, not a valid push target for this subdirectory.
                # User must manually set up their own remote if they want to push back to a separate repo.
                logger.warning(
                    f"Subdirectory import from {base_url}#{subdir} - no remote configured. "
                    "Set up a remote manually if you want to push changes: comfydock remote add origin <url>"
                )
        else:
            logger.info(f"Cloning {base_url} to {cec_path}")
            git_clone(base_url, cec_path, ref=branch)

            # Validate it's a ComfyDock environment (only for non-subdir imports)
            pyproject_path = cec_path / "pyproject.toml"
            if not pyproject_path.exists():
                raise ValueError(
                    "Repository does not contain pyproject.toml - not a valid ComfyDock environment"
                )

            # Auto-add the clone URL as 'origin' remote
            # Note: git clone automatically sets up 'origin', but we validate it exists
            from ..utils.git import git_remote_add, git_remote_get_url

            origin_url = git_remote_get_url(cec_path, "origin")
            if not origin_url:
                # Should not happen after git clone, but add as safety
                logger.info(f"Adding 'origin' remote: {base_url}")
                git_remote_add(cec_path, "origin", base_url)
            else:
                logger.info(f"Remote 'origin' already configured: {origin_url}")

        logger.info("Successfully prepared environment from git")

        # Create and return Environment instance
        # NOTE: ComfyUI is not cloned yet, workflows not copied, models not resolved
        return Environment(
            name=name,
            path=env_path,
            workspace=workspace
        )

    @staticmethod
    def _create_initial_pyproject(
        name: str,
        python_version: str,
        comfyui_version: str,
        comfyui_version_type: str = "branch",
        comfyui_commit_sha: str | None = None
    ) -> dict:
        """Create the initial pyproject.toml."""
        config = {
            "project": {
                "name": f"comfydock-env-{name}",
                "version": "0.1.0",
                "requires-python": f">={python_version}",
                "dependencies": []
            },
            "tool": {
                "comfydock": {
                    "comfyui_version": comfyui_version,
                    "comfyui_version_type": comfyui_version_type,
                    "comfyui_commit_sha": comfyui_commit_sha,
                    "python_version": python_version,
                    "nodes": {}
                }
            }
        }
        return config
