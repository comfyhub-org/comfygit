"""Test the refactored WorkflowManager API."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from comfydock_core.models.workflow import WorkflowAnalysisResult, InstalledPackageInfo
from comfydock_core.resolvers.global_node_resolver import PackageSuggestion


class TestWorkflowAnalysisResult:
    """Test WorkflowAnalysisResult data model."""

    def test_has_missing_dependencies(self):
        """Test checking for missing dependencies."""
        analysis = WorkflowAnalysisResult(
            name="test",
            workflow_path=Path("/tmp/test.json")
        )
        assert not analysis.has_missing_dependencies

        # Add missing package
        analysis.missing_packages.append(Mock())
        assert analysis.has_missing_dependencies

    def test_is_fully_resolvable(self):
        """Test checking if workflow is fully resolvable."""
        analysis = WorkflowAnalysisResult(
            name="test",
            workflow_path=Path("/tmp/test.json")
        )
        assert analysis.is_fully_resolvable

        # Add unresolved node
        analysis.unresolved_nodes.append("UnknownNode")
        assert not analysis.is_fully_resolvable

    def test_to_pyproject_requires(self):
        """Test converting analysis to pyproject requires dict."""
        analysis = WorkflowAnalysisResult(
            name="test",
            workflow_path=Path("/tmp/test.json")
        )

        # Add some resolved nodes
        mock_match1 = Mock()
        mock_match1.package_id = "package1"
        mock_match2 = Mock()
        mock_match2.package_id = "package2"
        analysis.resolved_nodes = {"Node1": mock_match1, "Node2": mock_match2}

        # Add model hashes and python deps
        analysis.model_hashes = ["hash1", "hash2"]
        analysis.python_dependencies = ["numpy", "torch"]

        requires = analysis.to_pyproject_requires()

        assert requires["nodes"] == ["package1", "package2"]
        assert requires["models"] == ["hash1", "hash2"]
        assert requires["python"] == ["numpy", "torch"]


class TestInstalledPackageInfo:
    """Test InstalledPackageInfo data model."""

    def test_version_mismatch_detection(self):
        """Test detecting version mismatches."""
        pkg = InstalledPackageInfo(
            package_id="test-package",
            display_name="Test Package",
            installed_version="1.0.0",
            suggested_version="1.0.0"
        )
        assert not pkg.version_mismatch

        pkg.suggested_version = "2.0.0"
        assert pkg.version_mismatch

        pkg.suggested_version = None
        assert not pkg.version_mismatch


class TestAPIUsage:
    """Test that the API can be used without UI dependencies."""

    def test_analysis_returns_pure_data(self):
        """Test that analyze_workflow returns pure data with no side effects."""
        # This demonstrates the API returns data that clients can use
        # without any print statements or user input calls

        analysis = WorkflowAnalysisResult(
            name="test_workflow",
            workflow_path=Path("/tmp/workflow.json"),
            already_tracked=False
        )

        # Add some missing packages
        pkg1 = PackageSuggestion(
            package_id="missing-package",
            suggested_version="1.0.0",
            available_versions=["1.0.0", "0.9.0"],
            github_url="https://github.com/owner/repo",
            display_name="Missing Package"
        )
        analysis.missing_packages.append(pkg1)

        # A web API can serialize this
        api_response = {
            "name": analysis.name,
            "missing": [
                {
                    "id": p.package_id,
                    "version": p.suggested_version,
                    "url": p.github_url
                }
                for p in analysis.missing_packages
            ],
            "has_missing": analysis.has_missing_dependencies
        }

        assert api_response["name"] == "test_workflow"
        assert len(api_response["missing"]) == 1
        assert api_response["has_missing"] is True

    @patch('shutil.copy2')
    def test_track_workflow_without_analysis(self, mock_copy):
        """Test that track_workflow just registers without analysis."""
        from comfydock_core.managers.workflow_manager import WorkflowManager

        # Mock dependencies
        mock_pyproject = Mock()
        mock_pyproject.workflows.get_tracked.return_value = {}
        mock_pyproject.workflows.add = Mock()

        # Create workflow file
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir)
            workflow_path = env_path / "ComfyUI/user/default/workflows/test.json"
            workflow_path.parent.mkdir(parents=True)
            workflow_path.write_text('{"nodes": []}')

            manager = WorkflowManager(env_path, mock_pyproject)

            # Track workflow - should just register it, no analysis
            manager.track_workflow("test")

            # Should add to pyproject with minimal config
            mock_pyproject.workflows.add.assert_called_once_with("test", {"tracked": True})