"""UUID detection utilities for subgraph support."""
import re

# RFC 4122 UUID format: 8-4-4-4-12 hex digits
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)


def is_uuid(value: str) -> bool:
    """Check if string is a valid UUID (subgraph reference).

    Args:
        value: String to check

    Returns:
        True if value matches UUID format

    Examples:
        >>> is_uuid("0a58ac1f-cb15-4e01-aab3-26292addb965")
        True
        >>> is_uuid("CheckpointLoaderSimple")
        False
        >>> is_uuid("not-a-valid-uuid")
        False
    """
    return bool(UUID_PATTERN.match(value))
