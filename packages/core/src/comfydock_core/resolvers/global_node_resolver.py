"""Global node resolver using prebuilt mappings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, List
from urllib.parse import urlparse

from ..models.node_mapping import (
    GlobalNodeMapping,
    GlobalNodeMappings,
    GlobalNodeMappingsStats,
    GlobalNodePackage,
    GlobalNodePackageVersion
)

if TYPE_CHECKING:
    from comfydock_core.models.workflow import (
        NodeInput,
        WorkflowNode,
        ResolvedNodePackage,
        NodeResolutionResult,
    )

from ..logging.logging_config import get_logger
from ..utils.input_signature import create_node_key, normalize_workflow_inputs

logger = get_logger(__name__)


class GlobalNodeResolver:
    """Resolves unknown nodes using global mappings file."""

    def __init__(self, mappings_path: Path):
        self.mappings_path = mappings_path
        self.global_mappings, self.github_to_registry = self._load_mappings()

    def _load_mappings(self) -> tuple[GlobalNodeMappings, dict[str, GlobalNodePackage]]:
        """Load global mappings from file."""
        if not self.mappings_path.exists():
            logger.warning(f"Global mappings file not found: {self.mappings_path}")
            raise FileNotFoundError

        try:
            with open(self.mappings_path) as f:
                data = json.load(f)

            # Load into GlobalNodeMappings dataclass
            stats_data = data.get("stats", {})
            stats = GlobalNodeMappingsStats(
                packages=stats_data.get("packages"),
                signatures=stats_data.get("signatures"),
                total_nodes=stats_data.get("total_nodes"),
                augmented=stats_data.get("augmented"),
                augmentation_date=stats_data.get("augmentation_date"),
                nodes_from_manager=stats_data.get("nodes_from_manager"),
                synthetic_packages=stats_data.get("synthetic_packages"),
            )

            # Convert mappings dict to GlobalNodeMapping objects
            mappings = {}
            for key, mapping_data in data.get("mappings", {}).items():
                mappings[key] = GlobalNodeMapping(
                    id=key,
                    package_id=mapping_data.get("package_id", ""),
                    versions=mapping_data.get("versions", []),
                    source=mapping_data.get("source"),
                )

            # Convert packages dict to GlobalNodePackage objects
            packages = {}
            for pkg_id, pkg_data in data.get("packages", {}).items():
                # Loop over versions and create global node package version objects
                versions: dict[str, GlobalNodePackageVersion] = {}
                pkg_versions = pkg_data.get("versions", {})
                for version_id, version_data in pkg_versions.items():
                    version = GlobalNodePackageVersion(
                        version=version_id,
                        changelog=version_data.get("changelog"),
                        release_date=version_data.get("release_date"),
                        dependencies=version_data.get("dependencies"),
                        deprecated=version_data.get("deprecated"),
                        download_url=version_data.get("download_url"),
                        status=version_data.get("status"),
                        supported_accelerators=version_data.get("supported_accelerators"),
                        supported_comfyui_version=version_data.get("supported_comfyui_version"),
                        supported_os=version_data.get("supported_os"),
                    )
                    versions[version_id] = version

                packages[pkg_id] = GlobalNodePackage(
                    id=pkg_id,
                    display_name=pkg_data.get("display_name"),
                    author=pkg_data.get("author"),
                    description=pkg_data.get("description"),
                    repository=pkg_data.get("repository"),
                    downloads=pkg_data.get("downloads"),
                    github_stars=pkg_data.get("github_stars"),
                    rating=pkg_data.get("rating"),
                    license=pkg_data.get("license"),
                    category=pkg_data.get("category"),
                    tags=pkg_data.get("tags"),
                    status=pkg_data.get("status"),
                    created_at=pkg_data.get("created_at"),
                    versions=versions,
                    synthetic=pkg_data.get("synthetic", False),
                    source=pkg_data.get("source"),
                )

            global_mappings = GlobalNodeMappings(
                version=data.get("version", "unknown"),
                generated_at=data.get("generated_at", ""),
                stats=stats,
                mappings=mappings,
                packages=packages,
            )

            github_to_registry = self._build_github_to_registry_map(global_mappings)

            if stats:
                logger.info(
                    f"Loaded global mappings: {stats.signatures} signatures "
                    f"from {stats.packages} packages, "
                    f"{len(github_to_registry)} GitHub URLs"
                )

            return global_mappings, github_to_registry

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load global mappings: {e}")
            raise e

    def _normalize_github_url(self, url: str) -> str:
        """Normalize GitHub URL to canonical form."""
        if not url:
            return ""

        # Remove .git suffix
        url = re.sub(r"\.git$", "", url)

        # Parse URL
        parsed = urlparse(url)

        # Handle different GitHub URL formats
        if parsed.hostname in ("github.com", "www.github.com"):
            # Extract owner/repo from path
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                owner, repo = path_parts[0], path_parts[1]
                return f"https://github.com/{owner}/{repo}"

        # For SSH URLs like git@github.com:owner/repo
        if url.startswith("git@github.com:"):
            repo_path = url.replace("git@github.com:", "")
            repo_path = re.sub(r"\.git$", "", repo_path)
            return f"https://github.com/{repo_path}"

        # For SSH URLs like ssh://git@github.com/owner/repo
        if url.startswith("ssh://git@github.com/"):
            repo_path = url.replace("ssh://git@github.com/", "")
            repo_path = re.sub(r"\.git$", "", repo_path)
            return f"https://github.com/{repo_path}"

        return url

    def _build_github_to_registry_map(self, global_mappings: GlobalNodeMappings) -> dict[str, GlobalNodePackage]:
        """Build reverse mapping from GitHub URLs to registry IDs."""
        github_to_registry = {}

        for _, package in global_mappings.packages.items():
            if package.repository:
                normalized_url = self._normalize_github_url(package.repository)
                if normalized_url:
                    github_to_registry[normalized_url] = package

        return github_to_registry

    def resolve_github_url(self, github_url: str) -> GlobalNodePackage | None:
        """Resolve GitHub URL to registry ID and package data."""
        normalized_url = self._normalize_github_url(github_url)
        if mapping := self.github_to_registry.get(normalized_url):
            return mapping
        return None

    def get_github_url_for_package(self, package_id: str) -> str | None:
        """Get GitHub URL for a package ID."""
        if self.global_mappings and package_id in self.global_mappings.packages:
            return self.global_mappings.packages[package_id].repository
        return None

    def resolve_workflow_nodes(
        self, custom_nodes: list[WorkflowNode]
    ) -> NodeResolutionResult:
        """Resolve unknown/custom nodes from workflow.

        Args:
            custom_nodes: List of WorkflowNode that are not builtin nodes.

        Returns:
            Resolution result with matches and suggestions
        """
        result = NodeResolutionResult()

        for node in custom_nodes:
            node_type = node.type

            matches = self.resolve_single_node(node)

            if matches:
                if len(matches) > 1:
                    result.ambiguous[node_type] = matches
                else:
                    result.resolved[node_type] = matches[0]
            else:
                result.unresolved.append(node_type)

        return result

    def resolve_single_node(self, node: WorkflowNode) -> List[ResolvedNodePackage] | None:
        """Resolve a single node type."""
        mappings = self.global_mappings.mappings
        packages = self.global_mappings.packages

        node_type = node.type
        inputs = node.inputs

        # Strategy 1: Try exact match with input signature
        if inputs:
            input_signature = normalize_workflow_inputs(inputs)
            logger.debug(f"Input signature for {node_type}: {input_signature}")
            if input_signature:
                exact_key = create_node_key(node_type, input_signature)
                logger.debug(f"Exact key for {node_type}: {exact_key}")
                if exact_key in mappings:
                    mapping = mappings[exact_key]
                    logger.debug(
                        f"Exact match for {node_type}: {mapping.package_id}"
                    )
                    return [
                        ResolvedNodePackage(
                            package_id=mapping.package_id,
                            package_data=packages[mapping.package_id],
                            versions=mapping.versions,
                            match_type="exact",
                            match_confidence=1.0,
                        )
                    ]

        # Strategy 2: Try type-only match
        type_only_key = create_node_key(node_type, "_")
        if type_only_key in mappings:
            mapping = mappings[type_only_key]
            logger.debug(f"Type-only match for {node_type}: {mapping.package_id}")
            return [
                ResolvedNodePackage(
                    package_id=mapping.package_id,
                    package_data=packages[mapping.package_id],
                    versions=mapping.versions,
                    match_type="type_only",
                    match_confidence=0.9,
                )
            ]

        # Strategy 3: Fuzzy search (simple substring matching)
        matches: list[ResolvedNodePackage] = []
        node_type_lower = node_type.lower()

        for key, mapping in mappings.items():
            mapped_node_type = key.split("::")[0]

            # Simple substring matching
            if (
                node_type_lower in mapped_node_type.lower()
                or mapped_node_type.lower() in node_type_lower
            ):
                matches.append(
                    ResolvedNodePackage(
                        package_id=mapping.package_id,
                        package_data=packages[mapping.package_id],
                        versions=mapping.versions,
                        match_type="fuzzy",
                        match_confidence=0.8,
                    )
                )
        if matches:
            logger.debug(f"Fuzzy matches for {node_type}: {matches}")
            return matches

        logger.debug(f"No match found for {node_type}")
        return None
