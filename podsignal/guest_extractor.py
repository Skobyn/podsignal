# podsignal/guest_extractor.py
"""
Uses Claude to extract guest intelligence from episode titles and descriptions.

The key insight: most podcast episode descriptions are written to be indexable
and SEO-friendly. They're dense with guest names, companies, titles, and
the specific topics covered. Claude can pull structured data from this noise
reliably and cheaply.

One Claude call per episode. ~$0.001-0.002 per extraction.
"""

import os
import re
import time
import logging
import anthropic

from podsignal.utils import parse_llm_json, retry_on_transient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"

_client = None


def _get_client() -> anthropic.Anthropic:
    """Lazy-init the Anthropic client to avoid crashing on import."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# Episodes with these patterns in the title are likely guest interviews
INTERVIEW_SIGNALS = [
    " with ", " ft. ", " feat. ", " featuring ",
    "interview", "conversation with", "chat with",
    "guest", "founder of", "ceo of", "cto of",
]

SOLO_EPISODE_SIGNALS = [
    "solo", "q&a", "mailbag", "ama ", "ask me",
    "thoughts on", "my take", "announcement",
    "news roundup", "week in review",
]


def is_likely_interview(episode: dict) -> bool:
    """
    Quick heuristic filter before spending a Claude call.
    Returns True if the episode is likely a guest interview.
    """
    title = episode.get("title", "").lower()
    description = episode.get("description", "").lower()[:500]
    combined = f"{title} {description}"

    # Rule out obvious solo episodes
    if any(sig in combined for sig in SOLO_EPISODE_SIGNALS):
        return False

    # Check for interview signals
    if any(sig in combined for sig in INTERVIEW_SIGNALS):
        return True

    # If title has a pipe, colon, or dash with a name, it's usually a guest
    # Pattern: "Episode Title: First Last, Company"
    if re.search(r"[:\|—–-]\s+[A-Z][a-z]+ [A-Z][a-z]+", episode.get("title", "")):
        return True

    # Default: include it and let Claude decide
    return True


EXTRACTION_SYSTEM = """You are an expert at extracting structured information from podcast episode descriptions.

You will be given a podcast episode title and description. Your job is to determine:
1. Whether this episode features an external guest (not a solo/co-host episode)
2. If so, extract structured intelligence about the guest

Return ONLY valid JSON. No markdown fences. No explanation."""


EXTRACTION_PROMPT = """
Podcast: {podcast_name}
Episode Title: {title}
Published: {date}
Episode URL: {url}

Description:
{description}

Instructions:
- Determine if this episode features an external guest (not just the regular host(s))
- If it does, extract everything you can about the guest
- Key topics must be SPECIFIC — not generic like "growth" but "how they cut CAC by 40% using referral loops"
- The key_insight should be the most memorable or quotable specific thing discussed

Return this exact JSON:
{{
  "has_guest": true/false,
  "guest_name": "Full Name or null",
  "guest_company": "Company name at time of episode or null",
  "guest_title": "Their title/role if mentioned or null",
  "guest_background": "1 sentence on who they are based on the description",
  "key_topics": [
    "Specific topic 1 — be precise",
    "Specific topic 2 — be precise",
    "Specific topic 3 — be precise"
  ],
  "key_insight": "The most specific, memorable thing they discussed — a real point, not a generic topic",
  "episode_hook": "The ONE thing that makes this episode stand out as a reference point for outreach",
  "guest_stage": "early-stage founder / growth-stage founder / executive / investor / consultant / other",
  "skip_reason": "If has_guest is false, why (solo episode / co-host / roundtable / etc.)"
}}
"""


@retry_on_transient(max_retries=2, base_delay=1.0, exceptions=(anthropic.APIError,))
def extract_guest(episode: dict, model: str = None) -> dict:
    """
    Use Claude to extract guest intelligence from a single episode.
    Returns None if no guest detected.
    """
    client = _get_client()
    model = model or os.environ.get("PODSIGNAL_MODEL", DEFAULT_MODEL)

    response = client.messages.create(
        model=model,
        max_tokens=600,
        system=EXTRACTION_SYSTEM,
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(
                podcast_name=episode.get("podcast_name", ""),
                title=episode.get("title", ""),
                date=episode.get("published_str", ""),
                url=episode.get("episode_url", ""),
                description=episode.get("description", "")[:2000],
            )
        }]
    )

    raw = response.content[0].text
    try:
        result = parse_llm_json(raw)
    except ValueError as e:
        logger.warning("Failed to parse extraction response: %s", e)
        return None

    # Merge extracted data back into the episode dict
    if result.get("has_guest"):
        return {
            **episode,
            "guest_name": result.get("guest_name"),
            "guest_company": result.get("guest_company"),
            "guest_title": result.get("guest_title"),
            "guest_background": result.get("guest_background"),
            "key_topics": result.get("key_topics", []),
            "key_insight": result.get("key_insight"),
            "episode_hook": result.get("episode_hook"),
            "guest_stage": result.get("guest_stage"),
            "has_guest": True,
        }

    return None


def batch_extract_guests(episodes: list[dict], model: str = None) -> list[dict]:
    """
    Process a list of episodes, returning only those with confirmed guests.
    Filters obvious non-interviews before calling Claude to save tokens.
    """
    guests = []
    skipped = 0

    for episode in episodes:
        # Cheap heuristic filter first
        if not is_likely_interview(episode):
            skipped += 1
            continue

        try:
            result = extract_guest(episode, model=model)
            if result:
                guests.append(result)
        except Exception as e:
            logger.error("Extraction error on '%s': %s", episode.get("title", "")[:50], e)

        time.sleep(0.3)  # Gentle API pacing

    if skipped:
        logger.debug("Skipped %d non-interview episodes", skipped)

    return guests
