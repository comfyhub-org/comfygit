"""Unit tests for git-native branching CLI commands.

Tests for: checkout, branch, switch, reset, merge, revert commands.
Following TDD approach - these tests should FAIL initially.
"""
from argparse import Namespace
from unittest.mock import MagicMock, patch
import sys
from io import StringIO

import pytest

from comfygit_cli.env_commands import EnvironmentCommands
from comfygit_cli.cli import create_parser


class TestCheckoutCommand:
    """Test 'cg checkout' command handler."""

    def test_checkout_argparse_allows_branch_without_ref(self):
        """Argparse should allow `checkout -b <name>` without ref (git-native behavior)."""
        parser = create_parser()

        # This should NOT raise SystemExit (argparse error)
        # Git allows: git checkout -b feature (creates from HEAD)
        try:
            args = parser.parse_args(['checkout', '-b', 'feature'])
            assert args.branch == 'feature'
            # ref should be None or have a default value
            assert args.ref is None or args.ref == 'HEAD'
        except SystemExit as e:
            pytest.fail(f"Argparse should allow 'checkout -b <name>' without ref, but got SystemExit: {e}")

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_checkout_commit(self, mock_workspace):
        """Should call env.checkout() with ref."""
        # Setup mocks
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"
        mock_env.get_current_branch.return_value = None  # Detached HEAD

        # Create command handler
        cmd = EnvironmentCommands()

        # Create args
        args = Namespace(
            ref="abc123",
            branch=None,
            yes=False,
            force=False,
            target_env=None
        )

        # Execute
        with patch('builtins.print'):
            cmd.checkout(args)

        # Verify env.checkout was called
        assert mock_env.checkout.called
        call_args = mock_env.checkout.call_args
        assert call_args[0][0] == "abc123"  # ref
        assert call_args[1]["force"] is False

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_checkout_with_create_branch(self, mock_workspace):
        """Should call env.create_branch() and env.switch_branch() when -b is used."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            ref="main",
            branch="feature",
            yes=False,
            force=False,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.checkout(args)

        # Verify both calls
        mock_env.create_branch.assert_called_once_with("feature", start_point="main")
        mock_env.switch_branch.assert_called_once_with("feature")

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_checkout_with_force(self, mock_workspace):
        """Should pass force=True to env.checkout()."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"
        mock_env.get_current_branch.return_value = "main"

        cmd = EnvironmentCommands()
        args = Namespace(
            ref="v1",
            branch=None,
            yes=False,
            force=True,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.checkout(args)

        call_args = mock_env.checkout.call_args
        assert call_args[1]["force"] is True

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_checkout_create_branch_without_ref(self, mock_workspace):
        """Should create branch from HEAD when -b is used without ref (git-native behavior)."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            ref=None,  # No ref provided (like `cg checkout -b test`)
            branch="feature",
            yes=False,
            force=False,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.checkout(args)

        # Should create branch from HEAD (None or "HEAD" as start_point)
        mock_env.create_branch.assert_called_once()
        call_args = mock_env.create_branch.call_args
        assert call_args[0][0] == "feature"
        # start_point should be None (which core library interprets as HEAD)
        assert call_args[1]["start_point"] is None or call_args[1]["start_point"] == "HEAD"
        mock_env.switch_branch.assert_called_once_with("feature")


class TestBranchCommand:
    """Test 'cg branch' command handler."""

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_branch_list(self, mock_workspace):
        """Should call env.list_branches() when no name specified."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"
        mock_env.list_branches.return_value = [("main", True), ("feature", False)]

        cmd = EnvironmentCommands()
        args = Namespace(
            name=None,
            delete=False,
            force_delete=False,
            target_env=None
        )

        with patch('builtins.print') as mock_print:
            cmd.branch(args)

        mock_env.list_branches.assert_called_once()
        # Should print branches with * marker for current
        assert any("* main" in str(call) for call in mock_print.call_args_list)

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_branch_create(self, mock_workspace):
        """Should call env.create_branch() with name."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            name="feature",
            delete=False,
            force_delete=False,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.branch(args)

        mock_env.create_branch.assert_called_once_with("feature")

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_branch_delete(self, mock_workspace):
        """Should call env.delete_branch() with -d flag."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            name="old-feature",
            delete=True,
            force_delete=False,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.branch(args)

        mock_env.delete_branch.assert_called_once_with("old-feature", force=False)

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_branch_force_delete(self, mock_workspace):
        """Should call env.delete_branch() with force=True when -D flag."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            name="old-feature",
            delete=False,
            force_delete=True,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.branch(args)

        mock_env.delete_branch.assert_called_once_with("old-feature", force=True)


class TestSwitchCommand:
    """Test 'cg switch' command handler."""

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_switch_existing_branch(self, mock_workspace):
        """Should call env.switch_branch()."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            branch="feature",
            create=False,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.switch(args)

        mock_env.switch_branch.assert_called_once_with("feature", create=False)

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_switch_with_create(self, mock_workspace):
        """Should call env.switch_branch() with create=True."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            branch="new-feature",
            create=True,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.switch(args)

        mock_env.switch_branch.assert_called_once_with("new-feature", create=True)


class TestResetCommand:
    """Test 'cg reset' command handler."""

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_reset_hard(self, mock_workspace):
        """Should call env.reset() with mode='hard'."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            ref="HEAD",
            hard=True,
            mixed=False,
            soft=False,
            yes=True,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.reset_git(args)

        mock_env.reset.assert_called_once()
        call_args = mock_env.reset.call_args
        assert call_args[0][0] == "HEAD"
        assert call_args[1]["mode"] == "hard"
        assert call_args[1]["force"] is True

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_reset_mixed_default(self, mock_workspace):
        """Should default to mode='mixed' when no flags."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            ref="v1",
            hard=False,
            mixed=False,
            soft=False,
            yes=True,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.reset_git(args)

        call_args = mock_env.reset.call_args
        assert call_args[1]["mode"] == "mixed"

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_reset_soft(self, mock_workspace):
        """Should call env.reset() with mode='soft'."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            ref="HEAD~1",
            hard=False,
            mixed=False,
            soft=True,
            yes=True,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.reset_git(args)

        call_args = mock_env.reset.call_args
        assert call_args[1]["mode"] == "soft"


class TestMergeCommand:
    """Test 'cg merge' command handler."""

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_merge_branch(self, mock_workspace):
        """Should call env.merge_branch()."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"
        mock_env.get_current_branch.return_value = "main"

        cmd = EnvironmentCommands()
        args = Namespace(
            branch="feature",
            message=None,
            target_env=None
        )

        with patch('builtins.print'):
            cmd.merge(args)

        mock_env.merge_branch.assert_called_once_with("feature", message=None)

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_merge_with_message(self, mock_workspace):
        """Should pass custom message to env.merge_branch()."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"
        mock_env.get_current_branch.return_value = "main"

        cmd = EnvironmentCommands()
        args = Namespace(
            branch="feature",
            message="Custom merge message",
            target_env=None
        )

        with patch('builtins.print'):
            cmd.merge(args)

        mock_env.merge_branch.assert_called_once_with("feature", message="Custom merge message")

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_merge_fails_in_detached_head(self, mock_workspace):
        """Should exit with error when in detached HEAD state."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"
        mock_env.get_current_branch.return_value = None  # Detached

        cmd = EnvironmentCommands()
        args = Namespace(
            branch="feature",
            message=None,
            target_env=None
        )

        with patch('builtins.print'):
            with pytest.raises(SystemExit) as exc_info:
                cmd.merge(args)

        assert exc_info.value.code == 1
        # Should not have called merge_branch
        mock_env.merge_branch.assert_not_called()


class TestRevertCommand:
    """Test 'cg revert' command handler."""

    @patch('comfygit_cli.env_commands.get_workspace_or_exit')
    def test_revert_commit(self, mock_workspace):
        """Should call env.revert_commit()."""
        mock_env = MagicMock()
        mock_workspace.return_value.get_active_environment.return_value = mock_env
        mock_env.name = "test-env"

        cmd = EnvironmentCommands()
        args = Namespace(
            commit="abc123",
            target_env=None
        )

        with patch('builtins.print'):
            cmd.revert(args)

        mock_env.revert_commit.assert_called_once_with("abc123")
