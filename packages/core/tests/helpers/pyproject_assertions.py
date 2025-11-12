"""Assertion helpers for validating pyproject.toml state."""


class PyprojectAssertions:
    """Fluent assertions for pyproject.toml validation."""

    def __init__(self, env):
        self.env = env
        self.config = env.pyproject.load()

    def has_workflow(self, name: str) -> "WorkflowAssertions":
        """Assert workflow exists and return workflow-specific assertions."""
        workflows = self.config.get("tool", {}).get("comfygit", {}).get("workflows", {})
        assert name in workflows, f"Workflow '{name}' not found in pyproject.toml"
        return WorkflowAssertions(self.env, name, workflows[name])

    def has_global_model(self, model_hash: str) -> "ModelAssertions":
        """Assert model exists in global models table."""
        models = self.config.get("tool", {}).get("comfygit", {}).get("models", {})
        assert model_hash in models, f"Model {model_hash} not found in global models table"
        return ModelAssertions(models[model_hash])


class WorkflowAssertions:
    """Assertions for a specific workflow entry."""

    def __init__(self, env, name: str, workflow_config: dict):
        self.env = env
        self.name = name
        self.config = workflow_config

    def has_model_count(self, expected: int) -> "WorkflowAssertions":
        """Assert workflow has specific number of models."""
        models = self.config.get("models", [])
        actual = len(models)
        assert actual == expected, \
            f"Workflow '{self.name}' should have {expected} models, found {actual}"
        return self

    def has_model_with_hash(self, model_hash: str) -> "WorkflowAssertions":
        """Assert workflow has a model with specific hash."""
        models = self.config.get("models", [])
        model_hashes = [m.get("hash") for m in models if m.get("hash")]
        assert model_hash in model_hashes, \
            f"Model {model_hash} not found in workflow '{self.name}' models"
        return self

    def has_model_with_filename(self, filename: str) -> "WorkflowModelAssertions":
        """Assert workflow has model with filename and return model assertions."""
        models = self.config.get("models", [])
        matching = [m for m in models if m.get("filename") == filename]
        assert matching, f"Model '{filename}' not found in workflow '{self.name}'"
        return WorkflowModelAssertions(self, matching[0])

    def has_node_count(self, expected: int) -> "WorkflowAssertions":
        """Assert workflow has specific number of node packages."""
        nodes = self.config.get("nodes", [])
        actual = len(nodes)
        assert actual == expected, \
            f"Workflow '{self.name}' should have {expected} node packages, found {actual}"
        return self

    def has_node(self, package_id: str) -> "WorkflowAssertions":
        """Assert workflow references a specific node package."""
        nodes = self.config.get("nodes", [])
        assert package_id in nodes, \
            f"Node package '{package_id}' not found in workflow '{self.name}' nodes"
        return self


class WorkflowModelAssertions:
    """Assertions for a specific model in a workflow."""

    def __init__(self, workflow_assertions: WorkflowAssertions, model_config: dict):
        self.workflow = workflow_assertions
        self.config = model_config

    def has_status(self, expected: str) -> "WorkflowModelAssertions":
        """Assert model has specific status."""
        actual = self.config.get("status")
        assert actual == expected, \
            f"Expected status '{expected}', got '{actual}'"
        return self

    def has_criticality(self, expected: str) -> "WorkflowModelAssertions":
        """Assert model has specific criticality."""
        actual = self.config.get("criticality")
        assert actual == expected, \
            f"Expected criticality '{expected}', got '{actual}'"
        return self

    def has_category(self, expected: str) -> "WorkflowModelAssertions":
        """Assert model has specific category."""
        actual = self.config.get("category")
        assert actual == expected, \
            f"Expected category '{expected}', got '{actual}'"
        return self

    def has_no_sources(self) -> "WorkflowModelAssertions":
        """Assert model has no sources (cleaned after download)."""
        sources = self.config.get("sources", [])
        assert not sources or sources == [], \
            f"Expected no sources, got {sources}"
        return self

    def has_no_relative_path(self) -> "WorkflowModelAssertions":
        """Assert model has no relative_path (cleaned after download)."""
        rel_path = self.config.get("relative_path")
        assert rel_path is None, \
            f"Expected no relative_path, got '{rel_path}'"
        return self

    def and_workflow(self) -> WorkflowAssertions:
        """Return to workflow-level assertions."""
        return self.workflow


class ModelAssertions:
    """Assertions for global model entry."""

    def __init__(self, model_config: dict):
        self.config = model_config

    def has_filename(self, expected: str) -> "ModelAssertions":
        """Assert model has specific filename."""
        actual = self.config.get("filename")
        assert actual == expected, f"Expected filename '{expected}', got '{actual}'"
        return self

    def has_relative_path(self, expected: str) -> "ModelAssertions":
        """Assert model has specific relative path."""
        actual = self.config.get("relative_path")
        assert actual == expected, f"Expected path '{expected}', got '{actual}'"
        return self

    def has_category(self, expected: str) -> "ModelAssertions":
        """Assert model has specific category."""
        actual = self.config.get("category")
        assert actual == expected, f"Expected category '{expected}', got '{actual}'"
        return self

    def has_source(self, expected_url: str) -> "ModelAssertions":
        """Assert model has specific source URL."""
        sources = self.config.get("sources", [])
        assert expected_url in sources, \
            f"Expected source '{expected_url}' in {sources}"
        return self
