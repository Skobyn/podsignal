# podsignal/rss_fetcher.py
"""
Fetches and parses podcast RSS feeds.

RSS feeds are public HTTP endpoints — no auth, no API key, no scraping.
We pull episode titles, descriptions, dates, and guest links.

Most podcast platforms (Buzzsprout, Libsyn, Podbean, Transistor, Captivate,
Megaphone, Simplecast) use standard RSS 2.0 with iTunes extensions.
This parser handles all of them.
"""

import re
import logging
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

from podsignal.utils import retry_on_transient

logger = logging.getLogger(__name__)

# Some feeds are picky about User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PodSignal/1.0; RSS reader)"
}


class _TransientHTTPError(requests.RequestException):
    """Raised only for retryable HTTP errors (5xx, timeouts, connection errors)."""
    pass


@retry_on_transient(max_retries=2, base_delay=2.0, exceptions=(_TransientHTTPError, requests.ConnectionError, requests.Timeout))
def fetch_feed(podcast: dict) -> list[dict]:
    """
    Fetch all episodes from a podcast RSS feed.

    Args:
        podcast: dict with keys: name, rss, icp_notes

    Returns:
        List of episode dicts with title, description, date, url, duration
    """
    rss_url = podcast.get("rss", "")
    podcast_name = podcast.get("name", "Unknown Show")

    resp = requests.get(rss_url, headers=HEADERS, timeout=15)

    # Only retry on server errors (5xx). Client errors (4xx) are permanent.
    if resp.status_code >= 500:
        raise _TransientHTTPError(f"{resp.status_code} Server Error for url: {rss_url}")
    resp.raise_for_status()

    feed = feedparser.parse(resp.content)

    episodes = []
    for entry in feed.entries:
        episode = _parse_entry(entry, podcast_name, podcast.get("icp_notes", ""))
        if episode:
            episodes.append(episode)

    return episodes


def fetch_recent_episodes(
    podcast: dict,
    days_back: int = 30,
    max_episodes: int = 20,
) -> list[dict]:
    """
    Fetch only recent episodes from a podcast, filtered by date.
    """
    try:
        all_episodes = fetch_feed(podcast)
    except Exception as e:
        logger.error("Failed to fetch %s: %s", podcast.get("name", "?"), e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    recent = []
    for ep in all_episodes:
        pub_date = ep.get("published_datetime")
        if pub_date and pub_date >= cutoff:
            recent.append(ep)

    # Sort newest first, cap at max_episodes
    recent.sort(key=lambda e: e.get("published_datetime", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return recent[:max_episodes]


def _parse_entry(entry: dict, podcast_name: str, icp_notes: str) -> Optional[dict]:
    """Extract structured fields from a feedparser entry."""

    title = entry.get("title", "").strip()
    if not title:
        return None

    # Description: try multiple fields in priority order
    description = (
        entry.get("summary")
        or entry.get("content", [{}])[0].get("value", "")
        or entry.get("subtitle")
        or ""
    )

    # Clean HTML tags from description
    description = _strip_html(description)

    # Date parsing — RSS dates are inconsistently formatted
    published_datetime = None
    published_str = ""
    for date_field in ["published", "updated", "created"]:
        raw_date = entry.get(date_field, "")
        if raw_date:
            try:
                published_datetime = parsedate_to_datetime(raw_date)
                published_str = published_datetime.strftime("%Y-%m-%d")
                break
            except Exception:
                pass

    # Episode URL — prefer episode-specific link over feed link
    episode_url = entry.get("link", "")

    # Duration (iTunes extension)
    duration = entry.get("itunes_duration", "")

    # Season/episode number if present
    episode_number = entry.get("itunes_episode", "")
    season_number = entry.get("itunes_season", "")

    return {
        "podcast_name": podcast_name,
        "icp_notes": icp_notes,
        "title": title,
        "description": description[:3000],  # Truncate for token efficiency
        "published_str": published_str,
        "published_datetime": published_datetime,
        "episode_url": episode_url,
        "duration": duration,
        "episode_number": episode_number,
        "season_number": season_number,
    }


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text
