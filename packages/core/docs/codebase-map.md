# ComfyDock Core Package - Codebase Map

## Core Architecture

### Core Components (`core/`)
- **workspace.py** - Multi-environment workspace manager, coordinates all environments within a validated workspace
- **environment.py** - Single ComfyUI environment abstraction, owns nodes, models, workflows, and dependencies

### Models (`models/`)
Data structures and contracts:
- **environment.py** - EnvironmentStatus, GitStatus, PackageSyncStatus data classes
- **workflow.py** - WorkflowNode, WorkflowDependencies, DetailedWorkflowStatus structures
- **shared.py** - Common models (NodeInfo, NodePackage, ModelSourceResult)
- **exceptions.py** - Custom exception hierarchy (ComfyDockError, CDNodeConflictError, etc.)
- **workspace_config.py** - Workspace configuration schema
- **manifest.py** - Environment manifest for serialization
- **registry.py** - Node registry and mapping structures
- **civitai.py** - CivitAI API response models
- **commit.py** - Git commit tracking models
- **node_mapping.py** - Node to package mapping structures
- **system.py** - System information models
- **protocols.py** - Type protocols for strategies and callbacks

## Management Layer

### Managers (`managers/`)
Orchestrate operations on environments and their components:
- **node_manager.py** - Install/update/remove custom nodes with conflict detection
- **workflow_manager.py** - Workflow loading, parsing, and execution
- **pyproject_manager.py** - Read/write pyproject.toml dependencies
- **uv_project_manager.py** - Execute uv commands and manage Python packages
- **git_manager.py** - Git operations (clone, checkout, status)
- **model_symlink_manager.py** - Symlink models from global cache to environment
- **model_download_manager.py** - Download models from sources (CivitAI, etc)
- **export_import_manager.py** - Bundle and extract environment configurations

### Services (`services/`)
Stateless, reusable business logic:
- **node_lookup_service.py** - Find nodes across registries, GitHub, and local cache
- **registry_data_manager.py** - Load and cache the official ComfyUI node registry
- **model_downloader.py** - Coordinate model downloads across sources (CivitAI, URLs, etc.)

## Resolution & Analysis

### Analyzers (`analyzers/`)
Parse and extract information from workflows and environments:
- **workflow_dependency_parser.py** - Extract node and model dependencies from workflows
- **custom_node_scanner.py** - Scan custom node directories for metadata and inputs
- **model_scanner.py** - Scan models directory for available models
- **node_classifier.py** - Classify nodes (builtin vs custom, builtin subtypes)
- **git_change_parser.py** - Parse git diffs for node additions/removals
- **node_git_analyzer.py** - Extract git repo info from node URLs
- **status_scanner.py** - Analyze environment status (synced, missing deps, etc)

### Resolvers (`resolvers/`)
Determine what packages to install:
- **global_node_resolver.py** - Map unknown workflow nodes to known packages using embeddings/scoring
- **model_resolver.py** - Resolve model references to download sources (CivitAI, HuggingFace, URLs)

### Repositories (`repositories/`)
Data access layer:
- **node_mappings_repository.py** - Access prebuilt node-to-package mappings
- **workflow_repository.py** - Load and cache workflow files
- **workspace_config_repository.py** - Persist/load workspace configuration
- **model_repository.py** - Index and query available models across environments

## External Integration

### Clients (`clients/`)
API communication:
- **civitai_client.py** - Search and query CivitAI for models and metadata
- **github_client.py** - Query GitHub API for custom node repos and releases
- **registry_client.py** - Fetch official ComfyUI node registry

### Factories (`factories/`)
Object construction:
- **workspace_factory.py** - Create Workspace instances with dependencies
- **environment_factory.py** - Create Environment instances
- **uv_factory.py** - Create uv command executors

## Utilities & Infrastructure

### Utils (`utils/`)
Helper functions:
- **requirements.py** - Parse requirements.txt and pyproject.toml
- **dependency_parser.py** - Parse Python dependency version constraints
- **conflict_parser.py** - Detect and analyze dependency conflicts
- **version.py** - Version comparison and management
- **git.py** - Git URL manipulation and validation
- **input_signature.py** - Parse node input signatures for matching
- **download.py** - File downloading with retry logic
- **filesystem.py** - File and directory operations
- **system_detector.py** - Detect OS, Python version, CUDA availability
- **uv_error_handler.py** - Parse and handle uv command errors
- **comfyui_ops.py** - ComfyUI-specific operations
- **common.py** - General utilities (subprocess, logging, etc)
- **model_categories.py** - ComfyUI model category mappings
- **retry.py** - Retry decorators and strategies

### Caching (`caching/`)
Persistent caching layer:
- **api_cache.py** - Generic API response caching with TTL
- **custom_node_cache.py** - Specialized cache for custom node metadata

### Configs (`configs/`)
Static configuration data:
- **comfyui_builtin_nodes.py** - Registry of ComfyUI builtin nodes
- **comfyui_models.py** - Model information and paths
- **model_config.py** - Model configuration and loading

### Infrastructure (`infrastructure/`)
External system interfaces:
- **sqlite_manager.py** - SQLite database operations for persistence

### Strategies (`strategies/`)
Pluggable behavior patterns:
- **confirmation.py** - Node/model conflict resolution strategies (auto-confirm, manual, etc)
- **auto.py** - Automatic resolution strategies

### Validation (`validation/`)
Testing and verification:
- **resolution_tester.py** - Test that resolved dependencies are valid

### Integrations (`integrations/`)
External tool integration:
- **uv_command.py** - Execute uv commands with environment setup

### Logging (`logging/`)
- **logging_config.py** - Configure logging for the package

## Key Entry Points

- **Workspace** - Top-level API, manages multiple environments
- **Environment** - Single environment API for node/model/workflow operations
- **GlobalNodeResolver** - Resolve unknown nodes to packages
- **NodeLookupService** - Find nodes across all sources
