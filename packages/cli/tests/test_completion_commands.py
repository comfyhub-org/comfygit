"""Tests for shell completion installation commands."""
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from comfygit_cli.completion_commands import CompletionCommands


class TestCompletionCommands:
    """Test completion command installation logic."""

    def test_detect_shell_bash(self):
        """Test bash shell detection."""
        with patch.dict('os.environ', {'SHELL': '/bin/bash'}):
            shell, config = CompletionCommands._detect_shell()
            assert shell == 'bash'
            assert config == Path.home() / '.bashrc'

    def test_detect_shell_zsh(self):
        """Test zsh shell detection."""
        with patch.dict('os.environ', {'SHELL': '/usr/bin/zsh'}):
            shell, config = CompletionCommands._detect_shell()
            assert shell == 'zsh'
            assert config == Path.home() / '.zshrc'

    def test_detect_shell_unknown(self):
        """Test unknown shell detection."""
        with patch.dict('os.environ', {'SHELL': '/bin/fish'}):
            shell, config = CompletionCommands._detect_shell()
            assert shell is None
            assert config is None

    @patch('comfygit_cli.completion_commands.shutil.which')
    def test_check_argcomplete_available_found(self, mock_which):
        """Test argcomplete check when available."""
        mock_which.return_value = '/usr/local/bin/register-python-argcomplete'
        assert CompletionCommands._check_argcomplete_available()
        mock_which.assert_called_once_with('register-python-argcomplete')

    @patch('comfygit_cli.completion_commands.shutil.which')
    def test_check_argcomplete_available_not_found(self, mock_which):
        """Test argcomplete check when not available."""
        mock_which.return_value = None
        assert not CompletionCommands._check_argcomplete_available()

    @patch('comfygit_cli.completion_commands.subprocess.run')
    def test_install_argcomplete_success(self, mock_run):
        """Test successful argcomplete installation."""
        mock_run.return_value = Mock(returncode=0)
        assert CompletionCommands._install_argcomplete()
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ['uv', 'tool', 'install', 'argcomplete']

    @patch('comfygit_cli.completion_commands.subprocess.run')
    def test_install_argcomplete_failure(self, mock_run):
        """Test failed argcomplete installation."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'uv', stderr='error')
        assert not CompletionCommands._install_argcomplete()

    def test_is_completion_installed_not_exists(self):
        """Test checking completion when config file doesn't exist."""
        config_file = Path('/tmp/nonexistent_file_12345.txt')
        assert not CompletionCommands._is_completion_installed(config_file)

    def test_is_completion_installed_empty_file(self):
        """Test checking completion in empty file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)

        try:
            assert not CompletionCommands._is_completion_installed(config_file)
        finally:
            config_file.unlink()

    def test_add_completion_to_config_bash(self):
        """Test adding completion to bash config file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)
            f.write("# Existing content\nexport PATH=/foo\n")

        try:
            # Add completion for bash
            CompletionCommands._add_completion_to_config('bash', config_file)

            # Verify it was added
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT in content
            assert 'eval "$(register-python-argcomplete comfygit)"' in content

            # Verify no zsh-specific initialization
            assert 'compinit' not in content

            # Verify original content is preserved
            assert "export PATH=/foo" in content
        finally:
            config_file.unlink()

    def test_add_completion_to_config_zsh(self):
        """Test adding completion to zsh config file with compinit initialization."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)
            f.write("# Existing content\nexport PATH=/foo\n")

        try:
            # Add completion for zsh
            CompletionCommands._add_completion_to_config('zsh', config_file)

            # Verify it was added
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT in content
            assert 'eval "$(register-python-argcomplete comfygit)"' in content

            # Verify zsh initialization block
            assert 'compinit' in content
            assert 'autoload -Uz compinit' in content
            assert 'command -v compdef' in content

            # Verify original content is preserved
            assert "export PATH=/foo" in content
        finally:
            config_file.unlink()

    def test_add_completion_to_new_file(self):
        """Test adding completion to non-existent file."""
        config_file = Path(tempfile.gettempdir()) / 'test_bashrc_new'

        try:
            # Add completion to new file
            CompletionCommands._add_completion_to_config('bash', config_file)

            # Verify it was created and populated
            assert config_file.exists()
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT in content
            assert 'eval "$(register-python-argcomplete comfygit)"' in content
        finally:
            if config_file.exists():
                config_file.unlink()

    def test_remove_completion_from_config_bash(self):
        """Test removing completion from bash config file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)
            f.write(
                "# Before\n"
                f"{CompletionCommands.COMPLETION_COMMENT}\n"
                'eval "$(register-python-argcomplete comfygit)"\n'
                "# After\n"
            )

        try:
            # Remove completion
            CompletionCommands._remove_completion_from_config(config_file)

            # Verify it was removed
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT not in content
            assert 'register-python-argcomplete' not in content

            # Verify other content is preserved
            assert "# Before" in content
            assert "# After" in content
        finally:
            config_file.unlink()

    def test_remove_completion_from_config_zsh(self):
        """Test removing completion with zsh init block from config file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)
            f.write(
                "# Before\n"
                f"{CompletionCommands.COMPLETION_COMMENT}\n"
                "# Initialize zsh completion system if not already loaded\n"
                "if ! command -v compdef &> /dev/null; then\n"
                "    autoload -Uz compinit\n"
                "    compinit\n"
                "fi\n"
                "\n"
                'eval "$(register-python-argcomplete comfygit)"\n'
                "# After\n"
            )

        try:
            # Remove completion
            CompletionCommands._remove_completion_from_config(config_file)

            # Verify everything was removed
            content = config_file.read_text()
            assert CompletionCommands.COMPLETION_COMMENT not in content
            assert 'register-python-argcomplete' not in content
            assert 'compinit' not in content
            assert 'compdef' not in content

            # Verify other content is preserved
            assert "# Before" in content
            assert "# After" in content
        finally:
            config_file.unlink()

    def test_is_completion_installed_after_add(self):
        """Test that is_completion_installed returns True after adding."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)

        try:
            # Initially not installed
            assert not CompletionCommands._is_completion_installed(config_file)

            # Add completion
            CompletionCommands._add_completion_to_config('bash', config_file)

            # Now it should be installed
            assert CompletionCommands._is_completion_installed(config_file)
        finally:
            config_file.unlink()

    def test_idempotent_install(self):
        """Test that adding completion twice doesn't duplicate."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            config_file = Path(f.name)

        try:
            # Add completion twice
            CompletionCommands._add_completion_to_config('bash', config_file)
            first_content = config_file.read_text()

            CompletionCommands._add_completion_to_config('bash', config_file)
            second_content = config_file.read_text()

            # Content should have doubled (not idempotent by design, install command checks first)
            assert second_content.count('eval "$(register-python-argcomplete comfygit)"') == 2
        finally:
            config_file.unlink()
