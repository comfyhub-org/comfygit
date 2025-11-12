"""Model configuration loader and utilities."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .comfyui_models import COMFYUI_MODELS_CONFIG
from ..logging.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ModelConfig:
    """ComfyUI model configuration."""
    version: str
    default_extensions: list[str]
    standard_directories: list[str]
    directory_overrides: dict[str, dict[str, Any]]
    node_directory_mappings: dict[str, list[str]]
    node_widget_indices: dict[str, int]

    @classmethod
    def load(cls, config_path: Path | None = None) -> "ModelConfig":
        """Load model configuration from file.

        Args:
            config_path: Path to config file, or None to use default

        Returns:
            ModelConfig instance
        """
        data = {}
        if config_path is None:
            # Load hardcoded config (fallback)
            data = COMFYUI_MODELS_CONFIG
        else:
            if not config_path.exists():
                raise FileNotFoundError(f"Model config file not found: {config_path}")
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load model config from {config_path}: {e}")
                raise

        return cls(
            version=data.get("version", "unknown"),
            default_extensions=data.get("default_extensions", []),
            standard_directories=data.get("standard_directories", []),
            directory_overrides=data.get("directory_overrides", {}),
            node_directory_mappings=data.get("node_directory_mappings", {}),
            node_widget_indices=data.get("node_widget_indices", {})
        )

    def get_extensions_for_directory(self, directory: str) -> list[str]:
        """Get file extensions for a specific directory.

        Args:
            directory: Directory name (e.g., "checkpoints")

        Returns:
            List of supported extensions for this directory
        """
        if directory in self.directory_overrides:
            override = self.directory_overrides[directory]
            if "extensions" in override:
                return override["extensions"]

        return self.default_extensions

    def is_standard_directory(self, directory: str) -> bool:
        """Check if a directory is a standard ComfyUI directory.

        Args:
            directory: Directory name to check

        Returns:
            True if it's a standard directory, False for custom
        """
        return directory in self.standard_directories

    def is_model_file(self, file_path: Path) -> bool:
        """Check if a file is a potential model file based on extension.

        Args:
            file_path: Path to file to check

        Returns:
            True if file has a model extension
        """
        extension = file_path.suffix.lower()

        # Get directory from path to check for specific extensions
        parts = file_path.parts
        for part in parts:
            if self.is_standard_directory(part):
                return extension in self.get_extensions_for_directory(part)

        # Default to checking against default extensions
        return extension in self.default_extensions

    def get_directories_for_node(self, node_type: str) -> list[str]:
        """Get model directories for a node type.

        Args:
            node_type: ComfyUI node type (e.g., "LoraLoader")

        Returns:
            List of directories this node type loads from
        """
        return self.node_directory_mappings.get(node_type, [])

    def get_widget_index_for_node(self, node_type: str) -> int:
        """Get widget index containing model path for a node type.

        Args:
            node_type: ComfyUI node type

        Returns:
            Index in widgets_values containing the model path (defaults to 0)
        """
        return self.node_widget_indices.get(node_type, 0)

    def is_model_loader_node(self, node_type: str) -> bool:
        """Check if a node type is a known model loader.

        Args:
            node_type: ComfyUI node type

        Returns:
            True if node type loads models
        """
        return node_type in self.node_directory_mappings

    def reconstruct_model_path(self, node_type: str, widget_value: str) -> list[str]:
        """Reconstruct full model paths from node type and widget value.

        Args:
            node_type: ComfyUI node type
            widget_value: Value from node's widgets_values

        Returns:
            List of possible full relative paths
        """
        directories = self.get_directories_for_node(node_type)
        if not directories:
            return []

        return [f"{directory}/{widget_value}" for directory in directories]