"""Unit tests for ModelDownloader service."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from comfydock_core.services.model_downloader import (
    ModelDownloader,
    DownloadRequest,
    DownloadResult,
)


class TestModelDownloader:
    """Test ModelDownloader service."""

    def test_download_request_creation(self):
        """Test creating a DownloadRequest."""
        request = DownloadRequest(
            url="https://example.com/model.safetensors",
            target_path=Path("/models/checkpoints/model.safetensors"),
            workflow_name="test_workflow"
        )

        assert request.url == "https://example.com/model.safetensors"
        assert request.target_path == Path("/models/checkpoints/model.safetensors")
        assert request.workflow_name == "test_workflow"

    def test_download_result_success(self):
        """Test successful DownloadResult."""
        result = DownloadResult(
            success=True,
            model=None,
            error=None
        )

        assert result.success is True
        assert result.model is None
        assert result.error is None

    def test_download_result_failure(self):
        """Test failed DownloadResult."""
        result = DownloadResult(
            success=False,
            model=None,
            error="Connection timeout"
        )

        assert result.success is False
        assert result.error == "Connection timeout"

    def test_detect_url_type_civitai(self, tmp_path):
        """Test detecting CivitAI URLs."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        assert downloader.detect_url_type("https://civitai.com/api/download/models/123") == "civitai"
        assert downloader.detect_url_type("https://civitai.com/models/456") == "civitai"

    def test_detect_url_type_huggingface(self, tmp_path):
        """Test detecting HuggingFace URLs."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        assert downloader.detect_url_type("https://huggingface.co/user/model/blob/main/file.safetensors") == "huggingface"
        assert downloader.detect_url_type("https://hf.co/model/file") == "huggingface"

    def test_detect_url_type_custom(self, tmp_path):
        """Test detecting custom/direct URLs."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        assert downloader.detect_url_type("https://example.com/model.safetensors") == "custom"
        assert downloader.detect_url_type("https://cdn.example.org/files/model.ckpt") == "custom"

    def test_suggest_path_with_known_node(self, tmp_path):
        """Test path suggestion for known loader nodes."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        # CheckpointLoader should suggest checkpoints/
        path = downloader.suggest_path(
            url="https://example.com/sd15.safetensors",
            node_type="CheckpointLoaderSimple",
            filename_hint="sd15.safetensors"
        )

        assert path == Path("checkpoints/sd15.safetensors")

    def test_suggest_path_with_lora_loader(self, tmp_path):
        """Test path suggestion for LoraLoader."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        path = downloader.suggest_path(
            url="https://example.com/style.safetensors",
            node_type="LoraLoader",
            filename_hint="style.safetensors"
        )

        assert path == Path("loras/style.safetensors")

    def test_suggest_path_extracts_filename_from_url(self, tmp_path):
        """Test extracting filename from URL path."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        path = downloader.suggest_path(
            url="https://example.com/downloads/model.safetensors",
            node_type="CheckpointLoaderSimple",
            filename_hint=None
        )

        # Should extract "model.safetensors" from URL
        assert path.name == "model.safetensors"
        assert str(path).startswith("checkpoints/")

    def test_download_checks_existing_url(self, tmp_path):
        """Test that download checks for existing models by URL before downloading."""
        from comfydock_core.models.shared import ModelWithLocation

        repo = Mock()
        existing_model = ModelWithLocation(
            hash="abc123",
            file_size=1024000,
            blake3_hash="abc123def456",
            sha256_hash=None,
            relative_path="checkpoints/existing.safetensors",
            filename="existing.safetensors",
            mtime=1234567890.0,
            last_seen=1234567890,
            metadata={}
        )
        repo.find_by_source_url.return_value = existing_model

        downloader = ModelDownloader(repo, tmp_path)
        request = DownloadRequest(
            url="https://example.com/model.safetensors",
            target_path=tmp_path / "checkpoints/model.safetensors"
        )

        # Download should check for existing URL and return it
        result = downloader.download(request)

        repo.find_by_source_url.assert_called_once_with("https://example.com/model.safetensors")
        assert result.success is True
        assert result.model == existing_model

    @patch('requests.get')
    def test_download_new_model_success(self, mock_get, tmp_path):
        """Test downloading a new model successfully."""
        # Setup mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-length': '1024'}
        mock_response.iter_content = Mock(return_value=[b"test" * 256])
        mock_get.return_value = mock_response

        # Setup repository mock
        repo = Mock()
        repo.find_by_source_url.return_value = None  # No existing model

        downloader = ModelDownloader(repo, tmp_path)
        target_path = tmp_path / "checkpoints/new_model.safetensors"
        request = DownloadRequest(
            url="https://example.com/new_model.safetensors",
            target_path=target_path
        )

        result = downloader.download(request)

        # Verify HTTP request was made
        mock_get.assert_called_once_with(
            "https://example.com/new_model.safetensors",
            stream=True,
            timeout=300
        )

        # Verify file was created
        assert target_path.exists()

        # Verify model was indexed
        assert repo.ensure_model.called
        assert repo.add_location.called
        assert repo.add_source.called

        assert result.success is True
        assert result.model is not None
        assert result.error is None

    @patch('requests.get')
    def test_download_handles_http_errors(self, mock_get, tmp_path):
        """Test download handles HTTP errors gracefully."""
        # Setup mock to raise exception
        mock_get.side_effect = Exception("Connection timeout")

        repo = Mock()
        repo.find_by_source_url.return_value = None

        downloader = ModelDownloader(repo, tmp_path)
        request = DownloadRequest(
            url="https://example.com/model.safetensors",
            target_path=tmp_path / "checkpoints/model.safetensors"
        )

        result = downloader.download(request)

        assert result.success is False
        assert "Connection timeout" in result.error
        assert result.model is None

    @patch('requests.get')
    def test_download_computes_hash_during_download(self, mock_get, tmp_path):
        """Test that hash is computed during download (streaming)."""
        # Setup mock with known content
        test_content = b"test_model_content" * 1000
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-length': str(len(test_content))}

        # Split into chunks for streaming
        chunk_size = 8192
        chunks = [test_content[i:i+chunk_size] for i in range(0, len(test_content), chunk_size)]
        mock_response.iter_content = Mock(return_value=chunks)
        mock_get.return_value = mock_response

        repo = Mock()
        repo.find_by_source_url.return_value = None
        repo.calculate_short_hash.return_value = "abc123def456"  # Mock short hash

        downloader = ModelDownloader(repo, tmp_path)
        target_path = tmp_path / "checkpoints/test.safetensors"
        request = DownloadRequest(
            url="https://example.com/test.safetensors",
            target_path=target_path
        )

        result = downloader.download(request)

        assert result.success is True

        # Verify ensure_model was called with hash
        assert repo.ensure_model.called
        call_kwargs = repo.ensure_model.call_args[1]
        assert 'hash' in call_kwargs  # Hash should be provided
        assert call_kwargs['hash'] == "abc123def456"

    def test_download_uses_temp_file_then_atomic_move(self, tmp_path):
        """Test that download uses temp file and atomic move for safety."""
        # This test will be implemented when we add the actual download logic
        # For now, just verify the pattern is intended
        pass

    def test_suggest_path_without_node_type_uses_hint(self, tmp_path):
        """Test path suggestion falls back to filename hint when node type unknown."""
        repo = Mock()
        downloader = ModelDownloader(repo, tmp_path)

        # Unknown node type - should use filename hint directly
        path = downloader.suggest_path(
            url="https://example.com/file.safetensors",
            node_type=None,
            filename_hint="models/custom/file.safetensors"
        )

        # Should use the hint path
        assert "file.safetensors" in str(path)
