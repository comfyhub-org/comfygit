"""Workflow content hashing for cache invalidation.

Provides content-based hashing of workflow JSON with normalization
to ignore volatile fields like UI state and random seeds.
"""
import copy
import json
from pathlib import Path

import blake3


def compute_workflow_hash(workflow_path: Path) -> str:
    """Compute content hash for a workflow file.

    Uses blake3 for fast hashing and normalization to ignore
    volatile fields (UI state, random seeds, etc.).

    Args:
        workflow_path: Path to workflow JSON file

    Returns:
        16-character hex hash string (64-bit)

    Examples:
        >>> compute_workflow_hash(Path("my_workflow.json"))
        "a1b2c3d4e5f6g7h8"
    """
    # Note: Using direct json.load() rather than WorkflowRepository for performance
    # and separation of concerns (hashing != parsing). This is intentional.
    # Load workflow JSON
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # Normalize to remove volatile fields
    normalized = normalize_workflow(workflow)

    # Serialize with sorted keys for determinism
    normalized_json = json.dumps(normalized, sort_keys=True, separators=(',', ':'))

    # Compute blake3 hash
    hasher = blake3.blake3()
    hasher.update(normalized_json.encode('utf-8'))

    # Return first 16 hex chars (64-bit hash)
    return hasher.hexdigest()[:16]

def normalize_workflow(workflow: dict) -> dict:
    """Remove volatile fields that don't affect workflow functionality.

    Strips:
    - UI state (extra.ds - pan/zoom)
    - Frontend version (extra.frontendVersion)
    - Revision counter (revision)
    - Auto-generated seeds (when randomize/increment mode is set)

    Args:
        workflow: Raw workflow dict

    Returns:
        Normalized workflow dict
    """
    normalized = copy.deepcopy(workflow)

    # Remove UI state fields
    if 'extra' in normalized:
        normalized['extra'].pop('ds', None)  # Pan/zoom state
        normalized['extra'].pop('frontendVersion', None)  # Frontend version

    # Remove revision counter
    normalized.pop('revision', None)

    # Normalize nodes - remove auto-generated seed values when randomize is set
    if 'nodes' in normalized:
        for node in normalized['nodes']:
            if isinstance(node, dict):
                node_type = node.get('type', '')

                # For sampler nodes with randomize mode, normalize seed to fixed value
                if node_type in ('KSampler', 'KSamplerAdvanced', 'SamplerCustom'):
                    # widgets_values format: [seed, control_after_generate, steps, cfg, ...]
                    widgets_values = node.get('widgets_values', [])
                    if len(widgets_values) >= 2 and widgets_values[1] in ('randomize', 'increment'):
                        widgets_values[0] = 0  # Normalize to fixed value

                    api_widget_values = node.get('api_widget_values', [])
                    if len(api_widget_values) >= 2 and api_widget_values[1] in ('randomize', 'increment'):
                        api_widget_values[0] = 0  # Normalize to fixed value

    return normalized
