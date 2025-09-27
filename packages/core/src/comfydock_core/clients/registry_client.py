"""Comfy Registry API client for node discovery, validation, and metadata retrieval."""

import json
import urllib.error
import urllib.parse
import urllib.request

from comfydock_core.caching.api_cache import APICacheManager
from comfydock_core.constants import DEFAULT_REGISTRY_URL
from comfydock_core.logging.logging_config import get_logger
from comfydock_core.models.exceptions import (
    CDNodeNotFoundError,
    CDRegistryAuthError,
    CDRegistryConnectionError,
    CDRegistryError,
    CDRegistryServerError,
)
from comfydock_core.models.shared import RegistryNodeInfo, RegistryNodeVersion
from comfydock_core.utils.retry import (
    RateLimitManager,
    RetryConfig,
    retry_on_rate_limit,
)

logger = get_logger(__name__)


class ComfyRegistryClient:
    """Client for interacting with the Comfy Registry API.

    Provides node discovery, validation, version management, and download URLs.
    Includes intelligent fuzzy matching and caching for optimal performance.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_REGISTRY_URL,
        cache_manager: APICacheManager | None = None,
    ):
        self.base_url = base_url
        self.cache_manager = cache_manager or APICacheManager()
        self.rate_limiter = RateLimitManager(min_interval=0.05)
        self.retry_config = RetryConfig(
            max_retries=3,
            initial_delay=0.5,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True,
        )

    def get_node(self, node_id: str) -> RegistryNodeInfo | None:
        """Get exact node by ID from registry.

        Args:
            node_id: Exact registry node ID

        Returns:
            NodeInfo if found, None otherwise

        Raises:
            CDRegistryError: If registry request fails
        """
        url = f"{self.base_url}/nodes/{node_id}"

        data = self._make_registry_request(url)

        if data:
            logger.info(
                f"Registry client: Found node '{node_id}' in registry: {str(data)}"
            )
            return RegistryNodeInfo.from_api_data(data)

        return None

    def install_node(
        self, node_id: str, version: str | None
    ) -> RegistryNodeVersion | None:
        """Get the exact node download info by ID from registry.

        Args:
            node_id: Exact registry node ID

        Returns:
            NodeInfo if found, None otherwise

        Raises:
            CDRegistryError: If registry request fails
        """
        url = f"{self.base_url}/nodes/{node_id}/install"

        if version:
            url += f"?version={version}"

        data = self._make_registry_request(url)

        if data:
            logger.info(
                f"Registry client: Found install info for node '{node_id}' in registry: {str(data)}"
            )
            return RegistryNodeVersion.from_api_data(data)

        return None

    def search_nodes(
        self, query: str, limit: int = 20
    ) -> list[RegistryNodeInfo] | None:
        """Search for nodes by keyword.

        Args:
            query: Search term (name, author, description)
            limit: Max results

        Returns:
            List of matching nodes

        Raises:
            CDRegistryError: If registry request fails
        """
        params = {"search": query, "limit": limit}
        url = f"{self.base_url}/nodes/search?{urllib.parse.urlencode(params)}"

        data = self._make_registry_request(url)

        if data and "nodes" in data:
            return [
                info
                for n in data["nodes"]
                if (info := RegistryNodeInfo.from_api_data(n)) is not None
            ]

        return None

    def get_node_requirements(self, node_id: str) -> list[str]:
        """Get requirements for a specific node version.

        Raises:
            CDNodeNotFoundError: If node doesn't exist
            CDRegistryError: If registry request fails
        """
        url = f"{self.base_url}/nodes/{node_id}/install"

        install_info = self._make_registry_request(url)

        if install_info is None:
            # This is more exceptional - we're asking for requirements
            # of a node we expect to exist
            raise CDNodeNotFoundError(f"Node '{node_id}' not found in registry")

        return install_info.get("dependencies", [])

    @retry_on_rate_limit(RetryConfig(max_retries=3, initial_delay=0.5, max_delay=30.0))
    def _make_registry_request(self, url: str) -> dict | None:
        """Make a request to Registry API with retry logic.

        Returns:
            Response data or None for 404 (not found)

        Raises:
            CDRegistryAuthError: For 401/403 authentication issues
            CDRegistryServerError: For 5xx server errors
            CDRegistryConnectionError: For network issues
        """

        # Check cache first
        logger.debug(f"Registry client: Checking cache for '{url}'")
        cached_data = self.cache_manager.get("registry", url)
        if cached_data is not None:
            logger.debug(f"Registry client: Using cached data for '{url}'")
            return cached_data

        # Rate limit ourselves
        self.rate_limiter.wait_if_needed("registry_api")

        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ComfyDock/1.0")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    json_data = json.loads(response.read().decode("utf-8"))
                    logger.debug(f"Registry client: Got data for '{url}'")
                    self.cache_manager.set("registry", url, json_data)
                    return json_data

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Not found is expected for many operations
                logger.debug(f"Registry: Node not found at '{url}'")
                return None

            elif e.code in (401, 403):
                # Authentication/authorization errors
                logger.error(f"Registry auth error for '{url}': HTTP {e.code}")

                # Try to get more details from response
                error_msg = f"Registry authentication failed (HTTP {e.code})"
                try:
                    error_data = e.read().decode("utf-8")
                    if error_data:
                        error_msg += f": {error_data}"
                except:
                    pass

                raise CDRegistryAuthError(error_msg) from e

            elif e.code >= 500:
                # Server errors - these might be temporary
                logger.error(f"Registry server error for '{url}': HTTP {e.code}")
                raise CDRegistryServerError(
                    f"Registry server error (HTTP {e.code})"
                ) from e

            else:
                # Other HTTP errors
                logger.error(f"Registry HTTP error for '{url}': {e.code} {e.reason}")
                raise CDRegistryError(
                    f"Registry request failed: HTTP {e.code} {e.reason}"
                ) from e

        except urllib.error.URLError as e:
            # Network errors (connection refused, DNS failure, etc.)
            logger.error(f"Registry connection error for '{url}': {e}")
            raise CDRegistryConnectionError(
                f"Failed to connect to registry: {e.reason}"
            ) from e

        except Exception as e:
            # Unexpected errors
            logger.error(f"Unexpected error accessing registry at '{url}': {e}")
            raise CDRegistryError(f"Registry request failed: {e}") from e

        return None  # Shouldn't reach here, but for completeness
