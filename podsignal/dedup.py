# podsignal/dedup.py
"""Deduplication tracking for podcast guests across runs."""

import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

DEFAULT_SEEN_PATH = os.path.join("output", ".podsignal_seen.json")


def load_seen(path: str = DEFAULT_SEEN_PATH) -> dict:
    """Load the seen-guests file. Returns empty dict if not found or invalid."""
    if not os.path.exists(path):
        logger.debug("Seen-guests file not found at %s; starting fresh", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded %d seen guests from %s", len(data), path)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load seen-guests file %s: %s; starting fresh", path, exc)
        return {}


def save_seen(seen: dict, path: str = DEFAULT_SEEN_PATH) -> None:
    """Save the seen-guests dict to disk."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True)
    logger.info("Saved %d seen guests to %s", len(seen), path)


def make_guest_key(guest: dict) -> str:
    """Build a normalized dedup key: lowercase(name)|lowercase(company)|lowercase(podcast)."""
    name = (guest.get("guest_name") or "").strip().lower()
    company = (guest.get("guest_company") or "").strip().lower()
    podcast = (guest.get("podcast_name") or "").strip().lower()
    return f"{name}|{company}|{podcast}"


def filter_new_guests(guests: list[dict], seen: dict) -> list[dict]:
    """Return only guests whose dedup key is not already in *seen*."""
    new = []
    for guest in guests:
        key = make_guest_key(guest)
        if key in seen:
            logger.debug("Skipping already-seen guest: %s", key)
        else:
            new.append(guest)
    logger.info("Filtered %d guests -> %d new", len(guests), len(new))
    return new


def mark_seen(guests: list[dict], seen: dict) -> dict:
    """Add guests to *seen* with today's date (ISO format). Returns updated seen dict."""
    today = date.today().isoformat()
    for guest in guests:
        key = make_guest_key(guest)
        if key not in seen:
            seen[key] = today
            logger.debug("Marked as seen: %s", key)
    return seen
