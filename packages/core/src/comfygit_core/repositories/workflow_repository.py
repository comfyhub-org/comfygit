"""Repository for workflow file operations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from ..models.workflow import Workflow

logger = get_logger(__name__)


class WorkflowRepository:
    """Repository for workflow file operations."""

    @staticmethod
    def load(path: Path) -> Workflow:
        """Load workflow from file."""
        from ..models.workflow import Workflow

        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            return Workflow.from_json(data)
        except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to load workflow {path}: {e}") from e

    @staticmethod
    def load_raw_text(path: Path) -> str:
        """Load raw workflow text for string matching."""
        try:
            with open(path, encoding='utf-8') as f:
                return f.read()
        except (FileNotFoundError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to load workflow text {path}: {e}") from e

    @staticmethod
    def load_raw_json(path: Path) -> dict:
        """Load raw workflow JSON."""
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to load workflow JSON {path}: {e}") from e

    @staticmethod
    def save(workflow: Workflow, path: Path) -> None:
        """Save workflow to file."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(workflow.to_json(), f, indent=2)
        except (OSError, UnicodeEncodeError) as e:
            raise ValueError(f"Failed to save workflow {path}: {e}") from e
