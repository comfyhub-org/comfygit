# ComfyDock CLI - Codebase Map

## Overview
The CLI package provides command-line interface for ComfyDock, enabling environment and workspace management for ComfyUI. It handles user interactions through environment and global commands, with support for interactive node/model resolution, error handling, and structured logging.

## Core CLI (`comfydock_cli/`)

### Entry Points
- **__main__.py** - Package entry point allowing CLI to run as `python -m comfydock_cli`
- **__init__.py** - Package initialization exposing main CLI entry point
- **cli.py** - Main CLI parser and command router; creates argument parser and dispatches to environment or global commands

### Command Handlers
- **env_commands.py** - Environment-specific commands (activate, status, add/remove nodes, etc.)
- **global_commands.py** - Workspace-level commands (init, import, export, model operations)
- **cli_utils.py** - Shared utilities for workspace detection and CLI helper functions
- **resolution_strategies.py** - Model resolution strategies (interactive and automatic modes)

## Logging (`comfydock_cli/logging/`)
Structured logging system with environment-specific handlers and compression support.

- **logging_config.py** - Core logging setup with rotating file handlers and configurable levels
- **environment_logger.py** - Environment-specific logging with automatic handler management and decorator support
- **log_compressor.py** - Real-time log compression to reduce token count while preserving semantic content
- **compressed_handler.py** - Dual rotating file handler that writes both full and compressed logs simultaneously

## Strategies (`comfydock_cli/strategies/`)
Interactive resolution strategies for user-guided dependency resolution.

- **interactive.py** - Interactive node and model resolution strategies with search and selection UI
- **rollback.py** - Rollback confirmation logic with user prompts for destructive operations

## Formatters (`comfydock_cli/formatters/`)
Error and output formatting utilities.

- **error_formatter.py** - Converts core library errors to CLI command suggestions for user guidance

## Utilities (`comfydock_cli/utils/`)
General-purpose utilities for CLI operations.

- **progress.py** - Download progress callback and statistics display
- **pagination.py** - Terminal pagination for displaying large lists of items
- **civitai_errors.py** - Civitai authentication error messages and setup guidance

## Tests (`tests/`)
Test coverage for CLI components.

- **conftest.py** - Pytest fixtures and test configuration
- **test_error_formatter.py** - Tests for node action error formatting
- **test_interactive_optional_strategy.py** - Tests for interactive optional node resolution
- **test_status_displays_uninstalled_nodes.py** - Tests for status command uninstalled node display
- **test_status_uninstalled_reporting.py** - Tests for uninstalled node reporting accuracy
- **test_status_real_bug_scenario.py** - Regression tests for real bug scenarios

## Build and Registry Scripts (`scripts/`)
Utilities for building node registries and managing ComfyUI integrations (run during development/deployment).

- **registry_client.py** - Async HTTP client for ComfyUI registry API interactions
- **build_registry_cache.py** - Builds comprehensive registry cache with progressive enhancement phases
- **extract_builtin_nodes.py** - Extracts built-in ComfyUI nodes by parsing Python NODE_CLASS_MAPPINGS
- **build_global_mappings.py** - Constructs global node identifier mappings
- **extract_node_modules.py** - Extracts node module information from ComfyUI
- **augment_mappings.py** - Augments node mappings with additional metadata
- **test_concurrent_api.py** - Tests concurrent API interactions
- **get_hash.py** - Utility for computing content hashes
- **registry.py** - Registry management utilities
- **global-node-mappings.md** - Documentation for node mapping schema and format
- **README_REGISTRY.md** - Registry building and maintenance guide

## Configuration
- **pyproject.toml** - Package metadata, dependencies (comfydock-core), and CLI entry points (comfydock, cfd)

## Key Entry Points
- **comfydock / cfd commands** - Main CLI invocation points defined in pyproject.toml
- **EnvironmentCommands** - Handler for environment-scoped operations
- **GlobalCommands** - Handler for workspace-scoped operations
