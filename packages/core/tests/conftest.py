"""Shared fixtures for integration tests."""
import json
import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from comfydock_core.core.workspace import Workspace
from comfydock_core.core.environment import Environment

# ============================================================================
# Path Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"

@pytest.fixture(scope="session")
def workflow_fixtures(fixtures_dir):
    """Path to workflow fixture files."""
    return fixtures_dir / "workflows"

@pytest.fixture(scope="session")
def model_fixtures(fixtures_dir):
    """Path to model fixture metadata."""
    return fixtures_dir / "models"

# ============================================================================
# Workspace & Environment Fixtures
# ============================================================================

@pytest.fixture
def test_workspace(tmp_path):
    """Create isolated workspace for each test."""
    from comfydock_core.factories.workspace_factory import WorkspaceFactory

    workspace_path = tmp_path / "comfydock_workspace"

    # Use factory to create properly initialized workspace
    workspace = WorkspaceFactory.create(workspace_path)

    # Create empty node mappings file to avoid network fetch in tests
    custom_nodes_cache = workspace.paths.cache / "custom_nodes"
    custom_nodes_cache.mkdir(parents=True, exist_ok=True)
    node_mappings = custom_nodes_cache / "node_mappings.json"
    with open(node_mappings, 'w') as f:
        json.dump({"mappings": {}, "packages": {}, "stats": {}}, f)

    # Set up models directory inside workspace
    models_dir = workspace_path / "models"
    models_dir.mkdir(exist_ok=True)
    workspace.set_models_directory(models_dir)

    return workspace

@pytest.fixture
def test_env(test_workspace):
    """Create test environment with minimal setup (no actual ComfyUI clone)."""
    from comfydock_core.core.environment import Environment
    from comfydock_core.managers.git_manager import GitManager

    env_path = test_workspace.paths.environments / "test-env"
    env_path.mkdir(parents=True)

    # Create .cec directory
    cec_path = env_path / ".cec"
    cec_path.mkdir()

    # Create minimal ComfyUI structure (no actual clone)
    comfyui_path = env_path / "ComfyUI"
    comfyui_path.mkdir()
    (comfyui_path / "custom_nodes").mkdir()
    (comfyui_path / "user" / "default" / "workflows").mkdir(parents=True)

    # Create Environment instance
    env = Environment(
        name="test-env",
        path=env_path,
        workspace_paths=test_workspace.paths,
        model_repository=test_workspace.model_index_manager,
        node_mapping_repository=test_workspace.node_mapping_repository,
        workspace_config_manager=test_workspace.workspace_config_manager,
        model_downloader=test_workspace.model_downloader,
    )

    # Create minimal pyproject.toml
    config = {
        "project": {
            "name": "comfydock-env-test-env",
            "version": "0.1.0",
            "requires-python": ">=3.12",
            "dependencies": []
        },
        "tool": {
            "comfydock": {
                "comfyui_version": "test",
                "python_version": "3.12",
                "nodes": {}
            }
        }
    }
    env.pyproject.save(config)

    # Initialize git repo
    git_mgr = GitManager(cec_path)
    git_mgr.initialize_environment_repo("Initial test environment")

    return env

# ============================================================================
# Model Management Fixtures
# ============================================================================

@pytest.fixture
def test_models(test_workspace, model_fixtures):
    """Create and index test model files."""
    from comfydock_core.analyzers.model_scanner import ModelScanner
    from comfydock_core.models.shared import ModelInfo

    # Use workspace's configured models directory
    models_dir = test_workspace.workspace_config_manager.get_models_directory()

    created_models = {}

    # Load model specs
    with open(model_fixtures / "test_models.json") as f:
        model_specs = json.load(f)

    # Create each model
    for spec in model_specs:
        model = _create_test_model_file(
            models_dir=models_dir,
            filename=spec["filename"],
            relative_path=spec["path"],
            size_mb=spec.get("size_mb", 4)
        )
        created_models[spec["filename"]] = model

    # Index models
    test_workspace.sync_model_directory()

    return created_models

