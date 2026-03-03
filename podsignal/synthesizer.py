# podsignal/synthesizer.py
"""
Uses Claude to score prospect fit and generate personalized outreach emails.

The email references:
1. The specific podcast they appeared on
2. A specific thing they said or topic they covered
3. A connection between that topic and a pain point your product solves

"I heard you on X, you talked about Y, we help with that" is one of the
highest-converting cold email frameworks because it proves you listened.
"""

import os
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


def build_system_prompt(company_config: dict) -> str:
    name = company_config.get("name", "Our Company")
    description = company_config.get("description", "")
    pitch = company_config.get("pitch", "")

    return f"""You are a senior B2B sales strategist and copywriter for {name}.

{name} sells: {description}
Core pitch: {pitch}

THE GOLDEN RULE:
The email MUST reference something SPECIFIC the guest said on the podcast.
Not just "I heard your episode" but "when you talked about [SPECIFIC THING]."
If you cannot find a specific angle, score them lower.

Great emails:
- Open with the specific podcast reference (never "I hope this finds you well")
- Bridge from what they said to a relevant pain or opportunity
- End with ONE soft CTA ("worth a quick conversation?" not "hop on a 30-min call!")
- Read like a human who genuinely listened. 3-5 sentences MAX.

Return ONLY valid JSON. No markdown fences. No explanation."""


USER_PROMPT_TEMPLATE = """
=== GUEST PROFILE ===
Name: {guest_name}
Company: {guest_company}
Title: {guest_title}
LinkedIn: {linkedin_url}
Stage: {guest_stage}
Background: {guest_background}

=== EPISODE INTEL ===
Podcast: {podcast_name}
Episode: {episode_title}
Date: {episode_date}
URL: {episode_url}

Key Topics:
{key_topics}

Key Insight: {key_insight}
Episode Hook: {episode_hook}
Show Context: {icp_notes}

Return this exact JSON:
{{
  "is_good_prospect": true/false,
  "prospect_score": 1-10,
  "reasoning": "2-3 sentences. What specifically drove the score?",
  "inferred_pain_point": "The ONE pain point most relevant to what they discussed",
  "outreach_trigger": "The specific moment from the episode that bridges to your pitch",
  "personalization_angle": "What makes this email unique to this person",
  "email": {{
    "subject": "Subject line — specific, personal, under 50 chars ideally",
    "body": "3-5 sentences. Reference specific episode content. Sound human. Soft CTA at the end."
  }}
}}
"""


@retry_on_transient(max_retries=2, base_delay=1.0, exceptions=(anthropic.APIError,))
def synthesize_prospect(guest: dict, company_config: dict, model: str = None) -> dict:
    """Score a podcast guest and generate a personalized outreach email."""

    client = _get_client()
    model = model or os.environ.get("PODSIGNAL_MODEL", DEFAULT_MODEL)

    key_topics_text = "\n".join(
        f"  - {t}" for t in guest.get("key_topics", [])
    ) or "  - (not extracted)"

    prompt = USER_PROMPT_TEMPLATE.format(
        guest_name=guest.get("guest_name") or "Unknown",
        guest_company=guest.get("guest_company") or "Unknown",
        guest_title=guest.get("guest_title") or "Not mentioned",
        linkedin_url=guest.get("linkedin_url") or "Not found",
        guest_stage=guest.get("guest_stage") or "Unknown",
        guest_background=guest.get("guest_background") or "Not available",
        podcast_name=guest.get("podcast_name") or "",
        episode_title=guest.get("title") or "",
        episode_date=guest.get("published_str") or "",
        episode_url=guest.get("episode_url") or "",
        key_topics=key_topics_text,
        key_insight=guest.get("key_insight") or "Not extracted",
        episode_hook=guest.get("episode_hook") or "Not extracted",
        icp_notes=guest.get("icp_notes") or "General ICP",
    )

    response = client.messages.create(
        model=model,
        max_tokens=800,
        system=build_system_prompt(company_config),
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    try:
        return parse_llm_json(raw)
    except ValueError as e:
        logger.warning("Failed to parse synthesis response: %s", e)
        raise
