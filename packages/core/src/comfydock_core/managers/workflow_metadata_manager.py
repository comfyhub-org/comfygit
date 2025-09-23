"""Workflow metadata manager for simplified metadata format."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Any

if TYPE_CHECKING:
    from ..models.workflow import ModelReference
    from ..models.shared import ModelWithLocation

from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class WorkflowMetadataManager:
    """Manages simplified metadata format"""

    METADATA_KEY = "_comfydock_metadata"
    CURRENT_VERSION = "0.1.0"

    def inject_metadata(self, workflow: dict, references: List[ModelReference]) -> dict:
        """Inject metadata into workflow['extra']['_comfydock_metadata']

        Only includes resolved models to keep metadata clean.
        """
        if "extra" not in workflow:
            workflow["extra"] = {}

        metadata = {
            "version": self.CURRENT_VERSION,
            "last_updated": datetime.now().isoformat() + "Z",
            "models": {}
        }

        # Group by node, only including resolved references
        for ref in references:
            # Skip unresolved models - don't pollute metadata
            if not ref.resolved_model:
                continue

            node_key = str(ref.node_id)
            if node_key not in metadata["models"]:
                metadata["models"][node_key] = {
                    "node_type": ref.node_type,
                    "refs": []
                }

            model_data = {
                "widget_index": ref.widget_index,
                "path": ref.widget_value,
                "hash": ref.resolved_model.hash,
                "sha256": getattr(ref.resolved_model, 'sha256_hash', None),
                "blake3": getattr(ref.resolved_model, 'blake3_hash', None),
                "sources": self._get_sources(ref.resolved_model)
            }

            metadata["models"][node_key]["refs"].append(model_data)

        # Only set metadata if we have resolved models
        if metadata["models"]:
            workflow["extra"][self.METADATA_KEY] = metadata
        elif self.METADATA_KEY in workflow.get("extra", {}):
            # Clean up empty metadata
            del workflow["extra"][self.METADATA_KEY]

        return workflow

    def extract_metadata(self, workflow: dict) -> Dict[str, Any] | None:
        """Extract existing metadata if present"""
        return workflow.get("extra", {}).get(self.METADATA_KEY)

    def _get_sources(self, model: ModelWithLocation) -> List[str]:
        """Get source URLs for model if available"""
        sources = []
        if hasattr(model, 'metadata') and model.metadata:
            if 'civitai_id' in model.metadata:
                sources.append(f"civitai:{model.metadata['civitai_id']}")
            if 'huggingface_url' in model.metadata:
                sources.append(f"huggingface:{model.metadata['huggingface_url']}")
        return sources