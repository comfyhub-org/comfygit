from dataclasses import dataclass

@dataclass(repr=False)
class APICredentials:
    """Secure storage for external API credentials."""
    civitai_token: str | None = None

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        return cls(civitai_token=data.get("civitai_token"))

    def to_dict(self):
        return {"civitai_token": self.civitai_token} if self.civitai_token else {}

    def __repr__(self):
        """Obfuscate token in logs."""
        if self.civitai_token:
            return f"APICredentials(civitai_token='***{self.civitai_token[-4:]}')"
        return "APICredentials(civitai_token=None)"

@dataclass
class ModelDirectory:
    path: str
    added_at: str
    last_sync: str

    @classmethod
    def from_dict(cls, data):
        return cls(
            path=data["path"],
            added_at=data["added_at"],
            last_sync=data["last_sync"],
        )

    @classmethod
    def to_dict(cls, instance):
        return instance.__dict__

@dataclass
class WorkspaceConfig:
    version: int
    active_environment: str
    created_at: str
    global_model_directory: ModelDirectory | None
    api_credentials: APICredentials | None = None
    prefer_registry_cache: bool = True  # Use local node mappings cache instead of API

    @classmethod
    def from_dict(cls, data):
        return cls(
            version=data["version"],
            active_environment=data["active_environment"],
            created_at=data["created_at"],
            global_model_directory=ModelDirectory.from_dict(data["global_model_directory"]) if data.get("global_model_directory") else None,
            api_credentials=APICredentials.from_dict(data.get("api_credentials")) if data.get("api_credentials") else None,
            prefer_registry_cache=data.get("prefer_registry_cache", True),
        )

    @classmethod
    def to_dict(cls, instance):
        result = {
            "version": instance.version,
            "active_environment": instance.active_environment,
            "created_at": instance.created_at,
            "global_model_directory": ModelDirectory.to_dict(instance.global_model_directory) if instance.global_model_directory else None,
            "api_credentials": instance.api_credentials.to_dict() if instance.api_credentials else None,
            "prefer_registry_cache": instance.prefer_registry_cache,
        }
        return result