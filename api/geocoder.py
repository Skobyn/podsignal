"""
PodSignal Geocoder

Resolves guest/company locations to lat/lng using Nominatim (free, no API key).
Falls back to company name lookup if no city is explicitly mentioned.
"""

import asyncio
import logging
import httpx
import re

logger = logging.getLogger(__name__)

# Cache to avoid repeat lookups
_geo_cache: dict = {}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "PodSignal/2.0 (podcast-guest-intelligence; contact@getapexinsights.com)"}


async def geocode_location(query: str) -> dict | None:
    """Geocode a location string to lat/lng using Nominatim."""
    if not query or not query.strip():
        return None

    clean = query.strip().lower()
    if clean in _geo_cache:
        return _geo_cache[clean]

    try:
        async with httpx.AsyncClient(timeout=8, headers=HEADERS) as client:
            resp = await client.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1}
            )
            results = resp.json()
            if results:
                r = results[0]
                result = {
                    "lat": float(r["lat"]),
                    "lng": float(r["lon"]),
                    "name": r.get("display_name", query)[:60],
                }
                _geo_cache[clean] = result
                return result
    except Exception as e:
        logger.debug(f"Nominatim lookup failed for '{query}': {e}")

    _geo_cache[clean] = None
    return None


def extract_location_hints(guest: dict) -> list[str]:
    """
    Pull location candidates from guest data in priority order.
    """
    hints = []

    # 1. Explicit location field (if added to extraction)
    loc = guest.get("guest_location") or guest.get("location")
    if loc:
        hints.append(loc)

    # 2. Company name — often includes city for local businesses
    company = guest.get("guest_company", "")
    if company:
        # Check if company name contains common location patterns
        city_pattern = re.search(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),?\s*(NY|CA|TX|FL|IL|WA|CO|GA|MA|OH|PA|NC)\b', company)
        if city_pattern:
            hints.append(city_pattern.group(0))

    # 3. Try to extract location from background
    background = guest.get("guest_background", "")
    if background:
        # Look for "based in X", "from X", "in X"
        match = re.search(r'(?:based in|from|located in|headquartered in)\s+([A-Z][a-zA-Z\s,]+?)(?:\.|,|\s+where|\s+who|\s+and)', background)
        if match:
            hints.append(match.group(1).strip())

    # 4. Fall back to company name alone (might get a result)
    if company and company not in hints:
        hints.append(company)

    return hints


async def geocode_guest(guest: dict) -> dict | None:
    """
    Try to geocode a guest using available location hints.
    Returns {"lat": ..., "lng": ..., "name": ...} or None.
    """
    hints = extract_location_hints(guest)

    for hint in hints:
        if len(hint) < 3:
            continue
        result = await geocode_location(hint)
        if result:
            return result
        # Rate limit Nominatim (1 req/sec)
        await asyncio.sleep(1.1)

    return None
