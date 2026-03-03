# podsignal/utils.py
"""
Shared utilities for PodSignal.

- Logging setup
- LLM JSON response parsing (strips markdown fences)
- Retry decorator with exponential backoff
"""

import json
import logging
import time
import functools


def setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Configure and return a logger for PodSignal.

    Sets the root logger format so all modules get consistent output.
    Call once at startup (e.g. in main.py).

    Args:
        verbose: If True, set DEBUG level. Otherwise INFO.

    Returns:
        A logger instance named 'podsignal'.
    """
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="[PodSignal] %(levelname)s: %(message)s",
        force=True,  # Override any existing root config
    )

    return logging.getLogger("podsignal")


def parse_llm_json(raw_text: str) -> dict:
    """
    Parse JSON from an LLM response, stripping markdown code fences if present.

    Handles these common patterns from Claude:
        ```json\n{...}\n```
        ```\n{...}\n```
        {..."} (plain JSON, no fences)

    Args:
        raw_text: Raw text from the LLM response.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If the text cannot be parsed as JSON after cleanup.
    """
    text = raw_text.strip()

    # Strip leading code fence: ```json or ```
    if text.startswith("```"):
        # Find the end of the opening fence line
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            # Edge case: everything on one line like ```{...}```
            text = text[3:]

    # Strip trailing code fence
    if text.rstrip().endswith("```"):
        text = text.rstrip()
        text = text[:-3]

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse LLM response as JSON: {e}\n"
            f"Cleaned text was: {text[:200]}{'...' if len(text) > 200 else ''}"
        ) from e


def retry_on_transient(max_retries: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """
    Decorator that retries a function on transient errors with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (not counting the first call).
        base_delay: Base delay in seconds. Doubles each retry (1s, 2s, 4s, ...).
        exceptions: Tuple of exception types to catch and retry on.

    Usage::

        @retry_on_transient(max_retries=3, base_delay=1.0)
        def call_api():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger("podsignal")
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Retry %d/%d for %s after error: %s (waiting %.1fs)",
                            attempt + 1, max_retries, func.__name__, e, delay,
                        )
                        time.sleep(delay)

            # All retries exhausted
            raise last_exception

        return wrapper
    return decorator