def _create_test_model_file(models_dir: Path, filename: str, relative_path: str, size_mb: int = 4):
    """Create a stub model file with deterministic hash."""
    # Create path
    model_path = models_dir / relative_path / filename
    model_path.parent.mkdir(parents=True, exist_ok=True)

    # Write deterministic content for reproducible hash
    content = b"TEST_MODEL_" + filename.encode() + b"\x00" * (size_mb * 1024 * 1024)
    with open(model_path, 'wb') as f:
        f.write(content)

    # Simple deterministic hash based on filename
    from hashlib import sha256
    file_hash = sha256(filename.encode()).hexdigest()[:16]

    return {
        'filename': filename,
        'hash': file_hash,
        'file_size': model_path.stat().st_size,
        'relative_path': relative_path,
        'path': model_path
    }

# ============================================================================
# Workflow Simulation Helpers
# ============================================================================

def simulate_comfyui_save_workflow(env: Environment, name: str, workflow_data):
    """Simulate ComfyUI saving a workflow to disk."""
    workflows_dir = env.comfyui_path / "user" / "default" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflows_dir / f"{name}.json"

    # Handle both dict and Path inputs
    if isinstance(workflow_data, Path):
        shutil.copy(workflow_data, workflow_file)
    else:
        with open(workflow_file, 'w') as f:
            json.dump(workflow_data, f, indent=2)

    return workflow_file

def load_workflow_fixture(workflow_fixtures: Path, name: str) -> dict:
    """Load a workflow fixture file."""
    fixture_path = workflow_fixtures / f"{name}.json"
    with open(fixture_path) as f:
        return json.load(f)

# ============================================================================
# Test Strategy Fixtures
# ============================================================================

class TestModelStrategy:
    """Model resolution strategy for tests with predefined choices."""

    def __init__(self, choices: dict[str, int]):
        """
        Args:
            choices: Map model_ref.filename -> candidate index
        """
        self.choices = choices
        self.resolutions_attempted = []

    def resolve_ambiguous_model(self, model_ref, candidates):
        self.resolutions_attempted.append(model_ref.filename)

        if model_ref.filename in self.choices:
            idx = self.choices[model_ref.filename]
            if idx < len(candidates):
                return candidates[idx]

        return None

@pytest.fixture
def auto_model_strategy():
    """Strategy that auto-selects first match for any model."""
    class AutoFirstStrategy:
        def resolve_ambiguous_model(self, model_ref, candidates):
            return candidates[0] if candidates else None

    return AutoFirstStrategy()

# ============================================================================
# ComfyUI Mocking Fixtures
# ============================================================================

