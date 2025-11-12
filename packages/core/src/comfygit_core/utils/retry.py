"""Retry utilities with exponential backoff for API rate limiting."""

import random
import time
import urllib.error
from collections.abc import Callable
from functools import wraps
from typing import Any

from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Add random jitter to delays
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


def calculate_backoff_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate exponential backoff delay with optional jitter.

    Args:
        attempt: Current attempt number (0-based)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    # Calculate exponential backoff
    delay = min(
        config.initial_delay * (config.exponential_base**attempt), config.max_delay
    )

    # Add jitter if enabled
    if config.jitter:
        # Add random jitter between 0 and 25% of the delay
        jitter_amount = delay * 0.25 * random.random()
        delay += jitter_amount

    return delay


def is_rate_limit_error(error: Exception) -> bool:
    """Check if an error is a rate limit error.

    Args:
        error: The exception to check

    Returns:
        True if this is a rate limit error
    """
    if isinstance(error, urllib.error.HTTPError):
        # GitHub returns 403 for rate limits
        if error.code == 403:
            # Check headers for rate limit indication
            headers = error.headers
            if headers.get("X-RateLimit-Remaining") == "0":
                return True
            # Also check for rate limit message in response
            try:
                error_data = error.read().decode("utf-8")
                if (
                    "rate limit" in error_data.lower()
                    or "api rate limit" in error_data.lower()
                ):
                    return True
            except Exception:
                pass
        # Some APIs return 429 for rate limits
        elif error.code == 429:
            return True

    return False


def retry_on_rate_limit(config: RetryConfig | None = None):
    """Decorator for retrying functions that may hit rate limits.

    Args:
        config: Retry configuration (uses defaults if not provided)

    Returns:
        Decorated function
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if this is a rate limit error
                    if is_rate_limit_error(e):
                        if attempt < config.max_retries:
                            delay = calculate_backoff_delay(attempt, config)
                            logger.warning(
                                f"Rate limit hit in {func.__name__}, "
                                f"retrying in {delay:.1f}s (attempt {attempt + 1}/{config.max_retries})"
                            )
                            time.sleep(delay)
                            continue
                        else:
                            logger.error(
                                f"Rate limit hit in {func.__name__}, "
                                f"max retries ({config.max_retries}) exceeded"
                            )

                    # Re-raise if not a rate limit error
                    raise

            # If we get here, we've exhausted retries
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def retry_with_backoff(
    func: Callable,
    args: tuple = (),
    kwargs: dict | None = None,
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Any:
    """Execute a function with retry logic and exponential backoff.

    Args:
        func: Function to execute
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
        config: Retry configuration
        on_retry: Optional callback called on each retry with (attempt, exception)

    Returns:
        Result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    if kwargs is None:
        kwargs = {}
    if config is None:
        config = RetryConfig()

    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            return func(*args, **kwargs)

        except Exception as e:
            last_exception = e

            # Check if this is a rate limit error
            if is_rate_limit_error(e):
                if attempt < config.max_retries:
                    delay = calculate_backoff_delay(attempt, config)

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(attempt, e)

                    logger.warning(
                        f"Rate limit hit, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{config.max_retries})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Rate limit hit, max retries ({config.max_retries}) exceeded"
                    )

            # Re-raise if not a rate limit error or if retries exhausted
            raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


class RateLimitManager:
    """Manages rate limiting across multiple API calls."""

    def __init__(self, min_interval: float = 0.1):
        """Initialize rate limit manager.

        Args:
            min_interval: Minimum interval between API calls in seconds
        """
        self.min_interval = min_interval
        self.last_call_time = {}

    def wait_if_needed(self, api_key: str):
        """Wait if necessary to respect rate limits.

        Args:
            api_key: Unique key for the API being called
        """
        current_time = time.time()

        if api_key in self.last_call_time:
            elapsed = current_time - self.last_call_time[api_key]
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.3f}s")
                time.sleep(sleep_time)

        self.last_call_time[api_key] = time.time()
