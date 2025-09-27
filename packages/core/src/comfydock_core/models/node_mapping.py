"""Global node mappings table dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field

""" example mappings:
"mappings": {
    "(Down)Load Hibiki Model::_": {
        "package_id": "comfyui-hibiki",
        "versions": [
            "1.0.0"
        ]
    },
    "(Down)Load Kokoro Model::_": {
        "package_id": "comfyui-jhj-kokoro-onnx",
        "versions": [],
        "source": "manager"
    },
"""


@dataclass
class GlobalNodeMapping:
    """Mapping from node type to package ID."""

    id: str  # Compound key (e.g. "NodeType::<input list hash>")
    package_id: str  # Package ID
    versions: list[str]  # Compatible versions
    source: str | None  # Source of the mapping (e.g. "manager")


""" example package:
"comfyui-hibiki": {
    "display_name": "ComfyUI-hibiki",
    "author": "",
    "description": "ComfyUI wrapper for Speech-to-Speech translation, hibiki: https://github.com/kyutai-labs/hibiki",
    "repository": "https://github.com/jhj0517/ComfyUI-hibiki.git",
    "downloads": 909,
    "github_stars": 0,
    "rating": 0,
    "license": "{\"file\": \"LICENSE\"}",
    "category": "",
    "tags": [],
    "status": "NodeStatusActive",
    "created_at": "2025-02-09T12:51:54.479852Z",
    "versions": {
        "1.0.0": {
            "version": "1.0.0",
            "changelog": "",
            "release_date": "2025-02-09T12:51:54.912872Z",
            "dependencies": [
                "git+https://github.com/jhj0517/moshi_comfyui_wrapper.git@main#subdirectory=moshi"
            ],
            "deprecated": false,
            "download_url": "https://cdn.comfy.org/jhj0517/comfyui-hibiki/1.0.0/node.zip",
            "status": "NodeVersionStatusFlagged",
            "supported_accelerators": null,
            "supported_comfyui_version": "",
            "supported_os": null
        }
    }
},
...
"github_zzw5516_comfyui-zw-tools": {
    "display_name": "comfyui-zw-tools",
    "author": "zzw5516",
    "description": "",
    "repository": "https://github.com/zzw5516/ComfyUI-zw-tools",
    "synthetic": true,
    "source": "manager",
    "versions": {}
}
"""

@dataclass
class GlobalNodePackageVersion:
    """Package version data."""
    version: str  # Version
    changelog: str | None  # Changelog
    release_date: str | None  # Release date
    dependencies: list[str] | None  # Dependencies
    deprecated: bool | None  # Deprecated
    download_url: str | None  # Download URL
    status: str | None  # Status
    supported_accelerators: list[str] | None  # Supported accelerators
    supported_comfyui_version: str | None  # Supported ComfyUI version
    supported_os: list[str] | None  # Supported OS

@dataclass
class GlobalNodePackage:
    """Global standard package data."""

    id: str  # Package ID
    display_name: str | None  # Display name
    author: str | None  # Author
    description: str | None  # Description
    repository: str | None  # Repository
    downloads: int | None  # Downloads
    github_stars: int | None  # GitHub stars
    rating: int | None  # Rating
    license: str | None  # License
    category: str | None  # Category
    tags: list[str] | None  # Tags
    status: str | None  # Status
    created_at: str | None  # Created at
    versions: dict[str, GlobalNodePackageVersion] | None  # Versions
    synthetic: bool = False  # Whether this is a synthetic package from Manager
    source: str | None = None  # Source of the package (e.g. "manager")


""" example full mappings file:
"version": "2025.09.19",
"generated_at": "2025-09-19T18:25:18.347947",
"stats": {
    "packages": 3398,
    "signatures": 34049,
    "total_nodes": 15280,
    "augmented": true,
    "augmentation_date": "2025-09-19T18:26:03.820776",
    "nodes_from_manager": 19402,
    "synthetic_packages": 485
},
"mappings": {...},
"packages": {...},
"""


@dataclass
class GlobalNodeMappingsStats:
    packages: int | None
    signatures: int | None
    total_nodes: int | None
    augmented: bool | None
    augmentation_date: str | None
    nodes_from_manager: int | None
    synthetic_packages: int | None


@dataclass
class GlobalNodeMappings:
    """Global node mappings table."""

    version: str
    generated_at: str
    stats: GlobalNodeMappingsStats | None
    mappings: dict[str, GlobalNodeMapping] = field(default_factory=dict)
    packages: dict[str, GlobalNodePackage] = field(default_factory=dict)
