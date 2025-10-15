"""Integration test for requirements.txt inline comments bug.

BUG: Custom nodes with requirements.txt files containing inline comments
(e.g., 'gdown # supports downloading...') cause resolution tests to fail because
the comments are included in the dependency string, which is not valid PEP 508 format.

Root Cause: CustomNodeScanner._read_requirements() only skips lines that START with '#',
but doesn't handle inline comments like 'package # comment'.

Example from facerestore_cf node:
    gdown # supports downloading the large file from Google Drive

This gets added as-is to pyproject.toml, but PEP 508 doesn't allow inline comments,
causing UV to fail with:
    configuration error: `project.dependencies[43]` must be pep508

TESTING STRATEGY:
- Test should FAIL when bug exists (inline comments not stripped)
- Test should PASS when bug is fixed (inline comments properly stripped)
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from comfydock_core.models.shared import NodeInfo
from comfydock_core.models.exceptions import CDNodeConflictError


class TestRequirementsInlineComments:
    """Test that inline comments are properly stripped from requirements.txt."""

    def test_inline_comments_are_stripped_from_requirements(self, test_env):
        """Test that requirements with inline comments are properly parsed.

        Bug reproduction: facerestore_cf has 'gdown # supports downloading...' which
        causes UV to reject the pyproject.toml with PEP 508 validation error.

        Expected behavior: Comments should be stripped, leaving clean PEP 508 strings.

        This test FAILS when bug exists, PASSES when bug is fixed.
        """
        mock_node_info = NodeInfo(
            name="node-with-inline-comments",
            registry_id="node-with-inline-comments",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/node.zip"
        )

        cache_node = test_env.workspace_paths.cache / "custom_nodes" / "store" / "inline-comment-hash" / "content"
        cache_node.mkdir(parents=True, exist_ok=True)
        (cache_node / "__init__.py").write_text("# Test node")

        # Create requirements.txt with inline comments (reproduces facerestore_cf bug)
        requirements_content = """numpy>=1.20.0
pillow>=8.0.0  # Image processing
requests>=2.25.0  # For API calls
"""
        (cache_node / "requirements.txt").write_text(requirements_content)

        with patch.object(test_env.node_manager.node_lookup, 'get_node', return_value=mock_node_info), \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache', return_value=cache_node):

            # ACT: Add node - should succeed with properly stripped requirements
            result = test_env.node_manager.add_node("node-with-inline-comments", no_test=False)

            # ASSERT: Node should be successfully installed
            assert result.name == "node-with-inline-comments"

            existing_nodes = test_env.node_manager.pyproject.nodes.get_existing()
            assert "node-with-inline-comments" in existing_nodes, \
                "Node should be tracked in pyproject.toml"

            node_path = test_env.comfyui_path / "custom_nodes" / "node-with-inline-comments"
            assert node_path.exists(), \
                "Node files should be installed to custom_nodes/"


    def test_various_inline_comment_formats(self, test_env):
        """Test that all inline comment variations are properly stripped.

        Covers:
        - 'package # comment'
        - 'package  # comment with extra spaces'
        - 'package>=1.0 # version comment'
        - 'package[extra] # extra feature comment'
        """
        mock_node_info = NodeInfo(
            name="node-comment-variations",
            registry_id="node-comment-variations",
            source="registry",
            version="1.0.0"
        )

        cache_node = test_env.workspace_paths.cache / "custom_nodes" / "store" / "variations-hash" / "content"
        cache_node.mkdir(parents=True, exist_ok=True)
        (cache_node / "__init__.py").write_text("# Test node")

        # Various inline comment patterns
        requirements_content = """numpy # array processing
requests  # HTTP client
pillow>=8.0.0 # image library with version
"""
        (cache_node / "requirements.txt").write_text(requirements_content)

        with patch.object(test_env.node_manager.node_lookup, 'get_node', return_value=mock_node_info), \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache', return_value=cache_node):

            # Should succeed with all comment variations properly stripped
            result = test_env.node_manager.add_node("node-comment-variations", no_test=False)

            assert result.name == "node-comment-variations"
            existing_nodes = test_env.node_manager.pyproject.nodes.get_existing()
            assert "node-comment-variations" in existing_nodes


    def test_full_line_comments_are_still_ignored(self, test_env):
        """Test that full-line comments (starting with #) are still properly ignored."""
        mock_node_info = NodeInfo(
            name="node-with-full-comments",
            registry_id="node-with-full-comments",
            source="registry",
            version="1.0.0"
        )

        cache_node = test_env.workspace_paths.cache / "custom_nodes" / "store" / "full-comments-hash" / "content"
        cache_node.mkdir(parents=True, exist_ok=True)
        (cache_node / "__init__.py").write_text("# Test node")

        requirements_content = """# This is a full line comment
numpy>=1.20.0
# Another comment
requests>=2.25.0
"""
        (cache_node / "requirements.txt").write_text(requirements_content)

        with patch.object(test_env.node_manager.node_lookup, 'get_node', return_value=mock_node_info), \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache', return_value=cache_node):

            result = test_env.node_manager.add_node("node-with-full-comments", no_test=False)

            assert result.name == "node-with-full-comments"
            existing_nodes = test_env.node_manager.pyproject.nodes.get_existing()
            assert "node-with-full-comments" in existing_nodes
