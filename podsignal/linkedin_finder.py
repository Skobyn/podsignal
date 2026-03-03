# podsignal/linkedin_finder.py
"""
Finds LinkedIn profile URLs for podcast guests using Google search.

Strategy: Google "First Last Company site:linkedin.com/in"
This works reliably for public figures who've been on podcasts —
they almost always have a LinkedIn and Google indexes it.

No LinkedIn API. No paid search API (by default).
Uses requests + basic HTML parsing with a polite delay.

For higher volume: configure SerpAPI (100 free searches/month) in config.yaml.
"""

import re
import time
import random
import logging
import requests
from typing import Optional
from urllib.parse import quote_plus

from podsignal.utils import retry_on_transient

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

LINKEDIN_PATTERN = re.compile(
    r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+/?'
)


def find_linkedin_url(
    name: str,
    company: str = None,
    title: str = None,
    use_serpapi: bool = False,
    serpapi_key: str = None,
) -> Optional[str]:
    """
    Find a person's LinkedIn profile URL via Google search.

    Args:
        name: Full name of the guest
        company: Their company (improves accuracy significantly)
        title: Their title (optional, further improves accuracy)
        use_serpapi: Use SerpAPI instead of direct Google (more reliable at scale)
        serpapi_key: SerpAPI key if use_serpapi=True

    Returns:
        LinkedIn profile URL string, or None if not found
    """
    if not name:
        return None

    if use_serpapi and serpapi_key:
        return _search_serpapi(name, company, title, serpapi_key)
    else:
        return _search_google(name, company, title)


def _build_query(name: str, company: str = None, title: str = None) -> str:
    """Build a precise Google search query."""
    parts = [f'"{name}"']
    if company:
        parts.append(f'"{company}"')
    elif title:
        parts.append(f'"{title}"')
    parts.append("site:linkedin.com/in")
    return " ".join(parts)


def _search_google(name: str, company: str = None, title: str = None, _is_fallback: bool = False) -> Optional[str]:
    """
    Direct Google search — no API key.
    Works well for ~100 searches before Google may show a CAPTCHA.
    Add delay between calls to stay under the radar.
    """
    query = _build_query(name, company, title)
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&num=5"

    # Polite random delay: 2-4 seconds between searches
    time.sleep(random.uniform(2.0, 4.0))

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=10)

        if resp.status_code == 429:
            logger.warning("Google rate limit hit. Consider switching to SerpAPI.")
            return None

        if resp.status_code != 200:
            return None

        # Extract LinkedIn URLs from the response HTML
        matches = LINKEDIN_PATTERN.findall(resp.text)

        if matches:
            # Return the first clean match, strip query params
            linkedin_url = matches[0].rstrip("/")
            return linkedin_url

    except Exception as e:
        logger.error("Google search failed for %s: %s", name, e)

    # Fallback: try without company (once only, not recursive)
    if company and not _is_fallback:
        logger.debug("Retrying search for %s without company filter", name)
        return _search_google(name, title=title, _is_fallback=True)

    return None


@retry_on_transient(max_retries=2, base_delay=1.0, exceptions=(requests.RequestException,))
def _search_serpapi(
    name: str,
    company: str = None,
    title: str = None,
    api_key: str = None,
) -> Optional[str]:
    """
    SerpAPI-based search — more reliable at scale, 100 free searches/month.
    Sign up at serpapi.com — no credit card needed for free tier.
    """
    query = _build_query(name, company, title)

    resp = requests.get(
        "https://serpapi.com/search",
        params={
            "q": query,
            "api_key": api_key,
            "num": 5,
            "engine": "google",
        },
        timeout=10,
    )
    data = resp.json()

    # Check organic results for LinkedIn URLs
    for result in data.get("organic_results", []):
        link = result.get("link", "")
        if "linkedin.com/in/" in link:
            return link

    return None


def enrich_guests_with_linkedin(
    guests: list[dict],
    use_serpapi: bool = False,
    serpapi_key: str = None,
) -> list[dict]:
    """
    Add LinkedIn URLs to a list of guest dicts.
    Guests without names are skipped silently.
    """
    enriched = []

    for guest in guests:
        name = guest.get("guest_name")
        if not name:
            enriched.append(guest)
            continue

        logger.info("Finding LinkedIn for %s...", name)

        linkedin_url = find_linkedin_url(
            name=name,
            company=guest.get("guest_company"),
            title=guest.get("guest_title"),
            use_serpapi=use_serpapi,
            serpapi_key=serpapi_key,
        )

        guest["linkedin_url"] = linkedin_url
        enriched.append(guest)

        if linkedin_url:
            logger.info("  Found: %s", linkedin_url)
        else:
            logger.info("  Not found")

    return enriched