def _create_fake_comfyui_structure(comfyui_path: Path) -> None:
    """Create a minimal fake ComfyUI directory structure."""
    comfyui_path.mkdir(parents=True, exist_ok=True)

    # Create essential files
    (comfyui_path / "main.py").write_text("# Fake ComfyUI main.py")
    (comfyui_path / "nodes.py").write_text("# Fake ComfyUI nodes.py")
    (comfyui_path / "folder_paths.py").write_text("# Fake ComfyUI folder_paths.py")

    # Create essential directories
    (comfyui_path / "comfy").mkdir(exist_ok=True)
    (comfyui_path / "models").mkdir(exist_ok=True)
    (comfyui_path / "custom_nodes").mkdir(exist_ok=True)
    (comfyui_path / "user" / "default" / "workflows").mkdir(parents=True, exist_ok=True)

    # Create .git directory to simulate git repo
    git_dir = comfyui_path / ".git"
    git_dir.mkdir(exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/master")
    (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0")

@pytest.fixture
def mock_comfyui_clone(monkeypatch):
    """Mock ComfyUI clone operations to avoid network calls.

    This fixture mocks the clone_comfyui function to create a fake
    ComfyUI structure instead of cloning from GitHub.
    """
    import subprocess

    def fake_clone_comfyui(target_path: Path, version: str | None = None) -> str:
        """Fake clone that creates ComfyUI structure without network."""
        _create_fake_comfyui_structure(target_path)
        return "v0.0.1-test-fake"

    monkeypatch.setattr(
        "comfydock_core.utils.comfyui_ops.clone_comfyui",
        fake_clone_comfyui
    )

    # Mock git_rev_parse to return a fake commit SHA
    def fake_git_rev_parse(repo_path: Path, ref: str) -> str:
        return "abc123def456789012345678901234567890abcd"

    monkeypatch.setattr(
        "comfydock_core.utils.git.git_rev_parse",
        fake_git_rev_parse
    )

    # Mock subprocess.run to handle uv and git commands
    original_subprocess_run = subprocess.run

    def fake_subprocess_run(cmd, *args, **kwargs):
        """Mock subprocess calls for uv and git."""
        if isinstance(cmd, list) and len(cmd) > 0:
            command = cmd[0]

            # Handle uv commands
            if command == "uv":
                # Create successful result
                result = subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="",
                    stderr=""
                )

                # Handle specific uv subcommands
                if "sync" in cmd:
                    # Create .venv if needed
                    cwd = kwargs.get('cwd', Path.cwd())
                    if isinstance(cwd, (str, Path)):
                        cwd = Path(cwd)
                        venv_path = cwd / ".venv"
                        venv_path.mkdir(exist_ok=True)
                        (venv_path / "bin").mkdir(exist_ok=True)
                        (venv_path / "bin" / "python").touch()

                return result

            # Handle git commands
            elif command == "git":
                result = subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="",
                    stderr=""
                )

                if "init" in cmd:
                    # Create .git directory
                    cwd = kwargs.get('cwd', Path.cwd())
                    if isinstance(cwd, (str, Path)):
                        cwd = Path(cwd)
                        (cwd / ".git").mkdir(exist_ok=True)

                elif "rev-parse" in cmd:
                    result.stdout = "abc123def456789012345678901234567890abcd"

                return result

        # For other commands, use original
        return original_subprocess_run(cmd, *args, **kwargs)

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    # Mock ComfyUI cache to avoid caching operations
    class FakeComfyUICacheManager:
        def __init__(self, *args, **kwargs):
            pass

        def get_cached_comfyui(self, spec):
            """Always return None (no cache hit)."""
            return None

        def cache_comfyui(self, spec, source_path):
            """No-op cache operation."""
            pass

    monkeypatch.setattr(
        "comfydock_core.caching.comfyui_cache.ComfyUICacheManager",
        FakeComfyUICacheManager
    )

    return fake_clone_comfyui

@pytest.fixture
def mock_github_api(monkeypatch):
    """Mock GitHub API calls to avoid network requests."""

    class FakeRepositoryInfo:
        def __init__(self):
            self.latest_release = "v0.3.20"
            self.default_branch = "master"

    class FakeRelease:
        def __init__(self, tag_name: str):
            self.tag_name = tag_name
            self.name = f"Release {tag_name}"

    class FakeGitHubClient:
        def get_repository_info(self, repo_url: str):
            return FakeRepositoryInfo()

        def validate_version_exists(self, repo_url: str, version: str) -> bool:
            # Accept common test versions
            return version.startswith('v') or version in ('master', 'test')

        def list_releases(self, repo_url: str, limit: int = 10):
            return [FakeRelease("v0.3.20"), FakeRelease("v0.3.19")]

    # Patch GitHubClient instantiation in resolve_comfyui_version
    original_github_client_init = None
    try:
        from comfydock_core.clients.github_client import GitHubClient
        original_github_client_init = GitHubClient.__init__

        def patched_init(self, *args, **kwargs):
            # Copy attributes from FakeGitHubClient
            fake = FakeGitHubClient()
            for attr in dir(fake):
                if not attr.startswith('_'):
                    setattr(self, attr, getattr(fake, attr))

        monkeypatch.setattr(GitHubClient, "__init__", patched_init)
    except ImportError:
        pass

    return FakeGitHubClient()

# ============================================================================
# Enhanced Fixtures for Pipeline Tests
# ============================================================================

@pytest.fixture
def model_index_builder(test_workspace):
    """Create ModelIndexBuilder for fluent model setup."""
    from helpers.model_index_builder import ModelIndexBuilder
    return ModelIndexBuilder(test_workspace)

@pytest.fixture
def pyproject_assertions(test_env):
    """Create PyprojectAssertions for fluent validation."""
    from helpers.pyproject_assertions import PyprojectAssertions
    return PyprojectAssertions(test_env)
